# Local Air-Gapped PDF Extraction Pipeline (ETL)

A specialized, fully localized ETL pipeline designed to ingest, classify, and extract structural financial data from scanned and born-digital PDFs. This project is built for strict compliance environments where sensitive client financial data must remain entirely within the local network (no external cloud APIs).

## Architecture & Branching Strategy

This repository is structured to maintain a strictly isolated production baseline while allowing experimental integration with analytics and AI on parallel branches.

* **`main` (Air-Gapped Core):** The production-grade, offline baseline. Houses the core extraction logic (`pytesseract`, `pdfplumber`, `PyPDF2`) and local directory ingestion. Packaged as a standalone executable via PyInstaller for secure client drop-zone workflows.
* **`google-test` (Cloud API Integration):** Experimental branch integrating the Google Gemini API. Routes payloads for external reasoning and utilizes NotebookLM for document synthesis and mock data generation.
* **`doc-it` (Analytics Pipeline):** Data engineering branch focused on downstream ETL. Handles loading extracted tables into secondary databases and transforming them into structured schemas for Excel or Microsoft dashboards/Power BI.
* **`local-ai` (Self-Hosted Inference):** R&D branch connecting the local pipeline to self-hosted AI models (e.g., Ollama, Odysseus AI). Unlocks advanced LLM reasoning and data structuring without compromising network isolation.

## Core Pipeline Workflow (`main`)

1. **Ingestion:** The `LocalDirectoryIngester` polls a designated `client_drop` folder and securely transfers files to the `landing` zone without network dependencies.
2. **Classification:** `layerCheck.py` inspects PDF text layers to categorize documents as *born-digital* or *scanned*.
3. **Extraction:**
   * *Born-Digital:* Tables are extracted natively using `pdfplumber`.
   * *Scanned:* Routed to local `pytesseract` and `pdf2image` for offline OCR text extraction.
4. **Formatting:** Cleaned data structures are exported into unified formats (e.g., Pandas DataFrames) ready for the downstream database load.

## Local Setup & Installation

**Note:** Because branches target fundamentally different deployment environments, dependencies must remain isolated to prevent the offline executable from bloating with cloud libraries.

1. **Install Core Dependencies (Main):**
   ```bash
   pip install -r requirements.txt