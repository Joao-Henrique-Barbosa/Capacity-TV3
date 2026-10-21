"""Verifique instalação local, preservação de dados e rejeição de corrupção."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/setup_project.py'
spec = importlib.util.spec_from_file_location('setup_project', SCRIPT)
setup_project = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup_project)


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / 'data/geography'
        self.bundle.mkdir(parents=True)
        (self.root / 'configs').mkdir()
        (self.root / 'configs/paths.example.yaml').write_text('example: true\n')
        self.contents = b'geographic fixture\n'
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('terrain/data.tif', self.contents)
        payload = buffer.getvalue()
        (self.bundle / 'part01').write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        self.manifest = {'sha256': digest, 'parts': [{'name': 'part01', 'sha256': digest}],
                         'files': {'terrain/data.tif': {'sha256': hashlib.sha256(self.contents).hexdigest()}}}
        self.write_manifest()

    def write_manifest(self):
        (self.bundle / 'manifest.json').write_text(json.dumps(self.manifest))

    def test_fresh_setup_and_repeat_preserve_local_configuration(self):
        setup_project.setup(self.root)
        target = self.bundle / 'extracted/terrain/data.tif'
        self.assertEqual(target.read_bytes(), self.contents)
        local = self.root / 'configs/paths.local.yaml'
        self.assertEqual(local.read_text(), 'example: true\n')
        local.write_text('custom: true\n')
        setup_project.setup(self.root)
        self.assertEqual(local.read_text(), 'custom: true\n')

    def test_corrupt_archive_rejected_before_extraction(self):
        (self.bundle / 'part01').write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            setup_project.setup(self.root)
        self.assertFalse((self.bundle / 'extracted').exists())

    def test_modified_base_is_not_overwritten(self):
        setup_project.setup(self.root)
        target = self.bundle / 'extracted/terrain/data.tif'
        target.write_bytes(b'custom terrain')
        with self.assertRaises(ValueError):
            setup_project.setup(self.root)
        self.assertEqual(target.read_bytes(), b'custom terrain')

    def test_manifest_cannot_escape_destination(self):
        self.manifest['files'] = {'../outside.tif': {'sha256': 'unused'}}
        self.write_manifest()
        with self.assertRaises(ValueError):
            setup_project.setup(self.root)


if __name__ == '__main__':
    unittest.main()
