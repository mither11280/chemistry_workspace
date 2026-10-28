"""Verified immutable source files and user-initiated batch import."""
import json
import os
import shutil
import tempfile
from pathlib import Path
import fitz
from .format import SourceError, geometry, normalized_page, safe_path, sha256

class SourceStore:
    def __init__(self,root,catalog):
        self.root=Path(root).resolve();self.catalog=catalog;self._verified={}

    def resolve(self,source_id):
        return self._resolve_record(self.catalog.source(source_id))

    def _resolve_record(self,s):
        source_id=s['source_id'];path=safe_path(self.root,s['path'])
        if not path.is_file():raise SourceError('缺少原卷，请导入 '+s['filename'])
        stat=path.stat();key=(str(path),stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns,stat.st_ino,s['sha256'])
        if self._verified.get(source_id)!=key:
            if sha256(path)!=s['sha256']:raise SourceError('源文件哈希不匹配，拒绝使用坐标: '+s['filename'])
            with fitz.open(path) as d:
                if d.needs_pass:raise SourceError('暂不支持加密 PDF')
                if geometry(d)!=s['pages']:raise SourceError('页面几何与索引不一致: '+s['filename'])
            self._verified[source_id]=key
        return path

    def status(self,source_id):
        try:
            self.resolve(source_id);return {'state':'ready','message':'已校验'}
        except SourceError as e:
            return {'state':'missing' if '缺少' in str(e) else 'mismatch','message':str(e)}

    def import_file(self,path,filename=None,extract=True):
        path=Path(path);name=filename or path.name;digest=sha256(path)
        sources=self.catalog.manifest['sources'];matches=[s for s in sources if s['sha256']==digest]
        if not matches:
            named=any(s['filename']==name for s in sources)
            raise SourceError(('同名文件版本不符: ' if named else '该 PDF 不在当前 Source Manifest 中: ')+name)
        with fitz.open(path) as d:
            if d.needs_pass:raise SourceError('不支持加密 PDF')
            pages=geometry(d)
        results=[]
        for s in matches:
            if pages!=s['pages']:raise SourceError('PDF 页面几何与 manifest 不同')
            target=safe_path(self.root,s['path']);target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists() and sha256(target)!=digest:raise SourceError('目标存在不同内容，不覆盖。请先移走错误文件: '+str(target.relative_to(self.root)))
            if not target.exists():
                fd,temp=tempfile.mkstemp(dir=target.parent,suffix='.pdf');os.close(fd)
                try:
                    shutil.copyfile(path,temp)
                    if sha256(temp)!=digest:raise SourceError('复制校验失败')
                    os.replace(temp,target)
                finally:
                    if Path(temp).exists():Path(temp).unlink()
            self.resolve(s['source_id']);results.append(s['source_id'])
        if extract:self.extract_local_content(set(results))
        return {'filename':name,'source_ids':results,'state':'ready'}

    def ensure_local_content(self):
        """Index already present PDFs after a generation switch, once per material.

        Bundled assets may all exist from the old generation, so copying no new
        files does not imply the new SQLite catalog already contains their text.
        """
        with self.catalog.connect() as c:
            rows=c.execute('SELECT q.payload,l.source_hash FROM questions q LEFT JOIN local_content l USING(question_id)').fetchall()
        source_map={s['source_id']:s for s in self.catalog.manifest['sources']};needed=set()
        for row in rows:
            q=json.loads(row['payload']);sid=q['question']['source_id']
            if row['source_hash']!=source_map[sid]['sha256']:needed.add(sid)
        available=set()
        for sid in needed:
            try:self.resolve(sid);available.add(sid)
            except SourceError:continue
        if available:self.extract_local_content(available)
        return available

    def extract_local_content(self,source_ids=None):
        # Copyright text and MCQ answers stay exclusively in the ignored local catalog.
        with self.catalog.connect() as c:
            rows=c.execute('SELECT payload FROM questions').fetchall()
            # Snapshot source records before the write transaction. A second connection
            # can deadlock once a large local_content transaction spills SQLite pages.
            sources={r['source_id']:json.loads(r['payload']) for r in c.execute('SELECT * FROM sources')}
        documents={}
        try:
            with self.catalog.connect() as c:
                for row in rows:
                    q=json.loads(row[0]);block=q['question'];sid=block['source_id']
                    if source_ids and sid not in source_ids and q['answer']['source_id'] not in source_ids:continue
                    try:
                        if sid not in documents:documents[sid]=fitz.open(self._resolve_record(sources[sid]))
                        text='\n'.join(normalized_page(documents[sid],r['page_index']).get_text(clip=fitz.Rect(r['bbox'])) for r in block['regions'])
                    except SourceError:continue
                    answer=None;answer_hash=None
                    if q['answer']['type']=='mcq':
                        try:
                            a=q['answer'];msid=a['source_id']
                            if msid not in documents:documents[msid]=fitz.open(self._resolve_record(sources[msid]))
                            tokens=' '.join(normalized_page(documents[msid],r['page_index']).get_text(clip=fitz.Rect(r['bbox'])) for r in a['regions']).split()
                            candidates=[x for x in tokens if x in ['A','B','C','D']]
                            if len(candidates)==1:answer=candidates[0];answer_hash=sources[msid]['sha256']
                        except SourceError:pass
                    c.execute('INSERT OR REPLACE INTO local_content(question_id,source_hash,text,answer_value,answer_hash) VALUES (?,?,?,?,?)',(q['question_id'],sources[sid]['sha256'],text,answer,answer_hash))
                self.catalog._refresh_search(c)
        finally:
            for d in documents.values():d.close()
