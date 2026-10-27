"""Ephemeral CI-only keychain. Never log commands containing passwords or raw stderr."""
import base64
import os
from pathlib import Path
import secrets
import subprocess

def run(args):
    result=subprocess.run(args,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    if result.returncode:
        # CalledProcessError would include all argv, including the ephemeral keychain password.
        raise SystemExit('Signing keychain operation failed; credentials and command arguments are omitted.')

def main():
    root=Path(os.environ['RUNNER_TEMP']);keychain=root/'question-space-signing.keychain-db';password=secrets.token_urlsafe(32)
    cert=root/'developer-id.p12';cert.write_bytes(base64.b64decode(os.environ['MACOS_CERTIFICATE_P12']));cert.chmod(0o600)
    try:
        run(['/usr/bin/security','create-keychain','-p',password,str(keychain)])
        run(['/usr/bin/security','set-keychain-settings','-lut','21600',str(keychain)])
        run(['/usr/bin/security','unlock-keychain','-p',password,str(keychain)])
        run(['/usr/bin/security','import',str(cert),'-k',str(keychain),'-P',os.environ['MACOS_CERTIFICATE_PASSWORD'],'-T','/usr/bin/codesign'])
        run(['/usr/bin/security','set-key-partition-list','-S','apple-tool:,apple:,codesign:','-s','-k',password,str(keychain)])
        run(['/usr/bin/security','list-keychains','-d','user','-s',str(keychain)])
        key=root/'AuthKey.p8';key.write_text(os.environ['NOTARY_KEY_P8']);key.chmod(0o600)
    finally:
        cert.unlink(missing_ok=True)
    print('Temporary signing keychain prepared; credentials and command arguments are not logged.')
if __name__=='__main__':main()
