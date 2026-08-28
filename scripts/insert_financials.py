import os
import io
import json
import re
import gc
import functions_framework
import yaml
import pandas as pd
from google.auth import default
from google.cloud import storage
from google.cloud import bigquery
from datetime import datetime


def is_data_incomplete(data):
    """Check if extracted data is incomplete (any missing value)."""
    if data is None:
        return True
    
    financial_fields = ['revenue', 'net_income', 'total_debt', 'cash_and_cash_equivalents', 'total_equity']
    return any(data.get(field) is None for field in financial_fields)


def extract_text_from_pdf(pdf_content):
    """Extract full text from PDF across ALL pages using pdfplumber (falls back to pypdf)."""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        if text.strip():
            return text
    except Exception as e:
        print(f"    pdfplumber failed: {e}")
    
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if text.strip():
            return text
    except Exception as e:
        print(f"    pypdf failed: {e}")
    
    return None


def extract_relevant_pdf_pages(pdf_content, max_pages=40):
    """Scan all pages (including 50+) for keywords and compile a trimmed PDF payload."""
    from pypdf import PdfReader, PdfWriter

    try:
        reader = PdfReader(io.BytesIO(pdf_content))
        total_pages = len(reader.pages)

        if total_pages <= max_pages:
            return pdf_content

        keywords = [
            "bilan", "compte de résultat", "états financiers",
            "capitaux propres", "résultat net", "chiffre d'affaires",
            "dettes financières", "trésorerie actif", "passif", "exercice"
        ]

        selected_pages = set()
        selected_pages.update(range(min(5, total_pages)))

        for idx, page in enumerate(reader.pages):
            text = (page.extract_text() or "").lower()
            if any(kw in text for kw in keywords):
                selected_pages.add(idx)

        if len(selected_pages) <= 5:
            print(f"    No keywords matched. Selecting first {max_pages} pages.")
            selected_pages.update(range(min(max_pages, total_pages)))

        sorted_pages = sorted(list(selected_pages))[:max_pages]
        print(f"    Filtered PDF from {total_pages} down to {len(sorted_pages)} targeted pages.")

        writer = PdfWriter()
        for page_idx in sorted_pages:
            writer.add_page(reader.pages[page_idx])

        buffer = io.BytesIO()
        writer.write(buffer)
        return buffer.getvalue()

    except Exception as e:
        print(f"    Smart slicing failed: {e}")
        return pdf_content


