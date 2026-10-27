"""Original, synthetic PDF fixtures. No Cambridge content is included."""
import shutil
from pathlib import Path
import sys
import fitz
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from bank.format import COORDINATES,VERSION,geometry,sha256,write_json

def make_fixture(root):
    root=Path(root);root.mkdir(exist_ok=True,parents=True)
    shutil.copytree(ROOT/'schemas',root/'schemas',dirs_exist_ok=True)
    folder=root/'fixture-input';folder.mkdir(exist_ok=True)
    qp=folder/'original-qp.pdf';ms=folder/'original-ms.pdf'
    with fitz.open() as doc:
        for i in range(3):
            p=doc.new_page(width=600,height=800)
            p.insert_text((80,100),['AUTHORED QUESTION ONE - BEGIN','AUTHORED QUESTION ONE - CONTINUED','AUTHORED QUESTION TWO'][i],fontsize=13)
            p.draw_rect(fitz.Rect(90,120,240,160),color=(0,.5,.3))
            if i==0:p.set_cropbox(fitz.Rect(20,30,580,760));p.set_rotation(90)
        doc.save(qp,no_new_id=True)
    with fitz.open() as doc:
        for text in ['AUTHORED ANSWER ONE - 5 marks','2 B']:
            p=doc.new_page(width=600,height=800);p.insert_text((80,100),text,fontsize=13)
        doc.save(ms,no_new_id=True)
    sources=[]
    for role,path in [('qp',qp),('ms',ms)]:
        with fitz.open(path) as d:
            sources.append({'source_id':'fixture-'+role,'filename':path.name,'path':'sources/fixture/'+path.name,'sha256':sha256(path),'page_count':len(d),'pages':geometry(d),'metadata':{'role':role}})
    manifest={'schema_version':VERSION,'coordinate_system':COORDINATES,'sources':sources}
    questions=[]
    for n in [1,2]:
        questions.append({'question_id':'fixture-q'+str(n),'exam_board':'DEMO','qualification':'Example','subject_code':'DEMO','year':2024,'session':'Example','paper':2 if n==1 else 1,'variant':2,'original_question_number':str(n),'marks':5 if n==1 else 1,'topics':['example'],
            'question':{'source_id':'fixture-qp','regions':[{'page_index':0,'bbox':[40,50,530,170]},{'page_index':1,'bbox':[40,55,550,180]}] if n==1 else [{'page_index':2,'bbox':[40,55,550,180]}]},
            'answer':{'source_id':'fixture-ms','type':'regions' if n==1 else 'mcq','regions':[{'page_index':n-1,'bbox':[40,55,550,140]}]},
            'metadata':{'review_status':'pending_review','syllabus_mapping_status':'original_example'}})
    index={'schema_version':VERSION,'coordinate_system':COORDINATES,'bank_id':'fixture-bank','revision':'example.1','topics':[{'id':'example','name':'原创示例','english':'Original example'}],'questions':questions}
    write_json(root/'indexes/question-index.json',index);write_json(root/'indexes/source-manifest.json',manifest)
    return index,manifest,[qp,ms]

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    make_fixture(args.output.resolve())
    print('Created original example PDFs and matching indexes in',args.output)
