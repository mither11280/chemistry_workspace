#!/usr/bin/env python3
"""Package and verify the actual licensed expansion in disposable profiles, without touching user state."""
from pathlib import Path
import argparse,copy,csv,hashlib,json,shutil,sqlite3,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from bank.format import read_json,write_json,sha256,validate
from bank.catalog import Catalog
from bank.sources import SourceStore
from bank.render import Renderer
from bank.updates import build_package,install_package,rollback


def snapshot(path):return read_json(path/'question-index.json'),read_json(path/'source-manifest.json')

def seed_personal(home,ids):
    data=home/'data';data.mkdir(parents=True,exist_ok=True);path=data/'personal.sqlite3'
    job={'title':'Historical expansion persistence test','question_ids':ids,'notes':'Authored private teacher note'}
    with sqlite3.connect(path) as c:
        c.execute('CREATE TABLE jobs(id TEXT PRIMARY KEY,title TEXT NOT NULL,body TEXT NOT NULL,updated REAL NOT NULL)')
        c.execute('CREATE TABLE draft(slot INTEGER PRIMARY KEY,body TEXT NOT NULL)');c.execute('PRAGMA user_version=1')
        c.execute('INSERT INTO jobs VALUES (?,?,?,?)',('11111111-1111-1111-1111-111111111111',job['title'],json.dumps(job),1))
        c.execute('INSERT INTO draft VALUES (1,?)',(json.dumps(job),))
    return path,path.read_bytes(),job


