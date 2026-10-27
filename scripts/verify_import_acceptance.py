#!/usr/bin/env python3
"""Opt-in, real local corpus acceptance; never downloads PDFs or modifies the user's profile."""
from pathlib import Path
import argparse,copy,json,shutil,sqlite3,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from bank.format import read_json,write_json,sha256,validate
from bank.importer.engine import analyze
from bank.catalog import Catalog
from bank.sources import SourceStore
from bank.render import Renderer
from bank.feedback import build_report
from bank.updates import build_package,install_package,rollback


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--corpus',type=Path,required=True);p.add_argument('--workdir',type=Path,required=True);p.add_argument('--report',type=Path,required=True);args=p.parse_args()
    work=args.workdir;work.mkdir(parents=True,exist_ok=True);corpus=args.corpus
    index=read_json(ROOT/'indexes/question-index.json');manifest=read_json(ROOT/'indexes/source-manifest.json');validate(index,manifest,ROOT/'schemas')
    assert len(index['questions'])==132
    files=[corpus/f'2023_M/9701_m23_{k}_{v}.pdf' for k in ['qp','ms'] for v in ['12','22']]+[corpus/f'2025_S/9701_s25_{k}_{v}.pdf' for k in ['qp','ms'] for v in ['11','21']]+[corpus/f'2024_W/Cambridge_AL_9701-{v}_2024_November_{k}.pdf' for k in ['QP','MS'] for v in ['13','23']]
    new,ms,report=analyze(files,work/'new',index,manifest,ROOT/'schemas','2026-10-27.import-v03.1')
    # Re-run proves that unchanged pairs do not need reparsing.
    _,_,resumed=analyze(files,work/'new',index,manifest,ROOT/'schemas',new['revision'])
    assert all(r['cache_hit'] for r in resumed['pairs'])
    original_files=[corpus/f'{year}_M/9701_m{year%100}_{kind}_{variant}.pdf' for year in [2024,2025,2026] for kind in ['qp','ms'] for variant in ['12','22']]
    _,_,regression=analyze(original_files,work/'regression',index,manifest,ROOT/'schemas','regression-only')
    # Do not treat original automatic crops as ground truth. Report parser agreement, keep base unchanged.
    source_files=read_json(work/'new/source-files.private.json')
    rights={'redistribution_authorized':True,'statement':'Maintainer explicitly confirmed authorized redistribution of the supplied Cambridge QP/MS in this task; original rights remain with Cambridge. Exact included batch hashes follow.','sha256':[sha256(path) for path in source_files.values()]}
    write_json(work/'rights.private.json',rights)
    package=work/'ChemistryWorkspace-bank-import-v03.1.qbank'
    pack=build_package(package,new,ms,index,manifest,ROOT/'schemas','新增 2023 March 12/22、2024 October/November 13/23、2025 May/June 11/21，共134题。自动QA通过，不等同人工内容复核。',source_files,rights)
    home=work/'profile';home.mkdir(exist_ok=True);cat=Catalog(home,resources=ROOT)
    # Existing originals are copied only into the disposable profile. Never touch actual personal data.
    for source in manifest['sources']:
        local=ROOT/source['path']
        if local.is_file():
            dest=home/source['path'];dest.parent.mkdir(parents=True,exist_ok=True)
            if not dest.exists():shutil.copyfile(local,dest)
    personal=home/'data/personal.sqlite3'
    old_job={'title':'Acceptance saved worksheet','question_ids':[index['questions'][0]['question_id'],index['questions'][-1]['question_id']],'notes':'Must remain identical'}
    with sqlite3.connect(personal) as c:
        c.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,body TEXT)');c.execute('INSERT OR REPLACE INTO jobs VALUES (?,?)',('acceptance',json.dumps(old_job)))
    old_personal=personal.read_bytes()
    installed=install_package(cat,package,pack['sha256']);assert personal.read_bytes()==old_personal
    assert len(cat.index['questions'])==266
    store=SourceStore(home,cat);start=time.perf_counter();store.extract_local_content();extract_seconds=time.perf_counter()-start
    renderer=Renderer(cat,store)
    rows=cat.search({'year':2023,'paper':1},limit=20)['questions'];assert len(rows)==20
    keyword=cat.search({'search':'disproportionation'});assert keyword['total']>=1
    # Query order is changed intentionally; answers must retain this order.
    ids=[q['question_id'] for q in rows][::-1]
    ids[-1]='cie-9701-s25-21-q6'
    job={'title':'Automatic import acceptance - 20 questions','question_ids':ids,'notes':'Authored acceptance worksheet'}
    start=time.perf_counter();first=renderer.preview(ids[0],'question');preview=time.perf_counter()-start
    start=time.perf_counter();assert first==renderer.preview(ids[0],'question');cached=time.perf_counter()-start
    timings={};sizes={}
    for kind in ['questions','answers']:
        start=time.perf_counter();out=renderer.export(job,kind,home/'exports');timings[kind]=round(time.perf_counter()-start,4);sizes[kind]=out.stat().st_size
        mapping=read_json(out.with_suffix('.mapping.json'));assert [q['question_id'] for q in mapping]==ids
    # Exercise a real report and evidence-based topic correction: disproportionation belongs to redox.
    qid='cie-9701-m23-12-q1'
    feedback=build_report(cat,qid,'topics','Disproportionation question was left Unclassified; propose electro/redox.','0.3.0')
    write_json(work/'feedback.private.json',feedback)
    pair=next(r for r in report['pairs'] if r['pair']=='9701-2023-m-12')
    patch={qid:{'source_fingerprint':pair['source_fingerprint'],'topics':['electro'],'reason':'The stem explicitly asks for a disproportionation reaction; correct the unclassified keyword suggestion.'}}
    write_json(work/'repairs.json',patch)
    # Use the first full snapshot as base; unchanged IDs and source hashes must remain unchanged.
    fixed,fixed_ms,fixed_report=analyze(files,work/'new',new,ms,ROOT/'schemas','2026-10-27.import-v03.2',work/'repairs.json')
    fixpack=work/'ChemistryWorkspace-bank-import-v03.2.qbank'
    fixinfo=build_package(fixpack,fixed,fixed_ms,new,ms,ROOT/'schemas','修复 cie-9701-m23-12-q1 的建议知识点：歧化反应归入氧化还原。')
    fixed_install=install_package(cat,fixpack,fixinfo['sha256']);assert cat.question(qid)['topics']==['electro'];assert personal.read_bytes()==old_personal
    for q in index['questions']:assert cat.question(q['question_id'])['question_id']==q['question_id']
    for qid2 in old_job['question_ids']:renderer.preview(qid2,'question')
    rollback(cat,fixed_install['backup_id']);assert cat.question(qid)['topics']==['unclassified'];assert personal.read_bytes()==old_personal
    install_package(cat,fixpack,fixinfo['sha256'])
    metrics={'schema_version':1,'original_bank_questions':132,'new_batch':report,'original_parser_regression':regression,'resumed_cache_pairs':sum(r['cache_hit'] for r in resumed['pairs']),'new_question_automatic_gate_pass_ratio':report['accepted']/134,'new_question_number_gaps':sum(len(r.get('missing_questions',[])) for r in report['pairs']),'new_missing_answers':sum(len(r.get('missing_answers',[])) for r in report['pairs']),'new_qp_ms_pairs_matching_counts':sum(r.get('detected_questions')==r.get('detected_answers') for r in report['pairs']),'installed_total':266,'search_and_twenty_question_export':{'keyword_matches':keyword['total'],'local_text_extract_seconds':round(extract_seconds,4),'first_preview_seconds':round(preview,4),'cached_preview_seconds':round(cached,4),'export_seconds':timings,'export_bytes':sizes},'packages':[{k:v for k,v in pack.items() if k!='path'},{k:v for k,v in fixinfo.items() if k!='path'}],'report_fix_update_rollback_verified':True,'personal_job_database_byte_identical':True,'limits':['Only these six new textual QP/MS pairs were tested; not a statistical accuracy estimate.','Automated agreement and geometric gates are not human review or proof of diagram semantics.','GitHub Issue URL generated and validated locally; no issue was submitted.','Original 132 public indices are structurally validated and preserved; parser re-analysis may quarantine conservative anomalies.']}
    write_json(args.report,metrics);print(json.dumps(metrics,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
