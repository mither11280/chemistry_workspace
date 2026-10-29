"""Source-backed pilot: all subparts, shared material, vector output and mixed AS/A2."""
import argparse,json,shutil,sys,time
from pathlib import Path
import fitz
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from bank.format import read_json,write_json,validate
from bank.catalog import Catalog
from bank.sources import SourceStore
from bank.render import Renderer
from bank.teaching.worksheet import resolve

def verify(snapshot,paths,output):
    output=Path(output)
    if output.exists():raise ValueError('Use a fresh verification folder')
    output.mkdir(parents=True);resources=output/'resources';(resources/'indexes').mkdir(parents=True)
    index=read_json(Path(snapshot)/'question-index.json');manifest=read_json(Path(snapshot)/'source-manifest.json')
    pilot=list(index['questions']);assert len(pilot)==52 and sum(q['marks'] for q in pilot)==100
    assert all(q['paper']==4 and q['metadata']['teaching']['status']=='ready' for q in pilot)
    as_index=read_json(ROOT/'data/v051-as-trimmed-v2/question-index.json')
    as_samples=[q for q in as_index['questions'] if q['question_id'] in ['cie-9701-m24-12-q4','cie-9701-m24-22-q1-a']]
    assert len(as_samples)==2
    index['questions']+=as_samples;index['revision']='v051-pilot-acceptance'
    validate(index,manifest,ROOT/'schemas')
    write_json(resources/'indexes/question-index.json',index);write_json(resources/'indexes/source-manifest.json',manifest)
    shutil.copytree(ROOT/'schemas',resources/'schemas')
    paths=read_json(paths);needed={q[k]['source_id'] for q in index['questions'] for k in ['question','answer']}
    profile=output/'profile'
    for s in manifest['sources']:
        if s['source_id'] not in needed:continue
        dest=profile/s['path'];dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(paths[s['source_id']],dest)
    start=time.perf_counter();catalog=Catalog(profile,resources=resources);load=time.perf_counter()-start
    renderer=Renderer(catalog,SourceStore(profile,catalog));previews=[];start=time.perf_counter()
    for q in pilot:
        for kind in ['question','answer']:
            for n in range(len(q[kind]['regions'])):
                data=renderer.preview(q['question_id'],kind,n);assert data.startswith(b'RIFF')
                previews.append((q['question_id'],kind,n,data))
    cold=time.perf_counter()-start;start=time.perf_counter()
    for qid,kind,n,_ in previews:renderer.preview(qid,kind,n)
    warm=time.perf_counter()-start
    dependent=resolve(catalog,['cie-9701-m25-42-q1-c-ii'])
    assert dependent['question_ids']==['cie-9701-m25-42-q1-c-i','cie-9701-m25-42-q1-c-ii']
    assert catalog.search({'course':'AS'})['total']==2 and catalog.search({'course':'A2'})['total']==52
    for n in range(1,13):
        rows=catalog.search({'course':'A2','topic':f'a2-ch{n:02}'},limit=200)['questions']
        assert all(q['metadata']['teaching']['primary_chapter']==n for q in rows)
    exports={}
    for label,ids in [('season',[q['question_id'] for q in pilot]),('twenty',[q['question_id'] for q in pilot[:20]]),('mixed',[as_samples[0]['question_id'],'cie-9701-m25-42-q2-c-i',as_samples[1]['question_id'],'cie-9701-m25-42-q1-c-ii'])]:
        for kind in ['questions','answers']:
            start=time.perf_counter();pdf=renderer.export({'title':label,'question_ids':ids,'notes':'Complete every question.'},kind,output/'exports')
            elapsed=time.perf_counter()-start;mapping=read_json(pdf.with_suffix('.mapping.json'))
            assert [r['question_id'] for r in mapping]==resolve(catalog,ids)['question_ids']
            with fitz.open(pdf) as doc:
                assert all(p.get_text().strip() for p in doc)
                assert sum(len(p.get_fonts()) for p in doc)>0
                pages=len(doc)
                if label=='mixed':
                    thumbs=[]
                    for p in doc:
                        pix=p.get_pixmap(matrix=fitz.Matrix(.5,.5),alpha=False)
                        thumb=Image.frombytes('RGB',(pix.width,pix.height),pix.samples);thumb.thumbnail((295,420));thumbs.append(thumb)
                    contact=Image.new('RGB',(300*min(4,len(thumbs)),445*((len(thumbs)+3)//4)),'#ddd')
                    for j,img in enumerate(thumbs):contact.paste(img,(300*(j%4),445*(j//4)))
                    contact.save(output/(kind+'-contact.png'))
            exports[label+'-'+kind]={'seconds':round(elapsed,4),'bytes':pdf.stat().st_size,'pages':pages,'path':pdf.relative_to(output).as_posix()}
    # Browse every question and MS as a labelled contact sheet. These images are
    # inspection aids, not official stored content or a claim of human review.
    for kind in ['question','answer']:
        selected=[r for r in previews if r[1]==kind]
        for offset in range(0,len(selected),24):
            batch=selected[offset:offset+24];sheet=Image.new('RGB',(1200,350*((len(batch)+3)//4)),'#eee');draw=ImageDraw.Draw(sheet)
            for j,(qid,_,n,data) in enumerate(batch):
                import io
                img=Image.open(io.BytesIO(data));img.thumbnail((290,310));x=j%4*300;y=j//4*350
                sheet.paste(img,(x,y+28));draw.text((x+3,y+4),qid.replace('cie-9701-','')+f' r{n}',fill='black')
            sheet.save(output/f'{kind}-previews-{offset//24+1}.png')
    result={'status':'structural-checks-passed-awaiting-visual-inspection','subparts':52,'marks':100,'load_seconds':round(load,4),'preview_regions':len(previews),'cold_preview_seconds':round(cold,4),'warm_preview_seconds':round(warm,4),'exports':exports}
    write_json(output/'verification.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--snapshot',type=Path,required=True);p.add_argument('--sources',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();verify(a.snapshot,a.sources,a.output)
