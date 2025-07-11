# === Open Source Software ===
# This program is maintained by the University of Illinois Chicago Accessibility
# Engineering Team (https://uic.edu/accessibility/engineering).
# Copyright (C) 2025  University of Illinois Chicago.

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program. 

# === Standard library imports ===
import os
from dotenv import load_dotenv
load_dotenv()
BOX_ENABLED = all([
    os.getenv('BOX_CLIENT_ID'),
    os.getenv('BOX_CLIENT_SECRET'),
    os.getenv('BOX_ACCESS_TOKEN')
])
import gc
import logging
from io import BytesIO

# === Third-party imports ===
import pandas as pd
import requests
from tqdm import tqdm
from PyPDF2 import PdfReader
from pdfminer.high_level import extract_text
from boxsdk import OAuth2, Client
from boxsdk.exception import BoxAPIException

logging.basicConfig(level=logging.INFO, format='%(message)s')
# Silence pdfminer logging to CRITICAL
for noisy_logger in ["pdfminer", "pdfminer.layout", "pdfminer.pdfinterp"]:
    logging.getLogger(noisy_logger).setLevel(logging.CRITICAL)

if BOX_ENABLED:
    oauth = OAuth2(
        client_id=os.getenv('BOX_CLIENT_ID'),
        client_secret=os.getenv('BOX_CLIENT_SECRET'),
        access_token=os.getenv('BOX_ACCESS_TOKEN')
    )
    box_client = Client(oauth)

# Initialize output CSV with headers
output_headers = [
    'Link Type', 'Location Type', 'Title', 'Link', 'URL',
    'PDF Size (bytes)', 'Page Count', 'Text-based',
    'Tagged', 'Notes', 'Equalify Scan Results'
]
pd.DataFrame(columns=output_headers).to_csv('output.csv', index=False)

# Load input CSV
df = pd.read_csv('input.csv')

logging.info("Starting PDF accessibility analysis...")

results_batch = []
BATCH_SIZE = 100

equalify_batch = []
equalify_url_to_index = {}

