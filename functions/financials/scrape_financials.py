from curl_cffi import CurlHttpVersion, requests
import pandas as pd
from helper import (
    save_dataframe_as_csv,
    table_exists,
    upsert_financial_report_current_and_revision,
)
from datetime import datetime, timezone
from bs4 import BeautifulSoup
import functions_framework
from ingestion_observability import emit_event, managed_import_completion, observed_entrypoint
import os
import re
import json
import io
import hashlib
import importlib.util
import sys
import time
from google.auth import default


FINANCIALS_URL = "https://www.richbourse.com/common/actualite-categorie/index/etats-financiers"
# Keep the transport option typed; curl-cffi's impersonation profile supplies
# the browser headers.
HTTP_VERSION_1_1 = CurlHttpVersion.V1_1
RICHBOURSE_MAX_ATTEMPTS = 3
RICHBOURSE_RETRY_DELAYS = (1, 2)


class RichBourseTransportError(RuntimeError):
    """Raised when RichBourse returns unavailable or unusable content."""


def _is_challenge_or_interstitial(content):
    text = content.decode("utf-8", errors="ignore").lower()
    return any(
        marker in text
        for marker in (
            "just a moment",
            "checking your browser",
            "cf-chl-",
            "enable javascript and cookies",
            "access denied",
        )
    )


def _richbourse_get(session, url, headers, *, timeout):
    """Perform one validated, retryable RichBourse request."""
    for attempt in range(RICHBOURSE_MAX_ATTEMPTS):
        try:
            response = session.get(
                url,
                headers=headers,
                timeout=timeout,
                impersonate="chrome",
                http_version=HTTP_VERSION_1_1,
                allow_redirects=True,
            )
            content = response.content or b""
            retryable_status = response.status_code in {429, 500, 502, 503, 504}
            if response.status_code == 200 and content and not _is_challenge_or_interstitial(content):
                emit_event("ingestion.financials.transport", "succeeded", count=attempt + 1)
                return response
            if not retryable_status and response.status_code != 200:
                raise RichBourseTransportError(
                    f"RichBourse request failed with HTTP {response.status_code}: {url}"
                )
            if response.status_code == 200:
                reason = "challenge/interstitial" if _is_challenge_or_interstitial(content) else "empty body"
            else:
                reason = f"HTTP {response.status_code}"
            if attempt == RICHBOURSE_MAX_ATTEMPTS - 1:
                raise RichBourseTransportError(
                    f"RichBourse request unusable after {RICHBOURSE_MAX_ATTEMPTS} attempts ({reason}): {url}"
                )
            emit_event("ingestion.financials.transport", "retry", count=attempt + 1)
        except RichBourseTransportError:
            raise
        except Exception as error:
            if attempt == RICHBOURSE_MAX_ATTEMPTS - 1:
                raise RichBourseTransportError(
                    f"RichBourse request failed after {RICHBOURSE_MAX_ATTEMPTS} attempts: {url}"
                ) from error
            emit_event(
                "ingestion.financials.transport",
                "retry",
                count=attempt + 1,
                error_class=type(error).__name__,
            )
        time.sleep(RICHBOURSE_RETRY_DELAYS[attempt])
    raise AssertionError("unreachable")


def get_existing_symbols_and_years(table_id=None):
    """Read existing canonical rows to avoid unnecessary report processing.
    
    Returns a dict mapping (symbol, fiscal_year) tuples to the stored document link.
    Used to identify the canonical report already associated with each fiscal year.
    """
    from google.cloud import bigquery
    from google.auth import default
    
    credentials, project_id = default()
    table_id = table_id or f"{project_id}.stocks.financials"
    client = bigquery.Client(credentials=credentials, project=project_id)
    query = f"""
        SELECT symbol, fiscal_year, document_link
        FROM `{table_id}`
    """
    try:
        results = client.query(query).result()
        return {
            (row.symbol, row.fiscal_year): {
                'document_link': row.document_link,
            }
            for row in results
        }
    except Exception:
        return {}


