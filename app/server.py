import base64, hashlib, io, json, os, re, secrets, sqlite3, sys, threading, time, uuid, zlib
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
import fitz
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'; EXPORTS=ROOT/'exports'; EXPORTS.mkdir(exist_ok=True)
BUNDLED=ROOT/'question_bank/CIE/9701/AS'
# A fresh clone uses the checked-in bank. Older local-only installations still work.
BANK_ROOT=BUNDLED if (BUNDLED/'index.json').exists() else DATA
INDEX=BANK_ROOT/('index.json' if BANK_ROOT==BUNDLED else 'bank.json')
if not INDEX.exists():
 raise SystemExit('Question bank not found. Restore question_bank/ from the repository; see README.md.')
(DATA/'cache').mkdir(parents=True,exist_ok=True)
BANK=json.loads(INDEX.read_text(encoding='utf-8')); QUESTIONS={q['id']:q for q in BANK['questions']}
DB=Path(os.environ.get('QUESTION_BANK_DB',str(DATA/'personal.sqlite3')))
def connection():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
 c.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL, updated REAL NOT NULL)');return c
with connection() as c:
 c.execute('CREATE TABLE IF NOT EXISTS draft (slot INTEGER PRIMARY KEY, body TEXT NOT NULL)')

def validate_job(job):
 if not isinstance(job,dict):raise ValueError('作业格式不正确')
 ids=job.get('question_ids',[])
 if not isinstance(ids,list) or len(ids)>200 or any(not isinstance(x,str) for x in ids):raise ValueError('每份作业最多 200 题')
 if len(set(ids))!=len(ids):raise ValueError('一份作业不能重复加入同一题')
 missing=[x for x in ids if x not in QUESTIONS]
 if missing:raise ValueError('本地题库缺少题目：'+', '.join(missing[:5]))
 title=job.get('title','未命名作业')
 if not isinstance(title,str) or len(title)>120:raise ValueError('作业名称最多 120 个字符')
 return {'title':title.strip() or '未命名作业','question_ids':ids,'notes':str(job.get('notes',''))[:2000]}

def share(job):
 job=validate_job(job)
 payload={'schema':1,'bank':BANK['bank_id'],'revision':BANK['revision'],'job':job,'hashes':{name:BANK['sources'][name]['sha256'] for qid in job['question_ids'] for name in [QUESTIONS[qid]['qp'],QUESTIONS[qid]['ms']]}}
 return 'CIE1.'+base64.urlsafe_b64encode(zlib.compress(json.dumps(payload,ensure_ascii=False).encode())).decode().rstrip('=')
def unshare(code):
 if not isinstance(code,str) or len(code)>100000 or not code.startswith('CIE1.'):raise ValueError('不是有效的 CIE1 组卷代码')
 try:
  raw=base64.b64decode(code[5:]+'='*(-len(code[5:])%4),altchars=b'-_',validate=True)
  d=zlib.decompressobj();unpacked=d.decompress(raw,500001)
  if len(unpacked)>500000 or d.unconsumed_tail or not d.eof:raise ValueError()
  p=json.loads(unpacked)
 except Exception:raise ValueError('组卷代码已损坏或过大')
 if not isinstance(p,dict) or p.get('schema')!=1 or p.get('bank')!=BANK['bank_id']:raise ValueError('不支持的题库或分享版本')
 job=validate_job(p.get('job'))
 expected={name for qid in job['question_ids'] for name in [QUESTIONS[qid]['qp'],QUESTIONS[qid]['ms']]}
 hashes=p.get('hashes')
 if not isinstance(hashes,dict) or any(hashes.get(n)!=BANK['sources'][n]['sha256'] for n in expected):raise ValueError('题库版本或原卷内容不一致，不能静默替换题目')
 return job

def question_material(q,kind):
 # Portable pages already contain the crop. Original coordinates remain in the index for provenance.
 if q.get('files',{}).get(kind):
  path=BANK_ROOT/q['files'][kind]
  with fitz.open(path) as doc:
   regions=[{'page':i+1,'bbox':list(p.rect)} for i,p in enumerate(doc)]
  return path,regions
 return BANK_ROOT/'sources'/q['qp' if kind=='question' else 'ms'],q[kind+'_regions']

