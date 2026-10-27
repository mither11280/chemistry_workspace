import subprocess
import sys
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
