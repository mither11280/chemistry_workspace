"""Build a self-contained arm64 Swift app with a PyInstaller onedir helper and drag-install DMG."""
import argparse
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys
import tarfile
import time

ROOT=Path(__file__).resolve().parents[1]

def run(args,**kwargs):
    print('+',args[0],*map(str,args[1:3]),flush=True)
    subprocess.run([str(x) for x in args],check=True,**kwargs)

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def collect_exams(source_dir,destination):
    manifest=json.loads((ROOT/'indexes/source-manifest.json').read_text())
    required={s['sha256']:s for s in manifest['sources']};found={}
    for p in Path(source_dir).rglob('*'):
        if p.is_file() and p.suffix.lower()=='.pdf':
            sha=digest(p)
            if sha in required:found[sha]=p
    missing=[s['filename'] for sha,s in required.items() if sha not in found]
    if missing:raise SystemExit('Missing exact bundled exam sources: '+', '.join(missing))
    destination.mkdir(parents=True)
    records=[]
    for sha,source in required.items():
        target=destination/source['filename'];shutil.copyfile(found[sha],target)
        if digest(target)!=sha:raise SystemExit('Exam copy hash mismatch')
        records.append({'filename':source['filename'],'sha256':sha,'bytes':target.stat().st_size})
    return records

def notices(destination):
    destination.mkdir(parents=True,exist_ok=True);inventory=[]
    for name in ['PyMuPDF','Pillow','jsonschema','attrs','referencing','rpds-py','jsonschema-specifications','typing_extensions','PyInstaller']:
        dist=metadata.distribution(name);folder=destination/name;folder.mkdir()
        for item in dist.files or []:
            lower=str(item).lower()
            if any(part in lower for part in ['license','copying','notice']) and dist.locate_file(item).is_file():
                target=folder/Path(str(item)).name
                if not target.exists():shutil.copyfile(dist.locate_file(item),target)
        inventory.append({'name':name,'version':dist.version,'license':dist.metadata.get('License-Expression') or dist.metadata.get('License','See bundled license')})
    shutil.copyfile(ROOT/'LICENSE',destination/'APP-SOURCE-MIT.txt')
    for name in ['distribution-licensing.md','macos-distribution.md']:
        if (ROOT/'docs'/name).exists():shutil.copyfile(ROOT/'docs'/name,destination/name)
    for name in ['AGPL-3.0.txt','PYTHON-LICENSE.txt']:
        source=ROOT/'build/corresponding-source'/name
        if source.exists():shutil.copyfile(source,destination/name)
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if python_license.exists():shutil.copyfile(python_license,destination/'PYTHON-LICENSE.txt')
    else:
        import sysconfig
        candidate=Path(sysconfig.get_path('stdlib'))/'LICENSE.txt'
        if candidate.exists():shutil.copyfile(candidate,destination/'PYTHON-LICENSE.txt')
    (destination/'inventory.json').write_text(json.dumps({'python':sys.version,'dependencies':inventory},indent=2))
    if (ROOT/'packaging/exam-distribution.json').exists():shutil.copyfile(ROOT/'packaging/exam-distribution.json',destination/'exam-distribution.json')
    (destination/'README.txt').write_text('Application-authored source: MIT.\nCombined distribution includes PyMuPDF/MuPDF under AGPL-3.0 unless separately commercially licensed.\nSee PyMuPDF/COPYING and distribution-licensing.md. This binary is not MIT-only.\nCambridge exam and mark scheme PDFs are separate copyrighted data, not relicensed by MIT or AGPL.\n')

