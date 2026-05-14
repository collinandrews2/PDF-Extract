import pytesseract
import pdfplumber
from pdf2image import convert_from_path
import logging
import pandas as pd
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
    