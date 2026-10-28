"""Compatibility: retain IDs, CIE1 codes and personal jobs without needing real PDFs."""
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import shutil
import unittest
import zlib
from fixtures import ROOT
sys.path.insert(0,str(ROOT/'app'))
_tmp=tempfile.TemporaryDirectory();os.environ['QUESTION_BANK_DB']=str(Path(_tmp.name)/'test.sqlite3')
_legacy=Path(_tmp.name)/'legacy';_legacy.mkdir()
shutil.copytree(ROOT/'indexes/releases/v0.4-base-132',_legacy/'indexes')
shutil.copytree(ROOT/'schemas',_legacy/'schemas')
os.environ['QUESTION_BANK_ROOT']=str(_legacy)
import server
os.environ.pop('QUESTION_BANK_ROOT',None)
class CoreTests(unittest.TestCase):
    def setUp(self):self.job={'title':'原子结构 · 课堂练习','question_ids':['cie-9701-m25-12-q3','cie-9701-m25-22-q4'],'notes':'请写出完整步骤。'}
    def test_coverage(self):self.assertEqual(server.bank_info()['total'],132)
    def test_share_roundtrip_and_old_revision(self):
        code=server.share(self.job);self.assertEqual(server.unshare(code),self.job)
        p=json.loads(zlib.decompress(base64.urlsafe_b64decode(code[5:]+'='*(-len(code[5:])%4))))
        p['revision']='2026-10-27.1'
        encode=lambda p:'CIE1.'+base64.urlsafe_b64encode(zlib.compress(json.dumps(p).encode())).decode()
        self.assertEqual(server.unshare(encode(p)),self.job)
        p['hashes']={}
        with self.assertRaises(ValueError):server.unshare(encode(p))
        with self.assertRaises(ValueError):server.unshare('CIE1.garbage')
    def test_invalid_questions_and_bomb(self):
        for ids in [['missing'],[self.job['question_ids'][0]]*2]:
            with self.assertRaises(ValueError):server.validate_job(dict(self.job,question_ids=ids))
        with self.assertRaises(ValueError):server.unshare('CIE1.'+base64.urlsafe_b64encode(zlib.compress(b'x'*1000000)).decode())
    def test_sqlite_persistence_and_versions(self):
        with server.connection() as c:c.execute('INSERT OR REPLACE INTO jobs VALUES (?,?,?,?)',('test','title',json.dumps(self.job),1))
        server.CATALOG.rebuild(force=True)
        with server.connection() as c:
            self.assertEqual(json.loads(c.execute('SELECT body FROM jobs WHERE id=?',('test',)).fetchone()[0]),self.job)
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],1)
