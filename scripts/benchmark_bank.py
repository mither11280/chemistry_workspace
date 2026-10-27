"""Measure the actual available 132-question batch. No synthetic performance claims."""
import argparse
import contextlib
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
import fitz
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from bank.catalog import Catalog
from bank.sources import SourceStore
from bank.render import Renderer
from bank.format import read_json,sha256,write_json

def size(path):return sum(p.stat().st_size for p in Path(path).rglob('*') if p.is_file())
def timing(call,n=1):
    values=[];result=None
    for _ in range(n):
        start=time.perf_counter();result=call();values.append((time.perf_counter()-start)*1000)
    return round(statistics.median(values),3),result

class OldRenderer(Renderer):
    def __init__(self,*args,old_root,**kwargs):
        super().__init__(*args,**kwargs);self.old_root=Path(old_root)
        self.old={q['id']:q for q in read_json(self.old_root/'index.json')['questions']}
    def material(self,qid,kind):
        path=self.old_root/self.old[qid]['files'][kind]
        with fitz.open(path) as doc:regions=[{'page_index':i,'bbox':list(p.rect)} for i,p in enumerate(doc)]
        return path,regions,sha256(path),'legacy'

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--legacy',type=Path,default=ROOT/'question_bank/CIE/9701/AS');args=parser.parse_args()
    old=args.legacy.resolve()
    with tempfile.TemporaryDirectory(prefix='bank-benchmark-') as temp:
        data=Path(temp)/'data'
        build_ms,cat=timing(lambda:Catalog(ROOT,data))
        load_ms,_=timing(lambda:Catalog(ROOT,data),5)
        store=SourceStore(ROOT,cat)
        # Verify all originals; local extraction stays in the temporary catalog.
        verify_ms,_=timing(lambda:[store.resolve(s['source_id']) for s in cat.manifest['sources']])
        extract_ms,_=timing(lambda:store.extract_local_content())
        renderer=Renderer(cat,store,cache=Path(temp)/'cache')
        old_renderer=OldRenderer(cat,store,cache=Path(temp)/'old-cache',old_root=old)
        ids=[f'cie-9701-m25-12-q{i}' for i in range(1,17)]+['cie-9701-m24-22-q2','cie-9701-m25-22-q1','cie-9701-m25-22-q4','cie-9701-m26-22-q4']
        preview_ids=['cie-9701-m25-12-q3','cie-9701-m25-22-q4']
        old_load_ms,_=timing(lambda:{q['id']:q for q in read_json(old/'index.json')['questions']},5)
        def legacy_png(qid):
            path,regions,_,_=old_renderer.material(qid,'question');r=regions[0]
            with fitz.open(path) as d:return d[r['page_index']].get_pixmap(matrix=fitz.Matrix(1.6,1.6),clip=fitz.Rect(r['bbox']),alpha=False).tobytes('png')
        previews={}
        for qid in preview_ids:
            cold,_=timing(lambda:renderer.preview(qid,'question',use_cache=False),5)
            renderer.preview(qid,'question')
            warm,_=timing(lambda:renderer.preview(qid,'question'),5)
            old_ms,_=timing(lambda:legacy_png(qid),5)
            previews[qid]={'coordinates_uncached_ms':cold,'webp_cache_ms':warm,'legacy_png_uncached_ms':old_ms}
        job={'title':'20 question benchmark','question_ids':ids,'notes':'Actual sample: 16 MCQ and 4 structured questions.'}
        new_export_ms,newout=timing(lambda:renderer.export(job,'questions',Path(temp)/'new-exports'),3)
        old_export_ms,oldout=timing(lambda:old_renderer.export(job,'questions',Path(temp)/'old-exports'),3)
        answer_ms,answers=timing(lambda:renderer.export(job,'answers',Path(temp)/'answer-exports'),3)
        # Cache every question's first block, as in the list view, not all answer/continuation pages.
        cache_ms,_=timing(lambda:[renderer.preview(q['question_id'],'question') for q in cat.index['questions']])
        sources_bytes=sum(store.resolve(s['source_id']).stat().st_size for s in cat.manifest['sources'])
        json_bytes=(ROOT/'indexes/question-index.json').stat().st_size+(ROOT/'indexes/source-manifest.json').stat().st_size
        catalog_bytes=cat.path.stat().st_size
        old_cuts=sum((old/q['files'][kind]).stat().st_size for q in read_json(old/'index.json')['questions'] for kind in ['question','answer'])
        result={'sample':{'questions':len(cat.index['questions']),'sources':len(cat.manifest['sources']),'export_questions':20,'export_composition':'16 MCQ + 4 structured; 2024-2026 March; 3 median runs'},
            'bytes':{'legacy_total':size(old),'legacy_cut_pdfs_only':old_cuts,'original_pdfs':sources_bytes,'public_json':json_bytes,'catalog_with_local_text':catalog_bytes,'new_total_without_cache':sources_bytes+json_bytes+catalog_bytes,'webp_first_block_all_132':size(renderer.cache),'new_total_with_cache':sources_bytes+json_bytes+catalog_bytes+size(renderer.cache),'new_export_questions':newout.stat().st_size,'legacy_export_questions':oldout.stat().st_size,'new_export_answers':answers.stat().st_size},
            'milliseconds':{'legacy_json_read_and_id_map_median5':old_load_ms,'first_catalog_build':build_ms,'existing_catalog_load_median5':load_ms,'verify_all_sources':verify_ms,'extract_all_local_text':extract_ms,'generate_132_first_block_cache':cache_ms,'search_filter_median20':timing(lambda:cat.search({'topic':'atomic','year':2025}),20)[0],'new_export20_median3':new_export_ms,'legacy_export20_median3':old_export_ms,'new_answer_export20_median3':answer_ms},'previews':previews,
            'limits':['Single Mac; one measured run, process/OS caches not forcibly flushed.','Existing legacy batch has 132 questions; results do not predict a full historical corpus.','PDF clip may retain hidden resources outside visible rectangles. Exports are not redacted or sanitized PDFs.','Public JSON carries no question text; local FTS extraction is included in catalog size.','Old JSON load does not perform schema or geometry validation; new load includes validation and SQLite setup. Preview encodings differ: old PNG versus new WebP.',
                'Legacy export uses the same pagination engine and original reference appendices for an apples-to-apples storage comparison.']}
        output=ROOT/'docs/benchmark-results.json';write_json(output,result);print(json.dumps(result,ensure_ascii=False,indent=2))
        # Persist one pair for visual QA only, in ignored output directory.
        import shutil
        dest=ROOT/'exports/benchmark';dest.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(newout,dest/'coordinates-20-questions.pdf');shutil.copyfile(answers,dest/'coordinates-20-answers.pdf')
if __name__=='__main__':main()
