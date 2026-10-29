"""Register local Paper 4 sources by cover identity, exact hash and conservative equivalence."""
import argparse,collections,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from bank.format import read_json,write_json,sha256
from bank.importer.identity import identify
from bank.importer.equivalence import fingerprint
from bank.importer.inventory import exam_status


def scan(corpus,base_manifest,base_paths,output,reviews=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=True);groups=collections.defaultdict(list);rejected=[];reviews=reviews or {}
    for p in sorted(Path(corpus).rglob('*.pdf')):
        if not re.search(r'(?:_(?:qp|ms)_4[123]|9701-4[123]_).*\.pdf$',p.name,re.I):continue
        years=re.findall(r'20\d{2}',str(p.relative_to(corpus)))
        if years and not 2018<=int(years[0])<=2026:continue
        try:
            review=reviews.get(sha256(p),{})
            ident,source=identify(p,allow_page_count_mismatch=review.get('allow_page_count_mismatch',False))
            if review:source['metadata']['source_selection_review']=review
            if ident.paper!=4 or not 2018<=ident.year<=2026:continue
            groups[(ident.year,ident.session_code,ident.variant,ident.kind)].append((p,source))
        except Exception as e:rejected.append({'filename':p.name,'sha256':sha256(p),'issue':str(e)})
    sources=[];paths=dict(base_paths);records=[];pairs=[]
    for y,se,v in sorted({k[:3] for k in groups}):
        chosen={};problems=[]
        for role in ['qp','ms']:
            rows=groups.get((y,se,v,role),[]);by_hash={s['sha256']:(p,s) for p,s in rows}
            if not rows:problems.append('missing_'+role);continue
            signatures={fingerprint(p,s['sha256'],output/'equivalence-cache') for p,s in by_hash.values()} if len(by_hash)>1 else {next(iter(by_hash))}
            reviewed=[(p,s) for p,s in rows if reviews.get(s['sha256'],{}).get('select_canonical')]
            if len(signatures)!=1 and len(reviewed)!=1:problems.append('different_content_versions_'+role);continue
            p,s=min(reviewed or rows,key=lambda r:('_alt' in r[0].name.lower(),not r[0].name.startswith('9701_'),r[0].name))
            s['metadata'].update(qualification='A2',exam_series_status=exam_status(y,se),syllabus_version='2025-2027' if y in [2025,2026] else None)
            s['metadata']['source_aliases']=[{'filename':f.name,'sha256':a['sha256']} for f,a in rows if f!=p]
            chosen[role]=(p,s)
        row={'year':y,'session_code':se,'paper':4,'variant':v,'issues':problems,'selected':{k:s['source_id'] for k,(p,s) in chosen.items()}};records.append(row)
        if problems:continue
        for p,s in chosen.values():sources.append(s);paths[s['source_id']]=str(p.resolve())
        pairs.append(chosen['qp'][1]['source_id'])
    manifest=dict(base_manifest,sources=base_manifest['sources']+sources)
    write_json(output/'source-manifest.json',manifest);write_json(output/'source-files.private.json',paths)
    report={'source_pairs':len(pairs),'new_sources':len(sources),'pairs':records,'rejected':rejected,'qp_source_ids':pairs}
    write_json(output/'inventory.json',report);print(json.dumps({'pairs':len(pairs),'sources':len(sources),'rejected':rejected,'conflicts':[r for r in records if r['issues']]},ensure_ascii=False,indent=2))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--corpus',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reviews',type=Path);a=p.parse_args()
    scan(a.corpus,read_json(ROOT/'indexes/source-manifest.json'),read_json(ROOT/'data/import-v04/all-source-files.private.json'),a.output,read_json(a.reviews) if a.reviews else None)
