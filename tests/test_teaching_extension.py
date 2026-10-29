"""Same-generation upgrades preserve work, activation and manual calibration."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from fixtures import ROOT,make_fixture
sys.path.insert(0,str(ROOT/'app'))
from bank.catalog import Catalog
from bank.format import write_json,read_json
from bank.teaching import extension
from bank.teaching.taxonomy import BANK_ID,TAXONOMY_ID,A2_TAXONOMY_ID,topics

class ExtensionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.index,self.manifest,_=make_fixture(self.root)
        self.index.update(bank_id=BANK_ID,revision=extension.BASE_REVISION,topics=topics())
        for q in self.index['questions']:
            q['topics']=['ch01'];q['metadata']['teaching']={'taxonomy_id':TAXONOMY_ID,'status':'ready','primary_chapter':1,'required_chapters':[1],'prerequisites':[],'parent_question_id':q['question_id'],'part_path':['a'],'source_order':0,'own_regions':copy.deepcopy(q['question']['regions']),'contexts':[],'evidence':[{'method':'authored-fixture','reason':'Original synthetic task'}],'issues':[]}
        write_json(self.root/'indexes/question-index.json',self.index)
        self.catalog=Catalog(self.root)
        self.personal=self.root/'data/personal.sqlite3';self.personal.write_bytes(b'personal-work-remains-byte-identical')
        calibrated=copy.deepcopy(self.index['questions'][0]);calibrated['metadata']['calibration']='manual'
        self.overlay={'questions':[calibrated]};write_json(self.root/'data/question-index.local.json',self.overlay)
        self.catalog.rebuild()
        self.new=copy.deepcopy(self.index);self.new.update(revision='v051-synthetic',topics=topics()+topics('A2'))
        a2=copy.deepcopy(self.new['questions'][0]);a2.update(question_id='fixture-a2',paper=4,qualification='A2',topics=['a2-ch07'])
        a2['metadata']['teaching'].update(taxonomy_id=A2_TAXONOMY_ID,primary_chapter=7,required_chapters=[7],parent_question_id='fixture-a2')
        self.new['questions'].append(a2)
    def tearDown(self):self.temp.cleanup()
    def activate_old(self,revision=None):
        old=copy.deepcopy(self.index);old['revision']=revision or old['revision']
        folder=self.root/'data/bank-updates/generations/previous'
        write_json(folder/'question-index.json',old);write_json(folder/'source-manifest.json',self.manifest)
        write_json(self.root/'data/bank-updates/current.json',{'generation':'generations/previous','revision':old['revision']})
    def patches(self):
        # Production uses the published exact hashes. Only original synthetic
        # fixtures are allowlisted in these migration integration tests.
        return patch.multiple(extension,KNOWN_INDEX_HASH=extension.digest(self.index),KNOWN_MANIFEST_HASH=extension.digest(self.manifest))
    def launch_new(self):
        write_json(self.root/'indexes/question-index.json',self.new)
        return Catalog(self.root)
    def assert_preserved(self,catalog):
        self.assertEqual(self.personal.read_bytes(),b'personal-work-remains-byte-identical')
        self.assertEqual(read_json(self.root/'data/question-index.local.json'),self.overlay)
        self.assertEqual(catalog.question('fixture-q1')['metadata']['calibration'],'manual')
    def test_bundled_base_upgrade_backs_up_and_is_idempotent(self):
        catalog=self.launch_new();self.assert_preserved(catalog)
        backups=list((self.root/'data/bundled-extension-backups').iterdir());self.assertEqual(len(backups),1)
        self.assertTrue((backups[0]/'catalog.sqlite3').exists())
        self.assertEqual(catalog.search({'course':'A2'})['total'],1)
        self.assertEqual(catalog.search({'course':'AS'})['total'],2)
        self.assert_preserved(Catalog(self.root));self.assertEqual(len(list((self.root/'data/bundled-extension-backups').iterdir())),1)
    def test_known_full_bundle_activation_does_not_hide_a2(self):
        self.activate_old(extension.BASE_REVISION+'.assets.1')
        with self.patches():catalog=self.launch_new()
        self.assertEqual(len(catalog.index['questions']),3);self.assert_preserved(catalog)
        self.assertFalse((self.root/'data/bank-updates/current.json').exists())
        backup=next((self.root/'data/bundled-extension-backups').iterdir())
        self.assertTrue((backup/'active-index/question-index.json').exists())
    def test_known_base_activation_upgrades(self):
        self.activate_old()
        with self.patches():catalog=self.launch_new()
        self.assertEqual(catalog.search({'course':'A2'})['total'],1);self.assert_preserved(catalog)
    def test_unknown_custom_activation_preserved_with_notice(self):
        self.activate_old('custom.teacher.1');pointer=(self.root/'data/bank-updates/current.json').read_bytes()
        catalog=self.launch_new();self.assertEqual(catalog.search({'course':'A2'})['total'],0)
        self.assertIn('自定义',catalog.upgrade_notice);self.assert_preserved(catalog)
        self.assertEqual((self.root/'data/bank-updates/current.json').read_bytes(),pointer)
    def test_same_revision_modified_content_is_not_known_release(self):
        self.activate_old();p=self.root/'data/bank-updates/generations/previous/question-index.json'
        custom=read_json(p);custom['questions'][0]['metadata']['teacher_extension']='custom';write_json(p,custom)
        with self.patches():catalog=self.launch_new()
        self.assertIn('自定义',catalog.upgrade_notice);self.assertEqual(len(catalog.index['questions']),2)
    def test_failed_rebuild_restores_pointer_catalog_and_manual_overlay(self):
        self.activate_old();before=(self.root/'data/bank-updates/current.json').read_bytes()
        with self.patches(),patch.object(Catalog,'rebuild',side_effect=RuntimeError('simulated failure')):
            with self.assertRaisesRegex(RuntimeError,'simulated'):self.launch_new()
        self.assertEqual((self.root/'data/bank-updates/current.json').read_bytes(),before)
        self.assertFalse((self.root/'data/bundled-extension.pending.json').exists())
        with self.catalog.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM questions').fetchone()[0],2)
        self.assert_preserved(self.catalog)
    def test_interrupted_activation_is_recovered_before_retry(self):
        self.activate_old();write_json(self.root/'indexes/question-index.json',self.new)
        with self.patches():backup=extension.prepare(self.catalog)
        self.assertIsNotNone(backup);self.assertFalse((self.root/'data/bank-updates/current.json').exists())
        extension.recover(self.catalog)
        self.assertTrue((self.root/'data/bank-updates/current.json').exists());self.assert_preserved(self.catalog)
    def test_delta_then_full_asset_bundle_and_repeat_keep_activation_and_work(self):
        from bank.updates import build_package,install_package,pointer_path
        catalog=self.launch_new();target=copy.deepcopy(self.new);target['revision']+='.assets.1'
        files={s['source_id']:self.root/'fixture-input'/s['filename'] for s in self.manifest['sources']}
        rights={'redistribution_authorized':True,'statement':'Original authored synthetic fixtures','sha256':[s['sha256'] for s in self.manifest['sources']]}
        delta=self.root/'delta.qbank';full=self.root/'full.qbank'
        for out,subset in [(delta,{'fixture-qp':files['fixture-qp']}),(full,files)]:
            build_package(out,target,self.manifest,self.new,self.manifest,self.root/'schemas','Original fixture assets',source_files=subset,authorization=rights,minimum_app_version='0.5.1')
        install_package(catalog,delta);before=pointer_path(catalog).read_bytes()
        self.assertFalse((self.root/'sources/fixture/original-ms.pdf').exists())
        result=install_package(catalog,full)
        self.assertEqual(result['added_source_files'],1);self.assertEqual(pointer_path(catalog).read_bytes(),before)
        self.assertTrue(install_package(catalog,full)['already_installed']);self.assert_preserved(catalog)
    def test_old_reader_rejects_a2_package_before_activation(self):
        from bank.updates import build_package,inspect_package
        from bank.format import DataError
        target=copy.deepcopy(self.new);target['revision']+='.assets.1';package=self.root/'new.qbank'
        build_package(package,target,self.manifest,self.new,self.manifest,self.root/'schemas','A2 synthetic index',minimum_app_version='0.5.1')
        with patch('bank.updates.READER_VERSION',(0,5,0)):
            with self.assertRaisesRegex(DataError,'更新版本'):inspect_package(package,self.root/'schemas')
    def test_missing_generation_marker_does_not_archive_v050_work(self):
        from bank.teaching.generation import prepare
        write_json(self.root/'indexes/question-index.json',self.new)
        self.assertIsNone(prepare(self.root,self.root))
        self.assertFalse((self.root/'generation-archives').exists())
        self.assertEqual(read_json(self.root/'data/teaching-generation.json')['bank_id'],BANK_ID)
        self.assert_preserved(self.catalog)

if __name__=='__main__':unittest.main()
