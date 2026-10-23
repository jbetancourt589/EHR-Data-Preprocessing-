# EHR Data Cleaning & Structuring for LLMs

**Healthcare Data Engineering | Clinical Data Preprocessing | Python | Machine Learning**

## Overview

This project implements a Python-based preprocessing pipeline that converts raw Electronic Health Record (EHR) data into structured, chronologically organized patient timelines.

Clinical datasets often contain fragmented information across physician notes, laboratory results, medications, and hospital transfers. Inconsistent timestamps, duplicate records, and unstructured text make these datasets difficult to analyze or use in machine learning workflows.

The pipeline addresses these challenges by parsing JSONL records, extracting clinical events, standardizing their structure, cleaning text, and organizing patient histories into a consistent format.

**Goal:** Transform complex EHR records into structured datasets suitable for downstream analysis and potential clinical language-model applications.

## Technologies

**Language:** Python

**Data Formats:** JSON, JSONL

**Domain:** Electronic Health Records, clinical data preprocessing, healthcare data engineering

**Techniques:** Data cleaning, event extraction, chronological sorting, text normalization, record deduplication, structured data transformation

**Dataset:** MIMIC-derived clinical records (stored locally and excluded from GitHub)

## Processing Pipeline

```text
Raw EHR Records (JSONL)
          |
          v
JSON Parsing & Validation
          |
          v
Clinical Event Extraction
          |
          v
Text Cleaning & Normalization
          |
          v
Event Deduplication
          |
          v
Timestamp Processing
          |
          v
Chronological Event Ordering
          |
          v
Structured Patient Timeline
          |
          v
Downstream Analytics / LLM Preparation
```

The pipeline prepares data for potential downstream modeling. It does not itself train or evaluate a language model.

## Key Features

### 1. Clinical Event Extraction

Parses multiple types of clinical records into structured event representations.

**Medications**
- Medication name
- Dose and administration route
- Order or discontinuation status

**Laboratory Results**
- Laboratory test name
- Recorded value and units
- Available result flags, including abnormality indicators

**Hospital Transfers**
- Transfer direction (IN/OUT)
- Associated care unit

**Clinical Notes**
- Free-text medical documentation
- Cleaned and formatted note content

### 2. Chronological Patient Timelines

Organizes extracted events by their associated timestamps to create coherent patient histories.

The pipeline handles inconsistent or malformed timestamp values and groups related event types into a standardized output structure.

This enables clinical events from different sources to be reviewed in chronological context.

### 3. Clinical Note Cleaning

Processes unstructured medical documentation to improve consistency and readability.

Cleaning operations include:
- Removing unnecessary whitespace and formatting artifacts
- Normalizing line breaks
- Preserving meaningful section structure
- Retaining redaction placeholders
- Reducing redundant text

The objective is to improve formatting without intentionally removing clinically meaningful information.

### 4. Event Deduplication

Identifies and removes duplicate records to reduce repeated clinical information within the output timeline.

This supports more consistent downstream processing and patient-level inspection.

### 5. Patient-Level Debugging

Includes a utility for inspecting an individual patient's records after preprocessing.

This helps verify:
- Extracted event categories
- Clinical note formatting
- Event ordering
- Output structure
- Potential parsing inconsistencies

### 6. Dataset-Level Processing

Supports both individual-patient inspection and broader JSONL dataset processing.

This separation helps with debugging before running larger preprocessing jobs.

## Repository Structure

```text
EHR-Data-Preprocessing/
├── format.py
├── patient_checker.py
├── .gitignore
└── README.md
```

**`format.py`** — Main preprocessing script responsible for parsing clinical records, extracting events, cleaning text, and constructing structured timelines.

**`patient_checker.py`** — Utility for inspecting individual patient records and checking preprocessing results.

**`.gitignore`** — Excludes raw clinical datasets and generated files from version control.

## Example Input and Output

The following is a **synthetic illustration** of the intended data transformation. It is not a record from an actual patient.

### Input (simplified JSONL)

```json
{"patient_id": "EXAMPLE_001", "time": "2026-01-10 09:15:00", "type": "LAB", "name": "Potassium", "value": 4.2, "unit": "mmol/L"}
{"patient_id": "EXAMPLE_001", "time": "2026-01-10 08:30:00", "type": "TRANSFER", "direction": "IN", "care_unit": "ICU"}
```

### Output (illustrative structure)

```json
{
  "patient_info": {
    "patient_id": "EXAMPLE_001"
  },
  "timeline": [
    {
      "time": "2026-01-10 08:30:00",
      "category": "TRANSFER",
      "data": {
        "direction": "IN",
        "care_unit": "ICU"
      },
      "notes": null
    },
    {
      "time": "2026-01-10 09:15:00",
      "category": "LAB",
      "data": {
        "name": "Potassium",
        "value": 4.2,
        "unit": "mmol/L"
      },
      "notes": null
    }
  ]
}
```

The exact input field names and generated output schema depend on the implementation in `format.py`.

## How to Run

### 1. Clone the Repository

```bash
git clone https://github.com/jbetancourt589/EHR-Data-Preprocessing-.git
cd EHR-Data-Preprocessing-
```

### 2. Prepare Input Data

Place the required JSONL clinical records in the local input directory expected by the scripts.

```text
Raw Data/
```

Raw clinical data is not distributed with this repository.

Depending on the source dataset, access permissions and data-use requirements may apply.

### 3. Run the Preprocessing Pipeline

```bash
python format.py
```

The script processes clinical records and produces structured patient data according to its configured input and output paths.

### 4. Inspect an Individual Patient

```bash
python patient_checker.py
```

Use this utility to examine an individual patient timeline and assess whether clinical events were parsed, cleaned, and chronologically organized as expected.

## Applications

Structured EHR timelines can support several downstream research and engineering tasks.

**Healthcare Data Analytics:** Organizing heterogeneous clinical events into consistent records for analysis.

**Clinical NLP:** Preparing free-text notes and associated structured events for further language-processing workflows.

**Machine Learning Data Preparation:** Transforming raw clinical records into standardized representations for subsequent feature engineering or model development.

**Clinical Language Models:** Supporting the preparation of longitudinal patient histories for potential LLM training or evaluation.

These applications describe possible uses of the prepared data, not independently validated downstream results.

## Data Privacy and Limitations

- Raw MIMIC-derived records are excluded from the public repository.
- MIMIC data access and redistribution remain subject to the applicable PhysioNet credentialing and data-use agreements.
- Synthetic records should be used for public demonstrations.
- The pipeline does not independently guarantee the clinical accuracy of extracted information.
- Incorrect timestamps, incomplete source records, or duplicate-detection rules can affect timeline quality.
- This project does not implement clinical decision-making or diagnostic functionality.
- Prepared data should be evaluated for completeness, consistency, and privacy before downstream model training.

## Why This Project Matters

Clinical data preparation is a critical step in healthcare machine learning.

By converting fragmented, unstructured EHR records into standardized longitudinal timelines, this project demonstrates practical experience in:

- Python-based healthcare data engineering
- Clinical event parsing and data transformation
- Unstructured text preprocessing
- Patient-level data organization
- Preparation of structured datasets for machine learning research

## Author

**Jonathan Betancourt**

Computer Science — University of Florida

Research interests: Healthcare Data Science, Biomedical Informatics, Machine Learning, and Computational Genomics

[GitHub](https://github.com/jbetancourt589) | [LinkedIn](https://www.linkedin.com/in/jonathan-a-betancourt)
