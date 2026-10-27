"""Compatibility entry point: migrate coordinates instead of making per-question PDFs."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from bank.catalog import Catalog
from bank.sources import SourceStore
from bank.migration import migrate
if __name__=='__main__':
    catalog=Catalog(ROOT)
    print(migrate(ROOT,ROOT/'data',catalog,SourceStore(ROOT,catalog)))
