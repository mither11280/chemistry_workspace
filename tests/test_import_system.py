"""Original authored PDFs exercise the production importer without licensed test data."""
from copy import deepcopy
from pathlib import Path
import json,shutil,sqlite3,sys,tempfile,unittest,zipfile
from unittest.mock import patch
import fitz
from fixtures import ROOT,make_fixture
sys.path.insert(0,str(ROOT/'app'))
from bank.format import DataError,read_json,write_json,sha256
from bank.catalog import Catalog
from bank.importer.identity import identify
from bank.importer.engine import analyze
from bank.importer.parsing import reference_page
from bank.importer.quality import region_issues
from bank.updates import build_package,inspect_package,install_package,rollback,pointer_path
from bank.feedback import build_report


def authored_pair(folder,missing_answer=False,missing_question=False,wrong_total=False):
    """One original structured question continued across two portrait pages; landscape MS."""
    folder.mkdir(parents=True,exist_ok=True);paths=[]
    for kind in ['qp','ms']:
        path=folder/f'9701_s22_{kind}_22.pdf';paths.append(path)
        with fitz.open() as d:
            p=d.new_page();p.insert_text((50,90),'9701/22 May/June 2022')
            p.insert_text((50,120),'MARK SCHEME' if kind=='ms' else 'INSTRUCTIONS')
            p.insert_text((50,150),'Maximum Mark: 5' if kind=='ms' else 'The total mark for this paper is '+('6' if wrong_total else '5'))
            if kind=='qp':
                p=d.new_page()
                if not missing_question:p.insert_text((50,80),'1',fontname='hebo',fontsize=11)
                p.insert_text((73,80),'Explain electron configurations. Refer to the periodic table.')
                p.draw_rect((100,150,300,210));p.insert_text((73,300),'First part [2]')
                p=d.new_page();p.insert_text((73,80),'CONTINUED - authored context [3]');p.insert_text((400,160),'[Total: 5]')
            else:
                p=d.new_page(width=842,height=595)
                if not missing_answer:
                    p.insert_text((76,90),'1(a)');p.insert_text((150,90),'Authored first response');p.insert_text((770,90),'2')
                    p.insert_text((76,130),'1(b)');p.insert_text((150,130),'Authored second response');p.insert_text((770,130),'3')
                    for y in [75,110,150]:p.draw_line((60,y),(790,y))
            d.save(path)
    return paths

class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.index,self.manifest,self.files=make_fixture(self.root)
    def run_import(self,paths,overrides=None,revision='import.1'):
        return analyze(paths,self.root/'work',self.index,self.manifest,ROOT/'schemas',revision,overrides)
    def test_cover_identity_and_noncanonical_name(self):
        q,m=authored_pair(self.root/'in');new=q.with_name('teacher supplied.pdf');q.rename(new)
        identity,s=identify(new);self.assertEqual(identity.question_id(1),'cie-9701-s22-22-q1');self.assertEqual(s['page_count'],3)
        bad=new.with_name('9701_m23_qp_12.pdf');new.rename(bad)
        with self.assertRaisesRegex(DataError,'conflict'):identify(bad)
    def test_import_cross_pages_marks_topics_and_cache(self):
        paths=authored_pair(self.root/'in');index,manifest,r=self.run_import(paths)
        self.assertEqual((r['accepted'],r['quarantined']),(1,0));q=index['questions'][-1]
        self.assertEqual(len(q['question']['regions']),2);self.assertEqual(q['marks'],5);self.assertIn('atomic',q['topics'])
        self.assertEqual(q['metadata']['review_status'],'not_human_reviewed')
        _,_,again=self.run_import(paths);self.assertTrue(again['pairs'][0]['cache_hit'])
        patches={q['question_id']:{'source_fingerprint':again['pairs'][0]['source_fingerprint'],'topics':['bonding'],'reason':'Correct topic after a report'}}
        write_json(self.root/'patch.json',patches)
        fixed,_,r=self.run_import(paths,self.root/'patch.json','import.2');self.assertTrue(r['pairs'][0]['cache_hit']);self.assertEqual(fixed['questions'][-1]['topics'],['bonding'])
    def test_quarantine_missing_answers_and_mark_conflicts(self):
        for mode in ['missing_answer','missing_question','wrong_total']:
            with self.subTest(mode=mode):
                paths=authored_pair(self.root/mode,**{mode:True});_,_,r=self.run_import(paths)
                self.assertEqual(r['accepted'],0);self.assertGreaterEqual(r['quarantined'],1)
    def test_missing_pair_and_corrupt_pdf_reported(self):
        q,m=authored_pair(self.root/'in');bad=q.with_name('bad.pdf');bad.write_bytes(b'not a PDF')
        _,_,r=self.run_import([q,bad]);self.assertEqual(len(r['files_failed']),1);self.assertIn('missing_qp_or_ms',r['pairs'][0]['issues'])
    def test_crop_gate_and_periodic_table_mention(self):
        q,m=authored_pair(self.root/'in')
        with fitz.open(q) as d:
            self.assertFalse(reference_page(d[1]));self.assertIn('text_crosses_crop_edge',region_issues(d,[{'page_index':1,'bbox':[100,60,400,100]}]))
    def test_patch_cannot_bypass_region_or_answer_gates(self):
        paths=authored_pair(self.root/'in');_,_,r=self.run_import(paths)
        qid='cie-9701-s22-22-q1'
        bad={'source_fingerprint':r['pairs'][0]['source_fingerprint'],'question':{'source_id':'cie-9701-2022-s-22-qp','regions':[{'page_index':1,'bbox':[-10,40,550,200]}]}}
        write_json(self.root/'patch.json',{qid:bad})
        index,_,r=self.run_import(paths,self.root/'patch.json');self.assertEqual(r['accepted'],0);self.assertEqual(len(index['questions']),2)
    def test_bad_patch_fails_without_publication(self):
        paths=authored_pair(self.root/'in');self.run_import(paths);write_json(self.root/'badpatch.json',{'cie-9701-s22-22-q1':{'source_fingerprint':'wrong','marks':4}})
        with self.assertRaises(DataError):self.run_import(paths,self.root/'badpatch.json')
        self.assertEqual(read_json(self.root/'indexes/question-index.json'),self.index)

class UpdateAndFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.index,self.manifest,self.files=make_fixture(self.root);self.cat=Catalog(self.root)
        self.new=deepcopy(self.index);self.new['revision']='example.2';self.new['questions'][0]['topics']=[]
        self.package=self.root/'update.qbank'
    def package_update(self,new=None,files=None,rights=None):
        return build_package(self.package,new or self.new,self.manifest,self.index,self.manifest,ROOT/'schemas','Correct topic classification.',files,rights)
    def test_update_is_independent_and_keeps_personal_jobs(self):
        personal=self.root/'data/personal.sqlite3'
        with sqlite3.connect(personal) as c:c.execute('CREATE TABLE jobs(id TEXT PRIMARY KEY,body TEXT)');c.execute('INSERT INTO jobs VALUES (?,?)',('saved','my unchanged worksheet'))
        before=personal.read_bytes();result=self.package_update();installed=install_package(self.cat,self.package,result['sha256'])
        self.assertEqual(self.cat.index['revision'],'example.2');self.assertEqual(personal.read_bytes(),before)
        self.assertEqual(Catalog(self.root).index['revision'],'example.2')
        rollback(self.cat,installed['backup_id']);self.assertEqual(self.cat.index['revision'],'example.1');self.assertEqual(personal.read_bytes(),before)
    def test_failure_restores_pointer_catalog_and_personal_data(self):
        self.package_update();before=self.cat.search()['total'];real=self.cat.rebuild
        with patch.object(self.cat,'rebuild',side_effect=RuntimeError('injected SQL failure')):
            with self.assertRaises(RuntimeError):install_package(self.cat,self.package)
        self.assertFalse(pointer_path(self.cat).exists());real();self.assertEqual(self.cat.search()['total'],before)
    def test_stable_ids_source_identity_and_base_revision(self):
        bad=deepcopy(self.new);bad['questions'].pop()
        with self.assertRaises(DataError):self.package_update(bad)
        bad=deepcopy(self.new);bad['questions'][0]['year']=2023
        with self.assertRaises(DataError):self.package_update(bad)
        self.package_update();install_package(self.cat,self.package)
        with self.assertRaises(DataError):install_package(self.cat,self.package)
    def test_path_traversal_duplicate_and_damaged_package(self):
        self.package_update()
        with zipfile.ZipFile(self.package,'a') as z:z.writestr('../personal.sqlite3',b'x')
        with self.assertRaises(DataError):inspect_package(self.package,ROOT/'schemas')
        self.package_update()
        with zipfile.ZipFile(self.package,'a') as z:z.writestr('sources/extra.pdf',b'x')
        with self.assertRaises(DataError):inspect_package(self.package,ROOT/'schemas')
    def test_source_authorization_and_hashes(self):
        paths={s['source_id']:p for s,p in zip(self.manifest['sources'],self.files)}
        with self.assertRaises(DataError):self.package_update(files=paths)
        rights={'redistribution_authorized':True,'statement':'Original authored test PDFs','sha256':[s['sha256'] for s in self.manifest['sources']]}
        result=self.package_update(files=paths,rights=rights);install_package(self.cat,self.package,result['sha256'])
        for s in self.manifest['sources']:self.assertEqual(sha256(self.root/s['path']),s['sha256'])
    def test_local_automatic_overlay_does_not_mask_fixes_but_manual_does(self):
        write_json(self.root/'data/question-index.local.json',self.index)
        self.package_update();install_package(self.cat,self.package);self.assertEqual(self.cat.question('fixture-q1')['topics'],[])
        manual=deepcopy(self.index);manual['questions'][0]['metadata']['calibration']='manual';write_json(self.root/'data/question-index.local.json',manual)
        self.cat.rebuild();self.assertEqual(self.cat.question('fixture-q1')['topics'],['example'])
    def test_personal_custom_questions_survive_public_update(self):
        custom=deepcopy(self.index);q=deepcopy(custom['questions'][0]);q['question_id']='personal-q';custom['questions'].append(q)
        write_json(self.root/'data/question-index.local.json',custom);self.cat.rebuild()
        self.package_update();install_package(self.cat,self.package)
        self.assertEqual(self.cat.question('personal-q')['question_id'],'personal-q')
        self.assertEqual(self.cat.index['revision'],'example.2')
    def test_feedback_is_whitelisted_offline_and_user_submitted(self):
        from urllib.parse import urlparse,parse_qs
        result=build_report(self.cat,'fixture-q1','crop','Wrong crop at /Users/private/student/name.pdf and C:\\Users\\teacher\\secret.pdf','0.3.0')
        value=json.dumps(result,ensure_ascii=False)
        self.assertNotIn('/Users/private',value);self.assertNotIn('secret.pdf',value);self.assertNotIn('personal.sqlite3',value)
        self.assertEqual(set(result['report']),{'report_schema_version','question_id','category','description','bank_id','bank_revision','app_version','exam','sources'})
        url=urlparse(result['issue_url']);self.assertEqual(url.hostname,'github.com');self.assertEqual(parse_qs(url.query)['title'],['[crop] fixture-q1'])
        with self.assertRaises(DataError):build_report(self.cat,'fixture-q1','unknown','test','0.3.0')

if __name__=='__main__':unittest.main()
