"""Resource/profile separation, upgrades, and non-destructive old-project migration."""
import copy
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from fixtures import ROOT, make_fixture
import sys
sys.path.insert(0,str(ROOT/'app'))
from runtime import RuntimePaths
from bank.catalog import Catalog
from bank.sources import SourceStore
from bank.format import write_json
from profile_import import import_project

class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.resources=self.root/'resources';self.home=self.root/'profile'
        self.index,self.manifest,self.pdfs=make_fixture(self.resources)
        write_json(self.resources/'build-info.json',{'version':'0.2.0','distribution':'internal-adhoc'})
        self.paths=RuntimePaths(self.resources,self.home,True);self.paths.prepare()
        self.cat=Catalog(self.home,resources=self.resources);self.store=SourceStore(self.home,self.cat)
    def personal(self):
        db=self.home/'data/personal.sqlite3'
        with sqlite3.connect(db) as c:
            c.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,title TEXT,body TEXT,updated REAL)')
            c.execute('CREATE TABLE IF NOT EXISTS draft(slot INTEGER PRIMARY KEY,body TEXT)')
        return db
    def test_resources_readonly_profile_persistent(self):
        before={p.relative_to(self.resources):p.read_bytes() for p in self.resources.rglob('*') if p.is_file()}
        bundle=self.resources/'bundled-sources';bundle.mkdir()
        for p in self.pdfs:(bundle/p.name).write_bytes(p.read_bytes())
        report=self.paths.seed_sources(self.store);self.assertEqual(len(report),2);self.paths.mark_ready()
        self.assertTrue(self.store.resolve('fixture-qp').is_relative_to(self.home.resolve()))
        self.assertFalse((self.resources/'data').exists())
        for path,data in before.items():self.assertEqual((self.resources/path).read_bytes(),data)
        self.assertFalse(self.paths.seed_sources(self.store))
    def test_version_upgrade_preserves_database_and_sources(self):
        db=self.personal();body=json.dumps({'title':'Preserved','question_ids':['fixture-q1'],'notes':'teacher'})
        with sqlite3.connect(db) as c:c.execute('INSERT INTO jobs VALUES (?,?,?,?)',('id','Preserved',body,1))
        for p in self.pdfs:self.store.import_file(p)
        self.paths.mark_ready();write_json(self.resources/'build-info.json',{'version':'0.3.0','distribution':'internal-adhoc'})
        saved=self.paths.prepare();self.assertTrue((saved/'personal.sqlite3').exists())
        Catalog(self.home,resources=self.resources);self.paths.mark_ready()
        with sqlite3.connect(db) as c:self.assertEqual(c.execute('SELECT body FROM jobs').fetchone()[0],body)
        self.assertTrue(self.store.resolve('fixture-qp').exists())
    def test_existing_sources_are_indexed_after_fresh_catalog(self):
        for p in self.pdfs:self.store.import_file(p,extract=False)
        self.assertEqual(self.cat.search({'search':'AUTHORED'})['total'],0)
        self.paths.seed_sources(self.store)
        self.assertEqual(self.cat.search({'search':'AUTHORED'})['total'],2)
        with patch.object(self.store,'extract_local_content',wraps=self.store.extract_local_content) as extract:
            self.paths.seed_sources(self.store);extract.assert_not_called()
    def test_frozen_default_and_explicit_roots(self):
        with patch.dict(os.environ,{},clear=True),patch('sys.frozen',True,create=True):
            self.assertEqual(RuntimePaths.discover().home,Path.home()/'Library/Application Support/ChemistryWorkspace')
        with patch.dict(os.environ,{'QUESTION_BANK_RESOURCES':str(self.resources),'QUESTION_BANK_HOME':str(self.home)},clear=True):
            paths=RuntimePaths.discover();self.assertEqual(paths.resources,self.resources.resolve());self.assertEqual(paths.home,self.home.resolve())
    def test_project_import_never_overwrites_and_is_repeatable(self):
        old=self.root/'old-project';make_fixture(old);(old/'data').mkdir();old_db=old/'data/personal.sqlite3';db=self.personal()
        oldjob={'title':'Old job','question_ids':['fixture-q1'],'notes':'old note'};newjob={'title':'Current job','question_ids':['fixture-q2'],'notes':'new note'}
        with sqlite3.connect(old_db) as c:
            c.execute('CREATE TABLE jobs(id TEXT,title TEXT,body TEXT,updated REAL)');c.execute('CREATE TABLE draft(slot INTEGER,body TEXT)')
            c.execute('INSERT INTO jobs VALUES (?,?,?,?)',('same','Old job',json.dumps(oldjob),1));c.execute('INSERT INTO draft VALUES (1,?)',(json.dumps(oldjob),))
        with sqlite3.connect(db) as c:
            c.execute('INSERT INTO jobs VALUES (?,?,?,?)',('same','Current job',json.dumps(newjob),1));c.execute('INSERT INTO draft VALUES (1,?)',(json.dumps(newjob),))
        # Original source import paths mirror the old project layout.
        (old/'sources').mkdir()
        for p in (old/'fixture-input').glob('*.pdf'):(old/'sources'/p.name).write_bytes(p.read_bytes())
        report=import_project(old,self.cat,self.store,db);self.assertEqual(report['jobs_added'],2)
        with sqlite3.connect(db) as c:
            self.assertEqual(json.loads(c.execute("SELECT body FROM jobs WHERE id='same'").fetchone()[0]),newjob)
            self.assertEqual(json.loads(c.execute('SELECT body FROM draft').fetchone()[0]),newjob)
            count=c.execute('SELECT count(*) FROM jobs').fetchone()[0]
            draft_row=c.execute("SELECT updated FROM jobs WHERE title LIKE '%旧草稿%'").fetchone();self.assertGreater(draft_row[0],1700000000)
        again=import_project(old,self.cat,self.store,db);self.assertEqual(again['jobs_added'],0)
        with sqlite3.connect(db) as c:self.assertEqual(c.execute('SELECT count(*) FROM jobs').fetchone()[0],count)
        self.assertTrue(Path(report['snapshot']).exists());self.assertTrue(old_db.exists())
