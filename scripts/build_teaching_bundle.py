"""Build the v0.5 full offline asset package for an already installed teaching index.

The App and public Git checkout carry the complete teaching index. This package
adds verified source PDFs without crossing a bank generation or deleting IDs.
It advances the revision by an explicit asset suffix and uses ordinary update
validation, backup and activation. Old App users must first install v0.5.
"""
import argparse,copy,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from bank.format import read_json,write_json
from bank.teaching.taxonomy import BANK_ID
from bank.updates import build_package,required_reader


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot',type=Path,default=ROOT/'indexes')
    p.add_argument('--sources',type=Path,required=True,help='Private source_id to local PDF path map')
    p.add_argument('--authorization',type=Path,required=True,help='Explicit redistribution grant and SHA-256 allowlist')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--revision',help='Defaults to the public index revision plus .assets.1')
    p.add_argument('--previous-manifest',type=Path,help='Optional: include only source hashes absent from this previous full installation; still carries the complete new index')
    a=p.parse_args();start=time.perf_counter()
    base=read_json(a.snapshot/'question-index.json');manifest=read_json(a.snapshot/'source-manifest.json')
    if base['bank_id']!=BANK_ID:raise ValueError('Install/build the new teaching generation before its asset bundle')
    if any('value' in q['answer'] for q in base['questions']):raise ValueError('Public teaching index must not embed official MCQ answers')
    files=read_json(a.sources);missing=[s['source_id'] for s in manifest['sources'] if s['source_id'] not in files]
    if missing:raise ValueError('Full bundle is missing registered sources: '+', '.join(missing))
    if a.previous_manifest:
        previous={s['source_id']:s['sha256'] for s in read_json(a.previous_manifest)['sources']}
        files={s['source_id']:files[s['source_id']] for s in manifest['sources'] if previous.get(s['source_id'])!=s['sha256']}
    index=copy.deepcopy(base);index['revision']=a.revision or base['revision']+'.assets.1'
    minimum='.'.join(map(str,max(required_reader(index),(0,5,1) if any(q['paper']==4 for q in index['questions']) else (0,5,0))))
    result=build_package(a.output,index,manifest,base,manifest,ROOT/'schemas',
                         '完整离线题库资料包：安装已登记的原卷与评分标准。保持当前教学代际及稳定题目ID。',
                         source_files=files,authorization=read_json(a.authorization),minimum_app_version=minimum)
    result['path']=a.output.name
    result.update(bank_id=BANK_ID,base_revision=base['revision'],questions=len(index['questions']),
                  ready=sum(q['metadata']['teaching']['status']=='ready' for q in index['questions']),
                  source_files=len(files),registered_sources=len(manifest['sources']),delta=bool(a.previous_manifest),seconds=round(time.perf_counter()-start,3))
    write_json(a.output.with_suffix('.report.json'),result)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
