
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

logging.basicConfig(level=logging.INFO, format='%(message)s')
# Silence pdfminer logging to CRITICAL
for noisy_logger in ["pdfminer", "pdfminer.layout", "pdfminer.pdfinterp"]:
    logging.getLogger(noisy_logger).setLevel(logging.CRITICAL)

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
        row = df.iloc[i].to_dict()
        row.update({
            'PDF Size (bytes)': None,
            'Page Count': None,
            'Text-based': None,
            'Tagged': None,
            'Notes': 'Skipped: Box link'
        })
        filtered_row = {key: row.get(key, None) for key in output_headers}
        results_batch.append(filtered_row)
        if len(results_batch) >= BATCH_SIZE:
            pd.DataFrame(results_batch).to_csv('output.csv', mode='a', header=False, index=False)
            results_batch = []
        gc.collect()
        logging.info("→ Skipped: Box link")
        continue
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
    size = len(response.content)

    # Page Count
    try:
        reader = PdfReader(BytesIO(response.content))
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
        text = extract_text(BytesIO(response.content))
        is_text_based = bool(text.strip())
    except Exception as e:
        logging.warning(f"→ Failed to extract text: {e}")
        notes.append("Failed to extract text")

    # Tag detection using pdfminer3 only
    try:
        from pdfminer3.pdfinterp import PDFResourceManager, PDFPageInterpreter
        from pdfminer3.pdfdevice import TagExtractor
        from pdfminer3.pdfpage import PDFPage

        rsrcmgr = PDFResourceManager()
        retstr = BytesIO()
        try:
            device = TagExtractor(rsrcmgr, retstr, codec='utf-8')
        except:
            device = TagExtractor(rsrcmgr, retstr, codec='ascii')
        interpreter = PDFPageInterpreter(rsrcmgr, device)
        maxpages = 1
        pagenos = set()
        import contextlib
        import os
        import sys
        for page in PDFPage.get_pages(BytesIO(response.content), pagenos, maxpages=maxpages, caching=True, check_extractable=True):
            with contextlib.redirect_stdout(open(os.devnull, 'w')), contextlib.redirect_stderr(open(os.devnull, 'w')):
                interpreter.process_page(page)
        contents = retstr.getvalue().decode()

        # Acrobat tag indicators
        tag_indicators = ["<b'Part'", "</b'Sect'", "</b'Art'", "<b'Content'", "<b'Artifact'"]
        if any(tag in contents for tag in tag_indicators):
            is_tagged = True
            notes.append("Tags detected via pdfminer3")
        else:
            is_tagged = False
            notes.append("No tags detected via pdfminer3")
    except Exception as e:
        is_tagged = None
        notes.append(f"pdfminer3 tag check failed: {e}")

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