def package(name,index,manifest,base,base_manifest,sources,rights,out):
    start=time.perf_counter();result=build_package(out/name,index,manifest,base,base_manifest,ROOT/'schemas','CIE 9701 2018–2026 expansion; only automatically validated questions, original PDFs immutable. See coverage and anomalies.',sources,rights,minimum_app_version='0.4.0')
    print('PACKAGED',name,result['bytes'],flush=True);return dict(result,seconds=round(time.perf_counter()-start,4))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--corpus',type=Path,required=True);p.add_argument('--workdir',type=Path,required=True);p.add_argument('--base',type=Path,required=True);p.add_argument('--authorization',type=Path,required=True);p.add_argument('--output',type=Path,default=ROOT/'dist/v04-bank');args=p.parse_args()
    work=args.workdir;out=args.output;out.mkdir(parents=True,exist_ok=True);base,base_manifest=snapshot(args.base);index,manifest=snapshot(work/'final');rights=read_json(args.authorization)
    # Exact content lookup, including existing 266 questions; no trust in filenames alone.
    candidates={}
    for row in read_json(work/'inventory/inventory.json')['rows']:
        for role in ['qp','ms']:
            for source in row['sources'][role]:candidates.setdefault(source['sha256'],args.corpus/source['relative_path'])
    sources={}
    for source in manifest['sources']:
        path=ROOT/source['path']
        if not path.is_file():path=candidates.get(source['sha256'])
        if path is None or not path.is_file() or sha256(path)!=source['sha256']:raise RuntimeError('Missing exact source: '+source['source_id'])
        sources[source['source_id']]=str(path)
    write_json(work/'all-source-files.private.json',sources)
    expected={s['sha256'] for s in manifest['sources']};assert expected<=set(rights['sha256'])
    validate(index,manifest,ROOT/'schemas');original_ids={q['question_id'] for q in base['questions']};final_ids={q['question_id'] for q in index['questions']};assert original_ids<=final_ids
    identity=lambda q:tuple(q[k] for k in ['exam_board','subject_code','year','session','paper','variant','original_question_number'])
    assert len({identity(q) for q in index['questions']})==len(index['questions'])
    for q in index['questions']:
        if q['question_id'] not in original_ids:assert q['metadata']['automatic_qa']['status']=='passed'
    profile=work/'acceptance-incremental'
    if profile.exists():raise RuntimeError('Use a fresh acceptance profile or archive previous acceptance directory')
    resources=work/'acceptance-resources';shutil.copytree(ROOT/'schemas',resources/'schemas',dirs_exist_ok=True)
    write_json(resources/'indexes/question-index.json',base);write_json(resources/'indexes/source-manifest.json',base_manifest)
    cat=Catalog(profile,resources=resources);store=SourceStore(profile,cat)
    for source in base_manifest['sources']:store.import_file(sources[source['source_id']],extract=False)
    ids=['cie-9701-m25-12-q3','cie-9701-m25-22-q4'];personal,before,job=seed_personal(profile,ids)
    old_q={q['question_id']:q for q in base['questions']};new_q={q['question_id']:q for q in index['questions']}
    assert all(all(old_q[qid][k]==new_q[qid][k] for k in ['question','answer','marks','topics']) for qid in original_ids)
    packages=[];installations=[];previous,previous_manifest=base,base_manifest
    for phase in ['modern','year2026','legacy']:
        next_index,next_manifest=snapshot(work/phase);phase_sources=read_json(work/phase/'source-files.private.json')
        info=package('ChemistryWorkspace-v04-'+phase+'.qbank',next_index,next_manifest,previous,previous_manifest,phase_sources,rights,out);packages.append(info)
        start=time.perf_counter();result=install_package(cat,info['path'],info['sha256']);installations.append(dict(result,seconds=round(time.perf_counter()-start,4)))
        assert personal.read_bytes()==before
        print('INSTALLED',phase,result['questions'],flush=True);previous,previous_manifest=next_index,next_manifest
    assert cat.index['revision']==index['revision'] and len(cat.index['questions'])==len(index['questions'])
    # A single cumulative package for existing v0.3 teachers, and one for fresh 132-question apps.
    for name,b,bm in [('from-266',base,base_manifest),('from-132',*snapshot(ROOT/'indexes'))]:
        info=package('ChemistryWorkspace-v04-full-'+name+'.qbank',index,manifest,b,bm,sources,rights,out);packages.append(info)
    fresh=work/'acceptance-cumulative';fresh_cat=Catalog(fresh,resources=ROOT);fresh_personal,fresh_before,_=seed_personal(fresh,ids)
    full=packages[-1];start=time.perf_counter();full_install=install_package(fresh_cat,full['path'],full['sha256']);assert fresh_personal.read_bytes()==fresh_before
    cumulative_seconds=round(time.perf_counter()-start,4);print('INSTALLED cumulative',len(fresh_cat.index['questions']),flush=True)
    start=time.perf_counter();store.extract_local_content();text_seconds=round(time.perf_counter()-start,4);renderer=Renderer(cat,store)
    chosen=[]
    for year in range(2018,2027):
        for paper in [1,2]:
            number='31' if paper==1 and year<=2021 else '1'
            q=next(q for q in index['questions'] if q['year']==year and q['session']=='March' and q['paper']==paper and q['original_question_number']==number)
            chosen.append(q['question_id'])
    chosen+=['cie-9701-s18-11-q1','cie-9701-s26-21-q1'];chosen=chosen[::-1];assert len(chosen)==len(set(chosen))==20
    preview_count=0
    start=time.perf_counter()
    for qid in chosen:
        q=cat.question(qid)
        for kind in ['question','answer']:
            for n in range(len(q[kind]['regions'])):assert renderer.preview(qid,kind,n).startswith(b'RIFF');preview_count+=1
    previews_seconds=round(time.perf_counter()-start,4)
    sample={'title':'Historical 2018–2026 acceptance','question_ids':chosen,'notes':'Authored mixed-year, reordered, twenty-question worksheet.'};exports={}
    for kind in ['questions','answers']:
        start=time.perf_counter();path=renderer.export(sample,kind,profile/'exports');mapping=read_json(path.with_suffix('.mapping.json'));assert [m['question_id'] for m in mapping]==chosen
        import fitz
        with fitz.open(path) as d:
            text='\n'.join(page.get_text() for page in d);assert 'Assignment 1' in text and 'Assignment 20' in text
            exports[kind]={'seconds':round(time.perf_counter()-start,4),'bytes':path.stat().st_size,'pages':len(d),'file':path.name}
    self_count=cat.search({'year':2018,'paper':1})['total'];assert self_count>0
    # Roll back one stage, preserve personal DB, restore exact stage without touching saved jobs.
    last=installations[-1];rolled=rollback(cat,last['backup_id']);assert rolled['revision']==installations[-2]['revision'];assert personal.read_bytes()==before
    install_package(cat,packages[2]['path'],packages[2]['sha256']);assert personal.read_bytes()==before
    # Source SHA-256 verification occurs in every resolver even when a thumbnail is cached.
    for source in manifest['sources']:assert store.status(source['source_id'])['state']=='ready'
    output={'schema_version':1,'bank_revision':index['revision'],'base_revision':base['revision'],'base_questions':len(base['questions']),'questions':len(index['questions']),'new_questions':len(final_ids-original_ids),'source_documents':len(manifest['sources']),'source_bytes':sum(Path(p).stat().st_size for p in sources.values()),'duplicate_question_ids':len(index['questions'])-len(final_ids),'duplicate_exam_identities':0,'existing_266_ids_materials_marks_topics_unchanged':True,'personal_databases_byte_identical':True,'incremental_installations':installations,'cumulative_install_seconds':cumulative_seconds,'rollback_and_reinstall_passed':True,'previews_rendered':preview_count,'previews_seconds':previews_seconds,'local_text_extract_seconds':text_seconds,'search_2018_p1_count':self_count,'exports':exports,'packages':[{k:v for k,v in info.items() if k!='path'} for info in packages],'limits':['Programmatic QA is not human content review or a statistical recognition-accuracy measurement.','Unmatched marks/answers remain quarantined; see anomaly report.','Current-syllabus compatibility is unknown for historical syllabus periods.','No third-party PDF download or real GitHub Issue submission occurred.']}
    write_json(work/'acceptance.json',output)
    for info in packages:
        path=Path(info['path']);path.with_suffix('.qbank.sha256').write_text(info['sha256']+'  '+path.name+'\n')
    print(json.dumps(output,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
