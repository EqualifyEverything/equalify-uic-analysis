# Equalify UIC PDF Analysis

This project includes two key tools for analyzing PDF accessibility linked in a CSV input file:

## Components

### 1. Equalify UIC PDF Analysis
This script (`equalify-uic-pdf-analysis.py`) performs automated checks on PDF files. It:
- Analyzes each PDF's size, page count, text content, and tag structure.
- Supports PDFs hosted on direct links or Box.com.
- Submits eligible PDFs for advanced accessibility analysis via Equalify’s scan service.
- Outputs results to `output.csv`.

### 2. Equalify UIC PDF Dashboard
This Streamlit dashboard (`equalify-uic-pdf-dashboard.py`) provides a visual summary of the analysis results. It:
- Displays key metrics like total checks passed/failed and number of files.
- Includes a pie chart and table of failure reasons by description.
- Reads Equalify result JSONs from the `results/` folder.

## Getting Started

1. Place your input data in a file called `input.csv` in the root directory. The file should include a column named `Link` with PDF or Box file URLs.
2. Run the analysis script:
   ```bash
   python equalify-uic-pdf-analysis.py
   ```
3. After the analysis completes, start the dashboard:
   ```bash
   streamlit run equalify-uic-pdf-dashboard.py
   ```

Make sure to install required dependencies (see `requirements.txt`) and set your Box API credentials in a `.env` file.

## Maintainers

This project is maintained by the Accessibility Engineering team at University of Illinois Chicago (UIC) Technology Solutions.