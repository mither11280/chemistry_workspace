"""Tighten proven empty exterior bands and retain portable source-bound evidence."""
import argparse,collections,copy,json,sys,time
from pathlib import Path
import fitz
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from bank.format import read_json,write_json,sha256,validate
from bank.teaching.whitespace import tighten,VERSION
from bank.teaching.decisions import fingerprint


def trim(snapshot,sources,output,decisions=None,candidates=None):
    snapshot=Path(snapshot);output=Path(output)
    if output.exists():raise ValueError('Use a fresh output directory')
    index=read_json(snapshot/'question-index.json');manifest=read_json(snapshot/'source-manifest.json');paths=read_json(sources);sm={s['source_id']:s for s in manifest['sources']}
    docs=collections.OrderedDict();cache={};proofs=[];affected=[];start=time.perf_counter()
    def doc(sid):
        if sid not in docs:
            if sha256(paths[sid])!=sm[sid]['sha256']:raise ValueError('Source mismatch: '+sid)
            if len(docs)>=4:docs.popitem(last=False)[1].close()
            docs[sid]=fitz.open(paths[sid])
        docs.move_to_end(sid);return docs[sid]
    def regions(sid,rs,preserve_answer_space=False):
        out=[]
        for r in rs:
            key=(sid,json.dumps(r,sort_keys=True),preserve_answer_space)
            if key not in cache:
                new,proof=tighten(doc(sid),r,preserve_answer_space=preserve_answer_space);cache[key]=(new,proof)
                if proof:proofs.append(dict(proof,source_id=sid,source_sha256=sm[sid]['sha256']))
            out.append(copy.deepcopy(cache[key][0]))
        return out
    try:
        for q in index['questions']:
            before=fingerprint(q,sm);m=q['metadata']['teaching'];sid=q['question']['source_id']
            m['own_regions']=regions(sid,m['own_regions'],preserve_answer_space=q['paper']!=1)
            for c in m['contexts']:c['regions']=regions(sid,c['regions'])
            q['question']['regions']=[r for c in m['contexts'] for r in c['regions']]+m['own_regions']
            q['answer']['regions']=regions(q['answer']['source_id'],q['answer']['regions'])
            after=fingerprint(q,sm)
            if before!=after:
                affected.append({'question_id':q['question_id'],'before_fingerprint':before,'after_fingerprint':after})
                m['evidence'].append({'method':VERSION,'reason':'Only exterior bands proven ink-free by rendering and protected content geometry were removed; original answer space, diagrams, score labels and classification are retained.'})
        validate(index,manifest,ROOT/'schemas')
        output.mkdir(parents=True);write_json(output/'question-index.json',index);write_json(output/'source-manifest.json',manifest)
        if decisions:
            ds=read_json(decisions);by={q['question_id']:q for q in index['questions']}
            for a in affected:
                d=ds.get(a['question_id'])
                if d:
                    if d['fingerprint']!=a['before_fingerprint']:raise ValueError('Stale input decision: '+a['question_id'])
                    d['fingerprint']=a['after_fingerprint'];d['evidence']=by[a['question_id']]['metadata']['teaching']['evidence']
            write_json(output/'decisions.json',ds)
        if candidates:
            records=read_json(candidates);by={q['question_id']:q for q in index['questions']}
            for r in records:r['fingerprint']=fingerprint(by[r['question_id']],sm)
            write_json(output/'candidates.private.json',records)
        result={'version':VERSION,'questions':len(index['questions']),'changed_questions':len(affected),'changed_unique_regions':len(proofs),'removed_height_points':round(sum(p['removed_height_points'] for p in proofs),3),'seconds':round(time.perf_counter()-start,3),'affected':affected,'regions':proofs}
        write_json(output/'whitespace-report.json',result);print({k:v for k,v in result.items() if k not in ['affected','regions']});return result
    finally:
        for d in docs.values():d.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--snapshot',type=Path,required=True);p.add_argument('--sources',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--decisions',type=Path);p.add_argument('--candidates',type=Path);a=p.parse_args();trim(a.snapshot,a.sources,a.output,a.decisions,a.candidates)
