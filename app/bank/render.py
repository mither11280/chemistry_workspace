"""On-demand previews and vector export. Cache is disposable and never authoritative."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import uuid
import fitz
from PIL import Image
from .format import DataError, SourceError, normalized_page, sha256

RENDER_VERSION='webp-crop-v1'

class Renderer:
    def __init__(self,catalog,sources,cache=None,max_cache_bytes=128*1024*1024):
        self.catalog=catalog;self.sources=sources
        self.cache=Path(cache or catalog.data/'cache/webp');self.cache.mkdir(parents=True,exist_ok=True)
        self.max_cache_bytes=max_cache_bytes;self.lock=threading.RLock()

    def legacy(self,qid,kind):
        with self.catalog.connect() as c:row=c.execute('SELECT payload FROM legacy WHERE question_id=?',(qid,)).fetchone()
        if not row:raise SourceError('此题没有可用旧 PDF')
        old=json.loads(row[0]);path=Path(old.get('legacy_paths',{}).get(kind,''))
        if not path.is_file():raise SourceError('旧 PDF 文件缺失，需校准原卷区域')
        expected=old.get('file_sha256',{}).get(kind)
        if expected and sha256(path)!=expected:raise SourceError('旧 PDF 哈希不匹配')
        with fitz.open(path) as d:regions=[{'page_index':i,'bbox':list(p.rect)} for i,p in enumerate(d)]
        return path,regions,sha256(path),'legacy'

    def material(self,qid,kind):
        if kind not in ['question','answer']:raise DataError('无效内容类型')
        q=self.catalog.question(qid)
        if 'question_id' not in q:return self.legacy(qid,kind)
        block=q[kind]
        try:return self.sources.resolve(block['source_id']),block['regions'],self.catalog.source(block['source_id'])['sha256'],'coordinates'
        except SourceError as e:
            # A mismatched source must never silently downgrade. Missing sources may use explicitly marked legacy PDFs.
            if '缺少' not in str(e):raise
            try:return self.legacy(qid,kind)
            except SourceError:raise e

    def availability(self,qid):
        result={}
        for kind in ['question','answer']:
            try:
                _,_,_,mode=self.material(qid,kind);result[kind]={'state':mode,'message':'旧 PDF · 待校准' if mode=='legacy' else '原卷已校验'}
            except SourceError as e:result[kind]={'state':'missing' if '缺少' in str(e) else 'mismatch','message':str(e)}
        return result

    def preview(self,qid,kind,index=0,scale=1.6,use_cache=True):
        path,regions,digest,mode=self.material(qid,kind)
        if index<0 or index>=len(regions):raise DataError('区域编号超出范围')
        region=regions[index]
        key=hashlib.sha256(json.dumps([RENDER_VERSION,qid,kind,digest,regions,index,scale,mode],sort_keys=True).encode()).hexdigest()
        target=self.cache/(key+'.webp')
        with self.lock:
            # Always verify the original before returning a cached thumbnail.
            if use_cache and target.exists():
                os.utime(target,None);return target.read_bytes()
            with fitz.open(path) as doc:
                page=normalized_page(doc,region['page_index'])
                pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale),clip=fitz.Rect(region['bbox']),alpha=False,colorspace=fitz.csRGB)
                output=io.BytesIO();Image.frombytes('RGB',[pix.width,pix.height],pix.samples).save(output,format='WEBP',quality=88,method=4)
                data=output.getvalue()
            if use_cache:
                fd,temp=tempfile.mkstemp(dir=self.cache)
                try:
                    with os.fdopen(fd,'wb') as stream:stream.write(data)
                    os.replace(temp,target)
                finally:
                    if Path(temp).exists():Path(temp).unlink()
                self.clean()
            return data

    def clean(self,clear=False):
        with self.lock:
            files=sorted(self.cache.glob('*.webp'),key=lambda p:p.stat().st_mtime)
            total=sum(p.stat().st_size for p in files);removed=0
            for p in files:
                if clear or total>self.max_cache_bytes:
                    size=p.stat().st_size;p.unlink();total-=size;removed+=1
            return {'bytes':total,'files':len(files)-removed,'removed':removed,'limit_bytes':self.max_cache_bytes}

    def page_preview(self,sid,page_index):
        path=self.sources.resolve(sid)
        with fitz.open(path) as d:
            if page_index<0 or page_index>=len(d):raise DataError('页面编号超出范围')
            page=normalized_page(d,page_index)
            scale=min(1.5,1100/page.rect.width)
            return page.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False).tobytes('png')

    def export(self,job,kind,output_dir):
        if kind not in ['questions','answers']:raise DataError('无效导出类型')
        if not job['question_ids']:raise DataError('请先加入题目')
        output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
        answer=kind=='answers';title=job['title'];mapping=[]
        with contextlib.ExitStack() as stack:
            doc=stack.enter_context(fitz.open());opened={}
            def source(path):
                if path not in opened:opened[path]=stack.enter_context(fitz.open(path))
                return opened[path]
            def new_page(header,landscape=False):
                p=doc.new_page(width=841.89 if landscape else 595.28,height=595.28 if landscape else 841.89)
                p.insert_textbox(fitz.Rect(42,24,p.rect.width-42,47),header,fontname='china-s',fontsize=11,color=(.16,.22,.25))
                p.draw_line((42,51),(p.rect.width-42,51),color=(.8,.83,.84),width=.5)
                return p
            page=new_page('CIE AS Chemistry 9701 | '+('Mark scheme' if answer else 'Worksheet'))
            page.insert_textbox(fitz.Rect(42,88,553,165),title,fontname='china-s',fontsize=24)
            questions=[self.catalog.question(qid) for qid in job['question_ids']]
            total=sum(q.get('marks') or 0 for q in questions)
            page.insert_text((42,190),f"{len(questions)} questions / {total:g} marks",fontsize=12)
            page.insert_textbox(fitz.Rect(42,220,553,285),'教师试用稿：题图与分类尚待逐题复核。请核对后使用。\n保留原题编号；Assignment 编号对应本作业题序。',fontname='china-s',fontsize=11)
            if not answer:page.insert_text((42,315),'Name: ____________________    Class: _______________',fontsize=11)
            if job.get('notes'):page.insert_textbox(fitz.Rect(42,350,553,490),job['notes'],fontname='china-s',fontsize=11)
            y=515
            for idx,(qid,q) in enumerate(zip(job['question_ids'],questions),1):
                path,regions,_,mode=self.material(qid,'answer' if answer else 'question');src=source(path)
                number=q.get('original_question_number',q.get('number'));variant=str(q['paper'])+str(q['variant']) if 'question_id' in q else str(q['variant'])
                label=f"Assignment {idx} | {q['year']} {q.get('session','March')} 9701/{variant} Q{number} | {q['marks']} marks"
                mapping.append({'assignment_number':idx,'question_id':qid,'original_question_number':str(number),'mode':mode})
                value=None
                if answer and 'question_id' in q and q['answer'].get('type')=='mcq' and mode=='coordinates':
                    # Verify both expected sources before trusting a locally extracted answer.
                    self.sources.resolve(q['answer']['source_id']);self.sources.resolve(q['question']['source_id'])
                    with self.catalog.connect() as c:r=c.execute('SELECT answer_value,source_hash,answer_hash FROM local_content WHERE question_id=?',(qid,)).fetchone()
                    if r and r['source_hash']==self.catalog.source(q['question']['source_id'])['sha256'] and r['answer_hash']==self.catalog.source(q['answer']['source_id'])['sha256']:value=r['answer_value']
                if value:
                    if y+65>785:page=new_page(title);y=70
                    page.insert_text((42,y+11),label,fontsize=9);page.insert_text((56,y+39),f'{idx}.  {value}',fontsize=14);y+=65
                    continue
                for ri,r in enumerate(regions):
                    sp=normalized_page(src,r['page_index']);clip=fitz.Rect(r['bbox']);width=511;height=clip.height*width/clip.width
                    if height>680:width*=680/height;height=680
                    if y+height+45>785:page=new_page(title);y=70
                    page.insert_text((42,y+11),label+(' (continued)' if ri else ''),fontsize=9,color=(.2,.35,.35));y+=25
                    page.show_pdf_page(fitz.Rect(42,y,42+width,y+height),src,r['page_index'],clip=clip,keep_proportion=True)
                    y+=height+22
            seen=set()
            for q in questions:
                if 'question_id' not in q:continue
                block=q['answer' if answer else 'question'];sid=block['source_id']
                if sid in seen:continue
                seen.add(sid);s=self.catalog.source(sid)
                # Source references are explicit metadata, no hidden layout heuristics in export.
                refs=s['metadata'].get('references',[])
                if not refs:continue
                try:src=source(self.sources.resolve(sid))
                except SourceError:
                    # Legacy fallback can export when originals are absent, but clearly marks missing references.
                    page=new_page('Source reference unavailable')
                    page.insert_textbox(fitz.Rect(42,80,553,200),'缺少原卷参考数据：'+s['filename'],fontname='china-s',fontsize=12)
                    continue
                for r in refs:
                    normalized_page(src,r['page_index']);rotate=r.get('rotate',0);clip=fitz.Rect(r['bbox'])
                    page=new_page('Source reference | '+s['filename'],landscape=rotate in [90,270] or clip.width>clip.height)
                    page.show_pdf_page(fitz.Rect(35,65,page.rect.width-35,page.rect.height-45),src,r['page_index'],clip=clip,rotate=rotate)
            for i,page in enumerate(doc):
                page.insert_text((42,page.rect.height-25),'TEACHER REVIEW DRAFT - Original content: Cambridge / UCLES',fontsize=7,color=(.45,.48,.5))
                page.insert_text((page.rect.width-85,page.rect.height-25),f'{i+1} / {len(doc)}',fontsize=8)
            out=output_dir/(uuid.uuid4().hex+'_'+kind+'.pdf')
            doc.save(out,garbage=4,deflate=True)
        out.with_suffix('.mapping.json').write_text(json.dumps(mapping,ensure_ascii=False,indent=2),encoding='utf-8')
        return out
