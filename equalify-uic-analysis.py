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

def read_input_csv():
    with open(INPUT_CSV, newline='', encoding='utf-8') as csvfile:
        reader = list(csv.DictReader(csvfile))
    logging.info(f"Read {len(reader)} rows from {INPUT_CSV}")
    return reader

def write_output_csv(rows, fieldnames):
    with open(OUTPUT_CSV, mode='w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    logging.info(f"Wrote results to {OUTPUT_CSV}")

def send_scan_request(urls, mode=None):
    logging.info(f"Sending scan request for {len(urls)} URLs with mode={mode}")
    body = {"urls": [{"url": url} for url in urls]}
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
                else:
                    logging.info(f"Job {job_id} status is {status}")
        except Exception as e:
            logging.warning(f"Attempt {attempt+1} failed for job {job_id}: {e}")
        logging.info(f"Checked job {job_id}, attempt {attempt+1}")
        time.sleep(10)
    return None

def main():
    from collections import defaultdict
    # Clean output files
    if os.path.exists(OUTPUT_CSV):
        os.remove(OUTPUT_CSV)
    for filename in os.listdir(RESULTS_DIR):
        file_path = os.path.join(RESULTS_DIR, filename)
        if os.path.isfile(file_path):
            os.remove(file_path)

    def chunked(iterable, size):
        for i in range(0, len(iterable), size):
            yield iterable[i:i + size]

    input_rows = read_input_csv()
    url_to_row = {}
    pdf_urls = []
    html_urls = []
    output_rows = []

    for idx, row in enumerate(input_rows):
        url_type = row["Link Type"].strip().lower()
        url = row["URL"].strip()
        row["Equalify Scan Results"] = ""
        row["Notes"] = ""
        logging.info(f"Processing row {idx+1}/{len(input_rows)}: {url}")

        if not url:
            row["Notes"] = "Missing URL"
            output_rows.append(row)
            continue

        if url_type == "box":
            row["Notes"] = "Box links aren't accessible."
            output_rows.append(row)
            continue

        if url_type == "pdf":
            pdf_urls.append(url)
            url_to_row[url] = row
        else:
            html_urls.append(url)
            url_to_row[url] = row

    for url_list, mode in [(pdf_urls, "verapdf"), (html_urls, None)]:
        for chunk in chunked(url_list, 100):
            jobs = send_scan_request(chunk, mode=mode)
            if isinstance(jobs, dict) and "error" in jobs:
                for url in chunk:
                    row = url_to_row[url]
                    row["Notes"] = f"Error during scan request: {jobs['error']}"
                    output_rows.append(row)
                continue
            if not jobs:
                for url in chunk:
                    row = url_to_row[url]
                    row["Notes"] = "No job returned from scan"
                    output_rows.append(row)
                continue
            for job in jobs:
                url = job.get("url")
                job_id = job.get("jobId")
                row = url_to_row[url]
                if not job_id:
                    row["Notes"] = "No jobId found"
                    output_rows.append(row)
                    continue
                result = poll_job_result(job_id)
                if result:
                    filename = f"{job_id}.json"
                    filepath = os.path.join(RESULTS_DIR, filename)
                    with open(filepath, 'w', encoding='utf-8') as f:
                        json.dump(result, f, indent=2)
                    logging.info(f"Saved scan result to {filepath}")
                    row["Equalify Scan Results"] = filename
                else:
                    logging.error(f"Failed to get results for job {job_id}")
                    row["Notes"] = "Scan timed out or failed"
                output_rows.append(row)

    write_output_csv(output_rows, input_rows[0].keys())

if __name__ == "__main__":
    main()