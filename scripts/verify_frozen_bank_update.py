"""Exercise a cumulative bank update through the actual frozen backend HTTP boundary."""
from pathlib import Path
import argparse,json,os,select,signal,subprocess,tempfile,time,urllib.request


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--app',type=Path,required=True);p.add_argument('--package',type=Path,required=True);p.add_argument('--report',type=Path,required=True);args=p.parse_args()
    app=args.app.resolve();resources=app/'Contents/Resources/workspace';helper=app/'Contents/Helpers/QuestionBackend.app/Contents/MacOS/QuestionBackend'
    with tempfile.TemporaryDirectory(prefix='frozen-history-') as temp:
        root=Path(temp);profile=root/'profile';home=root/'home';home.mkdir();log=root/'backend.log'
        env={'HOME':str(home),'PATH':'/nonexistent','PYTHONPATH':'','TMPDIR':tempfile.gettempdir()}
        with log.open('w') as error:
            process=subprocess.Popen([str(helper),'--resources',str(resources),'--user-root',str(profile),'--parent-pid',str(os.getpid())],env=env,cwd=root,stdout=subprocess.PIPE,stderr=error,text=True)
            try:
                ready,_,_=select.select([process.stdout],[],[],60)
                if not ready:raise RuntimeError('Frozen backend did not become ready')
                base=process.stdout.readline().strip()
                if not base.startswith('http://127.0.0.1:'):raise RuntimeError('Frozen backend failed: '+log.read_text())
                def get(path):return urllib.request.urlopen(base+path,timeout=180).read()
                def post(path,value):
                    request=urllib.request.Request(base+path,json.dumps(value).encode(),headers={'Content-Type':'application/json','X-Local-Request':'1'})
                    return json.loads(urllib.request.urlopen(request,timeout=240).read())
                assert json.loads(get('/api/health'))['version']=='0.4.0';assert json.loads(get('/api/bank'))['total']==132
                job={'title':'Frozen historical bank update','question_ids':['cie-9701-m25-12-q3','cie-9701-m25-22-q4'],'notes':'Authored persistence check'}
                saved=post('/api/save',job);post('/api/draft',job);code=post('/api/share',job)['code'];personal=profile/'data/personal.sqlite3';before=personal.read_bytes()
                request=urllib.request.Request(base+'/api/bank-update-upload',args.package.read_bytes(),headers={'Content-Type':'application/octet-stream','X-Local-Request':'1'})
                preview=json.loads(urllib.request.urlopen(request,timeout=180).read());assert json.loads(get('/api/bank'))['total']==132
                start=time.perf_counter();installed=post('/api/bank-update-install',{'token':preview['token'],'sha256':preview['sha256']});seconds=time.perf_counter()-start
                assert personal.read_bytes()==before;assert installed['questions']==2523
                bank=json.loads(get('/api/bank'));assert bank['total']==2523 and 2018 in bank['years']
                old=json.loads(get('/api/questions?ids=cie-9701-m18-12-q31'))['questions'][0];assert old['metadata']['shared_context_regions']==1 and old['metadata']['current_syllabus']['compatibility']=='unknown'
                assert get('/preview/cie-9701-m18-12-q31/question/0').startswith(b'RIFF');assert get('/preview/cie-9701-m18-12-q31/question/1').startswith(b'RIFF');assert get('/preview/cie-9701-m18-22-q1/answer/0').startswith(b'RIFF')
                assert post('/api/import',{'code':code})==job
                assert json.loads(get('/api/draft'))==job
                assert next(q for q in json.loads(get('/api/jobs')) if q['id']==saved['id'])['notes']==job['notes']
                report=post('/api/report',{'question_id':'cie-9701-m18-12-q31','category':'topics','description':'Frozen bank acceptance only; no issue submitted.'});assert report['report']['bank_revision']==bank['revision']
                mixed={'title':'Frozen mixed historical export','notes':'','question_ids':['cie-9701-m18-12-q31','cie-9701-m18-22-q1','cie-9701-s26-21-q1']}
                for kind in ['questions','answers']:assert get(post('/api/export',{'job':mixed,'kind':kind})['url']).startswith(b'%PDF')
                checks=json.loads(get('/api/check'));assert checks['catalog']['integrity']=='ok';assert all(s['state']=='ready' for s in checks['sources'])
                result={'status':'passed','app_version':'0.4.0','bank_revision':bank['revision'],'questions':bank['total'],'sources':len(checks['sources']),'install_plus_text_extract_seconds':round(seconds,4),'personal_db_byte_identical_during_install':True,'old_share_code_and_jobs_preserved':True,'legacy_context_and_rotated_ms_previews':'passed','question_and_ms_http_export':'passed','report_prefill':'passed, no issue submitted','environment':'Actual frozen backend with empty PATH/PYTHONPATH, unrelated cwd and isolated profile; no developer runtime used by backend.'}
                args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))
            finally:
                if process.poll() is None:process.send_signal(signal.SIGTERM)
                try:process.wait(timeout=15)
                except subprocess.TimeoutExpired:process.kill();process.wait();raise
if __name__=='__main__':main()