def send_openrouter_payload(content, openrouter_api_key, max_retries=2):
    """Helper to call OpenRouter models with structured fallback strategy."""
    from curl_cffi import requests as curl_requests
    
    prompt = """You are a financial data extraction expert. Extract structured financial data from a BRVM annual financial statement PDF.

For each document, extract the following fields:

fiscal_year: The fiscal year of the report (e.g., 2024). Use the most recent year covered by the statement, not the publication date.

revenue: Total revenue or "chiffre d'affaires" (produits d'exploitation / chiffre d'affaires net). For banks, use "produit net bancaire" (PNB) if chiffre d'affaires is not presented. In local currency (XOF/FCFA), expressed in full units.

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

    model_tiers = [
        (["google/gemma-4-31b-it:free"], True, "Gemma 4 31B (free)"),
        (["deepseek/deepseek-v4-flash-0731"], False, "DeepSeek V4 Flash 0731")
    ]
    
    headers = {
        "Authorization": f"Bearer {openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://tradvisor.app",
        "X-Title": "TRADVISOR BRVM"
    }

    best_result = None

    for tier_idx, (models, is_free, model_name) in enumerate(model_tiers):
        if tier_idx > max_retries and not is_free:
            break
        
        payload = {
            "models": models,
            "provider": {"allow_fallbacks": False},
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}] + content
                }
            ]
        }
        
        try:
            response = curl_requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=300,
                impersonate="chrome"
            )
            
            if response.status_code == 200:
                result = response.json()
                text = result['choices'][0]['message']['content']
                
                json_start = text.find('{')
                json_end = text.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    data = json.loads(text[json_start:json_end])
                    best_result = data
                    
                    if not is_data_incomplete(data):
                        print(f"    ✓ Successfully extracted with {model_name}")
                        return data
                    else:
                        print(f"    ✗ Incomplete data from {model_name}, trying next model...")
            else:
                print(f"    OpenRouter API error: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"    Error with {model_name}: {e}")
            continue

    return best_result


def extract_financials_from_pdf(pdf_content, openrouter_api_key):
    """Extract financial data handling full-text extraction, smart slicing, and image chunking."""
    import base64

    print("    Extracting text from PDF...")
    pdf_text = extract_text_from_pdf(pdf_content)
    
    # 1. Standard Path: Text Extraction
    if pdf_text and len(pdf_text) > 100:
        print(f"    Using full document text extraction ({len(pdf_text)} chars)")
        text_content = [{"type": "text", "text": f"\n\n--- PDF TEXT CONTENT ---\n\n{pdf_text}"}]
        result = send_openrouter_payload(text_content, openrouter_api_key)
        if result and not is_data_incomplete(result):
            return result

    # 2. Scanned / Image Fallback: Smart Keyword Slicing
    print("    Text extraction empty or incomplete. Applying Smart Keyword PDF slicing...")
    sliced_pdf_bytes = extract_relevant_pdf_pages(pdf_content, max_pages=40)
    pdf_base64 = base64.b64encode(sliced_pdf_bytes).decode('utf-8')
    
    file_content = [{
        "type": "file",
        "file": {
            "filename": "document.pdf",
            "file_data": f"data:application/pdf;base64,{pdf_base64}"
        }
    }]
    
    result = send_openrouter_payload(file_content, openrouter_api_key)
    if result and not is_data_incomplete(result):
        return result

    # 3. Last-resort Fallback: Sequential Chunking
    try:
        from pypdf import PdfReader, PdfWriter
        reader = PdfReader(io.BytesIO(pdf_content))
        total_pages = len(reader.pages)
        
        if total_pages > 40:
            print(f"    Attempting sequential chunk processing across {total_pages} pages...")
            for start in range(0, total_pages, 40):
                end = min(start + 40, total_pages)
                print(f"    Scanning page chunk {start + 1} to {end}...")

                writer = PdfWriter()
                for i in range(start, end):
                    writer.add_page(reader.pages[i])

                chunk_buf = io.BytesIO()
                writer.write(chunk_buf)
                chunk_b64 = base64.b64encode(chunk_buf.getvalue()).decode('utf-8')

                chunk_content = [{
                    "type": "file",
                    "file": {
                        "filename": f"chunk_{start}.pdf",
                        "file_data": f"data:application/pdf;base64,{chunk_b64}"
                    }
                }]
                
                chunk_result = send_openrouter_payload(chunk_content, openrouter_api_key)
                if chunk_result and not is_data_incomplete(chunk_result):
                    return chunk_result
    except Exception as e:
        print(f"    Sequential chunking error: {e}")

    return result


def get_existing_data_in_bigquery(project_id):
    """Query BigQuery to get existing (symbol, fiscal_year) pairs."""
    client = bigquery.Client(project=project_id)
    query = f"""
        SELECT symbol, fiscal_year
        FROM `{project_id}.stocks.financials`
    """
    
    try:
        results = client.query(query).result()
        return {(row.symbol, row.fiscal_year) for row in results}
    except Exception:
        return set()


def upsert_into_bigquery(df, project_id, dataset, table, primary_keys):
    """Upsert data into BigQuery using MERGE statement."""
    client = bigquery.Client(project=project_id)
    table_id = f"{project_id}.{dataset}.{table}"
    
    # Create a temporary table
    temp_table_id = f"{table_id}_temp"
    job = client.load_table_from_dataframe(df, temp_table_id)
    job.result()
    
    try:
        def get_cast_expression(col):
            col_lower = col.lower()
            if col_lower.endswith('_at') or 'time' in col_lower:
                return f"PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S', CAST(source.{col} AS STRING))"
            elif 'date' in col_lower:
                return f"PARSE_DATE('%Y-%m-%d', CAST(source.{col} AS STRING))"
            return f"source.{col}"

        primary_key_conditions = ' AND '.join([f"target.{pk} = {get_cast_expression(pk)}" for pk in primary_keys])
        update_columns = [col for col in df.columns if col not in primary_keys]
        update_set = ', '.join([f"target.{col} = {get_cast_expression(col)}" for col in update_columns])
        insert_values = ', '.join([get_cast_expression(col) for col in df.columns])
        
        merge_query = f"""
        MERGE `{table_id}` target
        USING `{temp_table_id}` source
        ON {primary_key_conditions}
        WHEN MATCHED THEN
          UPDATE SET {update_set}
        WHEN NOT MATCHED THEN
          INSERT ({', '.join(df.columns)})
          VALUES ({insert_values})
        """
        
        client.query(merge_query).result()
        
    finally:
        try:
            client.delete_table(temp_table_id, not_found_ok=True)
        except Exception as e:
            print(f"Warning: Failed to delete temporary table {temp_table_id}: {e}")


def move_pdf_to_archive(blob, source_bucket, project_number):
    """Move a processed PDF to the archive bucket.
    
    Returns:
    - True if successful, False otherwise
    """
    try:
        archive_bucket = source_bucket.client.bucket(f"archive-{project_number}")
        source_blob = source_bucket.blob(blob.name)
        destination_blob_name = blob.name
        
        # Copy to archive bucket
        source_bucket.copy_blob(source_blob, archive_bucket, destination_blob_name)
        
        # Delete from source bucket
        source_blob.delete()
        
        print(f"    ✓ Moved to archive: gs://archive-{project_number}/{destination_blob_name}")
        return True
        
    except Exception as e:
        print(f"    Warning: Failed to move PDF to archive: {e}")
        return False


def process_financial_pdfs(openrouter_api_key):
    """Process PDF files from GCS and extract financial data to BigQuery."""
    credentials, project_id = default()
    
    # Get storage bucket
    from helper import get_project_number
    project_number = get_project_number(project_id)
    storage_client = storage.Client(credentials=credentials)
    bucket = storage_client.bucket(f"data-{project_number}")
    
    # Get existing data in BigQuery to avoid duplicates
    print("Checking existing data in BigQuery...")
    existing_data = get_existing_data_in_bigquery(project_id)
    print(f"Found {len(existing_data)} existing (symbol, fiscal_year) pairs.")
    
    # List all PDF files in financials/ prefix
    print("Listing PDF files in GCS...")
    blobs = list(bucket.list_blobs(prefix='financials/'))
    pdf_blobs = [b for b in blobs if b.name.endswith('.pdf')]
    print(f"Found {len(pdf_blobs)} PDF files.")
    
    total_processed = 0
    total_skipped = 0
    total_failed = 0
    
    for blob in pdf_blobs:
        # Parse filename: financials/SYMBOL/YEAR/title.pdf
        parts = blob.name.replace('.pdf', '').split('/')
        
        # Format: financials/SYMBOL/YEAR/title.pdf
        symbol = parts[1]
        try:
            fiscal_year = int(parts[2])
        except (ValueError, IndexError):
            # Try alternative format
            filename = os.path.basename(blob.name).replace('.pdf', '')
            filename_parts = filename.split('_')
            if len(filename_parts) >= 2:
                symbol = filename_parts[0]
                try:
                    fiscal_year = int(filename_parts[1])
                except ValueError:
                    print(f"  Skipping {blob.name}: could not parse symbol/year")
                    total_skipped += 1
                    continue
            else:
                print(f"  Skipping {blob.name}: could not parse filename")
                total_skipped += 1
                continue
        
        # Check if already in BigQuery
        if (symbol, fiscal_year) in existing_data:
            print(f"  {symbol} FY{fiscal_year} - already in BigQuery, skipping")
            total_skipped += 1
            continue
        
        print(f"  Processing {symbol} FY{fiscal_year}...")
        
        try:
            # Download PDF
            pdf_content = blob.download_as_bytes()
            
            # Extract financial data
            financial_data = extract_financials_from_pdf(pdf_content, openrouter_api_key)
            
            del pdf_content
            
            if not financial_data:
                print(f"    ERROR: Failed to extract data from PDF")
                total_failed += 1
                continue
            
            # Move PDF to archive bucket FIRST
            move_pdf_to_archive(blob, bucket, project_number)
            
                    
            # Build GCS URL for document_link (pointing to archive location)
            document_link = f"gs://archive-{project_number}/{blob.name}"
            
            # Create DataFrame for BigQuery
            df = pd.DataFrame([{
                'symbol': symbol,
                'fiscal_year': fiscal_year,
                'revenue': financial_data.get('revenue'),
                'net_income': financial_data.get('net_income'),
                'total_debt': financial_data.get('total_debt'),
                'cash_and_cash_equivalents': financial_data.get('cash_and_cash_equivalents'),
                'total_equity': financial_data.get('total_equity'),
                'document_link': document_link,
                'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }])
            
            # Upsert to BigQuery
            upsert_into_bigquery(df, project_id, 'stocks', 'financials', ['symbol', 'fiscal_year'])
            print(f"    ✓ Upserted {symbol} FY{fiscal_year} to BigQuery")
            
            total_processed += 1
            
            del df
            del financial_data
            
        except Exception as e:
            print(f"    ERROR processing {blob.name}: {e}")
            total_failed += 1
            continue
        
        gc.collect()
    
    print(f"\nProcessing complete.")
    print(f"  Total processed: {total_processed}")
    print(f"  Total skipped (existing): {total_skipped}")
    print(f"  Total failed: {total_failed}")
    
    return total_processed


@functions_framework.http
def entry_point(request=None):
    openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
    
    if not openrouter_api_key:
        return "Error: OPENROUTER_API_KEY environment variable not set\n", 500
    
    process_financial_pdfs(openrouter_api_key)
    
    return "Financial data extraction complete.\n"


if __name__ == "__main__":
    print(entry_point())
