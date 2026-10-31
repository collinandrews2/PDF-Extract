import argparse
import logging
from pathlib import Path
import pandas as pd

from document_store import DocumentStore
from ingestion import LocalDirectoryIngester
from layer_check import classify_pdf
from extract import extract_pdf_tables, extract_data, extract_scanned_pdf

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def setup_environment(base_dir: str = 'data'):
    """Ensures local staging zones exist before execution."""
    paths = {
        "client_drop": f"{base_dir}/client_drop",
        "landing": f"{base_dir}/landing",
        "processed": f"{base_dir}/processed",
        "failed": f"{base_dir}/failed"
    }
    for path in paths.values():
        Path(path).mkdir(parents=True, exist_ok=True)
        
    return paths

def process_document(file_path: Path):
    """Routes the document through the local pipeline based on file type and layer."""
    file_str = str(file_path)
    
    try:
        if file_path.suffix.lower() == '.csv':
            df = extract_data(file_str)
            return {"file": file_path.name, "type": "csv", "data": [df]} if df is not None else None
            
        elif file_path.suffix.lower() == '.pdf':
            doc_type = classify_pdf(file_str)
            
            if doc_type == "born_digital":
                logging.info(f"Extracting native tables from {file_path.name}")
                tables = extract_pdf_tables(file_str)
                return {"file": file_path.name, "type": "pdf_digital", "data": tables}
            else:
                logging.info(f"{file_path.name} is scanned. Routing to local OCR engine.")
                ocr_data = extract_scanned_pdf(file_str)
                return {"file": file_path.name, "type": "pdf_scanned", "data": ocr_data}
    except Exception as e:
        logging.error(f"Error processing {file_path.name}: {e}")
        return None

def export_results(results: list, processed_dir: str):
    """Saves extracted DataFrames locally to the processed zone."""
    exported = 0
    for result in results:
        base_name = Path(result["file"]).stem
        
        for i, df in enumerate(result["data"]):
            if isinstance(df, pd.DataFrame) and not df.empty:
                output_filename = f"{base_name}_table_{i+1}.csv"
                output_path = Path(processed_dir) / output_filename
                
                df.to_csv(output_path, index=False)
                logging.info(f"Saved extracted data to {output_path}")
                exported += 1
    if not exported:
        raise ValueError('Extraction produced no nonempty tables to export')
    return exported

def main(base_dir='data', retry_failed=False):
    summary = {'completed': 0, 'failed': 0, 'intake_errors': 0, 'new': 0, 'duplicates': 0}
    with DocumentStore(base_dir) as store:
        dirs = setup_environment(str(store.base))
        store.recover(retry_failed=retry_failed)
        # Also register legacy flat landing files. Their originals remain untouched.
        for source in (dirs['client_drop'], dirs['landing']):
            result = LocalDirectoryIngester(source, dirs['landing'], store=store).ingest()
            summary['intake_errors'] += len(result['errors'])
            summary['new'] += result['document_count']
            summary['duplicates'] += result['duplicate_count']
            if result['skipped']:
                logging.info('Skipped unsupported files in %s: %s', source, result['skipped'])
        for document in store.pending():
            document_id = document['document_id']
            store.start(document_id)
            try:
                file = store.stage(document_id)
                result = process_document(file)
                if not result or not result['data']:
                    raise ValueError('Extraction failed or produced no data; see extraction logs')
                # Original filename is metadata only; the ID isolates output paths.
                result['file'] = document['original_name']
                with store.export_attempt(document_id) as output:
                    export_results([result], output)
            except Exception as exc:
                store.finish(document_id, error=str(exc))
                summary['failed'] += 1
                logging.exception('Document %s failed; original retained for retry', document_id)
                continue
            summary['completed'] += 1
            # A cleanup failure must never turn a committed export into a failed job.
            try:
                file.unlink(missing_ok=True)
            except OSError:
                logging.warning('Could not clean landing file %s', file, exc_info=True)
    logging.info('Pipeline complete: %s', summary)
    return summary

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run the offline document extraction pipeline')
    parser.add_argument('--data-dir', default='data', help='Local document store directory')
    parser.add_argument('--retry-failed', action='store_true', help='Retry previously failed documents once')
    args = parser.parse_args()
    result = main(args.data_dir, retry_failed=args.retry_failed)
    raise SystemExit(1 if result['failed'] or result['intake_errors'] else 0)
