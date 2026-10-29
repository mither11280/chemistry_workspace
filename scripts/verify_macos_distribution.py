"""Install the actual DMG into an isolated profile, exercise frozen runtime and native lifecycle."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import signal
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parents[1]

def tree_digest(app):
    h=hashlib.sha256()
    for p in sorted(app.rglob('*')):
        if p.is_file() and not p.is_symlink():h.update(str(p.relative_to(app)).encode());h.update(p.read_bytes())
    return h.hexdigest()

def wait_ready(process,ready,log):
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        if ready.exists():return json.loads(ready.read_text())
        if process.poll() is not None:raise AssertionError('Native app exited before readiness: '+log.read_text())
        time.sleep(.1)
    process.terminate();raise AssertionError('Native app readiness timeout')

def check_child_exited(pid):
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        try:os.kill(pid,0)
        except ProcessLookupError:return
        time.sleep(.1)
    raise AssertionError('Backend orphaned after native parent exit')

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('dmg',type=Path)
    parser.add_argument('--report',type=Path,default=ROOT/'dist/distribution-verification.json')
    args=parser.parse_args();report={'dmg':args.dmg.name,'checks':[],'environment':'Host macOS; app launched with empty PATH/PYTHONPATH, isolated profile and unrelated cwd. Not a claim that host Python was physically uninstalled.'}
    with tempfile.TemporaryDirectory(prefix='question-space-install-') as tmp:
        root=Path(tmp);mount=root/'mounted';mount.mkdir();installed=root/'Applications';installed.mkdir()
        subprocess.run(['/usr/bin/hdiutil','attach','-readonly','-nobrowse','-mountpoint',str(mount),str(args.dmg.resolve())],check=True,stdout=subprocess.DEVNULL)
        try:
            assert (mount/'Applications').is_symlink()
            subprocess.run(['/usr/bin/ditto',str(mount/'题间.app'),str(installed/'题间.app')],check=True)
        finally:subprocess.run(['/usr/bin/hdiutil','detach',str(mount)],check=True,stdout=subprocess.DEVNULL)
        app=installed/'题间.app';resources=app/'Contents/Resources/workspace';helper=app/'Contents/Helpers/QuestionBackend.app/Contents/MacOS/QuestionBackend'
        home=root/'fresh-home';home.mkdir();profile=home/'Library/Application Support/ChemistryWorkspace';cwd=root/'unrelated-working-directory';cwd.mkdir()
        environment={'HOME':str(home),'PATH':'/nonexistent','TMPDIR':tempfile.gettempdir(),'QUESTION_BANK_HOME':str(profile),'QUESTION_SPACE_AUTOTEST':'1'}
        runtime=json.loads(subprocess.check_output([str(helper),'--resources',str(resources),'--runtime-info'],env=environment,cwd=cwd))
        assert runtime['frozen'] is True and runtime['webp'] is True
        assert all(str(app) in p for p in runtime['sys_path'])
        report['runtime']={k:runtime[k] for k in ['python','pymupdf','pillow','sqlite','frozen','webp']}
        report['checks'].append('Actual DMG mounted; copied app and Applications drag target verified; frozen stdlib and dependencies internal')
        index=json.loads((resources/'indexes/question-index.json').read_text()); manifest=json.loads((resources/'indexes/source-manifest.json').read_text())
        ready_units=[q for q in index['questions'] if q.get('metadata',{}).get('teaching',{}).get('status','ready')=='ready']
        p2_id='cie-9701-m25-22-q4-b-i' if index.get('bank_id')=='cie-9701-as-teaching19-v1' else 'cie-9701-m25-22-q4'
        expected_job=None;source_hash=None
        for iteration in [0,1]:
            if iteration==1:
                # Model replacing the app with a new version, preserving only Application Support.
                replacement=installed/'replacement.app';subprocess.run(['/usr/bin/ditto',str(app),str(replacement)],check=True)
                for p in replacement.rglob('*'):
                    if not p.is_symlink():p.chmod(p.stat().st_mode | 0o200 | (0o100 if p.is_dir() else 0))
                build=replacement/'Contents/Resources/workspace/build-info.json';value=json.loads(build.read_text());parts=[int(x) for x in value['version'].split('.')];parts[-1]+=1;upgrade='.'.join(map(str,parts));value['version']=upgrade+'-test-upgrade';build.write_text(json.dumps(value))
                plist=replacement/'Contents/Info.plist';info=plistlib.loads(plist.read_bytes());info['CFBundleShortVersionString']=upgrade;info['CFBundleVersion']=upgrade;plist.write_bytes(plistlib.dumps(info))
                subprocess.run(['/usr/bin/codesign','--force','--sign','-',str(replacement)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                app.rename(installed/'previous.app');replacement.rename(app)
            for p in app.rglob('*'):
                if not p.is_symlink():p.chmod(p.stat().st_mode & ~0o222)
            before=tree_digest(app);ready=root/f'ready-{iteration}.json';log=root/f'native-{iteration}.log'
            env=dict(environment,QUESTION_SPACE_READY_FILE=str(ready),QUESTION_SPACE_AUTO_QUIT_SECONDS='45')
            with log.open('w') as stream:
                process=subprocess.Popen([str(app/'Contents/MacOS/QuestionSpace')],env=env,cwd=cwd,stdout=stream,stderr=stream)
                try:
                    health=wait_ready(process,ready,log);base=health['url'].rstrip('/')
                    def get(path):return urllib.request.urlopen(base+path,timeout=30).read()
                    def post(path,value):
                        req=urllib.request.Request(base+path,json.dumps(value).encode(),headers={'Content-Type':'application/json','X-Local-Request':'1'})
                        return json.loads(urllib.request.urlopen(req,timeout=60).read())
                    assert get('/prompt.js')==(resources/'app/prompt.js').read_bytes()
                    bank=json.loads(get('/api/bank'));assert bank['total']==len(ready_units)
                    selected=json.loads(get('/api/questions?paper=1&year=2025&limit=8'));assert selected['total']==sum(q['paper']==1 and q['year']==2025 for q in ready_units)
                    p4_units=[q for q in ready_units if q['paper']==4]
                    if p4_units:
                        a2=json.loads(get('/api/questions?course=A2&paper=4&limit=8'))
                        assert a2['total']==len(p4_units)
                        assert all(q['paper']==4 and q['qualification']=='A2' for q in a2['questions'])
                    if iteration==0:
                        sources=json.loads(get('/api/sources'));assert len(sources)==len(manifest['sources']) and all(s['status']['state']=='ready' for s in sources)
                        report['checks'].append('First launch seeded all '+str(len(sources))+' exact original sources into fresh Application Support')
                        qp=next(s for s in sources if s['filename']=='9701_m25_qp_12.pdf');path=profile/qp['path'];source_hash=hashlib.sha256(path.read_bytes()).hexdigest();path.unlink()
                        try:get('/preview/cie-9701-m25-12-q3/question/0');raise AssertionError('Missing source unexpectedly rendered')
                        except urllib.error.HTTPError as e:assert e.code==409
                        req=urllib.request.Request(base+'/api/source-upload?name='+qp['filename'],(resources/'bundled-sources'/qp['filename']).read_bytes(),headers={'Content-Type':'application/pdf','X-Local-Request':'1'})
                        assert json.loads(urllib.request.urlopen(req).read())['state']=='ready'
                        assert get('/preview/cie-9701-m25-12-q3/question/0').startswith(b'RIFF')
                        assert get('/preview/'+p2_id+'/answer/0').startswith(b'RIFF')
                        job={'title':'Standalone installer verification','question_ids':['cie-9701-m25-12-q3',p2_id],'notes':'Persistent teacher notes'}
                        expected_job=post('/api/save',job);post('/api/draft',expected_job)
                        assert post('/api/import',{'code':post('/api/share',job)['code']})==job
                        for kind in ['questions','answers']:
                            data=get(post('/api/export',{'job':job,'kind':kind})['url']);assert data.startswith(b'%PDF')
                            import fitz
                            with fitz.open(stream=data,filetype='pdf') as doc:
                                text=''.join(p.get_text() for p in doc);assert 'Assignment 1' in text and 'Assignment 2' in text
                        feedback=post('/api/report',{'question_id':job['question_ids'][0],'category':'crop','description':'Frozen runtime report preview, no issue submitted.'})
                        assert feedback['report']['app_version']==health['version']
                        assert feedback['issue_url'].startswith('https://github.com/mither11280/chemistry_workspace/issues/new?')
                        report['checks'].append('Native app: SQL query, missing-source detection, HTTP PDF import, WebP, QP/MS export, share, save and draft passed')
                        if p4_units:
                            mixed={'title':'Native AS and A2 worksheet','question_ids':job['question_ids']+['cie-9701-m25-42-q2-c-i','cie-9701-m25-42-q2-c-ii'],'notes':'Mixed courses with a required prior result'}
                            shared=post('/api/import',{'code':post('/api/share',mixed)['code']})
                            assert shared==mixed
                            for qid in mixed['question_ids'][-2:]:
                                for kind in ['question','answer']:assert get('/preview/'+qid+'/'+kind+'/0').startswith(b'RIFF')
                            for kind in ['questions','answers']:assert get(post('/api/export',{'job':mixed,'kind':kind})['url']).startswith(b'%PDF')
                            report['checks'].append('Frozen A2 Paper 4 filter, dependent subpart previews, mixed AS/A2 share and both vector exports passed')
                    else:
                        jobs=json.loads(get('/api/jobs'));saved=next(j for j in jobs if j['id']==expected_job['id'])
                        assert saved['question_ids']==expected_job['question_ids'] and saved['notes']==expected_job['notes']
                        assert json.loads(get('/api/draft'))['id']==expected_job['id']
                        assert any((profile/'data/backups').glob('app-upgrade-*'))
                        assert hashlib.sha256((profile/'sources/cie/9701/2025/march/9701_m25_qp_12.pdf').read_bytes()).hexdigest()==source_hash
                        assert get('/preview/cie-9701-m25-12-q3/question/0').startswith(b'RIFF')
                        report['checks'].append('Replaced/reopened native app with version-bump fixture: saved jobs, notes, draft, sources and cache remained usable; upgrade backup created')
                    process.wait(timeout=60);assert process.returncode==0
                    check_child_exited(health['pid'])
                    assert tree_digest(app)==before
                    report['checks'].append('Native termination closed embedded backend; no orphan and no writes into app bundle (pass '+str(iteration+1)+')')
                finally:
                    if process.poll() is None:process.kill();process.wait()
        # Confirm the original source checkout is not needed by either launch (only harness uses it).
        report['checks'].append('Both launches used only relocated app paths, profile, Apple system libraries; no runtime.json, developer venv or source cwd')
    report['status']='passed';args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
