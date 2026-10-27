#!/usr/bin/env python3
"""Maintainer CLI. All import, validation and update logic is in app/bank/."""
from pathlib import Path
from datetime import date
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from bank.format import read_json,DataError
from bank.catalog import Catalog
from bank.importer.engine import analyze
from bank.updates import build_package,install_package,rollback

def main(argv=None):
    p=argparse.ArgumentParser(description='CIE 9701 bank maintainer: analyze, package, install, rollback. No personal jobs are modified.')
    p.add_argument('--resources',type=Path,default=ROOT)
    sub=p.add_subparsers(dest='command',required=True)
    inv=sub.add_parser('inventory');inv.add_argument('corpus',type=Path);inv.add_argument('--base',type=Path);inv.add_argument('--output',type=Path,required=True);inv.add_argument('--as-of',default=date.today().isoformat())
    a=sub.add_parser('analyze');a.add_argument('pdfs',nargs='+',type=Path);a.add_argument('--workdir',type=Path,required=True);a.add_argument('--revision',required=True);a.add_argument('--overrides',type=Path);a.add_argument('--base',type=Path,help='Directory containing question-index.json + source-manifest.json; defaults to resources/indexes')
    b=sub.add_parser('package');b.add_argument('--workdir',type=Path,required=True);b.add_argument('--base',type=Path);b.add_argument('--output',type=Path,required=True);b.add_argument('--changelog',required=True);b.add_argument('--minimum-app-version',default='0.4.0');b.add_argument('--include-sources',action='store_true');b.add_argument('--authorization',type=Path)
    c=sub.add_parser('install');c.add_argument('package',type=Path);c.add_argument('--home',type=Path,required=True);c.add_argument('--sha256',required=True)
    d=sub.add_parser('rollback');d.add_argument('backup_id');d.add_argument('--home',type=Path,required=True)
    args=p.parse_args(argv);schemas=args.resources/'schemas';base=getattr(args,'base',None) or args.resources/'indexes'
    if args.command=='inventory':
        from bank.importer.inventory import scan
        inventory,_=scan(args.corpus,read_json(base/'question-index.json'),read_json(base/'source-manifest.json'),args.output,args.as_of);result=inventory['summary']
    elif args.command=='analyze':
        _,_,result=analyze(args.pdfs,args.workdir,read_json(base/'question-index.json'),read_json(base/'source-manifest.json'),schemas,args.revision,args.overrides)
    elif args.command=='package':
        result=build_package(args.output,read_json(args.workdir/'question-index.json'),read_json(args.workdir/'source-manifest.json'),read_json(base/'question-index.json'),read_json(base/'source-manifest.json'),schemas,args.changelog,read_json(args.workdir/'source-files.private.json') if args.include_sources else None,read_json(args.authorization) if args.authorization else None,args.minimum_app_version)
    elif args.command=='install':result=install_package(Catalog(args.home,resources=args.resources),args.package,args.sha256)
    else:result=rollback(Catalog(args.home,resources=args.resources),args.backup_id)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (DataError,OSError) as exc:print(str(exc),file=sys.stderr);raise SystemExit(2)
