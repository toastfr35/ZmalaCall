"""Clean only disposable fixtures, never the developer's checkout."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


spec = importlib.util.spec_from_file_location('clean', (Path(__file__).resolve().parents[3] / 'build_tools') / 'clean.py')
clean = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clean)


class CleanTests(unittest.TestCase):
    def test_cleanup_preview_and_protected_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            disposable = ['src/__pycache__/module.pyc', 'src/old.pyo', '.ruff_cache/entry',
                          'tmp/document.png', 'build_tools/tmp/test.log', 'requirements/output/index.html',
                          'build_tools/dist/setup.exe', 'build_tools/.npm-cache/cache', 'tests/adhoc/tmp/result.json']
            preserved = ['requirements/terminal/TERM001.yml', 'src/module.py', 'data/settings.json', '.venv/__pycache__/keep.pyc',
                         'node_modules/__pycache__/keep.pyc', 'build_tools/runtime/engine.dll',
                         'zmala_terminal/data/__pycache__/keep.pyc', '.env', 'important.tmp',
                         'source/__pycache__/tracked.txt']
            for name in disposable + preserved:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('fixture')
            subprocess.run(['git', 'add', '--', 'source/__pycache__/tracked.txt'], cwd=root, check=True)
            with contextlib.redirect_stdout(io.StringIO()):
                clean.clean(root, dry_run=True)
                self.assertTrue(all((root / name).exists() for name in disposable + preserved))
                clean.clean(root)
                clean.clean(root)  # Repeated cleanup is harmless.
            self.assertTrue(all(not (root / name).exists() for name in disposable))
            self.assertTrue(all((root / name).read_text() == 'fixture' for name in preserved))

    def test_directory_links_are_not_followed(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root, target = Path(directory), Path(outside)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            (target / 'important.pyc').write_text('keep')
            try:
                (root / 'tmp').symlink_to(target, target_is_directory=True)
            except OSError:
                if sys.platform != 'win32':
                    self.skipTest('Creating directory symlinks requires platform permissions')
                # Junction creation needs no elevated symlink privilege on Windows.
                subprocess.run(['cmd', '/c', 'mklink', '/J', str(root / 'tmp'), str(target)],
                               check=True, stdout=subprocess.PIPE)
            with contextlib.redirect_stdout(io.StringIO()):
                clean.clean(root)
            self.assertEqual((target / 'important.pyc').read_text(), 'keep')
            self.assertTrue(clean.linked(root / 'tmp'))


if __name__ == '__main__':
    unittest.main()
