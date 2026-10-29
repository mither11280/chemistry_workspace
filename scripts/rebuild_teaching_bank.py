"""Reproducible teaching-bank candidates; decisions are explicit source-bound records."""
import argparse,copy,json,re,sys,time
from collections import Counter
from pathlib import Path
import fitz
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from bank.format import read_json,write_json,sha256,validate
from bank.pdf_layout import canonicalize,layout_page
from bank.teaching.taxonomy import BANK_ID,TAXONOMY_ID,topics,topic_id,normalize_provenance,course_for,taxonomy_for
from bank.teaching.parts import qp_parts,ms_parts,supplement_contexts
from bank.teaching.decisions import fingerprint as material_fingerprint
from bank.importer.strategies import strategy_for
from bank.importer.quality import region_issues
from bank.importer.syllabus import metadata as syllabus_metadata


def dependencies(parts):
    paths={p['path']:p for p in parts}
    for i,p in enumerate(parts):
        text=p['text'];deps=set();problems=[]
        for m in re.finditer(r'\(([a-z])\)(?:\(([ivx]+)\))?|\(([ivx]+)\)',text):
            before=text[max(0,m.start()-90):m.start()]
            # O2(g), Na2O2(s), C4H4S(l) are state symbols, not lettered
            # subparts. Preserve a genuine explicitly numbered reference 1(g).
            parent_number=p['label'].split('(')[0]
            numbered=re.search(r'(?<![A-Za-z0-9])'+re.escape(parent_number)+r'$',before)
            # PDF fonts can separate a chemical subscript: MgCl 2(s) in Q2
            # is still a solid-state label, not a reference to question 2(s).
            chemical_number=re.search(r'(?:[A-Z][a-z]?\d*\s*)+\d+[+\-−–]*$',before)
            if m[1] in ['s','l','g'] and not m[2] and before and (before[-1].isalnum() or before[-1] in '+-−–]}') and (not numbered or chemical_number):continue
            path=tuple(x for x in m.groups()[:2] if x) if m[1] and (m[2] or m[1] not in ['i','v','x']) else (*p['path'][:1],m[3] or m[1])
            if path==p['path'] or path==p['path'][:1]:continue
            matches=[q for k,q in paths.items() if k==path or (len(path)==1 and k[:1]==path)]
            if matches:
                deps.update(q['id'] for q in matches if q['order']<p['order'])
            elif re.search(r'answer|result|calculated|value',before,re.I):problems.append('unresolved_prior_result_reference')
        if re.search(r'^\s*(?:\([a-zivx]+\)\s*)?[\x07\s]*Hence\b|(?:using|use|from) your (?:answer|result|value)|your (?:answer|result|value) to(?!\s*(?:\d+|one|two|three|four)\s*(?:significant|decimal))',text,re.I) and not deps:
            if i>0 and parts[i-1]['path'][:1]==p['path'][:1]:deps.add(parts[i-1]['id'])
            else:problems.append('implicit_dependency_needs_confirmation')
        p['dependencies']=sorted(deps);p['issues']+=problems


