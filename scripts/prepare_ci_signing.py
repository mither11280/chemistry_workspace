"""Ephemeral CI-only keychain. Values arrive via masked environment variables, never source."""
import base64
import os
from pathlib import Path
import secrets
import subprocess

root=Path(os.environ['RUNNER_TEMP']);keychain=root/'question-space-signing.keychain-db';password=secrets.token_urlsafe(32)
def run(args):subprocess.run(args,check=True,stdout=subprocess.DEVNULL)
cert=root/'developer-id.p12';cert.write_bytes(base64.b64decode(os.environ['MACOS_CERTIFICATE_P12']));cert.chmod(0o600)
run(['/usr/bin/security','create-keychain','-p',password,str(keychain)])
run(['/usr/bin/security','set-keychain-settings','-lut','21600',str(keychain)])
run(['/usr/bin/security','unlock-keychain','-p',password,str(keychain)])
run(['/usr/bin/security','import',str(cert),'-k',str(keychain),'-P',os.environ['MACOS_CERTIFICATE_PASSWORD'],'-T','/usr/bin/codesign'])
run(['/usr/bin/security','set-key-partition-list','-S','apple-tool:,apple:,codesign:','-s','-k',password,str(keychain)])
run(['/usr/bin/security','list-keychains','-d','user','-s',str(keychain)])
cert.unlink()
key=root/'AuthKey.p8';key.write_text(os.environ['NOTARY_KEY_P8']);key.chmod(0o600)
print('Temporary signing keychain prepared; certificate bytes and passwords are not logged.')
