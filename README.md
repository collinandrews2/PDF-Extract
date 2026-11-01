# Local Air-Gapped PDF Extraction Pipeline (ETL)

A specialized, fully localized ETL pipeline designed to ingest, classify, and extract structural financial data from scanned and born-digital PDFs. This project is built for strict compliance environments where sensitive client financial data must remain entirely within the local network (no external cloud APIs).

## Architecture & Branching Strategy

This repository is structured to maintain a strictly isolated production baseline while allowing experimental integration with analytics and AI on parallel branches.

* **`main` (Air-Gapped Core):** The production-grade, offline baseline. Houses the core extraction logic (`pytesseract`, `pdfplumber`, `PyPDF2`) and local directory ingestion. Packaged as a standalone executable via PyInstaller for secure client drop-zone workflows.
* **`google-test` (Cloud API Integration):** Experimental branch integrating the Google Gemini API. Routes payloads for external reasoning and utilizes NotebookLM for document synthesis and mock data generation.
* **`doc-it` (Analytics Pipeline):** Data engineering branch focused on downstream ETL. Handles loading extracted tables into secondary databases and transforming them into structured schemas for Excel or Microsoft dashboards/Power BI.
* **`local-ai` (Self-Hosted Inference):** R&D branch connecting the local pipeline to self-hosted AI models (e.g., Ollama, Odysseus AI). Unlocks advanced LLM reasoning and data structuring without compromising network isolation.

## Core Pipeline Workflow (`main`)

1. **Ingestion:** The `LocalDirectoryIngester` scans `client_drop`, archives original bytes, and registers content hashes and document IDs in a local manifest. Processing stages verified working copies in `landing`.
2. **Classification:** `layer_check.py` inspects PDF text layers to categorize documents as *born-digital* or *scanned*.
3. **Extraction:**
   * *Born-Digital:* Tables are extracted natively using `pdfplumber`.
   * *Scanned:* Routed to local `pytesseract` and `pdf2image` for offline OCR text extraction.
4. **Formatting:** Cleaned data structures are exported into unified formats (e.g., Pandas DataFrames) ready for the downstream database load.

## Local Setup & Installation

**Note:** Because branches target fundamentally different deployment environments, dependencies must remain isolated to prevent the offline executable from bloating with cloud libraries.

1. **Install Core Dependencies (Main):**
   ```bash
   pip install -r requirements.txt
   ```

## Reliable local intake

Run from the repository directory:

```bash
python main.py
python main.py --retry-failed
python main.py --data-dir /path/to/local/data
python -m unittest discover -s tests -v
```

The pipeline keeps its state in `data/manifest.sqlite3` using Python's built-in
SQLite library. All document content and state remain local. Use a local disk,
not a shared network filesystem, for this data directory.

- Each distinct `(SHA-256 of file bytes, lowercase extension)` receives a UUID
  document ID. Renamed duplicates reuse the ID; changed contents under an existing
  filename create a new document. PDF and CSV interpretations are distinct.
- `originals/<document_id>/original.<ext>` retains the original bytes. The pipeline
  never deletes or rewrites these originals or the files in `client_drop`.
- `sources` records source paths and first/last observations. `documents` records
  the hash, original name, size, status, attempt count, output location, and latest
  error. `events` records timestamped processing transitions and errors per attempt.
- Jobs transition through `pending -> processing -> completed` or `failed`.
  Completed documents are skipped on later runs. Interrupted processing attempts
  are automatically queued again on startup. Failed jobs are retried once per run
  only when `--retry-failed` is supplied, using their archived originals even if
  the drop files have been removed.
- Exports go to `processed/<document_id>/attempt-0001/`, alongside `document.json`.
  A temporary directory holds all tables until export succeeds. Only then is the
  directory published and the manifest marked completed. Consumers must use the
  completed record's `output_dir`, not scan every attempt directory for results.
- A crash between export publication and the manifest commit can leave an
  uncommitted attempt on disk. A retry writes a new attempt directory; old outputs
  are never overwritten. Interrupted temporary files and unregistered archive
  directories can also remain after crashes; automatic garbage collection is not
  included in this version.
- Landing copies are removed only after successful completion. Failed copies and
  archived originals remain available. Archive hashes are verified before use;
  corrupt or missing originals fail the attempt instead of silently being replaced.
- An OS process lock rejects concurrent runs against the same data directory and
  is released when a process exits or crashes. The lock file itself may remain.
- Only `.pdf` and `.csv` files are ingested. Uploaders should write to a temporary
  extension such as `.part`, then atomically rename the finished file into place.
  Intake detects size/mtime/inode changes during its copy, but cannot guarantee an
  upload is finished if another application pauses writing an eligible filename.

### Existing data and operational limits

Existing flat files in `landing/` are registered on the next run and retained.
Existing `failed/` files are left untouched: copy files you want retried into
`client_drop/` to register them. Old flat `processed/` outputs are also untouched;
there is no reliable historical mapping from those files to source hashes, so
existing drop files will be processed once into the new document-ID layout.

The originals archive is retained by application convention, not protected against
manual edits or disk failure. Back up the entire data directory together, including
the manifest. There is no automatic retention/deletion policy. The process lock and
atomic publication protect local process retries; this is not a distributed job
queue or a guarantee against every hardware/power-loss scenario.

Extraction errors currently swallowed by the PDF extraction helpers appear as a
failed/no-data event; detailed parser/OCR exceptions remain in the application log.
This change does not alter OCR, PDF classification, or financial interpretation.

Inspect history using a SQLite client, for example:

```sql
SELECT document_id, original_name, status, attempts, output_dir, last_error
FROM documents ORDER BY created_at;
SELECT document_id, timestamp, status, attempt, detail
FROM events ORDER BY event_id;
```
