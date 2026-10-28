"""Render original coordinate regions for maintainer inspection; never changes source PDFs."""
import argparse,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
import fitz
from bank.format import read_json,sha256,normalized_page
from bank.pdf_layout import rotation
p=argparse.ArgumentParser(description=__doc__);p.add_argument('question_id');p.add_argument('--workdir',type=Path,default=ROOT/'data/teaching19');p.add_argument('--sources',type=Path,default=ROOT/'data/import-v04/all-source-files.private.json');p.add_argument('--kind',choices=['question','answer'],default='question');p.add_argument('--output',type=Path,default=Path('/tmp/teaching-peek'));a=p.parse_args()
i=read_json(a.workdir/'question-index.json');m=read_json(a.workdir/'source-manifest.json');q=next(q for q in i['questions'] if q['question_id']==a.question_id);block=q[a.kind];s=next(s for s in m['sources'] if s['source_id']==block['source_id']);path=Path(read_json(a.sources)[s['source_id']]);assert sha256(path)==s['sha256'];a.output.mkdir(parents=True,exist_ok=True)
with fitz.open(path) as d:
 for n,r in enumerate(block['regions']):
  pg=normalized_page(d,r['page_index']);pix=pg.get_pixmap(matrix=fitz.Matrix(1.35,1.35).prerotate(rotation(d,r['page_index'])),clip=fitz.Rect(r['bbox']),alpha=False);out=a.output/(a.question_id+'-'+a.kind+'-'+str(n)+'.png');pix.save(out);print(out)
