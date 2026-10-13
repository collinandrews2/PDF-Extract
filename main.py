import logging
from pathlib import Path

from ingestion import LocalDirectoryIngester
from layerCheck import classify_pdf
from extract import extract_pdf_tables, extract_data, extract_scanned_pdf

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def setup_environment(base_dir: str = 'data'):
    """Ensures local staging zones exist before execution."""
    paths = [
        f"{base_dir}/client_drop", 
        f"{base_dir}/landing", 
        f"{base_dir}/processed", 
        f"{base_dir}/failed"
    ]
    for path in paths:
        Path(path).mkdir(parents=True, exist_ok=True)
        
    return paths[0], paths[1]  # Return client_drop and landing

def process_document(file_path: Path):
    """Routes the document through the local pipeline based on file type and layer."""
    file_str = str(file_path)
    
    if file_path.suffix.lower() == '.csv':
        df = extract_data(file_str)
        return {"file": file_path.name, "type": "csv", "data": [df]}
        
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

def main():
    client_drop_zone, landing_zone = setup_environment()
    
    # 1. Local Ingestion (Air-gapped)
    ingester = LocalDirectoryIngester(source_dir=client_drop_zone, landing_dir=landing_zone)
    ingest_result = ingester.ingest()
    
    if ingest_result['status'] == 'error':
        logging.error("Ingestion failed. Halting pipeline.")
        return
        
    # 2. Local Processing
    results = []
    for file in Path(landing_zone).iterdir():
        if file.is_file():
            data = process_document(file)
            if data:
                results.append(data)
            
    # 3. Output payload formatting logic goes here
    logging.info(f"Self-contained pipeline complete. Processed {len(results)} files.")

if __name__ == "__main__":
    main()