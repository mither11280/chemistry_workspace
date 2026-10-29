"""Re-measure one source pair without rescanning or altering other reviewed material."""
import argparse,copy,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from bank.format import read_json,write_json,validate
from rebuild_teaching_bank import build

def refresh(snapshot,paths_file,source_id,output):
    snapshot=Path(snapshot);output=Path(output)
    if output.exists():raise ValueError('Use a fresh output folder')
    index=read_json(snapshot/'question-index.json');manifest=read_json(snapshot/'source-manifest.json')
    overrides=read_json(ROOT/'indexes/teaching19-context-overrides.json')['questions']
    updated,_=build(copy.deepcopy(index),manifest,read_json(paths_file),output/'measured-pair',pairs=[source_id],context_overrides=overrides,papers=(4,))
    before=[q for q in index['questions'] if q['question']['source_id']==source_id];after=updated['questions']
    if not before or not after:raise ValueError('Refusing to replace a missing/empty pair')
    first=next(i for i,q in enumerate(index['questions']) if q['question']['source_id']==source_id)
    others=[q for q in index['questions'] if q['question']['source_id']!=source_id]
    index['questions']=others[:first]+after+others[first:]
    validate(index,manifest,ROOT/'schemas')
    records=read_json(snapshot/'candidates.private.json');old_ids={q['question_id'] for q in before}
    records=[r for r in records if r['question_id'] not in old_ids]+read_json(output/'measured-pair/candidates.private.json')
    write_json(output/'question-index.json',index);write_json(output/'source-manifest.json',manifest);write_json(output/'candidates.private.json',records)
    write_json(output/'refresh.json',{'source_id':source_id,'before_questions':len(before),'after_questions':len(after),'added_ids':sorted({q['question_id'] for q in after}-old_ids),'removed_ids':sorted(old_ids-{q['question_id'] for q in after})})
    print('Refreshed',source_id,'in',len(index['questions']),'units')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--snapshot',type=Path,required=True);p.add_argument('--sources',type=Path,required=True);p.add_argument('--source-id',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();refresh(a.snapshot,a.sources,a.source_id,a.output)
