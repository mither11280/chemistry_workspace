import unittest, tempfile, os, sys, json, base64, zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
_tmp=tempfile.TemporaryDirectory();os.environ['QUESTION_BANK_DB']=str(Path(_tmp.name)/'test.sqlite3')
import server
import fitz
class CoreTests(unittest.TestCase):
 def setUp(self):self.job={'title':'原子结构 · 课堂练习','question_ids':['cie-9701-m25-12-q3','cie-9701-m25-22-q4'],'notes':'请写出完整步骤。'}
 def test_coverage(self):
  self.assertEqual(len(server.QUESTIONS),132)
  for row in server.BANK['coverage']:self.assertEqual(row['marks'],40 if row['paper']==1 else 60)
 def test_regions_and_sources(self):
  import hashlib
  for name,source in server.BANK['sources'].items():self.assertEqual(hashlib.sha256((server.BANK_ROOT/'sources'/name).read_bytes()).hexdigest(),source['sha256'])
  for q in server.QUESTIONS.values():
   for kind in ['question','answer']:
    with fitz.open(server.BANK_ROOT/'sources'/q['qp' if kind=='question' else 'ms']) as d:
     for r in q[kind+'_regions']:
      rect=fitz.Rect(r['bbox']);self.assertTrue(d[r['page']-1].rect.contains(rect));self.assertGreater(rect.height,10)
 def test_portable_bank(self):
  import hashlib
  self.assertEqual(server.BANK_ROOT,server.BUNDLED)
  self.assertNotIn('original_path',json.dumps(server.BANK))
  topics=json.loads((server.BANK_ROOT/'topics.json').read_text())
  for topic in topics:
   self.assertEqual(topic['question_ids'],[q['id'] for q in server.BANK['questions'] if topic['id'] in q['topics']])
  for q in server.QUESTIONS.values():
   folder=server.BANK_ROOT/Path(q['files']['question']).parent
   self.assertEqual(json.loads((folder/'metadata.json').read_text()),q)
   for kind in ['question','answer']:
    path,regions=server.question_material(q,kind)
    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),q['file_sha256'][kind])
    self.assertEqual(len(regions),len(q[kind+'_regions']))
    with fitz.open(path) as doc:
     for page,original in zip(doc,q[kind+'_regions']):
      rect=fitz.Rect(original['bbox'])
      self.assertAlmostEqual(page.rect.width,rect.width,places=2)
      self.assertAlmostEqual(page.rect.height,rect.height,places=2)
      # Every packaged region must actually render ink, including graphical questions.
      pixels=page.get_pixmap(matrix=fitz.Matrix(.5,.5),colorspace=fitz.csGRAY)
      self.assertLess(min(pixels.samples),200)
 def test_share_roundtrip_and_tampering(self):
  code=server.share(self.job);self.assertEqual(server.unshare(code),self.job)
  payload=json.loads(zlib.decompress(base64.urlsafe_b64decode(code[5:]+'='*(-len(code[5:])%4))))
  payload['hashes']={}
  broken='CIE1.'+base64.urlsafe_b64encode(zlib.compress(json.dumps(payload).encode())).decode()
  with self.assertRaises(ValueError):server.unshare(broken)
  with self.assertRaises(ValueError):server.unshare('CIE1.garbage')
 def test_invalid_questions(self):
  with self.assertRaises(ValueError):server.validate_job(dict(self.job,question_ids=['missing']))
  with self.assertRaises(ValueError):server.validate_job(dict(self.job,question_ids=[self.job['question_ids'][0]]*2))
 def test_bounded_decompression(self):
  code='CIE1.'+base64.urlsafe_b64encode(zlib.compress(b'x'*1000000)).decode()
  with self.assertRaises(ValueError):server.unshare(code)
 def test_sqlite_persistence(self):
  with server.connection() as c:c.execute('INSERT INTO jobs VALUES (?,?,?,?)',('test','title',json.dumps(self.job),1))
  with server.connection() as c:self.assertEqual(json.loads(c.execute('SELECT body FROM jobs WHERE id=?',('test',)).fetchone()[0]),self.job)
 def test_pdf(self):
  for kind in ['questions','answers']:
   out=server.make_pdf(self.job,kind)
   with fitz.open(out) as d:
    text=''.join(p.get_text() for p in d)
    self.assertIn('Assignment 1',text);self.assertIn('Assignment 2',text);self.assertIn('TEACHER REVIEW DRAFT',text)
    self.assertIn('9701/22 Q4',text)
    d[1].get_pixmap(matrix=fitz.Matrix(1,1)).save(server.ROOT/'tests'/f'{kind}-page2.png')
   (server.ROOT/'tests'/f'sample-{kind}.pdf').write_bytes(out.read_bytes());out.unlink()
if __name__=='__main__':unittest.main()