def get_symbols_from_company_reference(table_id, project_id):
    """Load the tracked BRVM symbols without scraping the provider dropdown."""
    from google.cloud import bigquery

    client = bigquery.Client(project=project_id)
    query = f"""
        SELECT symbol
        FROM `{table_id}`
        WHERE symbol IS NOT NULL AND TRIM(symbol) != ''
        ORDER BY symbol
    """
    return [row.symbol for row in client.query(query).result()]


def extract_year_from_title(title):
    """Extract fiscal year from announcement title."""
    # Look for patterns like "Exercice 2024", "2024", "Exercice 2023-2024"
    patterns = [
        r'Exercice\s*(\d{4})',
        r'(\d{4})',
        r'(\d{4})-(\d{2,4})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            year_str = match.group(1)
            try:
                return int(year_str)
            except ValueError:
                continue
    
    return None


def should_reject_announcement(title):
    """Check if announcement should be rejected (trimestre/semestre)."""
    title_lower = title.lower()
    reject_keywords = ['trimestre', 'trimestriel', 'semestre', 'semestriel', 'quarterly']
    return any(keyword in title_lower for keyword in reject_keywords)


def get_announcements_for_symbol(symbol):
    """Fetch announcements for a specific symbol."""
    url = f"https://www.richbourse.com/common/actualite-categorie/index/etats-financiers?symbole={symbol}"
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.richbourse.com/common/actualite-categorie/index/etats-financiers"
    }
    
    session = requests.Session()
    response = _richbourse_get(session, url, headers, timeout=30)
    
    soup = BeautifulSoup(response.content, 'html.parser')
    
    announcements = []
    # Find all announcement rows
    rows = soup.find_all('div', class_=lambda x: x and ('ligne_paire' in x or 'ligne_impaire' in x))
    
    for row in rows:
        date_div = row.find('div', class_=lambda x: x and ('col-xs-4' in x or 'col-md-3' in x))
        link_elem = row.find('a', href=True)
        
        if not date_div or not link_elem:
            continue
        
        date_text = date_div.get_text(strip=True)
        title = link_elem.get_text(strip=True)
        href = link_elem.get('href', '')
        
        # Parse date (format: DD/MM/YYYY)
        try:
            parts = date_text.split('/')
            if len(parts) == 3:
                day, month, year = parts
                announcement_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            else:
                continue
        except:
            continue
        
        # Skip trimestre/semestre
        if should_reject_announcement(title):
            continue
        
        # Extract fiscal year
        fiscal_year = extract_year_from_title(title)
        if not fiscal_year:
            continue
        
        # Build PDF URL - ensure it's absolute
        if href.startswith('/'):
            pdf_url = f"https://www.richbourse.com{href}"
        elif href.startswith('http'):
            pdf_url = href
        else:
            # Relative URL - prepend base URL
            pdf_url = f"https://www.richbourse.com/common/actualite-categorie/index/{href}"
        
        announcements.append({
            'symbol': symbol,
            'title': title,
            'announcement_date': announcement_date,
            'fiscal_year': fiscal_year,
            'url': pdf_url
        })
    
    return announcements


def is_data_incomplete(data):
    """Check if extracted data is incomplete (any missing value).
    
    Returns True if at least one financial field is null/missing.
    """
    if data is None:
        return True
    
    financial_fields = ['net_income', 'total_debt', 'cash_and_cash_equivalents', 'total_equity']
    category = data.get("financial_category")
    if not (isinstance(category, str) and category in {"bank", "insurer"}):
        financial_fields.insert(0, "revenue")
    
    # Return True if any field is missing
    return any(data.get(field) is None for field in financial_fields)


