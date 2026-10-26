"""Guard released bundle selection and corrupt/unsafe archive rejection."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from download_models import download
import prepare


def sha(data):
    return hashlib.sha256(data).hexdigest()


class BundleTests(unittest.TestCase):
    def test_context_selects_matching_v10_files_and_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'context'
            with patch.dict(os.environ, GH_TOKEN='test-only'), \
                 patch.object(prepare, 'asset_url', return_value='https://example.invalid/model'), \
                 patch.object(prepare, 'release_asset_api_url', return_value='https://api.github.com/test'):
                prepare.prepare(output)
            sources = json.loads((output / 'model-sources.json').read_text())
            item = next(x for x in sources if x['path'] == 'jev-call-v10.zip')
            release = json.loads((prepare.ROOT / 'backend/jev-posttrain/v10_release.json').read_text())
            self.assertEqual(item['sha256'], release['sha256'])
            manifest = json.loads((output / 'backend/jev-posttrain/model_downloads.json').read_text())
            bundle = next(x for x in manifest if x['version'] == 'V10')
            self.assertEqual(set(bundle['files']), {'model.onnx', 'tokenizer.json', 'calibration.json'})
            for name, info in bundle['files'].items():
                self.assertEqual(item['files']['JevCallV10/' + name], {'member': name, **info})
            self.assertIn('JEV_MODEL_VERSION=V10', (output / 'Dockerfile').read_text())
            self.assertNotIn('test-only', (output / 'model-sources.json').read_text())

    def archive(self, folder):
        archive = folder / 'release.zip'
        with zipfile.ZipFile(archive, 'w') as output:
            output.writestr('model.onnx', b'model')
            output.writestr('model.safetensors', b'unneeded training weights')
        return {'path': 'download.zip', 'url': archive.as_uri(), 'sha256': sha(archive.read_bytes()),
                'files': {'JevCallV10/model.onnx': {'member': 'model.onnx', 'bytes': 5, 'sha256': sha(b'model')}}}

    def test_extracts_only_verified_inference_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            item = self.archive(folder)
            destination = folder / 'models'
            download([item], destination)
            self.assertEqual((destination / 'JevCallV10/model.onnx').read_bytes(), b'model')
            self.assertEqual([str(x.relative_to(destination)) for x in destination.rglob('*') if x.is_file()],
                             ['JevCallV10/model.onnx'])

    def test_rejects_archive_or_member_mismatch_and_path_escape(self):
        for failure in ('archive', 'checksum', 'size', 'path'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary)
                item = self.archive(folder)
                member = item['files']['JevCallV10/model.onnx']
                if failure == 'archive':
                    item['sha256'] = '0' * 64
                elif failure == 'checksum':
                    member['sha256'] = '0' * 64
                elif failure == 'size':
                    member['bytes'] = 10
                else:
                    item['files'] = {'../escaped': member}
                with self.assertRaises(ValueError):
                    download([item], folder / 'models')
                self.assertFalse((folder / 'escaped').exists())
                self.assertFalse((folder / 'models/download.zip.partial').exists())


if __name__ == '__main__':
    unittest.main()
