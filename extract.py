import os
import pytesseract
import pdfplumber
from pdf2image import convert_from_path
import logging
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def extract_data(file_path):
    """Extract data from a CSV file."""
    logging.info(f"Starting data extraction from {file_path}")
    try:
        data = pd.read_csv(file_path)
        logging.info(f"Data successfully extracted from {file_path}")
        return data
    except FileNotFoundError:
        logging.error(f"File not found: {file_path}")
        return None
    except pd.errors.EmptyDataError:
        logging.error(f"No data: {file_path} is empty")
        return None
    except Exception as e:
        logging.error(f"An error occurred while extracting data from {file_path}: {e}")
        return None

def extract_pdf_tables(file_path):
    """Extract native tables from a born-digital PDF file."""
    logging.info(f"Starting table extraction from {file_path}")
    try:
        tables = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables():
                    if table:
                        df = pd.DataFrame(table[1:], columns=table[0])
                        tables.append(df)
        logging.info(f"Tables successfully extracted from {file_path}")
        return tables
    except Exception as e:
        logging.error(f"An error occurred while extracting tables from {file_path}: {e}")
        return []

def extract_scanned_pdf(file_path):
    """Extract text from a scanned PDF using local Tesseract OCR."""
    logging.info(f"Starting local OCR extraction on scanned PDF: {file_path}")
    
    try:
        # Convert PDF pages to images
        images = convert_from_path(file_path)
        
        ocr_results = []
        for i, image in enumerate(images):
            # Run local Tesseract OCR
            text = pytesseract.image_to_string(image)
            ocr_results.append({
                "Page": i + 1,
                "OCR_Text": text
            })
            
        logging.info(f"Local OCR successfully completed for {file_path}")
        
        # Note: If structural table extraction from scanned PDFs is required later,
        # integrating `img2table` with Tesseract here is recommended.
        return [pd.DataFrame(ocr_results)]
        
    except Exception as e:
        logging.error(f"OCR failed for {file_path}. Ensure Tesseract is installed locally: {e}")
        return []