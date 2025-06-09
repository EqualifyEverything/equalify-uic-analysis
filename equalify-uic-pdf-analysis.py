import pikepdf
from pdfminer.high_level import extract_text
import pandas as pd
import requests
from PyPDF2 import PdfReader
from io import BytesIO
import logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

# Initialize output CSV with headers
output_headers = [
    'Site Name', 'Site ID', 'Link Type', 'Location Type', 'Title', 'Link', 'URL',
    'PDF Size (bytes)', 'Page Count', 'Text-based', 'Has Title',
    'Language Set', 'Tagged', 'Notes'
]
pd.DataFrame(columns=output_headers).to_csv('output.csv', index=False)

# Load input CSV
df = pd.read_csv('input.csv')

logging.info("Starting PDF accessibility analysis...")

for i, url in enumerate(df['Link']):
    logging.info(f"\nProcessing: {url}")
    link_type = str(df.iloc[i]['Link Type']).strip().lower()
    if link_type == 'Box':
        row = df.iloc[i].to_dict()
        row.update({
            'PDF Size (bytes)': None,
            'Page Count': None,
            'Text-based': None,
            'Has Title': None,
            'Language Set': None,
            'Tagged': None,
            'Notes': 'Skipped: Box link'
        })
        pd.DataFrame([row]).to_csv('output.csv', mode='a', header=False, index=False)
        logging.info("→ Skipped: Box link")
        continue
    if not url.lower().endswith('.pdf'):
        row = df.iloc[i].to_dict()
        row.update({
            'PDF Size (bytes)': None,
            'Page Count': None,
            'Text-based': None,
            'Has Title': None,
            'Language Set': None,
            'Tagged': None,
            'Notes': 'Skipped: Not a PDF link'
        })
        pd.DataFrame([row]).to_csv('output.csv', mode='a', header=False, index=False)
        continue

    try:
        response = requests.get(url)
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
            'Has Title': None,
            'Language Set': None,
            'Tagged': None,
            'Notes': f"Download failed: {e}"
        })
        pd.DataFrame([row]).to_csv('output.csv', mode='a', header=False, index=False)
        continue

    # Default values
    size = None
    pages = None
    is_text_based = None
    has_title = None
    lang = None
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

    # Metadata
    try:
        with pikepdf.open(BytesIO(response.content)) as pdf:
            docinfo = pdf.docinfo
            has_title = bool(docinfo.get('/Title'))

            root = getattr(pdf, "root", None)
            if root and '/Lang' in root:
                lang = root.get('/Lang', 'Not Set')
            else:
                lang = 'Unknown'
                notes.append("Missing /Lang in outline root")

            mark_info = root.get('/MarkInfo') if root else None
            is_tagged = mark_info.get('/Marked') if mark_info and '/Marked' in mark_info else False
            if not mark_info:
                notes.append("Missing /MarkInfo in outline root")
    except Exception as e:
        logging.warning(f"→ Failed to extract metadata: {e}")
        notes.append("Failed to extract metadata")
        has_title = None
        lang = 'Unknown'
        is_tagged = None

    row = df.iloc[i].to_dict()
    row.update({
        'PDF Size (bytes)': size,
        'Page Count': pages,
        'Text-based': is_text_based,
        'Has Title': has_title,
        'Language Set': lang,
        'Tagged': is_tagged,
        'Notes': "; ".join(notes)
    })
    pd.DataFrame([row]).to_csv('output.csv', mode='a', header=False, index=False)

logging.info("\nAnalysis complete. Results saved to 'output.csv'.")