def extract_pdf_url_from_details_page(details_url, session, headers):
    """Fetch the details HTML page and extract the actual PDF URL.
    
    RichBourse changed their URL format from:
    - Old: /common/actualite/afficher-fichier/... (direct PDF)
    - New: /common/actualite/details/... (HTML page with PDF link)
    
    This function handles the new format by extracting the PDF link from the HTML.
    """
    try:
        # Update headers to request HTML
        html_headers = headers.copy()
        html_headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        
        response = _richbourse_get(session, details_url, html_headers, timeout=30)
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Look for PDF links - common patterns:
        # 1. Links with .pdf extension
        # 2. Links containing 'fichier' or 'download'
        
        pdf_link = None
        
        # First, try to find direct PDF links
        for a_tag in soup.find_all('a', href=True):
            href = a_tag.get('href', '')
            if '.pdf' in href.lower() or 'fichier' in href.lower() or 'download' in href.lower():
                pdf_link = href
                break
        
        # If not found, try to find links in content containers
        if not pdf_link:
            for container in soup.find_all(['div', 'section', 'article'], class_=lambda x: x and ('content' in x.lower() or 'file' in x.lower() or 'document' in x.lower())):
                for a_tag in container.find_all('a', href=True):
                    href = a_tag.get('href', '')
                    if '.pdf' in href.lower() or 'fichier' in href.lower():
                        pdf_link = href
                        break
                if pdf_link:
                    break
        
        # Last resort: look for any link that might be a PDF
        if not pdf_link:
            for a_tag in soup.find_all('a', href=True):
                href = a_tag.get('href', '')
                if 'afficher-fichier' in href or 'download' in href or 'fichier' in href:
                    pdf_link = href
                    break
        
        if not pdf_link:
            emit_event("ingestion.financials.pdf_url", "missing")
            return None
        
        # Convert to absolute URL if needed
        if pdf_link.startswith('/'):
            pdf_url = f"https://www.richbourse.com{pdf_link}"
        elif pdf_link.startswith('http'):
            pdf_url = pdf_link
        else:
            pdf_url = f"https://www.richbourse.com/common/actualite/{pdf_link}"
        
        emit_event("ingestion.financials.pdf_url", "resolved")
        return pdf_url
        
    except Exception as e:
        emit_event("ingestion.financials.pdf_url", "failed", error_class=type(e).__name__)
        return None


def extract_text_from_pdf(pdf_content):
    """Extract text from PDF using pdfplumber (falls back to pypdf).
    
    Args:
        pdf_content: The PDF file content as bytes
    
    Returns:
        Extracted text as string, or None if extraction fails
    """
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        return text if text.strip() else None
    except Exception as e:
        emit_event("ingestion.financials.pdf_text", "failed", error_class=type(e).__name__)
    
    # Fallback to pypdf
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return text if text.strip() else None
    except Exception as e:
        emit_event("ingestion.financials.pdf_text", "failed", error_class=type(e).__name__)
    
    return None


