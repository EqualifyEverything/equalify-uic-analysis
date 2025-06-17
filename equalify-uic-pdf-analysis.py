# === Standard library imports ===
import os
import sys
import gc
import logging
import contextlib
from io import BytesIO

# === Third-party imports ===
import pandas as pd
import requests
from tqdm import tqdm
from PyPDF2 import PdfReader
from pdfminer.high_level import extract_text
from boxsdk import OAuth2, Client

logging.basicConfig(level=logging.INFO, format='%(message)s')
# Silence pdfminer logging to CRITICAL
for noisy_logger in ["pdfminer", "pdfminer.layout", "pdfminer.pdfinterp"]:
    logging.getLogger(noisy_logger).setLevel(logging.CRITICAL)

oauth = OAuth2(
    client_id='97mcp2od8tlluiu7skbo6coxzkir178z',
    client_secret='YOUR_CLIENT_SECRET',
    access_token='9R5TneoJhBnDIuYcoJ7CXlkpJoiNx47P'
)
box_client = Client(oauth)

# Initialize output CSV with headers
output_headers = [
    'Link Type', 'Location Type', 'Title', 'Link', 'URL',
    'PDF Size (bytes)', 'Page Count', 'Text-based',
    'Tagged', 'Notes'
]
pd.DataFrame(columns=output_headers).to_csv('output.csv', index=False)

# Load input CSV
df = pd.read_csv('input.csv')

logging.info("Starting PDF accessibility analysis...")

results_batch = []
BATCH_SIZE = 100

for i, url in enumerate(tqdm(df['Link'], desc="Processing PDFs", unit="file")):
    logging.info(f"\nProcessing: {url}")
    link_type = str(df.iloc[i]['Link Type']).strip().lower()
    if link_type == 'box':
        from boxsdk.exception import BoxAPIException

        try:
            shared_link_url = url
            box_file = box_client.get_shared_item(shared_link_url)
            if box_file.type != 'file':
                raise ValueError("Box item is not a file")
            if not box_file.name.lower().endswith('.pdf'):
                raise ValueError("Box file is not a PDF")
            pdf_stream = BytesIO()
            box_file.download_to(pdf_stream)
            pdf_stream.seek(0)
            pdf_data = pdf_stream.read()
        except Exception as e:
            row = df.iloc[i].to_dict()
            row.update({
                'PDF Size (bytes)': None,
                'Page Count': None,
                'Text-based': None,
                'Tagged': None,
                'Notes': f'Skipped: Box access failed - {e}'
            })
            filtered_row = {key: row.get(key, None) for key in output_headers}
            results_batch.append(filtered_row)
            if len(results_batch) >= BATCH_SIZE:
                pd.DataFrame(results_batch).to_csv('output.csv', mode='a', header=False, index=False)
                results_batch = []
            gc.collect()
            continue
    if link_type == 'box':
        response_content = pdf_data
    else:
        if not url.lower().endswith('.pdf'):
            row = df.iloc[i].to_dict()
            row.update({
                'PDF Size (bytes)': None,
                'Page Count': None,
                'Text-based': None,
                'Tagged': None,
                'Notes': 'Skipped: Not a PDF link'
            })
            filtered_row = {key: row.get(key, None) for key in output_headers}
            results_batch.append(filtered_row)
            if len(results_batch) >= BATCH_SIZE:
                pd.DataFrame(results_batch).to_csv('output.csv', mode='a', header=False, index=False)
                results_batch = []
            gc.collect()
            continue

        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            if 'application/pdf' not in response.headers.get('Content-Type', ''):
                raise ValueError("Not a PDF based on Content-Type")
            response_content = response.content
        except Exception as e:
            logging.warning(f"→ Failed to download PDF: {e}")
            row = df.iloc[i].to_dict()
            row.update({
                'PDF Size (bytes)': None,
                'Page Count': None,
                'Text-based': None,
                'Tagged': None,
                'Notes': f"Download failed: {e}"
            })
            filtered_row = {key: row.get(key, None) for key in output_headers}
            results_batch.append(filtered_row)
            if len(results_batch) >= BATCH_SIZE:
                pd.DataFrame(results_batch).to_csv('output.csv', mode='a', header=False, index=False)
                results_batch = []
            gc.collect()
            continue

    # Default values
    size = None
    pages = None
    is_text_based = None
    is_tagged = None
    notes = []

    # Size
    size = len(response_content)

    # Page Count
    try:
        reader = PdfReader(BytesIO(response_content))
        pages = len(reader.pages
        )
    except Exception as e:
        if "invalid float value" in str(e).lower():
            logging.warning("→ PDF parsing issue: invalid float in color setting (non-fatal).")
        else:
            logging.warning(f"→ Failed to read page count: {e}")
        notes.append("Failed to read page count")
        pages = None

    # Text-based check
    try:
        text = extract_text(BytesIO(response_content))
        is_text_based = bool(text.strip())
    except Exception as e:
        logging.warning(f"→ Failed to extract text: {e}")
        notes.append("Failed to extract text")

    # Tag detection heuristic
    try:
        reader = PdfReader(BytesIO(response_content))
        if "/StructTreeRoot" in reader.trailer["/Root"]:
            is_tagged = True
            notes.append("StructTreeRoot tag found")
        else:
            is_tagged = False
            notes.append("No StructTreeRoot tag")
    except Exception as e:
        is_tagged = None
        notes.append(f"Tag check failed: {e}")

    row = df.iloc[i].to_dict()
    row.update({
        'PDF Size (bytes)': size,
        'Page Count': pages,
        'Text-based': is_text_based,
        'Tagged': is_tagged,
        'Notes': "; ".join(notes)
    })
    # Filter row to only include output_headers keys in correct order
    filtered_row = {key: row.get(key, None) for key in output_headers}
    results_batch.append(filtered_row)
    if len(results_batch) >= BATCH_SIZE:
        pd.DataFrame(results_batch).to_csv('output.csv', mode='a', header=False, index=False)
        results_batch = []
    gc.collect()

if results_batch:
    pd.DataFrame(results_batch).to_csv('output.csv', mode='a', header=False, index=False)

logging.info("\nAnalysis complete. Results saved to 'output.csv'.")