def source_archive(destination):
    try:
        paths=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT,stderr=subprocess.DEVNULL).decode().split('\0')
    except (subprocess.CalledProcessError,FileNotFoundError):
        paths=[str(p.relative_to(ROOT)) for folder in ['app','native','scripts','packaging','tests','docs','schemas','indexes','examples','.github'] for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
        paths += ['README.md','LICENSE','requirements.txt','requirements-build.txt','.gitignore','启动.command']
    with tarfile.open(destination,'w:gz') as archive:
        for relative in sorted(set(paths)):
            if not relative:continue
            allowed_prefixes=('app/','native/','scripts/','packaging/','tests/','docs/','schemas/','indexes/','examples/','.github/')
            allowed_files={'README.md','LICENSE','requirements.txt','requirements-build.txt','.gitignore','启动.command'}
            if not relative.startswith(allowed_prefixes) and relative not in allowed_files:continue
            p=ROOT/relative
            if not p.is_file() or p.suffix.lower() in ['.pdf','.dmg','.webp','.sqlite3','.p12','.p8']:continue
            if relative.startswith(('sources/','data/','question_bank/','dist/','build/','.git/')):continue
            archive.add(p,arcname='chemistry-workspace/'+relative,recursive=False)

def sign_bundle(app,identity,internal):
    # PyInstaller already signs its nested Mach-O binaries. Re-sign nested bundle after copying,
    # then outer executable/app, inside out; never depend on codesign --deep to discover code.
    helper=app/'Contents/Helpers/QuestionBackend.app'
    common=['/usr/bin/codesign','--force','--sign',identity]
    if not internal:common+=['--timestamp','--options','runtime']
    run(common+['--entitlements',ROOT/'packaging/backend.entitlements.plist',helper])
    run(common+[app/'Contents/MacOS/QuestionSpace'])
    run(common+['--entitlements',ROOT/'packaging/app.entitlements.plist',app])
    run(['/usr/bin/codesign','--verify','--deep','--strict','--verbose=2',app])

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version',default='0.2.0')
    parser.add_argument('--exam-source-dir',type=Path,default=ROOT/'sources')
    parser.add_argument('--output',type=Path,default=ROOT/'dist')
    parser.add_argument('--sign-identity',default=os.environ.get('CODESIGN_IDENTITY'))
    parser.add_argument('--skip-dmg',action='store_true')
    args=parser.parse_args()
    if sys.platform!='darwin' or platform.machine()!='arm64':raise SystemExit('Build on an Apple Silicon macOS host. Cross-compilation is not supported.')
    if sys.version_info<(3,11):raise SystemExit('Build requires Python 3.11+; end users do not need Python.')
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    work=ROOT/'build/macos';work.mkdir(parents=True,exist_ok=True)
    internal=not args.sign_identity;identity=args.sign_identity or '-'
    env=dict(os.environ,APP_VERSION=args.version,MACOSX_DEPLOYMENT_TARGET='13.0')
    if args.sign_identity:env['CODESIGN_IDENTITY']=args.sign_identity
    run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--distpath',work/'pyinstaller-dist','--workpath',work/'pyinstaller-work',ROOT/'packaging/backend.spec'],env=env,cwd=ROOT)
    app=output/'题间.app'
    if app.exists():
        # Never remove the previous artifact: keep a recoverable build under the ignored work directory.
        previous=work/('previous-app-'+str(time.time_ns())+'.app');shutil.move(app,previous)
    (app/'Contents/MacOS').mkdir(parents=True);(app/'Contents/Resources').mkdir();(app/'Contents/Helpers').mkdir()
    shutil.copytree(work/'pyinstaller-dist/QuestionBackend.app',app/'Contents/Helpers/QuestionBackend.app',symlinks=True)
    resources=app/'Contents/Resources/workspace';resources.mkdir()
    for folder in ['indexes','schemas']:shutil.copytree(ROOT/folder,resources/folder)
    (resources/'app').mkdir()
    for name in ['index.html','app.js','style.css','tokens.css']:shutil.copyfile(ROOT/'app'/name,resources/'app'/name)
    exams=collect_exams(args.exam_source_dir,resources/'bundled-sources')
    build_info={'version':args.version,'architecture':'arm64','distribution':'internal-adhoc' if internal else 'developer-id','notarized':False,'includes_cambridge_pdfs':True,'exam_files':exams,'runtime_python':platform.python_version()}
    (resources/'build-info.json').write_text(json.dumps(build_info,indent=2))
    notices(resources/'licenses')
    source=output/f'ChemistryWorkspace-{args.version}-AppSource.tar.gz';source_archive(source)
    shutil.copyfile(source,resources/'licenses/AppSource.tar.gz')
    credits='<html><meta charset="utf-8"><body><h2>题间 '+args.version+'</h2><p>'+('内部测试 · Ad-hoc 签名 · 未经 Apple 公证' if internal else 'Developer ID 签名；公证状态以随包验证报告为准')+'</p><p>源码 MIT；PyMuPDF/MuPDF 为 AGPL-3.0 或商业许可。完整许可及对应源代码说明位于 Resources/workspace/licenses。</p><p>Cambridge 试卷与评分标准版权归原权利人，软件许可不授予考试资料再分发权。</p></body></html>'
    (app/'Contents/Resources/Credits.html').write_text(credits)
    plist={'CFBundleExecutable':'QuestionSpace','CFBundleIdentifier':'com.mither.chemistry-workspace','CFBundleName':'题间','CFBundleDisplayName':'题间（内部测试）' if internal else '题间','CFBundlePackageType':'APPL','CFBundleVersion':args.version,'CFBundleShortVersionString':args.version,'LSMinimumSystemVersion':'13.0','NSHighResolutionCapable':True,'NSAppTransportSecurity':{'NSAllowsLocalNetworking':True},'QuestionSpaceDistribution':build_info['distribution'],'NSHumanReadableCopyright':'App source © 2026 mither11280. Includes AGPL-3.0 PyMuPDF/MuPDF and separately copyrighted Cambridge materials.'}
    (app/'Contents/Info.plist').write_bytes(plistlib.dumps(plist))
    run(['/usr/bin/xcrun','swiftc','-target','arm64-apple-macosx13.0','-O','-module-cache-path',work/'swift-cache',ROOT/'native/main.swift','-o',app/'Contents/MacOS/QuestionSpace','-framework','Cocoa','-framework','WebKit'])
    sign_bundle(app,identity,internal)
    run([sys.executable,ROOT/'scripts/audit_macos_bundle.py',app,'--report',output/'bundle-audit.json'])
    if not args.skip_dmg:
        staging=work/('dmg-stage-'+str(time.time_ns()));staging.mkdir()
        shutil.copytree(app,staging/'题间.app',symlinks=True)
        (staging/'Applications').symlink_to('/Applications',target_is_directory=True)
        (staging/'安装说明.txt').write_text('将「题间.app」拖到 Applications，再从应用程序打开。\n无需 Python、pip、Swift 或 Xcode。\n'+('此包为内部测试，ad-hoc 签名，未经 Apple 公证。Gatekeeper 可能阻止首次打开；它不是正式签名发行版。\n' if internal else 'Developer ID 包须完成随附公证流程后发布。\n')+'用户数据位于 ~/Library/Application Support/ChemistryWorkspace；更新时只替换 App，不删除用户目录。\n软件含 AGPL 组件和单独版权的 Cambridge 真题；详见应用「关于」与许可目录。\n')
        name=f'ChemistryWorkspace-{args.version}-arm64'+('-INTERNAL-UNNOTARIZED' if internal else '')+'.dmg'
        dmg=output/name
        if dmg.exists():shutil.move(dmg,work/(str(time.time_ns())+'-'+name))
        run(['/usr/bin/hdiutil','create','-volname','题间 Internal Test' if internal else '题间','-srcfolder',staging,'-format','UDZO','-ov',dmg])
        if not internal:run(['/usr/bin/codesign','--force','--sign',identity,'--timestamp',dmg])
        run(['/usr/bin/hdiutil','verify',dmg])
        (output/(name+'.sha256')).write_text(digest(dmg)+'  '+name+'\n')
    print('Built self-contained app:',app,flush=True)
if __name__=='__main__':main()
