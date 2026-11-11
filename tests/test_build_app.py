import plistlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
from build_app import install_desktop  # noqa: E402


def make_app(path, bundle='local.djintake.launcher'):
    (path / 'Contents').mkdir(parents=True)
    (path / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': bundle}))


class DesktopLinkTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.output = self.tmp / 'outputs/DJ Intake.app'
        make_app(self.output)
        self.desktop = self.tmp / 'Desktop/DJ Intake.app'
        self.desktop.parent.mkdir()

    def test_creates_link(self):
        install_desktop(self.output, self.desktop)
        self.assertTrue(self.desktop.is_symlink())
        self.assertEqual(self.desktop.resolve(), self.output.resolve())

    def test_replaces_old_copy_with_link(self):
        make_app(self.desktop)
        install_desktop(self.output, self.desktop)
        self.assertTrue(self.desktop.is_symlink())

    def test_existing_link_is_left_alone(self):
        install_desktop(self.output, self.desktop)
        before = self.desktop.lstat().st_mtime_ns
        install_desktop(self.output, self.desktop)
        self.assertEqual(self.desktop.lstat().st_mtime_ns, before)

    def test_unrelated_app_is_kept(self):
        make_app(self.desktop, bundle='com.example.other')
        with self.assertRaises(SystemExit):
            install_desktop(self.output, self.desktop)
        self.assertFalse(self.desktop.is_symlink())


if __name__ == '__main__':
    unittest.main()
