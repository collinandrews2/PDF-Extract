import os
import logging
from pathlib import Path

# Assuming you update your modules to handle these imports
from ingestion import S3Ingester
from layerCheck import classify_pdf
from extract import extract_pdf_tables, extract_data

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def setup_environment(base_dir: str = 'data'):
    """Ensures landing zones exist before execution."""
    paths = [f"{base_dir}/landing", f"{base_dir}/processed", f"{base_dir}/failed"]
    for path in paths:
        Path(path).mkdir(parents=True, exist_ok=True)
    return paths[0]

def process_document(file_path: Path):
    """Routes the document based on its file type and digital layer."""
    if file_path.suffix.lower() == '.csv':
        df = extract_data(file_path)
        return {"file": file_path.name, "type": "csv", "tables": [df]}
        
    elif file_path.suffix.lower() == '.pdf':
        doc_type = classify_pdf(file_path)
        
        if doc_type == "born_digital":
            logging.info(f"Extracting native tables from {file_path.name}")
            tables = extract_pdf_tables(file_path)
            return {"file": file_path.name, "type": "pdf_digital", "tables": tables}
        else:
            logging.warning(f"{file_path.name} is scanned. Routing to OCR queue.")
            # OCR logic would go here
            return {"file": file_path.name, "type": "pdf_scanned", "tables": []}

def main():
    landing_zone = setup_environment()
    
    # 1. Ingest
    ingester = S3Ingester(bucket_name='tax-documents-bucket')
    # Note: Update S3Ingester to actually download files to `landing_zone`
    ingester.ingest() 
    
    # 2. Process
    results = []
    for file in Path(landing_zone).iterdir():
        if file.is_file():
            data = process_document(file)
            results.append(data)
            
    # 3. Output logic goes here
    logging.info(f"Pipeline complete. Processed {len(results)} files.")

if __name__ == "__main__":
    main()