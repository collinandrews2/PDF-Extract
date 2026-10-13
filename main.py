import os
import logging
from pathlib import Path
import pandas as pd

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
    for result in results:
        base_name = Path(result["file"]).stem
        
        for i, df in enumerate(result["data"]):
            if isinstance(df, pd.DataFrame) and not df.empty:
                output_filename = f"{base_name}_table_{i+1}.csv"
                output_path = os.path.join(processed_dir, output_filename)
                
                df.to_csv(output_path, index=False)
                logging.info(f"Saved extracted data to {output_path}")

def main():
    dirs = setup_environment()
    
    # 1. Local Ingestion (Air-gapped)
    ingester = LocalDirectoryIngester(source_dir=dirs["client_drop"], landing_dir=dirs["landing"])
    ingest_result = ingester.ingest()
    
    if ingest_result['status'] == 'error':
        logging.error("Ingestion failed. Halting pipeline.")
        return
        
    # 2. Local Processing
    results = []
    for file in Path(dirs["landing"]).iterdir():
        if file.is_file():
            data = process_document(file)
            if data and data["data"]:
                results.append(data)
            else:
                # Move failed or empty files to the failed directory
                failed_path = Path(dirs["failed"]) / file.name
                file.rename(failed_path)
                logging.warning(f"Moved {file.name} to failed directory.")
            
    # 3. Export Output
    export_results(results, dirs["processed"])
    logging.info(f"Self-contained pipeline complete. Successfully processed {len(results)} files.")

if __name__ == "__main__":
    main()