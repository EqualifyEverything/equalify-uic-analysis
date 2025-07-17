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

# Basin Imports
import csv
import json
import os
import time
import requests
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

INPUT_CSV = "input.csv"
OUTPUT_CSV = "output.csv"
RESULTS_DIR = "results"
SCAN_URL = "https://scan-dev.equalify.app/generate/urls"
JOB_URL_BASE = "https://scan-dev.equalify.app/"

os.makedirs(RESULTS_DIR, exist_ok=True)


def write_output_csv(rows, fieldnames):
    with open(OUTPUT_CSV, mode='w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    logging.info(f"Wrote results to {OUTPUT_CSV}")

def send_scan_request(urls, mode=None):
    logging.info(f"Sending scan request for {len(urls)} URLs with mode={mode}")
    body = {"urls": [{"url": url, "flags": "scanAsPdf"} if mode == "verapdf" else {"url": url} for url in urls]}
    if mode:
        body["mode"] = mode
    try:
        response = requests.post(SCAN_URL, json=body)
        response.raise_for_status()
        jobs = response.json().get("jobs", [])
        logging.info(f"Received response with {len(jobs)} jobs")
        return jobs
    except Exception as e:
        return {"error": str(e)}

def poll_job_result(job_id):
    result_url = f"{JOB_URL_BASE}results/axe/{job_id}"
    logging.info(f"Requesting scan result from {result_url}")
    logging.info(f"Polling job result for job_id={job_id}")
    for attempt in range(6):
        try:
            response = requests.get(result_url)
            if response.ok:
                logging.info(f"Received {len(response.text)} characters in response")
                result = response.json()
                status = result.get("status")
                if status == "completed":
                    logging.info(f"Job {job_id} status is completed at attempt {attempt+1}")
                    return result
                if status == "failed":
                    logging.info(f"Job {job_id} status is failed")
                    return result
                else:
                    logging.info(f"Job {job_id} status is {status}")
        except Exception as e:
            logging.warning(f"Attempt {attempt+1} failed for job {job_id}: {e}")
        logging.info(f"Checked job {job_id}, attempt {attempt+1}")
        time.sleep(10)
    return None

def main():
    from collections import defaultdict

    processed_urls = set()
    file_exists = os.path.exists(OUTPUT_CSV)
    if file_exists:
        with open(OUTPUT_CSV, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                url_type = row["Link Type"].strip().lower()
                scanned_url = row["Link"].strip() if url_type == "pdf" else row["URL"].strip()
                if row.get("Equalify Scan Results"):
                    processed_urls.add(scanned_url)
                elif row.get("Notes"):
                    processed_urls.add(scanned_url)
        logging.info(f"Skipping {len(processed_urls)} previously processed URLs")

    # Streaming read and chunking
    pdf_batch = []
    html_batch = []
    url_to_row = {}

    with open(INPUT_CSV, newline='', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)
        fieldnames = reader.fieldnames + ["Equalify Scan Results", "Notes"]
        with open(OUTPUT_CSV, mode='a', newline='', encoding='utf-8') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            if not file_exists or os.stat(OUTPUT_CSV).st_size == 0:
                writer.writeheader()

            def process_batch(urls, mode):
                if not urls:
                    return
                jobs = send_scan_request(urls, mode=mode)
                if isinstance(jobs, dict) and "error" in jobs:
                    for url in urls:
                        row = url_to_row[url]
                        row["Notes"] = f"Error during scan request: {jobs['error']}"
                        writer.writerow(row)
                    return
                if not jobs:
                    for url in urls:
                        row = url_to_row[url]
                        row["Notes"] = "No job returned from scan"
                        writer.writerow(row)
                    return
                for job in jobs:
                    url = job.get("url")
                    job_id = job.get("jobId")
                    row = url_to_row[url]
                    if not job_id:
                        row["Notes"] = "No jobId found"
                        writer.writerow(row)
                        continue
                    result = poll_job_result(job_id)
                    if result:
                        if result.get("status") == "completed":
                            filename = f"{job_id}.json"
                            filepath = os.path.join(RESULTS_DIR, filename)
                            with open(filepath, 'w', encoding='utf-8') as f:
                                json.dump(result, f, indent=2)
                            logging.info(f"Saved scan result to {filepath}")
                            row["Equalify Scan Results"] = filename
                        else:
                            logging.info(f"Scan job {job_id} returned status: {result.get('status')}")
                            row["Notes"] = f"Scan {result.get('status')}"
                    else:
                        logging.error(f"Failed to get results for job {job_id}")
                        row["Notes"] = "Scan timed out or failed"
                    writer.writerow(row)

            for idx, row in enumerate(reader):
                url_type = row["Link Type"].strip().lower()
                url = row["Link"].strip() if url_type == "pdf" else row["URL"].strip()
                row["Equalify Scan Results"] = ""
                row["Notes"] = ""
                logging.info(f"Processing row {idx+1}: {url}")
                # Improved URL match traceability
                if url in processed_urls:
                    logging.info(f"Skipping already processed URL (matched): {url}")
                    continue
                else:
                    if any(url.strip() == p.strip() for p in processed_urls):
                        logging.warning(f"URL {url} differs only by whitespace from processed.")
                if not url:
                    row["Notes"] = "Missing URL"
                    writer.writerow(row)
                    continue
                elif url_type == "box":
                    row["Notes"] = "Box links aren't accessible."
                    writer.writerow(row)
                    continue
                else:
                    url_to_row[url] = row
                    if url_type == "pdf":
                        pdf_batch.append(url)
                        if len(pdf_batch) >= 100:
                            process_batch(pdf_batch, mode="verapdf")
                            pdf_batch.clear()
                    else:
                        html_batch.append(url)
                        if len(html_batch) >= 100:
                            process_batch(html_batch, mode=None)
                            html_batch.clear()

            # Process any remaining batches after loop
            if pdf_batch:
                process_batch(pdf_batch, mode="verapdf")
            if html_batch:
                process_batch(html_batch, mode=None)

if __name__ == "__main__":
    main()