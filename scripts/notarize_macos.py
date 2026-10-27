"""Developer ID notarization; requires real credentials, never fakes a successful ticket."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]

def notarize(path,credentials):
    result=subprocess.run(['/usr/bin/xcrun','notarytool','submit',str(path),'--wait','--output-format','json',*credentials],capture_output=True,text=True)
    if result.returncode:raise SystemExit('Apple notarization submission failed: '+result.stderr)
    info=json.loads(result.stdout)
    if info.get('status')!='Accepted':raise SystemExit('Apple rejected notarization: '+json.dumps(info))
    return info

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('app',type=Path);p.add_argument('--identity',required=True)
    p.add_argument('--keychain-profile');p.add_argument('--key',type=Path);p.add_argument('--key-id');p.add_argument('--issuer')
    p.add_argument('--output',type=Path,default=ROOT/'dist');args=p.parse_args()
    app=args.app.resolve();info=plistlib.loads((app/'Contents/Info.plist').read_bytes())
    if info.get('QuestionSpaceDistribution')!='developer-id':raise SystemExit('Internal/ad-hoc app cannot be notarized as an official release; rebuild with --sign-identity.')
    credentials=['--keychain-profile',args.keychain_profile] if args.keychain_profile else ['--key',str(args.key),'--key-id',str(args.key_id),'--issuer',str(args.issuer)] if args.key and args.key_id and args.issuer else None
    if not credentials:raise SystemExit('Provide a stored notarytool profile or App Store Connect key/ID/issuer; no credentials are embedded in code.')
    args.output.mkdir(parents=True,exist_ok=True);version=info['CFBundleShortVersionString']
    with tempfile.TemporaryDirectory(prefix='qs-notary-') as temporary:
        temporary=Path(temporary);zipfile=temporary/'app.zip'
        subprocess.run(['/usr/bin/ditto','-c','-k','--keepParent',str(app),str(zipfile)],check=True)
        app_result=notarize(zipfile,credentials)
        subprocess.run(['/usr/bin/xcrun','stapler','staple',str(app)],check=True)
        subprocess.run(['/usr/bin/xcrun','stapler','validate',str(app)],check=True)
        staging=temporary/'staging';staging.mkdir();shutil.copytree(app,staging/'题间.app',symlinks=True);(staging/'Applications').symlink_to('/Applications')
        (staging/'安装说明.txt').write_text('拖动题间到 Applications。运行环境已内置，用户数据位于 Application Support/ChemistryWorkspace。')
        dmg=args.output/f'ChemistryWorkspace-{version}-arm64.dmg'
        if dmg.exists():dmg.rename(args.output/(dmg.stem+'-BEFORE-NOTARIZATION.dmg'))
        subprocess.run(['/usr/bin/hdiutil','create','-volname','题间','-srcfolder',str(staging),'-format','UDZO','-ov',str(dmg)],check=True)
        subprocess.run(['/usr/bin/codesign','--force','--sign',args.identity,'--timestamp',str(dmg)],check=True)
        dmg_result=notarize(dmg,credentials)
        subprocess.run(['/usr/bin/xcrun','stapler','staple',str(dmg)],check=True)
        subprocess.run(['/usr/bin/xcrun','stapler','validate',str(dmg)],check=True)
        subprocess.run(['/usr/sbin/spctl','--assess','--type','execute','--verbose=2',str(app)],check=True)
        subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(app)],check=True)
        (args.output/'notarization-report.json').write_text(json.dumps({'status':'Accepted','app':app_result,'dmg':dmg_result},indent=2))
        (args.output/(dmg.name+'.sha256')).write_text(hashlib.sha256(dmg.read_bytes()).hexdigest()+'  '+dmg.name+'\n')
if __name__=='__main__':main()
