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
    """
    Extract data from a CSV file.

    Parameters:
    file_path (str): The path to the CSV file.

    Returns:
    pd.DataFrame: The extracted data as a DataFrame.
    """

    "keep track of the data extraction process and log any issues that arise"
    logging.info(f"Starting data extraction from {file_path}")

    "looks for the specified file and attempts to read it into a DataFrame, logging success or failure"
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
    """
    Extract tables from a PDF file.

    Parameters:
    file_path (str): The path to the PDF file.

    Returns:
    list: A list of DataFrames, each representing a table extracted from the PDF.
    """
    logging.info(f"Starting table extraction from {file_path}")

    try:
        tables = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables():
                    df = pd.DataFrame(table[1:], columns=table[0])
                    tables.append(df)
        logging.info(f"Tables successfully extracted from {file_path}")
        return tables
    except FileNotFoundError:
        logging.error(f"File not found: {file_path}")
        return []
    except Exception as e:
        logging.error(f"An error occurred while extracting tables from {file_path}: {e}")
        return []