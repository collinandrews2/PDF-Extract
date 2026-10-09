import os
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Dict, Any
import boto3
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TaxDocumentIngester(ABC):
    #Abstract base class for tax document ingestion sources.
    
    @abstractmethod
    def ingest(self) -> Dict[str, Any]:
        #Ingest tax documents from the source.
        pass


class S3Ingester(TaxDocumentIngester):
    #Handles document ingestion from S3 (API, email scraping, SFTP uploads).
    
    def __init__(self, bucket_name: str, region: str = 'us-east-1'):
        self.s3_client = boto3.client('s3', region_name=region)
        self.bucket_name = bucket_name
        self.landing_prefix = 'landing-zone/'
    
    def ingest(self) -> Dict[str, Any]:
        #List and verify documents in landing zone.
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=self.landing_prefix
            )
            documents = response.get('Contents', [])
            logger.info(f"Found {len(documents)} documents in landing zone")
            return {
                'status': 'success',
                'document_count': len(documents),
                'documents': [obj['Key'] for obj in documents],
                'timestamp': datetime.now().isoformat()
            }
        except ClientError as e:
            logger.error(f"S3 ingestion error: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def upload_document(self, file_path: str, document_name: str) -> bool:
        #Upload tax document to landing zone.
        try:
            s3_key = f"{self.landing_prefix}{document_name}"
            self.s3_client.upload_file(file_path, self.bucket_name, s3_key)
            logger.info(f"Uploaded {document_name} to {s3_key}")
            return True
        except ClientError as e:
            logger.error(f"Upload failed: {e}")
            return False


class APIIngester(TaxDocumentIngester):
    """Handles document ingestion from API endpoints."""
    
    def __init__(self, api_endpoint: str, api_key: Optional[str] = None):
        self.api_endpoint = api_endpoint
        self.api_key = api_key or os.getenv('API_KEY')
    
    def ingest(self) -> Dict[str, Any]:
        """Fetch documents from API endpoint."""
        try:
            import requests
            headers = {'Authorization': f'Bearer {self.api_key}'} if self.api_key else {}
            response = requests.get(self.api_endpoint, headers=headers, timeout=30)
            response.raise_for_status()
            logger.info("Successfully fetched documents from API")
            return {
                'status': 'success',
                'data': response.json(),
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"API ingestion error: {e}")
            return {'status': 'error', 'message': str(e)}


class EmailIngester(TaxDocumentIngester):
    """Handles document ingestion from email attachments."""
    
    def __init__(self, imap_server: str, email: str, password: str):
        self.imap_server = imap_server
        self.email = email
        self.password = password
    
    def ingest(self) -> Dict[str, Any]:
        """Scrape tax documents from email attachments."""
        try:
            import imaplib
            mail = imaplib.IMAP4_SSL(self.imap_server)
            mail.login(self.email, self.password)
            mail.select('INBOX')
            
            status, messages = mail.search(None, 'ALL')
            email_ids = messages[0].split()
            logger.info(f"Found {len(email_ids)} emails")
            
            mail.close()
            mail.logout()
            
            return {
                'status': 'success',
                'email_count': len(email_ids),
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Email ingestion error: {e}")
            return {'status': 'error', 'message': str(e)}


class SFTPIngester(TaxDocumentIngester):
    """Handles document ingestion from SFTP servers."""
    
    def __init__(self, host: str, username: str, password: str, remote_path: str):
        self.host = host
        self.username = username
        self.password = password
        self.remote_path = remote_path
    
    def ingest(self) -> Dict[str, Any]:
        """Fetch documents from SFTP server."""
        try:
            import paramiko
            transport = paramiko.Transport((self.host, 22))
            transport.connect(username=self.username, password=self.password)
            sftp = paramiko.SFTPClient.from_transport(transport)
            
            files = sftp.listdir(self.remote_path)
            logger.info(f"Found {len(files)} files on SFTP server")
            
            sftp.close()
            transport.close()
            
            return {
                'status': 'success',
                'file_count': len(files),
                'files': files,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"SFTP ingestion error: {e}")
            return {'status': 'error', 'message': str(e)}


def trigger_pipeline_event(document_info: Dict[str, Any]) -> bool:
    """Trigger pipeline event to start processing."""
    try:
        event_payload = {
            'event_type': 'document_ingested',
            'document_info': document_info,
            'timestamp': datetime.now().isoformat()
        }
        logger.info(f"Pipeline event triggered: {json.dumps(event_payload)}")
        # In production, this would publish to EventBridge, SQS, or similar
        return True
    except Exception as e:
        logger.error(f"Failed to trigger pipeline event: {e}")
        return False


if __name__ == '__main__':
    # Example usage
    s3_ingester = S3Ingester(bucket_name='tax-documents-bucket')
    result = s3_ingester.ingest()
    trigger_pipeline_event(result)
