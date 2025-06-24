import streamlit as st
import json
import os
import glob
import pandas as pd
import plotly.express as px

# Path to folder with JSON files
FOLDER = "./results/"

st.title("Equalify-UIC PDF Analysis Dashboard")

@st.cache_data
def load_data():
    records = []
    for path in glob.glob(os.path.join(FOLDER, "job_eq-*.json")):
        print(f"Loading {path}")  # Debug output
        with open(path) as f:
            try:
                data = json.load(f)
                job_id = data.get("jobID")
                job = data["PDFresults"]["report"]["jobs"][0]["validationResult"][0]
                passed = job["details"]["passedChecks"]
                failed = job["details"]["failedChecks"]
                compliant = job["compliant"]
                file_name = job["details"].get("fileName") or job.get("object") or "Unknown"
                records.append({
                    "Job ID": job_id,
                    "File": file_name,
                    "Passed Checks": passed,
                    "Failed Checks": failed,
                    "Compliant": compliant
                })
            except Exception as e:
                records.append({
                    "Job ID": os.path.basename(path),
                    "File": "Error",
                    "Passed Checks": None,
                    "Failed Checks": None,
                    "Compliant": f"Error: {e}"
                })
    return pd.DataFrame(records)

df = load_data()

total_failed_checks = df["Failed Checks"].sum()
st.metric(label="Total Failed Checks", value=int(total_failed_checks))

st.metric(label="Total Passed Checks", value=int(df["Passed Checks"].sum()))

st.metric(label="Total Files Processed", value=len(df))

total_passed_checks = df["Passed Checks"].sum()
check_summary = pd.DataFrame({
    "Result": ["Passed", "Failed"],
    "Count": [total_passed_checks, total_failed_checks]
})
st.subheader("Check Results Overview")
st.plotly_chart(
    px.pie(check_summary, names="Result", values="Count", title="Passed vs Failed Checks"),
    use_container_width=True
)

if df.empty:
    st.warning("No valid data loaded. Check your file paths and JSON structure.")
    st.stop()

st.dataframe(df)

# Add issue category summary
st.subheader("Issue Descriptions and Failed Checks")

def extract_issue_descriptions():
    description_counts = {}
    file_appearance = {}

    for path in glob.glob(os.path.join(FOLDER, "job_eq-*.json")):
        with open(path) as f:
            try:
                data = json.load(f)
                job_id = data.get("jobID", os.path.basename(path))
                rule_summaries = data["PDFresults"]["report"]["jobs"][0]["validationResult"][0]["details"].get("ruleSummaries", [])
                seen_descriptions = set()
                for rule in rule_summaries:
                    if rule["status"] == "failed":
                        desc = rule.get("description", "Unknown issue")
                        description_counts[desc] = description_counts.get(desc, 0) + rule.get("failedChecks", 1)
                        if desc not in seen_descriptions:
                            file_appearance.setdefault(desc, set()).add(job_id)
                            seen_descriptions.add(desc)
            except Exception:
                continue

    total_files = len(df)
    rows = []
    for desc, count in description_counts.items():
        percent = (len(file_appearance.get(desc, [])) / total_files) * 100
        rows.append((desc, count, f"{percent:.1f}%"))

    return pd.DataFrame(rows, columns=["Description", "Failed Checks", "Percent of Files"]).sort_values("Failed Checks", ascending=False)

desc_df = extract_issue_descriptions()
if not desc_df.empty:
    st.dataframe(desc_df)
else:
    st.info("No detailed rule description data available.")