def _legacy_extract_financials_from_pdf(pdf_content, openrouter_api_key, max_retries=2):
    """Extract financial data from PDF using OpenRouter API with retry on better models.
    
    First extracts text from PDF to avoid hitting image limits (50 max).
    
    Args:
        pdf_content: The PDF file content as bytes
        openrouter_api_key: OpenRouter API key
        max_retries: Maximum number of retries with better models (default: 2)
    
    Returns:
        Dictionary with extracted financial data or None if all attempts fail
    """
    # First, try to extract text from PDF to avoid image limit issues
    pdf_text = extract_text_from_pdf(pdf_content)
    
    use_text_mode = pdf_text and len(pdf_text) > 100  # Use text if we got meaningful content
    
    if use_text_mode:
        emit_event("ingestion.financials.pdf_text", "extracted")
    else:
        emit_event("ingestion.financials.pdf_text", "fallback")
    
    prompt = """You are a financial data extraction expert. Extract structured financial data from a BRVM annual financial statement PDF.

For each document, extract the following fields:

fiscal_year: The fiscal year of the report (e.g., 2024). Use the most recent year covered by the statement, not the publication date.

revenue: Generic operating revenue or "chiffre d'affaires" only. Never put bank net banking income ("produit net bancaire" / PNB), insurer premiums, interest income, or any category-specific activity measure in this field. Extract PNB separately as pnb. In local currency (XOF/FCFA), expressed in full units.

net_income: Net income or "résultat net" (résultat net de l'exercice). Use the net result attributable to the company (résultat net part du groupe if consolidated accounts are shown alongside company-only accounts, otherwise résultat net). In local currency, expressed in full units.

total_debt: Definition depends on company type:
  - For NON-FINANCIAL companies (industrial, commercial, services, utilities): use total financial/interest-bearing debt — "dettes financières", "emprunts et dettes financières", or total dettes (excluding trade payables/fournisseurs and other non-financial liabilities when itemized separately). If only "total passif" is available with no breakdown, use total passif minus capitaux propres.
  - For BANKS and financial institutions: "total_debt" does not follow the standard corporate definition. Instead, use the sum of interest-bearing liabilities to third parties, typically composed of: "dettes envers les établissements de crédit" (interbank borrowings), "dettes envers la clientèle" (customer deposits), and "emprunts obligataires et dettes rattachées" (bonds and related debt), if separately reported. If these line items are not individually broken out, use "total dettes" or "total passif" (excluding "capitaux propres" and "provisions techniques" for insurers) as a fallback. Do not include "capitaux propres", "provisions pour risques et charges", or off-balance-sheet commitments in this figure.
  - For INSURANCE companies: use total technical and financial liabilities excluding equity — primarily "provisions techniques" plus any interest-bearing debt, if the breakdown is available; otherwise use total passif minus capitaux propres.
  In local currency, expressed in full units.

cash_and_cash_equivalents: Cash and cash equivalents — "trésorerie", "trésorerie et équivalents de trésorerie", or "disponibilités". For banks, this may appear as "caisse, banques centrales" or "trésorerie active" — use that if the standard line is absent. In local currency, expressed in full units.

total_equity: Total equity — "capitaux propres" or "capitaux propres part du groupe" (total, including reserves, capital, and retained earnings — "report à nouveau"). In local currency, expressed in full units.

symbol: The first 4 or 5 letters of the document name (before the "_" character).

CRITICAL — DETECT COMPANY TYPE FIRST:
Before extracting total_debt, determine whether the document is a bank/financial institution, an insurance company, or a non-financial (corporate) company, based on the statement structure, sector references, or company name (e.g., BOA, SGBCI, NSIA, SONIBANK are banks/insurers; industrial or commercial names like SONATEL, NESTLE, SOLIBRA are non-financial). Apply the matching total_debt definition above.

CRITICAL — UNIT NORMALIZATION:
Financial statements often present figures in thousands, millions, or billions of XOF, with the unit noted near the table header or in a footnote (e.g., "en milliers de FCFA", "en millions de FCFA", "montants exprimés en milliers d'unités monétaires"). You MUST detect this unit and convert every extracted monetary value into full base units (i.e., the actual FCFA amount) before returning it. Examples:
- If the statement says "en milliers de FCFA" and shows 12 345, the actual value is 12345000.
- If the statement says "en millions de FCFA" and shows 12, the actual value is 12000000.
- If the statement says "en milliards de FCFA" and shows 1.2, the actual value is 1200000000.
- If no unit is specified, assume the figures are already in full units (do not scale).
Apply the detected scale factor consistently to ALL five monetary fields (revenue, net_income, total_debt, cash_and_cash_equivalents, total_equity) — do not mix scales within the same document. Double-check that the final numbers are plausible in magnitude for a BRVM-listed company (typically hundreds of millions to hundreds of billions of FCFA).

Instructions for each document:
- The documents are from companies listed on the BRVM (Bourse Régionale des Valeurs Mobilières), West Africa, and prepared under SYSCOHADA révisé / BCEAO-PCB norms.
- The documents may be in French — look for: "chiffre d'affaires", "résultat net", "trésorerie", "capitaux propres", "dettes", "passifs", along with the unit disclosure (milliers/millions/milliards).
- Extract the most recent fiscal year's data (usually the first/leftmost column in the balance sheet and income statement).
- If a field is not found, use null — do not guess or estimate.
- Do not include any explanation or text outside the output.

Output format: 
{
  "fiscal_year": <integer or null>,
  "revenue": <number or null>,
  "net_income": <number or null>,
  "total_debt": <number or null>,
  "cash_and_cash_equivalents": <number or null>,
  "total_equity": <number or null>
}
"""
    
    # Model tiers - from free to paid (better models first for retry)
    # Each entry: (model_id, is_free, display_name)
    model_tiers = [
        # Tier 1: Free model (tried first)
        (["google/gemma-4-31b-it:free"], True, "Gemma 4 31B (free)"),
        # Tier 2: Paid model (fallback)
        (["openai/gpt-4o-mini"], False, "GPT-4o Mini"),
    ]
    
    headers = {
        "Authorization": f"Bearer {openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://tradvisor.app",
        "X-Title": "TRADVISOR BRVM"
    }
    
    best_result = None
    
    for tier_idx, (models, is_free, model_name) in enumerate(model_tiers):
        # Skip paid models if we've reached max_retries with free models
        if tier_idx > max_retries and not is_free:
            emit_event("ingestion.financials.provider", "retry_limit")
            break
        
        emit_event("ingestion.financials.provider", "trying")
        
        if use_text_mode:
            # Send text instead of PDF to avoid image limit
            content = [
                {"type": "text", "text": prompt},
                {"type": "text", "text": f"\n\n--- PDF TEXT CONTENT ---\n\n{pdf_text}"}
            ]
        else:
            # Fall back to PDF file (may hit image limit)
            import base64
            pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
            content = [
                {"type": "text", "text": prompt},
                {
                    "type": "file",
                    "file": {
                        "filename": "document.pdf",
                        "file_data": f"data:application/pdf;base64,{pdf_base64}"
                    }
                }
            ]
        
        payload = {
            "models": models,
            "provider": {
                "allow_fallbacks": False
            },
            "messages": [
                {
                    "role": "user",
                    "content": content
                }
            ]
        }
        
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=300
            )
            
            if response.status_code == 200:
                result = response.json()
                text = result['choices'][0]['message']['content']
                
                # Parse JSON response
                json_start = text.find('{')
                json_end = text.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = text[json_start:json_end]
                    data = json.loads(json_str)
                    
                    # Store this result
                    best_result = data
                    
                    # Check if data is complete enough
                    if not is_data_incomplete(data):
                        emit_event("ingestion.financials.provider", "succeeded")
                        return data
                    else:
                        emit_event("ingestion.financials.provider", "incomplete")
                        # Continue to try better model
                        continue
            else:
                emit_event("ingestion.financials.provider", "failed", error_class="ProviderError")
        except Exception as e:
            emit_event("ingestion.financials.provider", "failed", error_class=type(e).__name__)
            continue
    
    # Return best result we got, even if incomplete
    if best_result:
        emit_event("ingestion.financials.provider", "incomplete")
    else:
        emit_event("ingestion.financials.provider", "failed", error_class="AllModelsFailed")
    
    return best_result


