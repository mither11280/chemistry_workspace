"""Apply explicit source-bound teaching decisions to an already measured split snapshot.
No PDF parsing or automatic keyword classification occurs in this step.
"""
import argparse,copy,csv,json
from collections import Counter
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from bank.format import read_json,write_json,validate
from bank.teaching.taxonomy import topic_id,normalize_provenance,course_for
from bank.teaching.proposals import propose


def apply(workdir,decisions_path,output):
    workdir=Path(workdir);output=Path(output);index=read_json(workdir/'question-index.json');manifest=read_json(workdir/'source-manifest.json');records={r['question_id']:r for r in read_json(workdir/'candidates.private.json')};decisions=read_json(decisions_path);qs={q['question_id']:q for q in index['questions']};visiting=set();done=set()
    for qid,q in qs.items():
        normalize_provenance(q)
        q['answer'].pop('value',None)  # official MCQ values remain in local extraction only
        r=records[qid];m=q['metadata']['teaching'];m.update(status='pending',primary_chapter=None,required_chapters=[],evidence=[],issues=list(r['material_issues']));q['topics']=[]
        if qid in decisions:
            d=decisions[qid]
            if d['fingerprint']!=r['fingerprint']:raise ValueError('Stale source/boundary decision: '+qid)
            m.update(required_chapters=d['required_chapters'],evidence=d['evidence']);m['issues']+=d.get('issues',[])
            if 'prerequisites' in d:m['prerequisites']=d['prerequisites']
        else:m['issues'].append('classification_not_confirmed')
    def visit(qid):
        if qid in done:return
        if qid in visiting:raise ValueError('dependency cycle: '+qid)
        visiting.add(qid);q=qs[qid];m=q['metadata']['teaching'];chapters=set(m['required_chapters'])
        for dep in m['prerequisites']:
            if dep not in qs:m['issues'].append('missing_prerequisite');continue
            visit(dep);dm=qs[dep]['metadata']['teaching'];chapters.update(dm['required_chapters'])
            if dm['primary_chapter']:chapters.add(dm['primary_chapter'])
            if dm['status']!='ready':m['issues'].append('prerequisite_pending')
        if not chapters:m['issues'].append('no_reliable_primary_chapter' if qid in decisions else 'classification_not_confirmed')
        m['issues']=sorted(set(m['issues']))
        if not m['issues']:
            m.update(status='ready',primary_chapter=max(chapters));q['topics']=[topic_id(max(chapters),course_for(q))];m.pop('candidate_chapters',None)
        else:
            m['candidate_chapters']=sorted(set(m['required_chapters'])|({v['chapter'] for v in propose(records[qid])} if q['paper']!=4 else set()))
        visiting.remove(qid);done.add(qid)
    for qid in qs:visit(qid)
    validate(index,manifest,ROOT/'schemas');output.mkdir(parents=True,exist_ok=True)
    write_json(output/'question-index.json',index);write_json(output/'source-manifest.json',manifest)
    pending=[q for q in qs.values() if q['metadata']['teaching']['status']=='pending'];ready=[q for q in qs.values() if q['metadata']['teaching']['status']=='ready']
    write_json(output/'pending.json',{'bank_id':index['bank_id'],'revision':index['revision'],'questions':pending})
    with (output/'pending.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f,lineterminator='\n');w.writerow(['question_id','year','session','paper','variant','label','marks','candidate_chapters','issues','question_source_id','question_regions_json','answer_source_id','answer_regions_json','prerequisites_json','classification_evidence_json'])
        for q in pending:
            m=q['metadata']['teaching'];w.writerow([q['question_id'],q['year'],q['session'],q['paper'],q['variant'],q['original_question_number'],q['marks'],';'.join(map(str,m.get('candidate_chapters',[]))),';'.join(m['issues']),q['question']['source_id'],json.dumps(q['question']['regions'],separators=(',',':')),q['answer']['source_id'],json.dumps(q['answer']['regions'],separators=(',',':')),json.dumps(m['prerequisites']),json.dumps(m['evidence'],ensure_ascii=False)])
    matrix=Counter((q['year'],q['session'],q['paper'],q['variant'],q['metadata']['teaching']['status']) for q in qs.values())
    report={'candidate_units':len(qs),'paper1':sum(q['paper']==1 for q in qs.values()),'paper2_subparts':sum(q['paper']==2 for q in qs.values()),'ready':len(ready),'pending':len(pending),'explicit_classification_decisions':len(decisions),'chapter_counts':{t['id']:sum(q['topics']==[t['id']] for q in ready) for t in index['topics']},'dependency_units':sum(bool(q['metadata']['teaching']['prerequisites']) for q in ready),'issue_counts':dict(Counter(e for q in pending for e in q['metadata']['teaching']['issues'])),'coverage':[dict(year=y,session=s,paper=p,variant=v,status=st,count=n) for (y,s,p,v,st),n in sorted(matrix.items())]}
    report['paper2_parent_questions']=len({q['metadata']['teaching']['parent_question_id'] for q in qs.values() if q['paper']==2})
    report['dependency_parent_groups']=len({q['metadata']['teaching']['parent_question_id'] for q in ready if q['metadata']['teaching']['prerequisites']})
    report['source_pairs']=len({q['question']['source_id'] for q in qs.values()})
    report['registered_source_pairs']=sum(s.get('metadata',{}).get('role')=='qp' for s in manifest['sources'])
    report['paper4_subparts']=sum(q['paper']==4 for q in qs.values())
    report['paper4_parent_questions']=len({q['metadata']['teaching']['parent_question_id'] for q in qs.values() if q['paper']==4})
    reused=sum(any(e.get('reference_question_id') and e.get('method','').startswith('identical-task-context-and-official-ms-rgb-') for e in d['evidence']) for qid,d in decisions.items() if qid in qs)
    report['classification_decisions']=sum(qid in qs for qid in decisions)
    report['proven_reused_decisions']=reused
    report['explicit_classification_decisions']=report['classification_decisions']-reused
    report['unread_units']=sum(qid not in decisions for qid in qs)
    write_json(output/'teaching-report.json',report);print({k:v for k,v in report.items() if k!='coverage'});return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workdir',type=Path,default=ROOT/'data/teaching19');p.add_argument('--decisions',type=Path,default=ROOT/'data/teaching19-decisions.json');p.add_argument('--output',type=Path,default=ROOT/'data/teaching19-current');a=p.parse_args();apply(a.workdir,a.decisions,a.output)
