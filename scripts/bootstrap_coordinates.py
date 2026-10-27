"""Maintainer one-time conversion; never needed by a new installation."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from bank.migration import convert_legacy
from bank.format import read_json,validate,write_json
if __name__=='__main__':
    legacy=ROOT/'question_bank/CIE/9701/AS'
    index,manifest,failures=convert_legacy(read_json(legacy/'index.json'),legacy)
    if failures:raise SystemExit(str(failures))
    validate(index,manifest,ROOT/'schemas')
    write_json(ROOT/'indexes/question-index.json',index)
    write_json(ROOT/'indexes/source-manifest.json',manifest)
    print(len(index['questions']),'questions',len(manifest['sources']),'sources; no exam text included')