def extract_financials_from_pdf(pdf_content, openrouter_api_key=None, **kwargs):
    """Compatibility entry point backed by the shared stored-response adapter."""
    shared_module = _load_shared_extraction_module()
    shared_adapter = shared_module.extract_financials_from_pdf

    return shared_adapter(pdf_content, openrouter_api_key, **kwargs)


def _load_shared_extraction_module():
    try:
        import insert_financials

        return insert_financials
    except ModuleNotFoundError as error:
        if error.name != "insert_financials":
            raise
    module_name = "tradvisor_shared_financial_extraction"
    if module_name not in sys.modules:
        module_path = os.path.join(os.path.dirname(__file__), "insert_financials.py")
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise ImportError("could not load the shared financial extraction adapter")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    return sys.modules[module_name]


def scrape_financials(url, openrouter_api_key=None, configuration=None):
    """Scrape annual financial statements - MONTHLY RUN.
    
    This script is for regular monthly runs. It collects current and previous
    year financials for symbols that don't already have them.
    
    Processes each symbol individually and upserts to BigQuery immediately
    to avoid memory issues with large datasets.
    """
    import gc

    _, project_id = default()
    if configuration is not None:
        configuration.validate_application_default_project(project_id)
        project_id = configuration.project_id
    
    current_year = datetime.now().year
    previous_year = current_year - 1
    
    # Get existing data from BigQuery
    financials_table = (
        configuration.table_for("financials")
        if configuration is not None
        else f"{project_id}.stocks.financials"
    )
    companies_table = (
        configuration.table_for("companies")
        if configuration is not None
        else f"{project_id}.stocks.brvm_companies"
    )
    if configuration is None:
        table_exists_flag = table_exists("financials")
        existing_data = get_existing_symbols_and_years() if table_exists_flag else {}
    else:
        table_exists_flag = table_exists(financials_table, project_id=project_id)
        existing_data = get_existing_symbols_and_years(financials_table) if table_exists_flag else {}
    
    # Initialization is a separate storage-first workflow. Do not fall back to
    # it here: this recurring function is packaged without its initializer-only
    # dependencies and must remain an incremental scraper.
    if not table_exists_flag and not existing_data:
        raise RuntimeError(
            "stocks.financials is unavailable; run financials-init-wf before "
            "the recurring financials-wf"
        )
    
    emit_event("ingestion.financials.existing", "loaded", count=len(existing_data))
    
    # Use the managed company reference table. RichBourse's symbol dropdown
    # is protected by anti-bot rules and is not needed for this workflow.
    all_symbols = (
        get_symbols_from_company_reference(project_id)
        if configuration is None
        else get_symbols_from_company_reference(companies_table, project_id)
    )
    if not all_symbols:
        raise RuntimeError("stocks.brvm_companies has no symbols to process")
    emit_event("ingestion.financials.symbols", "loaded", count=len(all_symbols))
    
    total_processed = 0
    completion_revisions = []
    
    for symbol in all_symbols:
        emit_event("ingestion.financials.symbol", "processing")
        
        announcements = get_announcements_for_symbol(symbol)
        
        if not announcements:
            emit_event("ingestion.financials.announcements", "none")
            continue
        
        # Deduplicate: keep only the most recent announcement per (symbol, fiscal_year)
        announcements_by_year = {}
        for ann in announcements:
            fiscal_year = ann['fiscal_year']
            
            # Only collect current or previous year
            if fiscal_year not in [current_year, previous_year]:
                continue
            
            key = (symbol, fiscal_year)
            ann_date = ann.get('announcement_date', '')
            
            # Keep most recent announcement
            if key not in announcements_by_year or ann_date > announcements_by_year[key].get('announcement_date', ''):
                announcements_by_year[key] = ann
        
        symbol_data = []
        
        for key, ann in announcements_by_year.items():
            fiscal_year = ann['fiscal_year']
            existing_financials = existing_data.get(key)
            
            current_matches_announcement = bool(
                existing_financials
                and existing_financials.get('document_link') == ann['url']
            )
            
            # Download PDF
            try:
                session = requests.Session()
                headers = {
                    "Accept": "application/pdf,*/*",
                    "Referer": "https://www.richbourse.com/",
                }
                
                # Handle new URL format: /details/ URLs return HTML with PDF link
                pdf_url = ann['url']
                if '/details/' in pdf_url:
                    emit_event("ingestion.financials.pdf_details", "detected")
                    pdf_url = extract_pdf_url_from_details_page(pdf_url, session, headers)
                    if not pdf_url:
                        raise Exception("Failed to extract PDF URL from details page")
                
                # Follow redirects and get the actual PDF
                pdf_response = _richbourse_get(session, pdf_url, headers, timeout=60)
                
                pdf_content = pdf_response.content
                if not pdf_content.startswith(b"%PDF-"):
                    raise RichBourseTransportError(
                        f"RichBourse returned invalid PDF content: {pdf_url}"
                    )
                document_revision = hashlib.sha256(pdf_content).hexdigest()
                shared_adapter = _load_shared_extraction_module()
                try:
                    if configuration is not None:
                        artifact_bucket_name = configuration.data_bucket
                    else:
                        from helper import get_project_number

                        artifact_bucket_name = f"data-{get_project_number(project_id)}"
                    artifact_bucket = shared_adapter.get_extraction_artifact_bucket(
                        project_id, artifact_bucket_name
                    )
                    artifact = shared_adapter.load_extraction_artifact(
                        artifact_bucket, document_revision
                    )
                except (ImportError, AttributeError):
                    artifact_bucket = None
                    artifact = None
                evidence = []
                if artifact_bucket is not None:
                    financial_data = extract_financials_from_pdf(
                        pdf_content,
                        openrouter_api_key,
                        recorded_response=artifact,
                        evidence_callback=evidence.append,
                    )
                else:
                    financial_data = extract_financials_from_pdf(
                        pdf_content, openrouter_api_key
                    )
                
                # CRITICAL: Delete PDF content from memory immediately after processing
                del pdf_content
                
                if is_data_incomplete(financial_data):
                    raise Exception("Failed to extract financial data from PDF - all AI models failed")

                normalized_collected_at = (
                    artifact.get("collected_at")
                    if isinstance(artifact, dict)
                    and isinstance(artifact.get("collected_at"), str)
                    else datetime.now(timezone.utc).isoformat(timespec="seconds")
                )
                if (
                    evidence
                    and artifact_bucket is not None
                    and (
                        not isinstance(artifact, dict)
                        or not isinstance(artifact.get("collected_at"), str)
                    )
                ):
                    shared_adapter.save_extraction_artifact(
                        artifact_bucket,
                        document_revision,
                        dict(evidence[-1], collected_at=normalized_collected_at),
                    )
                annual_revision = shared_adapter.annual_financial_revision_row(
                    financial_data,
                    company_id=symbol,
                    source_ref=ann['url'],
                    source_revision_id=document_revision,
                    collected_at=normalized_collected_at,
                )

                # Keep the canonical immutable revision ahead of legacy writes
                # and the legacy already-current fast path. A failed canonical
                # write must remain retryable from the same recorded report.
                if annual_revision is not None:
                    shared_adapter.persist_annual_financial_revision(
                        annual_revision, project_id
                    )

                if (
                    current_matches_announcement
                    and financial_data is not None
                    and annual_revision is not None
                ):
                    emit_event("ingestion.financials.report", "unchanged")
                    session.close()
                    continue
                
                # New or updated data - upsert
                # Smart download ensures we only get here if announcement_date is different
                emit_event("ingestion.financials.report", "upserting")
                # Convert announcement_date string to date object for BigQuery
                # Keep announcement_date as string in YYYY-MM-DD format - BigQuery will parse it as DATE
                symbol_data.append({
                    'symbol': symbol,
                    'fiscal_year': fiscal_year,
                    'revenue': shared_adapter.legacy_revenue_value(financial_data),
                    'net_income': financial_data.get('net_income'),
                    'total_debt': financial_data.get('total_debt'),
                    'cash_and_cash_equivalents': financial_data.get('cash_and_cash_equivalents'),
                    'total_equity': financial_data.get('total_equity'),
                    'announcement_date': ann['announcement_date'],  # String format "YYYY-MM-DD"
                    'document_link': ann['url'],
                    'document_revision': document_revision,
                'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                })
                emit_event("ingestion.financials.extraction", "succeeded")
                
                # Free financial data memory
                del financial_data
                
                # Close session to free memory
                session.close()
                
            except Exception as e:
                emit_event("ingestion.financials.process", "failed", error_class=type(e).__name__)
                raise
        
        # Upsert this symbol's data to BigQuery immediately
        if symbol_data:
            df_symbol = pd.DataFrame(symbol_data)
            try:
                completion_revisions.append(
                    upsert_financial_report_current_and_revision(df_symbol, project_id)
                )
                emit_event("ingestion.financials.upsert", "succeeded", count=len(df_symbol))
                total_processed += len(df_symbol)
            except Exception as e:
                emit_event("ingestion.financials.upsert", "failed", error_class=type(e).__name__)
                raise
            
            # Free memory
            del df_symbol
            del symbol_data
        
        # Force garbage collection after each symbol
        gc.collect()
    
    emit_event("ingestion.financials.scrape", "completed", count=total_processed)
    if completion_revisions:
        return managed_import_completion("financials", completion_revisions)
    return None


@functions_framework.http
@observed_entrypoint("ingestion.financials.scrape")
def entry_point(request=None):
    from ingestion_configuration import IngestionConfiguration

    configuration = IngestionConfiguration.from_environment()
    endpoints = configuration.endpoints
    
    # Get OpenRouter API key from environment
    openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
    
    # Scrape and upsert to BigQuery (memory-efficient, processes each symbol individually)
    completion = scrape_financials(
        endpoints['financials'],
        openrouter_api_key,
        configuration,
    )
    
    return completion or "Monthly run complete.\n"


# Local testing (only run when executed directly)
if __name__ == "__main__":
    entry_point()
