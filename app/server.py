"""Local HTTP boundary. Portable data, catalog and PDF engines live in bank/."""
import base64
import json
import os
import re
import sqlite3
import sys
import tempfile
import threading
import time
import uuid
import zlib
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
from bank.catalog import Catalog
from bank.sources import SourceStore
from bank.render import Renderer
from bank.format import DataError, SourceError, write_json
from bank.calibration import calibrate
from bank.feedback import build_report
from bank.updates import inspect_package,install_package
from bank.format import sha256
from runtime import RuntimePaths

PATHS=RuntimePaths.discover();PATHS.prepare()
ROOT=PATHS.home;RESOURCES=PATHS.resources
DATA=ROOT/'data';DATA.mkdir(parents=True,exist_ok=True)
EXPORTS=ROOT/'exports';EXPORTS.mkdir(exist_ok=True)
CATALOG=Catalog(ROOT,resources=RESOURCES);SOURCES=SourceStore(ROOT,CATALOG);RENDERER=Renderer(CATALOG,SOURCES)
DB=Path(os.environ.get('QUESTION_BANK_DB',str(DATA/'personal.sqlite3')))
MUTATION_LOCK=threading.RLock()

def connection():
    DB.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(DB,timeout=30);c.row_factory=sqlite3.Row
    version=c.execute('PRAGMA user_version').fetchone()[0]
    if version>1:c.close();raise DataError('个人作业数据库版本较新，不能降级')
    c.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY,title TEXT NOT NULL,body TEXT NOT NULL,updated REAL NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS draft (slot INTEGER PRIMARY KEY,body TEXT NOT NULL)')
    if version==0:c.execute('PRAGMA user_version=1')
    return c
with connection():pass

def validate_job(job):
    if not isinstance(job,dict):raise DataError('作业格式不正确')
    ids=job.get('question_ids',[])
    if not isinstance(ids,list) or len(ids)>200 or any(not isinstance(x,str) for x in ids):raise DataError('每份作业最多 200 题')
    if len(ids)!=len(set(ids)):raise DataError('一份作业不能重复加入同一题')
    from bank.teaching.worksheet import resolve
    resolved=resolve(CATALOG,ids)
    ids=resolved['question_ids']
    title=job.get('title','未命名作业')
    if not isinstance(title,str) or len(title)>120:raise DataError('作业名称最多 120 个字符')
    return {'title':title.strip() or '未命名作业','question_ids':ids,'notes':str(job.get('notes',''))[:2000]}

def source_hashes(job):
    hashes={}
    for qid in job['question_ids']:
        q=CATALOG.question(qid)
        if 'question_id' in q:
            for kind in ['question','answer']:
                s=CATALOG.source(q[kind]['source_id'])
                if s['filename'] in hashes and hashes[s['filename']]!=s['sha256']:raise DataError('同名原卷存在不同版本，请为修订版登记独立文件名')
                hashes[s['filename']]=s['sha256']
            qp=CATALOG.source(q['question']['source_id'])
            for reference in qp['metadata'].get('required_external_documents',[]):
                s=CATALOG.source(reference['source_id'])
                if s['filename'] in hashes and hashes[s['filename']]!=s['sha256']:raise DataError('参考数据文件版本冲突')
                hashes[s['filename']]=s['sha256']
        else:
            # Existing legacy CIE1 codes continue using original filenames/hashes if recorded.
            for name in [q.get('qp'),q.get('ms')]:
                s=next((x for x in CATALOG.manifest['sources'] if x['filename']==name),None)
                if not s:raise DataError('此旧题缺少已核验来源，请先校准后分享')
                hashes[name]=s['sha256']
    return hashes