def build(base,manifest,paths,out,decisions=None,pairs=None,context_overrides=None,papers=(1,2)):
    context_overrides={k:v for k,v in (context_overrides or {}).items() if int(k.split('-')[3][0]) in papers}
    available={s['source_id'] for s in manifest['sources'] if s['metadata'].get('role')=='qp' and s['metadata'].get('paper') in papers}
    if pairs and set(pairs)-available:
        raise ValueError('Unknown QP source IDs: '+', '.join(sorted(set(pairs)-available)))
    out=Path(out);out.mkdir(parents=True,exist_ok=True);decisions=decisions or {};private=[];questions=[];reports=[];original={q['question_id']:q for q in base['questions']}
    sources={s['source_id']:s for s in manifest['sources']};start=time.perf_counter()
    for qs in manifest['sources']:
        meta=qs['metadata']
        if meta.get('role')!='qp' or meta.get('paper') not in papers:continue
        sid=qs['source_id'];msid=sid[:-2]+'ms'
        if pairs and sid not in pairs:continue
        if msid not in paths:reports.append({'source_id':sid,'issues':['missing_ms']});continue
        for source in [qs,sources[msid]]:
            if sha256(paths[source['source_id']])!=source['sha256']:raise ValueError('Source hash mismatch: '+source['source_id'])
        with fitz.open(paths[sid]) as qdoc,fitz.open(paths[msid]) as mdoc:
            paper=meta['paper'];strategy=strategy_for(meta['year']);qp,errors=strategy.question_paper(qdoc,paper);answers,ae=strategy.mark_scheme(mdoc,paper) if paper==1 else ms_parts(mdoc)
            source_issues=sorted({f'source:{e}' for source in [qs,sources[msid]] for e in source['metadata'].get('source_integrity_issues',[]) if source['metadata'].get('assessment_completeness')!='verified-against-official-ms-and-required-context'})
            pair_rows=[];context_qa={}
            for n,parent in qp.items():
                parent_id=next((q.get('metadata',{}).get('teaching',{}).get('parent_question_id',q['question_id']) for q in base['questions'] if q['question']['source_id']==sid and q['original_question_number']==str(n)),f"cie-9701-{meta['session_code'] if 'session_code' in meta else {'March':'m','May/June':'s','October/November':'w'}[meta['session']]}{str(meta['year'])[-2:]}-{paper}{meta['variant']}-q{n}")
                canonical=canonicalize(qdoc,parent['regions'])
                if paper==1:
                    ans=answers.get(n,{});shared=parent.get('shared_context_regions',0);parts=[{'id':parent_id,'path':(),'label':str(n),'own_regions':canonical[shared:],'contexts':[{'key':'section-b-codes','global_key':sid+':section-b-codes','regions':canonical[:shared]}] if shared else [],'text':parent['text'],'marks':1,'order':0,'issues':list(errors+ae),'dependencies':[]}]
                else:
                    parts,pe=qp_parts(qdoc,canonical,n,allow_unlabelled=paper==4)
                    for p in parts:p.update(id=parent_id+'-'+ ('-'.join(p['path']) or 'unit'),issues=list(errors+ae+pe+source_issues))
                    dependencies(parts)
                    supplement_contexts(parts,context_overrides or {},qdoc)
                    if sum(p['marks'] or 0 for p in parts)!=parent['marks']:
                        for p in parts:p['issues'].append('qp_child_marks_do_not_reconcile')
                    if not parts:reports.append({'parent_question_id':parent_id,'issues':pe or ['no_parts'],'question':{'source_id':sid,'regions':canonical}})
                for p in parts:
                    ans=answers.get(n if paper==1 else (n,p['path']),{})
                    official_label=None
                    if paper!=1 and not p['path'] and not ans:
                        matches=[(key,value) for key,value in answers.items() if key[0]==n]
                        if len(matches)==1 and matches[0][1]['marks']==p['marks']:
                            key,ans=matches[0];official_label=str(n)+''.join('('+v+')' for v in key[1])
                    if paper!=1 and not any(key[0]==n for key in answers):p['issues'].append('ms_parent_question_absent')
                    if not ans.get('regions'):p['issues'].append('exact_ms_label_missing')
                    if p['marks'] is None or ans.get('marks')!=p['marks']:p['issues'].append('subpart_marks_mismatch')
                    own=p['own_regions'];contexts=[dict(c,key=c.get('global_key',parent_id+':'+c['key'])) for c in p['contexts']]
                    for context in contexts:
                        key=json.dumps(context['regions'],sort_keys=True)
                        if key not in context_qa:context_qa[key]=region_issues(qdoc,context['regions'])
                        p['issues']+=['context:'+e for e in context_qa[key]]
                    for kind,rs,doc in [('question',own,qdoc),('answer',ans.get('regions',[]),mdoc)]:
                        p['issues']+=['%s:%s'%(kind,e) for e in region_issues(doc,rs)] if rs else []
                    q=copy.deepcopy(original.get(parent_id,{}))
                    if not q:q={'exam_board':meta['exam_board'],'qualification':'A2' if paper==4 else 'AS','subject_code':'9701','year':meta['year'],'session':meta['session'],'paper':paper,'variant':meta['variant'],'metadata':{}}
                    if paper==4:
                        # Period provenance is distinct from the teaching taxonomy.
                        # Empty topics avoid presenting the AS broad-topic crosswalk
                        # as a verified mapping of A2 syllabus statements.
                        q['metadata'].update(syllabus_metadata(meta['year'],[],meta['session']))
                    q.update(question_id=p['id'],original_question_number=p['label'],marks=p['marks'],topics=[],question={'source_id':sid,'regions':[r for c in contexts for r in c['regions']]+own},answer={'type':'mcq' if paper==1 else 'regions','source_id':msid,'regions':ans.get('regions',[])})
                    normalize_provenance(q)
                    q['metadata']['automatic_qa']={'status':'quarantined' if p['issues'] else 'passed','checks_version':'teaching19-parts-v1','issues':sorted(set(p['issues']))}
                    q['metadata']['teaching']={'taxonomy_id':taxonomy_for('A2' if paper==4 else 'AS'),'status':'pending','primary_chapter':None,'required_chapters':[],'prerequisites':p['dependencies'],'parent_question_id':parent_id,'part_path':list(p['path']),'source_order':p['order'],'own_regions':own,'contexts':contexts,'evidence':[],'issues':sorted(set(p['issues']))}
                    if official_label:q['metadata']['teaching']['official_answer_label']=official_label
                    context_text='\n'.join(layout_page(qdoc,r['page_index']).get_text(clip=fitz.Rect(r['bbox'])) for c in p['contexts'] for r in c['regions'])
                    fingerprint=material_fingerprint(q,sources)
                    record={'question_id':p['id'],'fingerprint':fingerprint,'context':context_text,'task':p['text'],'answer':ans.get('text',''),'mcq_answer':ans.get('value'),'material_issues':list(q['metadata']['teaching']['issues'])}
                    decision=decisions.get(p['id'])
                    if decision:
                        if decision['fingerprint']!=fingerprint:raise ValueError('Stale teaching decision: '+p['id'])
                        q['metadata']['teaching'].update(required_chapters=decision['required_chapters'],evidence=decision['evidence'])
                        q['metadata']['teaching']['issues']+=decision.get('issues',[])
                        if 'prerequisites' in decision:q['metadata']['teaching']['prerequisites']=decision['prerequisites']
                    else:q['metadata']['teaching']['issues'].append('classification_not_confirmed')
                    private.append(record);questions.append(q);pair_rows.append(q)
            reports.append({'source_id':sid,'parent_questions':len(qp),'subparts':len(pair_rows),'issues':errors+ae})
        print(sid,len(pair_rows),flush=True)
    by_id={q['question_id']:q for q in questions};done=set();visiting=set()
    if not pairs and set(context_overrides or {})-by_id.keys():
        raise ValueError('Context correction targets were not parsed: '+', '.join(sorted(set(context_overrides)-by_id.keys())))
    def finish(q):
        qid=q['question_id'];m=q['metadata']['teaching']
        if qid in done:return
        if qid in visiting:m['issues'].append('dependency_cycle');return
        visiting.add(qid);chapters=set(m['required_chapters'])
        for dep in m['prerequisites']:
            if dep not in by_id:m['issues'].append('missing_prerequisite');continue
            d=by_id[dep];finish(d);dm=d['metadata']['teaching'];chapters.update(dm['required_chapters'])
            if dm['primary_chapter']:chapters.add(dm['primary_chapter'])
            if dm['status']!='ready':m['issues'].append('prerequisite_pending')
        if not chapters:m['issues'].append('classification_not_confirmed')
        m['issues']=sorted(set(m['issues']))
        if not m['issues']:m.update(status='ready',primary_chapter=max(chapters));q['topics']=[topic_id(max(chapters),course_for(q))]
        visiting.remove(qid);done.add(qid)
    for q in questions:finish(q)
    index=dict(base,bank_id=BANK_ID,revision='2026-10-28.teaching19.1',topics=topics()+topics('A2') if 4 in papers else topics(),questions=questions)
    # Candidate records with missing material remain in a separate portable holding file.
    valid=[q for q in questions if q['question']['regions'] and q['answer']['regions'] and q['marks'] is not None]
    invalid=[q for q in questions if q not in valid];valid=questions;index['questions']=valid
    # A dependency on an omitted material candidate is represented by a pending reason, not a broken reference.
    valid_ids={q['question_id'] for q in valid}
    for q in valid:
        m=q['metadata']['teaching'];missing=[d for d in m['prerequisites'] if d not in valid_ids]
        if missing:m['missing_prerequisites']=missing;m['prerequisites']=[d for d in m['prerequisites'] if d in valid_ids];m['issues']=sorted(set(m['issues']+['missing_prerequisite']));m['status']='pending';q['topics']=[]
    write_json(out/'question-index.json',index);write_json(out/'source-manifest.json',manifest)
    write_json(out/'candidates.private.json',private);write_json(out/'unavailable-candidates.json',invalid)
    report={'input_questions':len(base['questions']),'source_pairs':len([s for s in reports if 'source_id' in s]),'candidate_questions':len(questions),'indexed_candidates':len(valid),'ready':sum(q['metadata']['teaching']['status']=='ready' for q in valid),'pending':sum(q['metadata']['teaching']['status']=='pending' for q in valid),'chapter_counts':dict(Counter(q['metadata']['teaching']['primary_chapter'] for q in valid if q['metadata']['teaching']['status']=='ready')),'material_issue_counts':dict(Counter(e for q in questions for e in q['metadata']['teaching']['issues'] if e!='classification_not_confirmed')),'pairs':reports,'seconds':round(time.perf_counter()-start,3)}
    write_json(out/'report.json',report);return index,report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base',type=Path,default=ROOT/'indexes/releases/v0.4-2018-2026');p.add_argument('--sources',type=Path,default=ROOT/'data/import-v04/all-source-files.private.json');p.add_argument('--output',type=Path,default=ROOT/'data/teaching19');p.add_argument('--decisions',type=Path);p.add_argument('--pair',action='append');p.add_argument('--papers',default='1,2');a=p.parse_args()
    context_file=ROOT/'indexes/teaching19-context-overrides.json'
    overrides={}
    if context_file.exists():
        from jsonschema import Draft202012Validator
        corrections=read_json(context_file)
        Draft202012Validator(read_json(ROOT/'schemas/teaching-context-overrides.schema.json')).validate(corrections)
        overrides=corrections['questions']
    build(read_json(a.base/'question-index.json'),read_json(a.base/'source-manifest.json'),read_json(a.sources),a.output,read_json(a.decisions) if a.decisions else {},a.pair,overrides,tuple(map(int,a.papers.split(','))))
