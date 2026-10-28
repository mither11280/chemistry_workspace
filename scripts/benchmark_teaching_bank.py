"""Measure real legacy files and the corresponding source/coordinate representation.

The storage comparison covers the SAME original questions (P2 becomes child
units). The paired export is 20 identical P1 questions with the existing layout
engine. A second 20-unit mixed P1/P2 export exercises the new split bank. No
estimated full-corpus legacy sizes are reported.
"""
import argparse,copy,json,shutil,sqlite3,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from bank.catalog import Catalog
from bank.sources import SourceStore
from bank.render import Renderer
from bank.format import read_json,write_json,sha256


def resources(folder,index,manifest):
    write_json(folder/'indexes/question-index.json',index);write_json(folder/'indexes/source-manifest.json',manifest)
    shutil.copytree(ROOT/'schemas',folder/'schemas')


def timed_export(renderer,ids,folder,label):
    result={}
    for kind in ['questions','answers']:
        start=time.perf_counter();out=renderer.export({'title':label,'notes':'','question_ids':ids},kind,folder)
        result[kind]={'seconds':round(time.perf_counter()-start,4),'bytes':out.stat().st_size}
        import fitz
        with fitz.open(out) as doc:
            result[kind]['pages']=len(doc);result[kind]['image_objects']=sum(len(p.get_images()) for p in doc)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot',type=Path,default=ROOT/'data/teaching19-current')
    p.add_argument('--legacy',type=Path,default=ROOT/'question_bank/CIE')
    p.add_argument('--sources',type=Path,default=ROOT/'data/import-v04/all-source-files.private.json')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('Use a fresh benchmark output directory')
    a.output.mkdir(parents=True)
    start=time.perf_counter();old=[];old_files=[]
    for path in a.legacy.rglob('metadata.json'):
        q=read_json(path)
        if not all((path.parent/(k+'.pdf')).is_file() for k in ['question','answer']):continue
        q=copy.deepcopy(q);q['legacy_paths']={k:str((path.parent/(k+'.pdf')).resolve()) for k in ['question','answer']}
        old.append(q);old_files.extend([path,*[path.parent/(k+'.pdf') for k in ['question','answer']]])
    scan_seconds=time.perf_counter()-start
    if not old:raise ValueError('No actual legacy PDF/metadata triplets found')
    ids={q['id'] for q in old};index=read_json(a.snapshot/'question-index.json');manifest=read_json(a.snapshot/'source-manifest.json');paths=read_json(a.sources)
    subset=copy.deepcopy(index);subset['questions']=[q for q in index['questions'] if q['question_id'] in ids or q['metadata']['teaching']['parent_question_id'] in ids]
    represented={q['metadata']['teaching']['parent_question_id'] for q in subset['questions']}
    if ids-represented:raise ValueError('Legacy questions are not all represented: '+','.join(sorted(ids-represented)))
    used={q[k]['source_id'] for q in subset['questions'] for k in ['question','answer']}
    sm=copy.deepcopy(manifest);sm['sources']=[s for s in sm['sources'] if s['source_id'] in used]
    root=a.output/'coordinates';resources(root,subset,sm)
    for s in sm['sources']:
        dest=root/s['path'];dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(paths[s['source_id']],dest)
    start=time.perf_counter();cat=Catalog(root);store=SourceStore(root,cat);store.ensure_local_content();initialise_seconds=time.perf_counter()-start
    renderer=Renderer(cat,store)
    empty=copy.deepcopy(index);empty.update(bank_id='legacy-storage-benchmark',topics=[],questions=[])
    empty_manifest=copy.deepcopy(manifest);empty_manifest['sources']=[]
    legacy_root=a.output/'legacy-compat';resources(legacy_root,empty,empty_manifest);legacy_cat=Catalog(legacy_root)
    with legacy_cat.connect() as db:
        for q in old:db.execute('INSERT INTO legacy VALUES (?,?,?)',(q['id'],json.dumps(q),'pending_calibration'))
    legacy_renderer=Renderer(legacy_cat,SourceStore(legacy_root,legacy_cat))
    ready=[q for q in subset['questions'] if q['metadata']['teaching']['status']=='ready']
    p1=sorted(q['question_id'] for q in ready if q['paper']==1)[:20]
    p2=sorted(q['question_id'] for q in ready if q['paper']==2 and not q['metadata']['teaching']['prerequisites'])[:10]
    if len(p1)<20 or len(p2)<10:raise ValueError('Need 20 ready shared P1 questions and 10 independent P2 children')
    queries=[]
    for _ in range(20):
        start=time.perf_counter();cat.search({'paper':2,'min_marks':2,'max_marks':4},limit=8);queries.append(time.perf_counter()-start)
    cold=[];warm=[]
    for qid in p1[:10]+p2:
        q=cat.question(qid);region=sum(len(c['regions']) for c in q['metadata']['teaching']['contexts'])
        start=time.perf_counter();renderer.preview(qid,'question',region);cold.append(time.perf_counter()-start)
        start=time.perf_counter();renderer.preview(qid,'question',region);warm.append(time.perf_counter()-start)
    source_bytes=sum((root/s['path']).stat().st_size for s in sm['sources'])
    json_bytes=sum((root/'indexes'/name).stat().st_size for name in ['question-index.json','source-manifest.json'])
    sqlite_bytes=cat.path.stat().st_size;cache_bytes=sum(p.stat().st_size for p in renderer.cache.glob('*.webp'))
    report={'scope':'Same actual legacy original questions; full source PDFs + corresponding child units. App/runtime and export files excluded from storage.',
            'legacy_original_questions':len(old),'new_selection_units':len(subset['questions']),'new_ready_units':len(ready),'source_pdfs':len(sm['sources']),
            'legacy_pdf_and_metadata_bytes':sum(p.stat().st_size for p in old_files),'new_source_pdf_bytes':source_bytes,'new_json_bytes':json_bytes,'new_sqlite_bytes':sqlite_bytes,
            'new_without_cache_bytes':source_bytes+json_bytes+sqlite_bytes,'webp_preview_files':len(cold),'webp_cache_bytes':cache_bytes,'new_with_cache_bytes':source_bytes+json_bytes+sqlite_bytes+cache_bytes,
            'legacy_metadata_scan_seconds':round(scan_seconds,4),'new_first_catalog_and_text_index_seconds':round(initialise_seconds,4),
            'sql_filter_average_seconds':round(sum(queries)/len(queries),6),'cold_preview_average_seconds':round(sum(cold)/len(cold),6),'cached_preview_average_seconds':round(sum(warm)/len(warm),6),
            'same_20_p1_ids':p1,'legacy_20_p1':timed_export(legacy_renderer,p1,a.output/'exports-legacy','20 P1 legacy comparison'),
            'coordinates_20_p1':timed_export(renderer,p1,a.output/'exports-p1','20 P1 coordinate comparison'),
            'mixed_20_units_ids':p1[:10]+p2,'coordinates_20_mixed':timed_export(renderer,p1[:10]+p2,a.output/'exports-mixed','20 mixed independent units'),
            'limits':['Metadata scan and first SQLite/FTS construction are different operations, not old/new whole-App launch timings.','P2 counts differ because the same original big questions are now split into scored children.','Only this actual legacy sample has a paired storage comparison; no extrapolated full-corpus legacy size.','The coordinate export retains source-reference appendices; legacy triplets do not provide them, so these page counts are not identical-layout exports.','Cold preview means an absent WebP cache, not an empty operating-system disk cache.','Existing bitmap objects in original Mark Schemes are preserved; the exporter does not rasterise vector pages.']}
    write_json(a.output/'benchmark.json',report);print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
