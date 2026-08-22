import base64
import gc
import io
import json
import os
import yaml
import pandas as pd
from datetime import datetime
from curl_cffi import requests
import functions_framework
from google.auth import default
from google.cloud import storage, bigquery

from helper import upsert_into_bigquery, get_project_number

def is_data_incomplete(data):
    if data is None:
        return True
    fields = ['revenue', 'net_income', 'total_debt', 'cash_and_cash_equivalents', 'total_equity']
    return any(data.get(f) is None for f in fields)

def extract_text_from_pdf(pdf_content):
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        if text.strip():
            return text
    except Exception:
        pass
    
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if text.strip():
            return text
    except Exception:
        pass
    return None

def extract_relevant_pdf_pages(pdf_content, max_pages=40):
    from pypdf import PdfReader, PdfWriter
    try:
        reader = PdfReader(io.BytesIO(pdf_content))
        total_pages = len(reader.pages)
        if total_pages <= max_pages:
            return pdf_content

        keywords = ["bilan", "compte de resultat", "etats financiers", "capitaux propres", "resultat net", "chiffre d'affaires"]
        selected_pages = set(range(min(5, total_pages)))

        for idx, page in enumerate(reader.pages):
            text = (page.extract_text() or "").lower()
            if any(kw in text for kw in keywords):
                selected_pages.add(idx)

        sorted_pages = sorted(list(selected_pages))[:max_pages]
        writer = PdfWriter()
        for page_idx in sorted_pages:
            writer.add_page(reader.pages[page_idx])

        buffer = io.BytesIO()
        writer.write(buffer)
        return buffer.getvalue()
    except Exception:
        return pdf_content

def send_openrouter_payload(content, openrouter_api_key):
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
}"""

    models = ["google/gemma-4-31b-it:free", "deepseek/deepseek-v4-flash-0731"]
    headers = {
        "Authorization": f"Bearer {openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://tradvisor.app",
        "X-Title": "TRADVISOR BRVM"
    }

    for model in models:
        payload = {
            "models": [model],
            "provider": {"allow_fallbacks": False},
            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}] + content}]
        }
        try:
            res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=300)
            if res.status_code == 200:
                text = res.json()['choices'][0]['message']['content']
                json_start = text.find('{')
                json_end = text.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    data = json.loads(text[json_start:json_end])
                    if not is_data_incomplete(data):
                        return data
        except Exception:
            continue
    return None

def extract_financials_from_pdf(pdf_content, openrouter_api_key):
    pdf_text = extract_text_from_pdf(pdf_content)
    if pdf_text and len(pdf_text) > 100:
        res = send_openrouter_payload([{"type": "text", "text": f"\n\n--- PDF TEXT CONTENT ---\n\n{pdf_text}"}], openrouter_api_key)
        if res and not is_data_incomplete(res):
            return res

    sliced_bytes = extract_relevant_pdf_pages(pdf_content, max_pages=40)
    pdf_b64 = base64.b64encode(sliced_bytes).decode('utf-8')
    file_content = [{"type": "file", "file": {"filename": "document.pdf", "file_data": f"data:application/pdf;base64,{pdf_b64}"}}]
    return send_openrouter_payload(file_content, openrouter_api_key)

def process_gcs_financial_pdfs(openrouter_api_key):
    credentials, project_id = default()
    project_number = get_project_number(project_id)
    storage_client = storage.Client()
    source_bucket = storage_client.bucket(f"data-{project_number}")
    archive_bucket = storage_client.bucket(f"archive-{project_number}")

    blobs = list(source_bucket.list_blobs(prefix="financials_pdf/"))
    extracted_records = []

    for blob in blobs:
        if not blob.name.endswith(".pdf"):
            continue
        
        pdf_bytes = blob.download_as_bytes()
        metadata = blob.metadata or {}
        
        financial_data = extract_financials_from_pdf(pdf_bytes, openrouter_api_key)
        if financial_data:
            symbol = metadata.get('symbol') or blob.name.split('/')[-1].split('_')[0]
            fiscal_year = int(metadata.get('fiscal_year') or financial_data.get('fiscal_year'))
            ann_date = metadata.get('announcement_date')
            doc_link = metadata.get('document_link', '')

            extracted_records.append({
                'symbol': symbol,
                'fiscal_year': fiscal_year,
                'revenue': financial_data.get('revenue'),
                'net_income': financial_data.get('net_income'),
                'total_debt': financial_data.get('total_debt'),
                'cash_and_cash_equivalents': financial_data.get('cash_and_cash_equivalents'),
                'total_equity': financial_data.get('total_equity'),
                'announcement_date': ann_date,
                'document_link': doc_link,
                'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            })

            # Archive processed PDF
            source_bucket.copy_blob(blob, archive_bucket, blob.name)
            blob.delete()
        
        gc.collect()

    if extracted_records:
        df = pd.DataFrame(extracted_records)
        upsert_into_bigquery(df, project_id, 'stocks', 'financials', ['symbol', 'fiscal_year'])
        print(f"Upserted {len(df)} financial records into BigQuery.")

@functions_framework.http
def entry_point(request=None):
    openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
    process_gcs_financial_pdfs(openrouter_api_key)
    return "Financial extraction and BigQuery insertion complete.\n"

if __name__ == "__main__":
    print(entry_point())