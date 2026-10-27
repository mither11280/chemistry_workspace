import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from fixtures import ROOT
sys.path.insert(0,str(ROOT))
from scripts.prepare_ci_signing import run

class SigningSecurityTests(unittest.TestCase):
    def test_failed_keychain_operation_does_not_print_password(self):
        secret='test-only-ephemeral-password'
        with patch('scripts.prepare_ci_signing.subprocess.run',return_value=subprocess.CompletedProcess([],1,stderr=secret.encode())):
            with self.assertRaises(SystemExit) as failure:run(['security','create-keychain','-p',secret])
        self.assertNotIn(secret,str(failure.exception))
    def test_release_tag_targets_the_built_commit(self):
        text=(ROOT/'.github/workflows/macos-release.yml').read_text()
        self.assertIn('--target "$GITHUB_SHA"',text)

    def test_full_license_preparation_precedes_packaging(self):
        text=(ROOT/'.github/workflows/macos-release.yml').read_text()
        self.assertLess(text.index('--prepare-only'),text.index('name: Build app and DMG'))
    def test_builder_refuses_to_silently_omit_license_texts(self):
        from scripts import build_macos
        with tempfile.TemporaryDirectory() as folder,patch.object(build_macos,'ROOT',Path(folder)):
            with self.assertRaises(SystemExit) as failure:build_macos.notices(Path(folder)/'licenses')
        self.assertIn('--prepare-only',str(failure.exception))
