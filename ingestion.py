"""Offline intake with content deduplication and retained originals."""

import logging
from pathlib import Path

from document_store import DocumentStore, now

logger = logging.getLogger(__name__)


class LocalDirectoryIngester:
    def __init__(self, source_dir: str, landing_dir: str, store=None):
        self.source_dir = Path(source_dir)
        self.landing_dir = Path(landing_dir)
        self.store = store

    def ingest(self):
        if self.store is None:
            with DocumentStore(self.landing_dir.parent) as store:
                return self._ingest(store)
        return self._ingest(self.store)

    def _ingest(self, store):
        self.source_dir.mkdir(parents=True, exist_ok=True)
        documents, errors, skipped = [], [], []
        duplicates = 0
        for source in sorted(self.source_dir.iterdir()):
            if not source.is_file():
                continue
            if source.is_symlink() or source.suffix.lower() not in ('.pdf', '.csv'):
                skipped.append(source.name)
                continue
            try:
                document_id, created = store.register(source)
                documents.append(document_id)
                duplicates += not created
            except Exception as exc:
                logger.exception('Intake failed for %s', source.name)
                errors.append({'file': source.name, 'error': str(exc)})
        return {
            'status': 'partial' if errors else 'success',
            'document_count': len(documents) - duplicates,
            'duplicate_count': duplicates,
            'documents': documents,
            'errors': errors,
            'skipped': skipped,
            'timestamp': now(),
        }


def trigger_pipeline_event(document_info):
    logger.info('Local ETL pipeline event triggered at %s', document_info.get('timestamp'))
    return True