def share(job):
    job=validate_job(job)
    p={'schema':2 if CATALOG.index['bank_id']=='cie-9701-as-teaching19-v1' else 1,'bank':CATALOG.index['bank_id'],'revision':CATALOG.index['revision'],'job':job,'hashes':source_hashes(job)}
    return ('CIE2.' if CATALOG.index['bank_id']=='cie-9701-as-teaching19-v1' else 'CIE1.')+base64.urlsafe_b64encode(zlib.compress(json.dumps(p,ensure_ascii=False).encode())).decode().rstrip('=')

def unshare(code):
    teaching=CATALOG.index['bank_id']=='cie-9701-as-teaching19-v1'
    if teaching and isinstance(code,str) and code.startswith('CIE1.'):raise DataError('这是旧版题库的分享代码，请使用旧版App与归档数据打开')
    if not isinstance(code,str) or len(code)>100000 or not code.startswith('CIE2.' if teaching else 'CIE1.'):raise DataError('不是当前题库代际的组卷代码')
    try:
        raw=base64.b64decode(code[5:]+'='*(-len(code[5:])%4),altchars=b'-_',validate=True)
        d=zlib.decompressobj();value=d.decompress(raw,500001)
        if len(value)>500000 or d.unconsumed_tail or not d.eof:raise ValueError()
        p=json.loads(value)
    except Exception:raise DataError('组卷代码已损坏或过大')
    if not isinstance(p,dict) or p.get('schema')!=(2 if teaching else 1) or p.get('bank')!=CATALOG.index['bank_id']:raise DataError('不支持的题库或分享版本')
    job=validate_job(p.get('job'));hashes=p.get('hashes')
    if not isinstance(hashes,dict) or any(hashes.get(n)!=h for n,h in source_hashes(job).items()):raise DataError('题库版本或原卷内容不一致，不能静默替换题目')
    return job

def compat(q):
    if 'question_id' not in q:
        return dict(q,availability=RENDERER.availability(q['id']),text='',summary='',question_regions=q.get('question_regions') or [{'page':1}],answer_regions=q.get('answer_regions') or [{'page':1}])
    value=dict(q,id=q['question_id'],number=q['original_question_number'],variant=str(q['paper'])+str(q['variant']),text='',summary='',
        qp=CATALOG.source(q['question']['source_id'])['filename'],ms=CATALOG.source(q['answer']['source_id'])['filename'],
        question_regions=q['question']['regions'],answer_regions=q['answer']['regions'],availability=RENDERER.availability(q['question_id']))
    value['required_documents']=CATALOG.source(q['question']['source_id'])['metadata'].get('required_external_documents',[])
    return value

def bank_info():
    with CATALOG.connect() as c:
        total=c.execute(CATALOG.CANDIDATES+'SELECT count(*) FROM candidates').fetchone()[0]
        counts=dict(c.execute(CATALOG.CANDIDATES+"SELECT j.value,count(DISTINCT q.question_id) FROM candidates q,json_each(q.payload,'$.topics') j GROUP BY j.value").fetchall())
        years=[r[0] for r in c.execute(CATALOG.CANDIDATES+'SELECT DISTINCT year FROM candidates ORDER BY year DESC')]
    teaching=CATALOG.index['bank_id']=='cie-9701-as-teaching19-v1'
    pending=CATALOG.search({'collection':'pending'},limit=1)['total'] if teaching else 0
    if teaching:total=CATALOG.search(limit=1)['total']
    courses={course:{'total':CATALOG.search({'course':course},limit=1)['total'],'pending':CATALOG.search({'course':course,'collection':'pending'},limit=1)['total']} for course in ['AS','A2']} if teaching else {}
    references=[{'source_id':s['source_id'],'title':s['metadata'].get('title',s['filename']),'status':SOURCES.status(s['source_id'])} for s in CATALOG.manifest['sources'] if s['metadata'].get('role')=='data-booklet']
    return {'teaching':teaching,'pending':pending,'courses':courses,'reference_documents':references,'upgrade_notice':CATALOG.upgrade_notice,'bank_id':CATALOG.index['bank_id'],'revision':CATALOG.index['revision'],'total':total,
            'topics':[dict(t,count=counts.get(t['id'],0)) for t in CATALOG.index['topics']],'years':years,'app_version':PATHS.build['version'],'maintainer':os.environ.get('QUESTION_BANK_MAINTAINER')=='1'}

