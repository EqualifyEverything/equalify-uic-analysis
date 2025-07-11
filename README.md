# Equalify UIC PDF Analysis

This project includes two key tools for analyzing PDF and HTML pages with the Equalify accessibility scan.

## Equalify UIC Analysis
This script (`equalify-uic-analysis.py`) performs automated checks on PDF and HTML files. It:
- Analyzes each PDF's size, page count, text content, and tag structure.
- Supports PDFs hosted on direct links.
- Submits eligible PDFs for advanced accessibility analysis via Equalify’s scan service.
- Submits eligble HTML pages via Equalify's scan service.
- Outputs results to `output.csv`.

## Getting Started

### Setup Python Environment

It's recommended to use a Python virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
pip install -r requirements.txt
```

1. Rename `input-sample.csv` to `input.csv` in the root directory. Add in data within similar format.
2. Run the analysis script:
   ```bash
   python equalify-uic-analysis.py
   ```

Make sure to install required dependencies (see `requirements.txt`).

## Maintainers

This project is maintained by the [Accessibility Engineering team](https://it.uic.edu/accessibility/engineering/) at University of Illinois Chicago (UIC) Technology Solutions.