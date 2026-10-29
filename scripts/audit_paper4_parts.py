"""Reconcile every registered P4 with independently parsed official MS labels and marks."""
import argparse,collections,json,sys
from pathlib import Path
import fitz
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from bank.format import read_json,write_json,sha256
from bank.teaching.parts import ms_parts,label_path

def audit(snapshot,paths_file,output):
    snapshot=Path(snapshot);index=read_json(snapshot/'question-index.json');manifest=read_json(snapshot/'source-manifest.json');paths=read_json(paths_file)
    grouped=collections.defaultdict(list)
    for q in index['questions']:
        if q['paper']==4:grouped[q['question']['source_id']].append(q)
    sources={s['source_id']:s for s in manifest['sources']};report=[]
    for sid,rows in grouped.items():
        msid=sid[:-2]+'ms';ms=sources[msid]
        if sha256(paths[msid])!=ms['sha256']:raise ValueError('Source changed: '+msid)
        with fitz.open(paths[msid]) as doc:official,issues=ms_parts(doc)
        parsed={label_path(q['metadata']['teaching'].get('official_answer_label',q['original_question_number'])):q for q in rows}
        missing=[{'original_question_number':str(n)+''.join('('+v+')' for v in path),'marks':v['marks'],'answer_regions':v['regions']} for (n,path),v in official.items() if (n,path) not in parsed]
        extra=[q['question_id'] for key,q in parsed.items() if key not in official]
        mismatch=[q['question_id'] for key,q in parsed.items() if key in official and q['marks']!=official[key]['marks']]
        report.append({'source_id':sid,'question_source_sha256':sources[sid]['sha256'],'answer_source_sha256':ms['sha256'],'cover_marks':ms['metadata']['cover_total_marks'],'qp_subparts':len(rows),'qp_marks':sum(q['marks'] or 0 for q in rows),'ms_subparts':len(official),'ms_marks':sum(v['marks'] for v in official.values()),'missing_qp_labels':missing,'missing_ms_labels':extra,'marks_mismatches':mismatch,'ms_parser_issues':issues,'source_integrity_issues':sources[sid]['metadata'].get('source_integrity_issues',[])})
    value={'pairs':len(report),'subparts':sum(r['qp_subparts'] for r in report),'papers':report}
    write_json(output,value)
    print(json.dumps({'pairs':len(report),'anomalies':[{k:v for k,v in r.items() if k not in ['question_source_sha256','answer_source_sha256']} for r in report if r['missing_qp_labels'] or r['missing_ms_labels'] or r['marks_mismatches'] or r['qp_marks']!=r['cover_marks'] or r['ms_marks']!=r['cover_marks']]},ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--snapshot',type=Path,required=True);p.add_argument('--sources',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();audit(a.snapshot,a.sources,a.output)
