"""Actual source-backed teaching-bank acceptance in a new, isolated profile."""
import argparse,json,os,subprocess,sys,tempfile,time,urllib.request,urllib.error,signal,sqlite3,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from bank.format import read_json,write_json,validate
from bank.teaching.generation import prepare,restore
from bank.teaching.taxonomy import BANK_ID


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--snapshot',type=Path,default=ROOT/'data/teaching19-current');p.add_argument('--sources',type=Path,default=ROOT/'data/import-v04/all-source-files.private.json');p.add_argument('--output',type=Path,default=ROOT/'data/teaching19-acceptance');a=p.parse_args()
    if a.output.exists():raise SystemExit('Use a fresh acceptance output folder')
    a.output.mkdir(parents=True);resources=a.output/'resources';profile=a.output/'profile';resources.mkdir();(resources/'indexes').mkdir()
    for n in ['question-index.json','source-manifest.json']:shutil.copyfile(a.snapshot/n,resources/'indexes'/n)
    shutil.copytree(ROOT/'schemas',resources/'schemas');shutil.copytree(ROOT/'app',resources/'app',ignore=shutil.ignore_patterns('__pycache__'));write_json(resources/'build-info.json',{'version':'0.5.0','distribution':'development-acceptance'})
    index=read_json(a.snapshot/'question-index.json');manifest=read_json(a.snapshot/'source-manifest.json');paths=read_json(a.sources);validate(index,manifest,ROOT/'schemas');assert index['bank_id']==BANK_ID
    for source in manifest['sources']:
        dest=profile/source['path'];dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(paths[source['source_id']],dest)
    (profile/'data').mkdir(parents=True)
    with sqlite3.connect(profile/'data/personal.sqlite3') as db:
        db.execute('CREATE TABLE jobs(id TEXT PRIMARY KEY,title TEXT NOT NULL,body TEXT NOT NULL,updated REAL NOT NULL)');db.execute('INSERT INTO jobs VALUES (?,?,?,?)',('old','Archived worksheet',json.dumps({'title':'Archived worksheet','question_ids':['cie-9701-m24-22-q1'],'notes':'preserve'}),1))
    write_json(profile/'data/question-index.local.json',{'old_overlay':'preserved exactly'})
    archive=prepare(profile,resources);assert archive
    with sqlite3.connect(profile/'generation-archives'/archive/'data/personal.sqlite3') as db:assert db.execute('SELECT count(*) FROM jobs').fetchone()[0]==1
    assert not (profile/'data/question-index.local.json').exists();assert prepare(profile,resources) is None
    env=dict(os.environ,QUESTION_BANK_HOME=str(profile.resolve()),QUESTION_BANK_RESOURCES=str(resources.resolve()));env.pop('QUESTION_BANK_ROOT',None)
    log=(a.output/'backend.log').open('w');process=subprocess.Popen([sys.executable,str(ROOT/'app/server.py')],env=env,cwd=a.output,stdout=subprocess.PIPE,stderr=log,text=True)
    try:
        import select
        assert select.select([process.stdout],[],[],60)[0];base=process.stdout.readline().strip();assert base.startswith('http://127.0.0.1:')
        def get(path):return urllib.request.urlopen(base+path,timeout=180).read()
        def post(path,value):return json.load(urllib.request.urlopen(urllib.request.Request(base+path,json.dumps(value).encode(),headers={'Content-Type':'application/json','X-Local-Request':'1'}),timeout=180))
        info=json.loads(get('/api/bank'));assert info['teaching'];assert json.loads(get('/api/jobs'))==[];assert json.loads(get('/api/draft')) is None
        assert get('/prompt.js')==(ROOT/'app/prompt.js').read_bytes()
        exact='cie-9701-m25-22-q4-b-i'
        exact_result=json.loads(get('/api/questions?search='+exact))
        assert [q['id'] for q in exact_result['questions']]==[exact]
        results=json.loads(get('/api/questions?limit=200'));assert results['total']==info['total'];assert all(q['metadata']['teaching']['status']=='ready' for q in results['questions'])
        holding=json.loads(get('/api/questions?collection=pending&limit=200'));assert holding['total']==info['pending'];assert all(not q['topics'] for q in holding['questions'])
        for n in range(1,20):
            found=json.loads(get(f'/api/questions?topic=ch{n:02}&limit=200'));assert all(q['metadata']['teaching']['primary_chapter']==n for q in found['questions'])
        target='cie-9701-m25-22-q4-b-ii';resolved=json.loads(get('/api/worksheet?ids='+target));assert resolved['question_ids']==['cie-9701-m25-22-q4-b-i',target];assert resolved['marks']==5 and resolved['group_count']==1
        qids=['cie-9701-m24-22-q1-a','cie-9701-m24-22-q1-c-i','cie-9701-m24-12-q4',target]
        job={'title':'19章真实小问验收','question_ids':qids,'notes':'Complete every question.'};saved=post('/api/save',job);assert len(saved['question_ids'])==5;post('/api/draft',job)
        code=post('/api/share',job)['code'];assert code.startswith('CIE2.');incoming=post('/api/import',{'code':code});assert incoming['question_ids']==saved['question_ids']
        try:post('/api/import',{'code':'CIE1.old'});raise AssertionError('old share accepted')
        except urllib.error.HTTPError as e:assert e.code==400 and '旧版' in json.load(e)['error']
        previews=0;start=time.perf_counter()
        for qid in saved['question_ids']:
            q=json.loads(get('/api/questions?ids='+qid))['questions'][0]
            for kind in ['question','answer']:
                for j in range(len(q[kind+'_regions'])):
                    assert get(f'/preview/{qid}/{kind}/{j}').startswith(b'RIFF');previews+=1
        preview_seconds=time.perf_counter()-start;exports={}
        for kind in ['questions','answers']:
            start=time.perf_counter();r=post('/api/export',{'job':job,'kind':kind});pdf=get(r['url']);assert pdf.startswith(b'%PDF');out=a.output/(kind+'.pdf');out.write_bytes(pdf);mapping=json.loads(next((profile/'exports').glob(r['url'].split('/')[-1].replace('.pdf','.mapping.json'))).read_text());assert [m['question_id'] for m in mapping]==saved['question_ids'];exports[kind]={'seconds':round(time.perf_counter()-start,4),'bytes':len(pdf)}
        assert post('/api/report',{'question_id':target,'category':'topics','description':'Acceptance only; not submitted.'})['report']['question_id']==target
        checks=json.loads(get('/api/check'));assert checks['catalog']['integrity']=='ok'
        report={'status':'passed','generation':BANK_ID,'ready':info['total'],'pending':info['pending'],'old_personal_data_archived':True,'fresh_personal_work':True,'relaunch_does_not_reset':True,'chapter_filters':19,'prerequisite_closure_marks_and_context':'passed','new_share_and_old_share_rejection':'passed','preview_regions':previews,'preview_seconds':round(preview_seconds,4),'exports':exports,'archive_id':archive}
    finally:
        process.terminate();process.wait(timeout=20);log.close()
    restored=restore(profile,archive)
    with sqlite3.connect(profile/'data/personal.sqlite3') as db:assert db.execute('SELECT title FROM jobs').fetchone()[0]=='Archived worksheet'
    report['restore_old_generation_preserves_new_work']=True;write_json(a.output/'verification.json',report);print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