for i, url in enumerate(tqdm(df['Link'], desc="Processing PDFs", unit="file")):
    logging.info(f"\nProcessing: {url}")
    row = df.iloc[i].to_dict()

    # === Determine test requirements flags ===
    pdf_size_raw = row.get('PDF Size (bytes)', '')
    page_count_raw = row.get('Page Count', '')
    text_based_raw = row.get('Text-based', '')
    tagged_raw = row.get('Tagged', '')
    equalify_scan_raw = row.get('Equalify Scan Results', '')

    pdf_size_val = str(pdf_size_raw).strip().upper() if pd.notna(pdf_size_raw) else ""
    page_count_val = str(page_count_raw).strip().upper() if pd.notna(page_count_raw) else ""
    text_based_val = str(text_based_raw).strip().upper() if pd.notna(text_based_raw) else ""
    if pd.isna(tagged_raw):
        tagged_val = ""
    else:
        tagged_val = "TRUE" if str(tagged_raw).strip().upper() == "TRUE" else "FALSE"
    equalify_scan_val = str(equalify_scan_raw).strip().upper() if pd.notna(equalify_scan_raw) else ""

    needs_size = pdf_size_val in ["", "FAILED"]
    needs_pages = page_count_val in ["", "FAILED"]
    needs_text = text_based_val in ["", "FAILED"]
    needs_tagged = tagged_val in ["", "FAILED"]
    # Move link_type detection before needs_equalify
    link_type = str(row.get('Link Type', '')).strip().lower()

    # Immediately after defining link_type, adjust needs_equalify
    needs_equalify = (
        tagged_val == "TRUE"
        and equalify_scan_val in ["", "FAILED"]
    )
    if link_type == 'box':
        needs_equalify = False

    needs_anything = any([needs_size, needs_pages, needs_text, needs_tagged, needs_equalify])

    # Unified skip for both Box and PDF links if all tests previously failed and not tagged and not needing Equalify
    if all(val == "FAILED" for val in [pdf_size_val, page_count_val, text_based_val, tagged_val]) and not needs_equalify:
        row.update({
            'Notes': 'Skipped: All tests previously failed, skipping reprocessing'
        })
        filtered_row = {key: row.get(key, None) for key in output_headers}
        results_batch.append(filtered_row)
        if len(results_batch) >= BATCH_SIZE:
            pd.DataFrame(results_batch).to_csv('output.csv', mode='a', header=False, index=False)
            results_batch = []
        gc.collect()
        continue

    # Skip PDF download if only Equalify scan is required (no local tests needed)
    if needs_equalify and not any([needs_size, needs_pages, needs_text, needs_tagged]):
        equalify_batch.append({ "url": url })
        equalify_url_to_index[url] = len(results_batch)
        row.update({
            'PDF Size (bytes)': row.get('PDF Size (bytes)'),
            'Page Count': row.get('Page Count'),
            'Text-based': row.get('Text-based'),
            'Tagged': row.get('Tagged'),
            'Notes': "Skipped: Only Equalify scan required",
            'Equalify Scan Results': None
        })
        filtered_row = {key: row.get(key, None) for key in output_headers}
        results_batch.append(filtered_row)
        if len(results_batch) >= BATCH_SIZE:
            pd.DataFrame(results_batch).to_csv('output.csv', mode='a', header=False, index=False)
            results_batch = []
        gc.collect()
        continue

    if not needs_anything:
        filtered_row = {key: row.get(key, None) for key in output_headers}
        results_batch.append(filtered_row)
        if len(results_batch) >= BATCH_SIZE:
            pd.DataFrame(results_batch).to_csv('output.csv', mode='a', header=False, index=False)
            results_batch = []
        gc.collect()
        continue

    # Removed redundant Box skip condition that relied on needs_anything and needs_equalify

    # === Retrieve PDF content ===
    if link_type == 'box':
        if not BOX_ENABLED:
            row.update({
                'PDF Size (bytes)': None,
                'Page Count': None,
                'Text-based': None,
                'Tagged': None,
                'Notes': 'Skipped: BOX credentials not provided'
            })
            filtered_row = {key: row.get(key, None) for key in output_headers}
            results_batch.append(filtered_row)
            if len(results_batch) >= BATCH_SIZE:
                pd.DataFrame(results_batch).to_csv('output.csv', mode='a', header=False, index=False)
                results_batch = []
            gc.collect()
            continue

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
            response_content = pdf_data
        except Exception as e:
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
    else:
        if link_type != 'box' and not url.lower().endswith('.pdf'):
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

    # === Initialize default values ===
    size = None
    pages = None
    is_text_based = None
    is_tagged = None
    notes = []
    equalify_scan_results = None

    # === PDF Size (bytes) ===
    if needs_size:
        size = len(response_content)
    else:
        size = row.get('PDF Size (bytes)')

    # === Page Count ===
    if needs_pages:
        try:
            reader = PdfReader(BytesIO(response_content))
            pages = len(reader.pages)
        except Exception as e:
            if "invalid float value" in str(e).lower():
                logging.warning("→ PDF parsing issue: invalid float in color setting (non-fatal).")
            else:
                logging.warning(f"→ Failed to read page count: {e}")
            notes.append("Failed to read page count")
            pages = "FAILED"
    else:
        pages = row.get('Page Count')

    # === Text-based check ===
    if needs_text:
        try:
            text = extract_text(BytesIO(response_content))
            is_text_based = bool(text.strip())
        except Exception as e:
            logging.warning(f"→ Failed to extract text: {e}")
            notes.append("Failed to extract text")
            is_text_based = "FAILED"
    else:
        is_text_based = row.get('Text-based')

    # === Tag detection heuristic ===
    if needs_tagged:
        try:
            reader = PdfReader(BytesIO(response_content))
            if "/StructTreeRoot" in reader.trailer["/Root"]:
                is_tagged = True
                notes.append("StructTreeRoot tag found")
            else:
                is_tagged = False
                notes.append("No StructTreeRoot tag")
        except Exception as e:
            is_tagged = "FAILED"
            notes.append(f"Tag check failed: {e}")
    else:
        is_tagged = row.get('Tagged')

    # === Prepare Equalify batch if needed and not Box link ===
    if needs_equalify and link_type != 'box':
        equalify_batch.append({ "url": url })
        equalify_url_to_index[url] = len(results_batch)  # store index in results_batch
        equalify_scan_results = f"Equalify result saved to results/job_{url}.json"
    else:
        equalify_scan_results = row.get('Equalify Scan Results')
        if needs_equalify and link_type == 'box':
            equalify_scan_results = "Skipped Equalify scan: Box-hosted PDF"

    row.update({
        'PDF Size (bytes)': size,
        'Page Count': pages,
        'Text-based': is_text_based,
        'Tagged': is_tagged,
        'Notes': "; ".join(notes),
        'Equalify Scan Results': equalify_scan_results
    })
    # Filter row to only include output_headers keys in correct order
    filtered_row = {key: row.get(key, None) for key in output_headers}
    results_batch.append(filtered_row)
    if len(results_batch) >= BATCH_SIZE:
        pd.DataFrame(results_batch).to_csv('output.csv', mode='a', header=False, index=False)
        results_batch = []
    gc.collect()

