"""Source coverage, not a promise that every scheduled component exists locally."""
from collections import Counter,defaultdict
from pathlib import Path
import csv,re
from .identity import identify,SESSIONS
from . import VERSION
from .equivalence import fingerprint as content_fingerprint
from ..format import read_json,write_json,sha256

CANCELLATION_URL='https://www.cambridgeinternational.org/news/news-details/view/update-from-cambridge-international-on-may-june-2020-exams-20200323/'

def exam_status(year,session,as_of='2026-10-27'):
    if year==2020 and session=='s':return 'cancelled-published-practice-materials'
    if year==2026 and session=='w' and as_of<'2026-12-01':return 'series-in-progress-not-publication-ready'
    return 'historical-or-completed'


def scan(corpus,index,manifest,output,as_of='2026-10-27'):
    corpus=Path(corpus);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    groups=defaultdict(lambda:defaultdict(list));rejected=[];outside=0;all_files=0
    for path in sorted(corpus.rglob('*')):
        if not path.is_file() or path.suffix.lower()!='.pdf':continue
        all_files+=1
        years=re.findall(r'20\d{2}',str(path.relative_to(corpus)))
        if not years or not 2018<=int(years[0])<=2026:outside+=1;continue
        if re.search(r'(?:_(?:qp|ms)_[345]\d|9701-[345]\d_)',path.name,re.I):outside+=1;continue
        if not re.search(r'(?:_(?:qp|ms)_[12][123]|9701-[12][123]_).*\.pdf$',path.name,re.I):outside+=1;continue
        try:
            ident,s=identify(path)
            if not 2018<=ident.year<=2026:outside+=1;continue
            groups[(ident.year,ident.session_code,ident.paper,ident.variant)][ident.kind].append({'file':path.name,'relative_path':path.relative_to(corpus).as_posix(),'sha256':s['sha256'],'source':s})
        except Exception as exc:rejected.append({'file':path.name,'relative_path':path.relative_to(corpus).as_posix(),'sha256':sha256(path),'error':str(exc)})
    registered={s['source_id']:s for s in manifest['sources']};byexam=defaultdict(list)
    for q in index['questions']:byexam[(q['year'],q['session'],q['paper'],q['variant'])].append(q)
    keys={(y,se,p,v) for y in range(2018,2027) for se in SESSIONS for p in [1,2] for v in ([2] if se=='m' else [1,2,3])}|set(groups)
    rows=[];selected={};duplicate_files=[]
    for year,se,paper,variant in sorted(keys):
        group=groups.get((year,se,paper,variant),{});qs=byexam[(year,SESSIONS[se],paper,variant)]
        status=exam_status(year,se,as_of);choices={};issues=[]
        for role in ['qp','ms']:
            candidates=group.get(role,[]);byhash=defaultdict(list)
            for f in candidates:byhash[f['sha256']].append(f)
            for digest,fs in byhash.items():
                if len(fs)>1:duplicate_files.append({'year':year,'session':SESSIONS[se],'paper':paper,'variant':variant,'role':role,'sha256':digest,'copies':[f['file'] for f in fs]})
            if len(byhash)==1:choices[role]=candidates[0]
            elif len(byhash)>1:
                expected={registered[q['question' if role=='qp' else 'answer']['source_id']]['sha256'] for q in qs}
                match=[fs[0] for h,fs in byhash.items() if h in expected]
                if len(match)==1:choices[role]=match[0];issues.append('alternate-'+role+'-versions-held-existing-hash-selected')
                else:
                    variants=[fs[0] for fs in byhash.values()]
                    try:signatures={content_fingerprint(corpus/f['relative_path'],f['sha256'],output/'equivalence-cache') for f in variants}
                    except Exception:signatures=set()
                    if len(signatures)==1:
                        chosen=min(variants,key=lambda f:('_alt' in f['file'].lower(),f['file']))
                        choices[role]=chosen;issues.append('content-equivalent-'+role+'-versions-canonical-selected')
                        duplicate_files.append({'year':year,'session':SESSIONS[se],'paper':paper,'variant':variant,'role':role,'equivalence':'all-page-unrotated-boxes-text-and-rgb72-identical-display-rotation-may-differ','copies':[f['file'] for f in variants],'sha256_variants':list(byhash),'selected_sha256':chosen['sha256']})
                    else:issues.append('conflicting-'+role+'-versions')
        found={role:bool(group.get(role)) for role in ['qp','ms']}
        if status=='series-in-progress-not-publication-ready':issues.append('awaiting-series-completion')
        if not found['qp'] and status!='series-in-progress-not-publication-ready':issues.append('missing-qp')
        if not found['ms'] and status!='series-in-progress-not-publication-ready':issues.append('missing-ms')
        current_hashes=all(role in choices and all(registered[q['question' if role=='qp' else 'answer']['source_id']]['sha256']==choices[role]['sha256'] for q in qs) for role in ['qp','ms'])
        complete_existing=bool(qs) and current_hashes and sum(q['marks'] or 0 for q in qs)==(choices.get('ms',{}).get('source',{}).get('metadata',{}).get('cover_total_marks'))
        key=f'9701-{year}-{se}-{paper}{variant}'
        ready=all(role in choices for role in ['qp','ms']) and status!='series-in-progress-not-publication-ready'
        row={'pair':key,'year':year,'session_code':se,'session':SESSIONS[se],'paper':paper,'variant':variant,'exam_status':status,'qp_found':found['qp'],'ms_found':found['ms'],'already_imported':complete_existing,'imported_questions':len(qs),'qa_status':'existing-bank' if complete_existing else 'not-analyzed' if ready else 'unavailable-or-held','parser_version':VERSION,'sources':{role:[{k:v for k,v in f.items() if k!='source'} for f in group.get(role,[])] for role in ['qp','ms']},'issues':issues}
        rows.append(row)
        if ready and not complete_existing:selected[key]=[str(corpus/choices[role]['relative_path']) for role in ['qp','ms']]
    report={'schema_version':'1.0.0','as_of':as_of,'base_revision':index['revision'],'base_questions':len(index['questions']),'parser_version':VERSION,'total_scanned_pdfs':all_files,'outside_target_scope':outside,'identified_target_files':sum(len(fs) for group in groups.values() for fs in group.values()),'rejected_files':rejected,'duplicate_files':duplicate_files,'rows':rows,'cancellation_evidence':CANCELLATION_URL,'summary':{'scheduled_component_rows':len(rows),'paired':sum(r['qp_found'] and r['ms_found'] for r in rows),'already_imported_pairs':sum(r['already_imported'] for r in rows),'ready_unimported_pairs':len(selected),'existing_question_ids_unique':len({q['question_id'] for q in index['questions']})==len(index['questions'])}}
    write_json(output/'inventory.json',report);write_json(output/'selected-files.private.json',selected)
    with (output/'inventory.csv').open('w',newline='',encoding='utf-8-sig') as f:
        fields=['pair','year','session','paper','variant','exam_status','qp_found','ms_found','already_imported','imported_questions','qa_status','parser_version','issues']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for r in rows:writer.writerow({k:';'.join(r[k]) if isinstance(r[k],list) else r[k] for k in fields})
    return report,selected
