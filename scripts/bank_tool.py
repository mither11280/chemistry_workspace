"""Local bank maintenance. No network access and no automatic PDF downloads."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from bank.format import read_json,validate

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    commands=parser.add_subparsers(dest='command',required=True)
    v=commands.add_parser('validate');v.add_argument('--index',type=Path);v.add_argument('--manifest',type=Path)
    commands.add_parser('check');commands.add_parser('rebuild');commands.add_parser('cache-clear')
    imp=commands.add_parser('import');imp.add_argument('paths',type=Path,nargs='+')
    m=commands.add_parser('migrate');m.add_argument('--legacy',type=Path,required=True)
    r=commands.add_parser('rollback');r.add_argument('--backup',type=Path,required=True)
    a=commands.add_parser('archive');a.add_argument('--legacy',type=Path,required=True);a.add_argument('--confirm',action='store_true',required=True)
    args=parser.parse_args();root=args.root.resolve()
    if args.command=='validate':
        validate(read_json(args.index or root/'indexes/question-index.json'),read_json(args.manifest or root/'indexes/source-manifest.json'),root/'schemas')
        print('Valid schema, references, page geometry and bounding boxes');return
    if args.command=='rollback':
        from bank.migration import rollback
        print(json.dumps(rollback(root,args.backup),ensure_ascii=False));return
    from bank.catalog import Catalog
    from bank.sources import SourceStore
    from bank.render import Renderer
    cat=Catalog(root);store=SourceStore(root,cat)
    if args.command=='check':result={'catalog':cat.check(),'sources':[{s['source_id']:store.status(s['source_id'])} for s in cat.manifest['sources']]}
    elif args.command=='rebuild':result=cat.rebuild(force=True);store.extract_local_content()
    elif args.command=='cache-clear':result=Renderer(cat,store).clean(clear=True)
    elif args.command=='migrate':
        from bank.migration import migrate
        result=migrate(root,args.legacy,cat,store)
    elif args.command=='archive':
        from bank.migration import archive_legacy
        # Verify every required original before moving legacy material.
        for q in cat.index['questions']:
            for kind in ['question','answer']:store.resolve(q[kind]['source_id'])
        result=archive_legacy(root,args.legacy,cat)
    elif args.command=='import':
        files=[]
        for path in args.paths:files.extend(path.rglob('*.pdf') if path.is_dir() else [path])
        result=[]
        for path in files:
            try:result.append(store.import_file(path,extract=False))
            except ValueError as e:result.append({'filename':str(path),'error':str(e)})
        store.extract_local_content()
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
