import os
import shutil
import logging
from datetime import datetime
from typing import Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LocalDirectoryIngester:
    """Handles self-contained, offline document ingestion from local directories."""
    
    def __init__(self, source_dir: str, landing_dir: str):
        self.source_dir = source_dir
        self.landing_dir = landing_dir
    
    def ingest(self) -> Dict[str, Any]:
        """Move documents from the local client drop zone to the landing zone."""
        try:
            if not os.path.exists(self.source_dir):
                os.makedirs(self.source_dir, exist_ok=True)
                
            if not os.path.exists(self.landing_dir):
                os.makedirs(self.landing_dir, exist_ok=True)
                
            ingested_files = []
            for filename in os.listdir(self.source_dir):
                src_path = os.path.join(self.source_dir, filename)
                if os.path.isfile(src_path):
                    dest_path = os.path.join(self.landing_dir, filename)
                    shutil.copy2(src_path, dest_path)
                    
                    # Optionally remove the original file after successful copy
                    # os.remove(src_path) 
                    
                    ingested_files.append(filename)
                    
            logger.info(f"Locally ingested {len(ingested_files)} documents into landing zone")
            return {
                'status': 'success',
                'document_count': len(ingested_files),
                'documents': ingested_files,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Local ingestion error: {e}")
            return {'status': 'error', 'message': str(e)}

def trigger_pipeline_event(document_info: Dict[str, Any]) -> bool:
    """Trigger local pipeline execution."""
    try:
        logger.info(f"Local ETL pipeline event triggered at {document_info.get('timestamp')}")
        return True
    except Exception as e:
        logger.error(f"Failed to trigger local pipeline event: {e}")
        return False