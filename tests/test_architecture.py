import copy
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
import fitz
from fixtures import ROOT,make_fixture
sys.path.insert(0,str(ROOT/'app'))
from bank.format import DataError,SourceError,read_json,sha256,validate,write_json
from bank.catalog import Catalog
from bank.sources import SourceStore
from bank.render import Renderer
from bank.calibration import calibrate
from bank.migration import migrate,rollback

class ArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.index,self.manifest,self.files=make_fixture(self.root)
        self.cat=Catalog(self.root);self.store=SourceStore(self.root,self.cat);self.renderer=Renderer(self.cat,self.store)
    def import_all(self):
        for p in self.files:self.store.import_file(p)
    def test_schema_and_cross_validation(self):
        self.assertTrue(validate(self.index,self.manifest,ROOT/'schemas'))
        for mutation in ['bbox','page','id','version','source','path','geometry']:
            index=copy.deepcopy(self.index);manifest=copy.deepcopy(self.manifest)
            if mutation=='bbox':index['questions'][0]['question']['regions'][0]['bbox'][2]=10000
            if mutation=='page':index['questions'][0]['question']['regions'][0]['page_index']=30
            if mutation=='id':index['questions'].append(index['questions'][0])
            if mutation=='version':index['schema_version']='2.0.0'
            if mutation=='source':index['questions'][0]['answer']['source_id']='wrong'
            if mutation=='path':manifest['sources'][0]['path']='../outside.pdf'
            if mutation=='geometry':manifest['sources'][0]['pages'][0]['width']=4
            with self.subTest(mutation=mutation),self.assertRaises(DataError):validate(index,manifest,ROOT/'schemas')
    def test_public_real_index(self):
        index=read_json(ROOT/'indexes/question-index.json');manifest=read_json(ROOT/'indexes/source-manifest.json')
        validate(index,manifest,ROOT/'schemas');self.assertEqual(len(index['questions']),132)
        for q in index['questions']:
            self.assertNotIn('text',q);self.assertNotIn('summary',q);self.assertNotIn('value',q['answer'])
        self.assertEqual(sum(q['marks'] for q in index['questions']),300)
    def test_missing_and_wrong_source(self):
        self.assertEqual(self.renderer.availability('fixture-q1')['question']['state'],'missing')
        with self.assertRaises(SourceError):self.renderer.preview('fixture-q1','question')
        wrong=self.root/'wrong.pdf';wrong.write_bytes(self.files[1].read_bytes()+b'\nWRONG')
        with self.assertRaises(SourceError):self.store.import_file(wrong,self.files[0].name)
        self.import_all();original=self.store.resolve('fixture-qp');original.write_bytes(original.read_bytes()+b'\nALTERED')
        with self.assertRaises(SourceError):self.renderer.preview('fixture-q1','question')
        with self.assertRaises(SourceError):self.store.import_file(self.files[0])
    def test_geometry_rotation_and_multi_page(self):
        before=self.files[0].read_bytes();self.import_all()
        self.assertEqual(self.store.resolve('fixture-qp').read_bytes(),before)
        self.assertTrue(self.renderer.preview('fixture-q1','question',0).startswith(b'RIFF'))
        self.assertTrue(self.renderer.preview('fixture-q1','question',1).startswith(b'RIFF'))
        job={'title':'Geometry','question_ids':['fixture-q1'],'notes':''}
        out=self.renderer.export(job,'questions',self.root/'exports')
        with fitz.open(out) as d:
            text=''.join(p.get_text() for p in d)
            self.assertIn('AUTHORED QUESTION ONE - BEGIN',text);self.assertIn('CONTINUED',text)
            self.assertTrue(all(not p.get_images() for p in d))
        self.assertEqual(self.store.resolve('fixture-qp').read_bytes(),before)
    def test_sql_filters_local_fts_and_rebuild(self):
        self.assertEqual(self.cat.search({'paper':1,'topic':'example','min_marks':1,'max_marks':1})['total'],1)
        self.assertEqual(self.cat.search({'paper':'1','year':'2024','topic':'example','min_marks':'1','max_marks':'1'})['total'],1)
        self.import_all();self.assertEqual(self.cat.search({'search':'CONTINUED'})['total'],1)
        personal=self.root/'data/personal.sqlite3'
        with sqlite3.connect(personal) as c:c.execute('CREATE TABLE jobs(id TEXT)');c.execute("INSERT INTO jobs VALUES ('preserve')")
        self.cat.rebuild(force=True)
        with sqlite3.connect(personal) as c:self.assertEqual(c.execute('SELECT * FROM jobs').fetchone()[0],'preserve')
        self.assertEqual(self.cat.check()['integrity'],'ok')
    def test_answer_order_and_vector_output(self):
        self.import_all();job={'title':'Reordered','question_ids':['fixture-q2','fixture-q1'],'notes':'Teacher notes'}
        for kind in ['questions','answers']:
            out=self.renderer.export(job,kind,self.root/'exports')
            mapping=read_json(out.with_suffix('.mapping.json'));self.assertEqual([r['question_id'] for r in mapping],job['question_ids'])
            with fitz.open(out) as d:
                text=''.join(p.get_text() for p in d)
                self.assertLess(text.index('Assignment 1'),text.index('Assignment 2'))
                self.assertIn('TEACHER REVIEW DRAFT',text)
                if kind=='answers':self.assertIn('1.  B',text);self.assertIn('AUTHORED ANSWER ONE',text)
                self.assertTrue(all(not p.get_images() for p in d))
    def test_cache_key_limits_and_rebuild(self):
        self.import_all();first=self.renderer.preview('fixture-q2','question');self.assertEqual(len(list(self.renderer.cache.glob('*.webp'))),1)
        self.assertEqual(first,self.renderer.preview('fixture-q2','question'))
        self.renderer.preview('fixture-q2','question',scale=1.2);self.assertEqual(len(list(self.renderer.cache.glob('*.webp'))),2)
        self.renderer.clean(clear=True);self.assertEqual(self.renderer.clean()['files'],0)
        self.assertEqual(first,self.renderer.preview('fixture-q2','question'))
        self.renderer.max_cache_bytes=1;self.renderer.clean();self.assertEqual(self.renderer.clean()['files'],0)
        self.renderer.max_cache_bytes=128*1024*1024
        q=copy.deepcopy(self.index['questions'][1]);q['question']['regions'][0]['bbox'][1]+=1
        calibrate(self.cat,self.store,q);self.renderer.preview('fixture-q2','question')
        self.assertEqual(len(list(self.renderer.cache.glob('*.webp'))),1)
    def test_calibration_and_rollback(self):
        self.import_all();q=copy.deepcopy(self.index['questions'][0]);q['question']['regions'][0]['bbox'][0]=45
        result=calibrate(self.cat,self.store,q)
        self.assertEqual(self.cat.question('fixture-q1')['question']['regions'][0]['bbox'][0],45)
        rollback(self.root,result['backup']);self.cat.rebuild(force=True)
        self.assertEqual(self.cat.question('fixture-q1')['question']['regions'][0]['bbox'][0],40)
        q['question']['regions'][0]['bbox'][0]=-10
        with self.assertRaises(DataError):calibrate(self.cat,self.store,q)
    def test_legacy_pending_fallback_and_failure_restore(self):
        folder=self.root/'old/Q01';folder.mkdir(parents=True)
        for kind,source in [('question',self.files[0]),('answer',self.files[1])]:shutil.copyfile(source,folder/(kind+'.pdf'))
        old={'id':'legacy-q1','year':2024,'paper':2,'variant':'22','number':1,'marks':5,'topics':['example']}
        write_json(folder/'metadata.json',old)
        result=migrate(self.root,folder.parent,self.cat,self.store)
        self.assertEqual(len(result['pending_calibration']),1);self.assertTrue((Path(result['backup'])/'legacy/Q01/question.pdf').exists())
        self.assertEqual(self.renderer.availability('legacy-q1')['question']['state'],'legacy')
        self.assertEqual(self.cat.search({'paper':2})['total'],2)
        self.assertTrue(self.renderer.preview('legacy-q1','question').startswith(b'RIFF'))
        out=self.renderer.export({'title':'Legacy','question_ids':['legacy-q1'],'notes':''},'answers',self.root/'exports');self.assertTrue(out.exists())
        again=migrate(self.root,folder.parent,self.cat,self.store)
        self.assertEqual(self.cat.check()['legacy'],1)
        # A malformed index fails only after backup and leaves state fully recoverable.
        (folder.parent/'index.json').write_text('{BROKEN')
        before=self.cat.check()
        with self.assertRaises(ValueError):migrate(self.root,folder.parent,self.cat,self.store)
        self.assertEqual(self.cat.check(),before)
    def test_legacy_manual_upgrade(self):
        folder=self.root/'old/Q01';folder.mkdir(parents=True)
        old={'id':'legacy-q1','year':2024,'paper':2,'variant':'22','number':1,'marks':5,'topics':['example']}
        write_json(folder/'metadata.json',old);shutil.copyfile(self.files[0],folder/'question.pdf');shutil.copyfile(self.files[1],folder/'answer.pdf')
        migrate(self.root,folder.parent,self.cat,self.store);self.import_all()
        payload=copy.deepcopy(self.index['questions'][0]);payload['question_id']='legacy-q1'
        calibrate(self.cat,self.store,payload)
        self.assertEqual(self.cat.question('legacy-q1')['metadata']['calibration'],'manual')
        self.assertEqual(self.renderer.availability('legacy-q1')['question']['state'],'coordinates')

    def test_reliable_migration_repeatable_and_archive(self):
        from bank.migration import archive_legacy
        oldroot=self.root/'old';(oldroot/'sources').mkdir(parents=True)
        old={'bank_id':'fixture-bank','topics':self.index['topics'],'sources':{},'questions':[]}
        for path,name in zip(self.files,['9701_m24_qp_12.pdf','9701_m24_ms_12.pdf']):
            shutil.copyfile(path,oldroot/'sources'/name)
            old['sources'][name]={'sha256':sha256(path)}
        q={'id':'cie-9701-m24-12-q2','year':2024,'paper':1,'variant':'12','number':2,'marks':1,'topics':['example'],'qp':'9701_m24_qp_12.pdf','ms':'9701_m24_ms_12.pdf','question_regions':[{'page':3,'bbox':[40,55,550,180]}],'answer_regions':[{'page':2,'bbox':[40,55,550,140]}]}
        old['questions']=[q];write_json(oldroot/'index.json',old)
        before=self.cat.check()['questions'];result=migrate(self.root,oldroot,self.cat,self.store)
        self.assertEqual(result['migrated'],1);self.assertFalse(result['pending_calibration'])
        self.assertEqual(self.cat.check()['questions'],before+1)
        result=migrate(self.root,oldroot,self.cat,self.store)
        self.assertEqual(self.cat.check()['questions'],before+1)
        self.assertEqual(self.renderer.availability(q['id'])['question']['state'],'coordinates')
        archived=archive_legacy(self.root,oldroot,self.cat)
        self.assertFalse(oldroot.exists());self.assertTrue(Path(archived['archive']).exists())

    def test_cache_invalidates_when_source_identity_changes(self):
        self.import_all();self.renderer.preview('fixture-q2','question');oldkeys=set(self.renderer.cache.glob('*.webp'))
        # A source revision needs a new stable ID; its new hash invalidates all old render keys.
        oldsource=self.store.resolve('fixture-qp')
        revised=self.root/'sources/fixture/revised-qp.pdf';revised.write_bytes(oldsource.read_bytes()+b'\n% approved revision\n')
        manifest=copy.deepcopy(self.manifest);revised_source=copy.deepcopy(manifest['sources'][0])
        revised_source.update(source_id='fixture-qp-v2',filename='revised-qp.pdf',path='sources/fixture/revised-qp.pdf',sha256=sha256(revised))
        manifest['sources'].append(revised_source)
        index=copy.deepcopy(self.index)
        for q in index['questions']:q['question']['source_id']='fixture-qp-v2'
        write_json(self.root/'indexes/source-manifest.json',manifest);write_json(self.root/'indexes/question-index.json',index);self.cat.rebuild(force=True)
        self.renderer.preview('fixture-q2','question')
        self.assertEqual(len(set(self.renderer.cache.glob('*.webp'))-oldkeys),1)
        self.assertEqual(self.cat.search({'search':'CONTINUED'})['total'],0)

    def test_source_id_cannot_silently_change_identity(self):
        manifest=copy.deepcopy(self.manifest);manifest['sources'][0]['sha256']='0'*64
        write_json(self.root/'indexes/source-manifest.json',manifest)
        with self.assertRaises(DataError):self.cat.rebuild(force=True)
        self.assertEqual(self.cat.source('fixture-qp')['sha256'],self.manifest['sources'][0]['sha256'])
        self.assertEqual(self.cat.manifest,self.manifest)
