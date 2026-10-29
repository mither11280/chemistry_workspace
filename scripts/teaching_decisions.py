"""Display decision batches and record explicit judgments against exact source fingerprints.

Only the approve command writes decisions; proposal generation never changes bank
readiness. Use --ids to reread a difficult question's complete context and answer.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from bank.format import read_json,write_json
from bank.teaching.proposals import propose,compact,task_stem
p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['list','show','approve']);p.add_argument('--workdir',type=Path,default=ROOT/'data/teaching19');p.add_argument('--decisions',type=Path,default=ROOT/'data/teaching19-decisions.json');p.add_argument('--paper',type=int);p.add_argument('--series');p.add_argument('--offset',type=int,default=0);p.add_argument('--limit',type=int,default=40);p.add_argument('--ids');p.add_argument('--judgments',type=Path);p.add_argument('--brief',action='store_true',help='Compact reading view; use show for complete material');a=p.parse_args()
rows=read_json(a.workdir/'candidates.private.json');decisions=read_json(a.decisions) if a.decisions.exists() else {};by_id={q['question_id']:q for q in rows}
if a.action=='list':
    todo=[q for q in rows if q['question_id'] not in decisions and (not a.series or q['question_id'].startswith(a.series)) and (not a.paper or int(q['question_id'].split('-')[3][0])==a.paper)]
    print('remaining',len(todo))
    for q in todo[a.offset:a.offset+a.limit]:
        print(q['question_id'], 'hints='+','.join(str(v['chapter']) for v in propose(q)), 'issues='+','.join(q['material_issues']))
        text=q['task']
        if text.lstrip().startswith('Section B'):
            import re
            n=q['question_id'].split('-q')[-1];m=re.search(r'(?m)^\s*'+re.escape(n)+r'\s+',text)
            if m:text=text[m.start():]
        text=text.split('The responses A to D should be selected')[0]
        print(compact(text)[:(280 if a.brief else 600)]);
        if q['question_id'].split('-')[3][0]!='1':print('CTX',compact(q.get('context',''))[:(110 if a.brief else 200)],'MS',compact(q.get('answer',''))[:(220 if a.brief else 350)])
elif a.action=='show':
    for qid in a.ids.split(','):print(json.dumps(by_id[qid],ensure_ascii=False,indent=2))
else:
    judgments=read_json(a.judgments)
    for qid,j in judgments.items():
        if qid not in by_id:raise ValueError(qid)
        r=by_id[qid];chapters=j['required_chapters']
        if j.get('review_input_fingerprint',r['fingerprint'])!=r['fingerprint']:raise ValueError('Judgment material changed since reading: '+qid)
        if chapters!=sorted(set(chapters)) or any(type(n)!=int or not 1<=n<=(12 if qid.split('-')[3][0]=='4' else 19) for n in chapters):raise ValueError('chapter ordering')
        if not j.get('reason'):raise ValueError('require solution-specific reasoning')
        if 'prerequisites' in j and (not isinstance(j['prerequisites'],list) or any(d not in by_id for d in j['prerequisites'])):raise ValueError('unknown prerequisite')
        decisions[qid]={'fingerprint':r['fingerprint'],'required_chapters':chapters,'evidence':[{'method':'agent-read-task-and-scoring-evidence','reason':j['reason']}],**({'issues':j['issues']} if j.get('issues') else {}),**({'prerequisites':j['prerequisites']} if 'prerequisites' in j else {})}
    write_json(a.decisions,decisions);print('Recorded',len(judgments),'explicit decisions; total',len(decisions))
