"""Restore an archived personal-data generation. Quit the App before running."""
import argparse,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from bank.teaching.generation import restore
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--home',type=Path,required=True);p.add_argument('archive_id');a=p.parse_args();print(json.dumps(restore(a.home,a.archive_id),ensure_ascii=False,indent=2))