def make_pdf(job,kind):
 job=validate_job(job)
 if not job['question_ids']:raise ValueError('请先加入题目')
 if kind not in ['questions','answers']:raise ValueError('无效的导出类型')
 doc=fitz.open();source_docs={};is_answer=kind=='answers'
 def source(name):
  if name not in source_docs:source_docs[name]=fitz.open(BANK_ROOT/'sources'/name)
  return source_docs[name]
 def page(header,landscape=False):
  p=doc.new_page(width=841.89 if landscape else 595.28,height=595.28 if landscape else 841.89)
  p.insert_textbox(fitz.Rect(42,24,553,47),header,fontname='china-s',fontsize=11,color=(.16,.22,.25))
  p.draw_line((42,51),(553,51),color=(.8,.83,.84),width=.5)
  return p
 title=job['title'];p=page('CIE AS Chemistry 9701 | '+('Mark scheme' if is_answer else 'Worksheet'))
 p.insert_textbox(fitz.Rect(42,88,553,165),title,fontname='china-s',fontsize=24)
 total=sum(QUESTIONS[i]['marks'] or 0 for i in job['question_ids'])
 p.insert_text((42,190),f"{len(job['question_ids'])} questions  /  {total} marks",fontsize=12)
 p.insert_textbox(fitz.Rect(42,220,553,285),'教师试用稿：题图与分类尚待逐题复核。请核对后使用。\n保留原题编号；Assignment 编号对应本作业题序。',fontname='china-s',fontsize=11)
 if not is_answer:p.insert_text((42,315),'Name: ____________________    Class: _______________',fontsize=11)
 if job['notes']:p.insert_textbox(fitz.Rect(42,350,553,490),job['notes'],fontname='china-s',fontsize=11)
 y=515
 for idx,qid in enumerate(job['question_ids'],1):
  q=QUESTIONS[qid];path,regions=question_material(q,'answer' if is_answer else 'question')
  if path not in source_docs:source_docs[path]=fitz.open(path)
  src=source_docs[path]
  label=f"Assignment {idx}  |  {q['year']} March 9701/{q['variant']} Q{q['number']}  |  {q['marks']} marks"
  for ri,r in enumerate(regions):
   clip=fitz.Rect(r['bbox']);width=511; height=clip.height*width/clip.width
   if height>700:width*=700/height;height=700
   if y+height+45>785:p=page(title);y=70
   p.insert_text((42,y+11),label+(' (continued)' if ri else ''),fontsize=9,color=(.2,.35,.35));y+=25
   p.show_pdf_page(fitz.Rect(42,y,42+width,y+height),src,r['page']-1,clip=clip,keep_proportion=True)
   y+=height+22
 # Include source-provided data / official marking principles, once per source.
 seen=set();data_years=set()
 for qid in job['question_ids']:
  q=QUESTIONS[qid];name=q['ms' if is_answer else 'qp']
  if name in seen:continue
  seen.add(name);src=source(name);append=[]
  if is_answer and q['paper']==2:
   first=min(r['page'] for item in BANK['questions'] if item['ms']==name for r in item['answer_regions'])
   append=[(i,src[i].rect) for i in range(1,first-1)]
  elif not is_answer and q['year'] not in data_years:
   data_years.add(q['year'])
   append=[(len(src)-1,src[-1].rect)]
   for i,sp in enumerate(src):
    hits=sp.search_for('Important values')
    if i>0 and hits:
     bottom=min(780,hits[0].y0+235)
     table_lines=[drawing['rect'].y1 for drawing in sp.get_drawings() if drawing['rect'].y0>=hits[0].y0 and drawing['rect'].y1<hits[0].y0+260]
     if table_lines:bottom=max(table_lines)+8
     append.insert(0,(i,fitz.Rect(44,hits[0].y0,552,bottom)))
  for pi,clip in append:
   periodic=not is_answer and pi==len(src)-1
   landscape=periodic or src[pi].rect.width>src[pi].rect.height
   p=page('Source reference | '+name,landscape)
   p.show_pdf_page(fitz.Rect(35,65,p.rect.width-35,p.rect.height-45),src,pi,clip=clip,rotate=270 if periodic else 0)
 for i,p in enumerate(doc):
  p.insert_text((42,p.rect.height-25),'TEACHER REVIEW DRAFT - Original content: Cambridge / UCLES',fontsize=7,color=(.45,.48,.5))
  p.insert_text((p.rect.width-85,p.rect.height-25),f'{i+1} / {len(doc)}',fontsize=8)
 out=EXPORTS/f'{uuid.uuid4().hex}_{kind}.pdf';doc.save(out,garbage=4,deflate=True)
 for d in source_docs.values():d.close()
 doc.close();return out

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def send(self,data,status=200,ctype='application/json; charset=utf-8'):
  if not isinstance(data,bytes):data=json.dumps(data,ensure_ascii=False).encode()
  self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(data)));self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
 def trusted(self):return self.headers.get('Host') in [f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}']
 def do_GET(self):
  if not self.trusted():return self.send({'error':'Invalid host'},403)
  path=unquote(urlparse(self.path).path)
  try:
   if path=='/api/bank':return self.send(BANK)
   if path=='/api/draft':
    with connection() as c:row=c.execute('SELECT body FROM draft WHERE slot=1').fetchone()
    return self.send(json.loads(row[0]) if row else None)
   if path=='/api/jobs':
    with connection() as c:rows=c.execute('SELECT * FROM jobs ORDER BY updated DESC').fetchall()
    return self.send([dict(json.loads(r['body']),id=r['id'],updated=r['updated']) for r in rows])
   if path.startswith('/preview/'):
    _,_,qid,kind,index=path.split('/');q=QUESTIONS[qid]
    if kind not in ['question','answer']:raise ValueError('无效预览类型')
    material,regions=question_material(q,kind);r=regions[int(index)]
    # Include crop identity to invalidate previews when the packaged bank changes.
    version=q.get('file_sha256',{}).get(kind,BANK['revision'])[:16]
    cache=DATA/'cache'/f'{qid}-{kind}-{index}-{version}.png'
    if not cache.exists():
     with fitz.open(material) as d:cache.write_bytes(d[r['page']-1].get_pixmap(matrix=fitz.Matrix(1.6,1.6),clip=fitz.Rect(r['bbox']),alpha=False).tobytes('png'))
    return self.send(cache.read_bytes(),ctype='image/png')
   if path.startswith('/exports/'):
    name=path.split('/')[-1]
    if not re.fullmatch(r'[a-f0-9]{32}_(questions|answers)\.pdf',name):raise ValueError('无效文件')
    return self.send((EXPORTS/name).read_bytes(),ctype='application/pdf')
   if path.startswith('/source/'):
    name=path.split('/')[-1]
    if name not in BANK['sources']:raise ValueError('无效原卷')
    return self.send((BANK_ROOT/'sources'/name).read_bytes(),ctype='application/pdf')
   files={'/':'index.html','/app.js':'app.js','/tokens.css':'tokens.css','/style.css':'style.css'}
   if path in files:
    mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8'};f=ROOT/'app'/files[path]
    return self.send(f.read_bytes(),ctype=mime[f.suffix])
   self.send({'error':'Not found'},404)
  except (ValueError,KeyError,IndexError,FileNotFoundError):self.send({'error':'找不到文件或题目'},404)
 def do_POST(self):
  origin=self.headers.get('Origin')
  if not self.trusted() or self.headers.get('X-Local-Request')!='1' or (origin and origin!=f'http://{self.headers.get("Host")}'):return self.send({'error':'Invalid origin'},403)
  try:
   size=int(self.headers.get('Content-Length','0'))
   if size>600000:raise ValueError('请求过大')
   body=json.loads(self.rfile.read(size));path=urlparse(self.path).path
   if path=='/api/draft':
    job=validate_job(body)
    if body.get('id'):job['id']=body['id']
    with connection() as c:c.execute('INSERT OR REPLACE INTO draft VALUES (1,?)',(json.dumps(job,ensure_ascii=False),))
    return self.send({'ok':True})
   if path=='/api/save':
    job=validate_job(body);ident=body.get('id') or str(uuid.uuid4())
    if not isinstance(ident,str) or not re.fullmatch(r'[a-f0-9-]{36}',ident):raise ValueError('无效作业 ID')
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
  except (ValueError,KeyError,TypeError) as e:self.send({'error':str(e)},400)
  except Exception as e:
   print('ERROR',repr(e),file=sys.stderr);self.send({'error':'操作失败，请检查本地文件或磁盘空间'},500)

def main():
 server=ThreadingHTTPServer(('127.0.0.1',int(os.environ.get('QUESTION_BANK_PORT','0'))),Handler)
 print(f'http://127.0.0.1:{server.server_port}',flush=True);server.serve_forever()
if __name__=='__main__':main()