# After processing all rows, handle Equalify batch scans
if equalify_batch:
    try:
        resp = requests.post(
            "https://scan-dev.equalify.app/generate/urls",
            json={"urls": equalify_batch, "mode": "verapdf"},
            timeout=30
        )
        resp.raise_for_status()
        resp_json = resp.json()
        jobs = resp_json.get("jobs", [])
        url_to_jobId = {}
        for job in jobs:
            if job is None:
                continue
            url = job.get("url") if isinstance(job, dict) else None
            jobId = job.get("jobId") if isinstance(job, dict) else None
            if url and jobId:
                url_to_jobId[url] = jobId
        import time
        max_wait = 60
        poll_interval = 15
        for url, jobId in url_to_jobId.items():
            waited = 0
            while waited < max_wait:
                logging.info(f"→ Polling Equalify job for {jobId} ({waited}/{max_wait} seconds elapsed)")
                poll_url = f"https://scan-dev.equalify.app/results/axe/{jobId}"
                try:
                    poll_resp = requests.get(poll_url, timeout=15)
                    poll_resp.raise_for_status()
                    poll_json = poll_resp.json()
                    if poll_json.get("status") == "completed":
                        result_obj = poll_json.get("result")
                        job_file_path = f"results/job_{jobId}.json"
                        os.makedirs("results", exist_ok=True)
                        with open(job_file_path, 'w') as f:
                            import json
                            json.dump(result_obj, f)
                        idx = equalify_url_to_index.get(url)
                        if idx is not None and idx < len(results_batch):
                            results_batch[idx]['Equalify Scan Results'] = f"Equalify result saved to {job_file_path}"
                        break
                    elif poll_json.get("status") == "error":
                        idx = equalify_url_to_index.get(url)
                        if idx is not None and idx < len(results_batch):
                            results_batch[idx]['Equalify Scan Results'] = f"Equalify scan error"
                        break
                except Exception as e:
                    logging.warning(f"→ Polling error for jobId {jobId}: {e}")
                time.sleep(poll_interval)
                waited += poll_interval
            else:
                idx = equalify_url_to_index.get(url)
                if idx is not None and idx < len(results_batch):
                    results_batch[idx]['Equalify Scan Results'] = "Equalify scan timed out after 180 seconds"
    except Exception as e:
        logging.warning(f"→ Equalify batch scan error: {e}")
        for url in equalify_batch:
            idx = equalify_url_to_index.get(url)
            if idx is not None and idx < len(results_batch):
                results_batch[idx]['Equalify Scan Results'] = f"Equalify scan error: {e}"

if results_batch:
    pd.DataFrame(results_batch).to_csv('output.csv', mode='a', header=False, index=False)

logging.info("\nAnalysis complete. Results saved to 'output.csv'.")