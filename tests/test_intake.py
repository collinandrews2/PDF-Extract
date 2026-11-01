"""Regression coverage for identity, recovery, and output publication."""

import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from document_store import DocumentStore, fingerprint
from ingestion import LocalDirectoryIngester
from main import main


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.drop = self.base / 'client_drop'
        self.drop.mkdir()
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

    def source(self, name='report.csv', content='account,amount\nRevenue,100\n'):
        path = self.drop / name
        path.write_text(content, encoding='utf-8')
        return path

    def rows(self):
        with DocumentStore(self.base) as store:
            return store.db.execute('SELECT * FROM documents ORDER BY created_at').fetchall()

    def test_duplicate_content_and_renamed_file_reuse_id_across_runs(self):
        original = self.source()
        self.assertEqual(main(self.base)['completed'], 1)
        document = self.rows()[0]
        self.source('renamed.CSV')
        self.assertEqual(main(self.base)['completed'], 0)
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['document_id'], document['document_id'])
        self.assertEqual(rows[0]['attempts'], 1)
        self.assertTrue(original.exists())
        self.assertEqual(fingerprint(self.base / document['original_path']), fingerprint(original))
        with DocumentStore(self.base) as store:
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM sources').fetchone()[0], 2)

    def test_same_filename_changed_content_preserves_both_versions(self):
        self.source()
        main(self.base)
        self.source(content='account,amount\nRevenue,200\n')
        main(self.base)
        rows = self.rows()
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]['document_id'], rows[1]['document_id'])
        self.assertNotEqual(rows[0]['output_dir'], rows[1]['output_dir'])
        values = [pd.read_csv(next((self.base / row['output_dir']).glob('*.csv'))).iloc[0]['amount']
                  for row in rows]
        self.assertEqual(values, [100, 200])

    def test_same_stem_pdf_and_csv_outputs_do_not_collide(self):
        self.source()
        self.source('report.pdf', '%PDF-test')
        with patch('main.process_document', return_value={'file': 'unused', 'data': [pd.DataFrame({'x': [1]})]}):
            self.assertEqual(main(self.base)['completed'], 2)
        rows = self.rows()
        self.assertEqual(len({row['output_dir'] for row in rows}), 2)
        for row in rows:
            self.assertTrue((self.base / row['output_dir'] / 'report_table_1.csv').is_file())

    def test_failed_export_retains_source_and_requires_explicit_retry(self):
        source = self.source()
        with patch('pandas.DataFrame.to_csv', side_effect=OSError('disk full')):
            self.assertEqual(main(self.base)['failed'], 1)
        row = self.rows()[0]
        self.assertEqual(row['status'], 'failed')
        self.assertIn('disk full', row['last_error'])
        self.assertIsNone(row['output_dir'])
        self.assertTrue((self.base / row['original_path']).exists())
        self.assertTrue((self.base / 'landing' / row['document_id'] / 'document.csv').exists())
        self.assertEqual(list((self.base / 'processed').rglob('*.csv')), [])
        source.unlink()  # Recovery must not depend on the drop folder.
        self.assertEqual(main(self.base)['completed'], 0)
        self.assertEqual(main(self.base, retry_failed=True)['completed'], 1)
        with DocumentStore(self.base) as store:
            row = store.get(row['document_id'])
            self.assertEqual(row['attempts'], 2)
            events = store.db.execute('SELECT status FROM events ORDER BY event_id').fetchall()
            self.assertEqual([event[0] for event in events],
                             ['pending', 'processing', 'failed', 'pending', 'processing', 'completed'])

    def test_interrupted_attempt_recovers_from_original(self):
        source = self.source()
        with DocumentStore(self.base) as store:
            document_id, _ = store.register(source)
            store.start(document_id)
            store.stage(document_id)
        source.unlink()
        self.assertEqual(main(self.base)['completed'], 1)
        row = self.rows()[0]
        self.assertEqual(row['attempts'], 2)
        self.assertEqual(row['status'], 'completed')

    def test_published_export_before_manifest_commit_is_not_treated_as_success(self):
        source = self.source()
        with DocumentStore(self.base) as store:
            document_id, _ = store.register(source)
            store.start(document_id)
            with patch.object(store, 'finish', side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    with store.export_attempt(document_id) as output:
                        (output / 'old.csv').write_text('x\n1\n')
            self.assertEqual(store.get(document_id)['status'], 'processing')
        self.assertEqual(main(self.base)['completed'], 1)
        row = self.rows()[0]
        self.assertTrue(row['output_dir'].endswith('attempt-0002'))
        self.assertTrue((self.base / 'processed' / document_id / 'attempt-0001' / 'old.csv').exists())

    def test_corrupt_archive_is_rejected_without_replacing_it(self):
        source = self.source()
        with DocumentStore(self.base) as store:
            document_id, _ = store.register(source)
            original = self.base / store.get(document_id)['original_path']
        original.write_text('corrupted')
        self.assertEqual(main(self.base)['failed'], 1)
        self.assertIn('integrity', self.rows()[0]['last_error'])
        self.assertEqual(original.read_text(), 'corrupted')

    def test_empty_dataframe_does_not_mark_job_completed(self):
        self.source(content='account,amount\n')
        self.assertEqual(main(self.base)['failed'], 1)
        self.assertEqual(self.rows()[0]['status'], 'failed')

    def test_one_intake_failure_does_not_block_other_documents(self):
        self.source('good.csv')
        self.source('bad.csv')
        self.source('upload.part')
        with DocumentStore(self.base) as store:
            register = store.register

            def fail_one(path):
                if path.name == 'bad.csv':
                    raise PermissionError('locked upload')
                return register(path)

            with patch.object(store, 'register', side_effect=fail_one):
                result = LocalDirectoryIngester(self.drop, self.base / 'landing', store).ingest()
            self.assertEqual(result['status'], 'partial')
            self.assertEqual(result['document_count'], 1)
            self.assertEqual(len(result['errors']), 1)
            self.assertEqual(result['skipped'], ['upload.part'])

    def test_legacy_flat_landing_files_are_imported_without_deletion(self):
        landing = self.base / 'landing'
        landing.mkdir()
        legacy = landing / 'legacy.csv'
        legacy.write_text('x\n1\n')
        self.assertEqual(main(self.base)['completed'], 1)
        self.assertTrue(legacy.exists())
        self.assertEqual(main(self.base)['completed'], 0)

    def test_os_lock_blocks_second_process_and_releases_on_close(self):
        script = 'from document_store import DocumentStore; import sys; s=DocumentStore(sys.argv[1]); s.__enter__(); s.__exit__()'
        command = [sys.executable, '-c', script, str(self.base)]
        with DocumentStore(self.base):
            blocked = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn('Another pipeline process', blocked.stderr)
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)

    def test_changing_source_is_not_registered(self):
        source = self.source()
        real_fsync = os.fsync

        def change_during_copy(fd):
            real_fsync(fd)
            source.write_text('account,amount\nChanged,100000\n')

        with DocumentStore(self.base) as store:
            with patch('document_store.os.fsync', side_effect=change_during_copy):
                with self.assertRaisesRegex(RuntimeError, 'Source changed'):
                    store.register(source)
            self.assertEqual(store.pending(), [])
            self.assertEqual(list((self.base / 'originals').iterdir()), [])
        self.assertTrue(source.exists())

    def test_partial_multi_table_export_is_never_published(self):
        self.source()
        tables = [pd.DataFrame({'x': [1]}), pd.DataFrame({'x': [2]})]
        original_export = pd.DataFrame.to_csv
        calls = 0

        def fail_second(frame, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('second table failed')
            return original_export(frame, *args, **kwargs)

        with patch('main.process_document', return_value={'file': 'unused', 'data': tables}):
            with patch.object(pd.DataFrame, 'to_csv', fail_second):
                self.assertEqual(main(self.base)['failed'], 1)
        self.assertEqual(list((self.base / 'processed').rglob('*.csv')), [])
        self.assertIsNone(self.rows()[0]['output_dir'])

    def test_process_crash_releases_lock(self):
        script = ('from document_store import DocumentStore; import sys,os; '
                  's=DocumentStore(sys.argv[1]); s.__enter__(); os._exit(23)')
        crashed = subprocess.run([sys.executable, '-c', script, str(self.base)], capture_output=True)
        self.assertEqual(crashed.returncode, 23)
        with DocumentStore(self.base) as store:
            self.assertEqual(store.pending(), [])


if __name__ == '__main__':
    unittest.main()