def make_pdf(job,kind):return RENDERER.export(validate_job(job),kind,EXPORTS)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def send(self,data,status=200,ctype='application/json; charset=utf-8'):
        if not isinstance(data,bytes):data=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(data)))
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
    def trusted(self):return self.headers.get('Host') in [f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}']
    def do_GET(self):
        if not self.trusted():return self.send({'error':'Invalid host'},403)
        url=urlparse(self.path);path=unquote(url.path);params={k:v[0] for k,v in parse_qs(url.query).items()}
        try:
            if path=='/api/health':return self.send({'ready':True,'pid':os.getpid(),'instance_id':os.environ.get('QUESTION_BANK_INSTANCE',''),'version':PATHS.build['version'],'distribution':PATHS.build['distribution']})
            if path=='/api/bank':return self.send(bank_info())
            if path=='/api/questions':
                if params.get('ids'):return self.send({'questions':[compat(CATALOG.question(x)) for x in params['ids'].split(',')[:200]]})
                result=CATALOG.search(params,int(params.get('limit',8)),int(params.get('offset',0)))
                result['questions']=[compat(q) for q in result['questions']];return self.send(result)
            if path=='/api/sources':return self.send([dict(s,status=SOURCES.status(s['source_id'])) for s in CATALOG.manifest['sources']])
            if path=='/api/check':return self.send({'catalog':CATALOG.check(),'cache':RENDERER.clean(),'sources':[{'source_id':s['source_id'],**SOURCES.status(s['source_id'])} for s in CATALOG.manifest['sources']]})
            if path=='/api/draft':
                with connection() as c:r=c.execute('SELECT body FROM draft WHERE slot=1').fetchone()
                return self.send(json.loads(r[0]) if r else None)
            if path=='/api/holding-list':return self.send({'schema_version':'1.0.0','bank_id':CATALOG.index['bank_id'],'revision':CATALOG.index['revision'],'questions':[q for q in CATALOG.index['questions'] if q.get('metadata',{}).get('teaching',{}).get('status')=='pending']})
            if path=='/api/worksheet':
                from bank.teaching.worksheet import resolve
                return self.send(resolve(CATALOG,[v for v in params.get('ids','').split(',') if v]))
            if path=='/api/jobs':
                with connection() as c:rows=c.execute('SELECT * FROM jobs ORDER BY updated DESC').fetchall()
                return self.send([dict(json.loads(r['body']),id=r['id'],updated=r['updated']) for r in rows])
            if path.startswith('/preview/'):
                _,_,qid,kind,index=path.split('/')
                return self.send(RENDERER.preview(qid,kind,int(index),use_cache=params.get('cache')!='0'),ctype='image/webp')
            if path.startswith('/page/'):
                _,_,sid,index=path.split('/')
                return self.send(RENDERER.page_preview(sid,int(index)),ctype='image/png')
            if path.startswith('/source/'):
                name=path.split('/')[-1];s=next((s for s in CATALOG.manifest['sources'] if s['filename']==name or s['source_id']==name),None)
                if not s:raise DataError('未知原卷')
                return self.send(SOURCES.resolve(s['source_id']).read_bytes(),ctype='application/pdf')
            if path.startswith('/exports/'):
                name=path.split('/')[-1]
                if not re.fullmatch(r'[a-f0-9]{32}_(questions|answers)\.pdf',name):raise DataError('无效文件')
                return self.send((EXPORTS/name).read_bytes(),ctype='application/pdf')
            files={'/':'index.html','/app.js':'app.js','/prompt.js':'prompt.js','/tokens.css':'tokens.css','/style.css':'style.css'}
            if path in files:
                f=RESOURCES/'app'/files[path];mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8'}
                return self.send(f.read_bytes(),ctype=mime[f.suffix])
            self.send({'error':'Not found'},404)
        except SourceError as e:self.send({'error':str(e),'code':'source_unavailable'},409)
        except (DataError,ValueError,KeyError,IndexError,FileNotFoundError) as e:self.send({'error':str(e)},400)
        except Exception as e:
            print('ERROR',repr(e),file=sys.stderr);self.send({'error':'读取失败，请检查本地数据'},500)
    def do_POST(self):
        origin=self.headers.get('Origin')
        if not self.trusted() or self.headers.get('X-Local-Request')!='1' or (origin and origin!=f'http://{self.headers.get("Host")}'):return self.send({'error':'Invalid origin'},403)
        try:
            size=int(self.headers.get('Content-Length','0'));path=urlparse(self.path).path
            if size<0 or size>(512*1024*1024 if path=='/api/bank-update-upload' else 64*1024*1024 if path=='/api/source-upload' else 600000):raise DataError('请求过大')
            if path=='/api/bank-update-upload':
                staging=DATA/'bank-updates/staging';staging.mkdir(parents=True,exist_ok=True)
                token=uuid.uuid4().hex;target=staging/(token+'.qbank')
                # Bound disk retention for abandoned confirmations.
                for old in staging.glob('*.qbank'):
                    if old.stat().st_mtime<time.time()-86400:old.unlink(missing_ok=True)
                try:
                    with target.open('xb') as stream:
                        remaining=size
                        while remaining:
                            chunk=self.rfile.read(min(remaining,1024*1024))
                            if not chunk:raise DataError('上传未完成')
                            stream.write(chunk);remaining-=len(chunk)
                    info,index,manifest,_=inspect_package(target,RESOURCES/'schemas')
                    return self.send({'token':token,'sha256':sha256(target),'revision':info['revision'],'base_revision':info['base_revision'],'changelog':info['changelog'],'questions':len(index['questions']),'included_sources':len([n for n in info['files'] if n.startswith('sources/')])})
                except Exception:target.unlink(missing_ok=True);raise
            if path=='/api/source-upload':
                name=parse_qs(urlparse(self.path).query).get('name',['upload.pdf'])[0]
                fd,temp=tempfile.mkstemp(dir=DATA,suffix='.pdf')
                try:
                    with os.fdopen(fd,'wb') as stream:
                        remaining=size
                        while remaining:
                            chunk=self.rfile.read(min(remaining,1024*1024))
                            if not chunk:raise DataError('上传未完成')
                            stream.write(chunk);remaining-=len(chunk)
                    with MUTATION_LOCK:result=SOURCES.import_file(temp,name)
                    return self.send(result)
                finally:Path(temp).unlink(missing_ok=True)
            body=json.loads(self.rfile.read(size))
            if path=='/api/report':return self.send(build_report(CATALOG,body['question_id'],body['category'],body['description'],PATHS.build['version']))
            if path=='/api/bank-update-install':
                token=body.get('token','')
                if not re.fullmatch(r'[a-f0-9]{32}',token):raise DataError('无效更新包')
                target=DATA/'bank-updates/staging'/(token+'.qbank')
                with MUTATION_LOCK:
                    result=install_package(CATALOG,target,body['sha256'])
                    SOURCES.extract_local_content()
                target.unlink(missing_ok=True)
                return self.send(result)
            if path=='/api/import-project':
                if CATALOG.index['bank_id']=='cie-9701-as-teaching19-v1':raise DataError('旧项目请使用归档恢复工具与旧版App打开')
                from profile_import import import_project
                with MUTATION_LOCK:result=import_project(body['path'],CATALOG,SOURCES,DB)
                return self.send(result)
            if path=='/api/select':
                if CATALOG.index['bank_id']=='cie-9701-as-teaching19-v1' and body.get('filters',{}).get('collection')=='pending':raise DataError('待整理题目不参与自动组卷')
                excluded=body.get('exclude',[]);count=int(body.get('count',10))
                if not isinstance(excluded,list) or any(not isinstance(x,str) for x in excluded) or not 1<=count<=200 or len(excluded)>200:raise DataError('每份作业最多 200 题')
                remaining=min(count,200-len(excluded))
                chosen=CATALOG.search(body.get('filters',{}),remaining,exclude=excluded,random_order=True)['questions'] if remaining else []
                return self.send({'questions':[compat(q) for q in chosen]})
            if path=='/api/calibrate':
                if os.environ.get('QUESTION_BANK_MAINTAINER')!='1':raise DataError('坐标维护请使用导入 Skill / CLI')
                with MUTATION_LOCK:result=calibrate(CATALOG,SOURCES,body)
                return self.send(result)
            if path=='/api/maintenance':
                action=body.get('action')
                with MUTATION_LOCK:
                    if action=='cache-clear':return self.send(RENDERER.clean(clear=True))
                    if action=='rebuild':
                        result=CATALOG.rebuild(force=True);SOURCES.extract_local_content();return self.send(result)
                    if action=='migrate':
                        if os.environ.get('QUESTION_BANK_MAINTAINER')!='1':raise DataError('旧库迁移请使用维护者 CLI')
                        from bank.migration import migrate
                        return self.send(migrate(ROOT,body['path'],CATALOG,SOURCES))
                raise DataError('未知维护操作')
            if path=='/api/draft':
                job=validate_job(body)
                if body.get('id'):job['id']=body['id']
                with connection() as c:c.execute('INSERT OR REPLACE INTO draft VALUES (1,?)',(json.dumps(job,ensure_ascii=False),))
                return self.send({'ok':True})
            if path=='/api/save':
                job=validate_job(body);ident=body.get('id') or str(uuid.uuid4())
                if not isinstance(ident,str) or not re.fullmatch(r'[a-f0-9-]{36}',ident):raise DataError('无效作业 ID')
                with connection() as c:c.execute('INSERT OR REPLACE INTO jobs VALUES (?,?,?,?)',(ident,job['title'],json.dumps(job,ensure_ascii=False),time.time()))
                return self.send(dict(job,id=ident))
            if path=='/api/delete':
                with connection() as c:c.execute('DELETE FROM jobs WHERE id=?',(body.get('id'),))
                return self.send({'ok':True})
            if path=='/api/share':return self.send({'code':share(body)})
            if path=='/api/import':return self.send(unshare(body.get('code','').strip()))
            if path=='/api/export':
                out=make_pdf(body['job'],body['kind']);return self.send({'url':'/exports/'+out.name,'filename':out.name})
            self.send({'error':'Not found'},404)
        except SourceError as e:self.send({'error':str(e),'code':'source_unavailable'},409)
        except (DataError,ValueError,KeyError,TypeError) as e:self.send({'error':str(e)},400)
        except Exception as e:
            print('ERROR',repr(e),file=sys.stderr);self.send({'error':'操作失败，请检查本地文件或磁盘空间'},500)

def main():
    import signal
    lock=(DATA/'backend.lock').open('a+')
    try:
        if sys.platform=='win32':
            import msvcrt
            lock.seek(0)
            if not lock.read(1):lock.write('0');lock.flush()
            lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except (BlockingIOError,OSError):raise SystemExit('此用户数据目录已有一个后端正在运行，请退出另一实例。')
    PATHS.seed_sources(SOURCES);PATHS.mark_ready()
    http=ThreadingHTTPServer(('127.0.0.1',int(os.environ.get('QUESTION_BANK_PORT','0'))),Handler)
    def stop(*_):threading.Thread(target=http.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    print(f'http://127.0.0.1:{http.server_port}',flush=True)
    try:http.serve_forever()
    finally:http.server_close();lock.close()
if __name__=='__main__':main()
