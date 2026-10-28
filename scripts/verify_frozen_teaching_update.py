"""Exercise the released teaching asset bundle through the frozen backend, in isolation."""
import argparse,json,os,select,signal,subprocess,tempfile,time,urllib.request,urllib.error,zipfile
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--app',type=Path,required=True);p.add_argument('--package',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--expected-version',default='0.5.0');a=p.parse_args()
    app=a.app.resolve();res=app/'Contents/Resources/workspace';helper=app/'Contents/Helpers/QuestionBackend.app/Contents/MacOS/QuestionBackend'
    initial=json.loads((res/'indexes/question-index.json').read_text())
    with zipfile.ZipFile(a.package) as z:target=json.loads(z.read('question-index.json'))
    assert initial['bank_id']==target['bank_id']=='cie-9701-as-teaching19-v1'
    expected=sum(q['metadata']['teaching']['status']=='ready' for q in target['questions'])
    with tempfile.TemporaryDirectory(prefix='frozen-teaching-') as tmp:
        root=Path(tmp);profile=root/'profile';home=root/'home';home.mkdir()
        env={'HOME':str(home),'PATH':'/nonexistent','PYTHONPATH':'','TMPDIR':tempfile.gettempdir()}
        with (root/'backend.log').open('w') as log:
            proc=subprocess.Popen([str(helper),'--resources',str(res),'--user-root',str(profile),'--parent-pid',str(os.getpid())],cwd=root,env=env,stdout=subprocess.PIPE,stderr=log,text=True)
            try:
                assert select.select([proc.stdout],[],[],90)[0];base=proc.stdout.readline().strip();assert base.startswith('http://127.0.0.1:')
                def get(path):return urllib.request.urlopen(base+path,timeout=240).read()
                def post(path,value):return json.load(urllib.request.urlopen(urllib.request.Request(base+path,json.dumps(value).encode(),headers={'Content-Type':'application/json','X-Local-Request':'1'}),timeout=240))
                assert json.loads(get('/api/health'))['version']==a.expected_version
                bank=json.loads(get('/api/bank'));assert bank['total']==expected and bank['teaching']
                assert get('/prompt.js')==(res/'app/prompt.js').read_bytes()
                job={'title':'Frozen 19 chapter update','question_ids':['cie-9701-m18-12-q31','cie-9701-m25-22-q4-b-ii'],'notes':'Preserve teacher notes'}
                saved=post('/api/save',job);post('/api/draft',saved);code=post('/api/share',saved)['code'];assert code.startswith('CIE2.')
                personal=profile/'data/personal.sqlite3';before=personal.read_bytes()
                request=urllib.request.Request(base+'/api/bank-update-upload',a.package.read_bytes(),headers={'Content-Type':'application/octet-stream','X-Local-Request':'1'})
                preview=json.load(urllib.request.urlopen(request,timeout=240));assert json.loads(get('/api/bank'))['revision']==initial['revision']
                start=time.perf_counter();installed=post('/api/bank-update-install',{'token':preview['token'],'sha256':preview['sha256']});elapsed=time.perf_counter()-start
                assert personal.read_bytes()==before
                bank=json.loads(get('/api/bank'));assert bank['revision']==target['revision'] and bank['total']==expected
                assert post('/api/import',{'code':code})['question_ids']==saved['question_ids']
                assert json.loads(get('/api/draft'))['question_ids']==saved['question_ids']
                assert next(j for j in json.loads(get('/api/jobs')) if j['id']==saved['id'])['notes']==job['notes']
                for qid in saved['question_ids']:
                    assert get('/preview/'+qid+'/question/0').startswith(b'RIFF');assert get('/preview/'+qid+'/answer/0').startswith(b'RIFF')
                for kind in ['questions','answers']:assert get(post('/api/export',{'job':saved,'kind':kind})['url']).startswith(b'%PDF')
                check=json.loads(get('/api/check'));assert check['catalog']['integrity']=='ok';assert all(s['state']=='ready' for s in check['sources'])
                try:post('/api/import',{'code':'CIE1.old'});raise AssertionError('Old generation silently accepted')
                except urllib.error.HTTPError as e:assert e.code==400 and '旧版' in json.load(e)['error']
                result={'status':'passed','app_version':a.expected_version,'bank_id':bank['bank_id'],'revision':bank['revision'],'ready':bank['total'],'pending':bank['pending'],'source_files':len(check['sources']),'install_seconds':round(elapsed,4),'personal_db_byte_identical':True,'dependency_share_draft_and_ms_export':'passed','old_share_rejected':True,'prompt_js_bundled':True,'environment':'Frozen backend, empty PATH/PYTHONPATH, isolated profile and unrelated cwd.'}
                a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))
            finally:
                if proc.poll() is None:proc.send_signal(signal.SIGTERM)
                try:proc.wait(timeout=15)
                except subprocess.TimeoutExpired:proc.kill();proc.wait();raise

if __name__=='__main__':main()
