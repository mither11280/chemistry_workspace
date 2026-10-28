"""Historical layout and encoding regressions using original authored PDFs, plus opt-in local originals."""
from pathlib import Path
from copy import deepcopy
import json,os,shutil,sys,tempfile,unittest
import fitz
from fixtures import ROOT,make_fixture
from test_import_system import authored_pair
sys.path.insert(0,str(ROOT/'app'))
from bank.format import DataError,geometry,sha256,normalized_page,validate,read_json
from bank.pdf_layout import layout_page,rotation,canonicalize,transform
from bank.importer.identity import identify
from bank.importer.strategies import strategy_for
from bank.importer.engine import analyze
from bank.importer.inventory import scan
from bank.importer.syllabus import metadata
from bank.importer.quality import region_issues
from bank.importer.ms_layout import columns,count_marks
from bank.updates import build_package,inspect_package,install_package
from bank.catalog import Catalog
from bank.sources import SourceStore
from bank.render import Renderer


def legacy_mcq(folder):
    folder.mkdir(parents=True,exist_ok=True);qp=folder/'9701_m19_qp_12.pdf';ms=folder/'9701_m19_ms_12.pdf'
    with fitz.open() as d:
        p=d.new_page();p.insert_text((50,80),'9701/12 February/March 2019');p.insert_text((50,110),'READ THESE INSTRUCTIONS FIRST');p.insert_text((50,140),'There are forty questions on this paper. Each correct answer will score one mark.')
        for n in range(1,41):
            if n==1 or n in [9,17,25,31,35]:
                p=d.new_page();p.insert_text((50,810),'© Authored fixture')
                y=80
                if n==31:
                    p.insert_text((80,80),'Section B');p.insert_text((80,110),'Shared instruction: A = all three; B = first two; C = last two; D = first only.')
                    y=170
            p.insert_text((50,y),str(n),fontname='hebo',fontsize=11);p.insert_text((80,y),'Authored question about electron configurations.');y+=65
        d.save(qp)
    with fitz.open() as d:
        p=d.new_page();p.insert_text((50,80),'9701/12 March 2019 MARK SCHEME');p.insert_text((50,110),'Maximum Mark: 40')
        for n in range(1,41):
            if n in [1,21]:p=d.new_page();y=90
            p.insert_text((82,y),str(n));p.insert_text((125,y),'ABCD'[(n-1)%4]);p.insert_text((534,y),'1');y+=25
        d.save(ms)
    return qp,ms


class HistoricalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.base,self.manifest,self.files=make_fixture(self.root)
    def test_old_cover_without_printed_total_and_singular_blank_page(self):
        qp,ms=legacy_mcq(self.root/'2019_M');identity,source=identify(qp)
        self.assertEqual(source['metadata']['cover_total_marks'],40);self.assertEqual(identify(ms)[0].session_code,'m')
        path=self.root/'old-structured.pdf'
        with fitz.open() as d:
            p=d.new_page();p.insert_text((50,80),'9701/22 February/March 2019 READ THESE INSTRUCTIONS FIRST');p.insert_text((50,120),'This document consists of 1 printed pages and 1 blank page.');d.new_page();d.save(path)
        _,s=identify(path);self.assertIsNone(s['metadata']['cover_total_marks']);self.assertEqual(s['page_count'],2)
    def test_section_b_shared_code_table_survives_import(self):
        qp,ms=legacy_mcq(self.root/'2019_M');index,manifest,r=analyze([qp,ms],self.root/'work',self.base,self.manifest,ROOT/'schemas','legacy.1')
        self.assertEqual(r['accepted'],40,r)
        q=next(q for q in index['questions'] if q['question_id']=='cie-9701-m19-12-q31')
        self.assertEqual(q['metadata']['shared_context_regions'],1);self.assertEqual(q['metadata']['section'],'B');self.assertEqual(len(q['question']['regions']),2)
        q30=next(q for q in index['questions'] if q['question_id']=='cie-9701-m19-12-q30');self.assertNotEqual(q30['question']['regions'][-1]['page_index'],q['question']['regions'][0]['page_index'])
    def test_guidance_numbers_are_not_awarded_marks(self):
        with fitz.open() as d:
            p=d.new_page(width=842,height=595)
            for x,text in [(60,'Question'),(180,'Answer'),(450,'Marks'),(620,'Guidance')]:p.insert_text((x,65),text)
            for y,part,mark,note in [(100,'1(a)',2,20),(150,'1(b)',3,19)]:
                for x,text in [(76,part),(180,'Authored response'),(466,str(mark)),(620,str(note))]:p.insert_text((x,y),text)
            for x in [55,120,440,490,800]:p.draw_line((x,50),(x,180))
            col=columns(p);self.assertLess(col['marks_max'],620);self.assertEqual(count_marks(p,p.get_text('words')),5)
    def test_rotated_native_coordinates_and_vector_export(self):
        paths=authored_pair(self.root/'in');ms=paths[1]
        with fitz.open(ms) as d:
            d.delete_page(1);p=d.new_page(width=595,height=842);inverse=~fitz.Matrix(0,1,-1,0,842,0)
            for x,y,text in [(60,65,'Question'),(160,65,'Answer'),(740,65,'Marks'),(76,100,'1(a)'),(160,100,'Authored first response'),(770,100,'2'),(76,150,'1(b)'),(160,150,'Authored second response'),(770,150,'3')]:p.insert_text(fitz.Point(x,y)*inverse,text,rotate=90)
            for y in [75,125,175]:p.draw_line(fitz.Point(60,y)*inverse,fitz.Point(790,y)*inverse)
            p.set_rotation(90);d.save(self.root/'rotated.pdf')
        shutil.copyfile(self.root/'rotated.pdf',ms)
        before=sha256(ms);index,manifest,r=analyze(paths,self.root/'work',self.base,self.manifest,ROOT/'schemas','rotated.1');self.assertEqual(r['accepted'],1,r)
        q=index['questions'][-1];source=next(s for s in manifest['sources'] if s['source_id']==q['answer']['source_id'])
        self.assertEqual(source['pages'][1]['rotation'],90);self.assertEqual(source['metadata']['reading_rotations_clockwise']['1'],90);self.assertEqual(sha256(ms),before)
        with fitz.open(ms) as d:
            self.assertEqual(rotation(d,1),90);self.assertEqual(region_issues(d,q['answer']['regions']),[])
            logical=fitz.Rect(q['answer']['regions'][0]['bbox'])*transform(d,1);self.assertGreater(logical.width,logical.height)
        result=build_package(self.root/'update.qbank',index,manifest,self.base,self.manifest,ROOT/'schemas','Rotated source test')
        cat=Catalog(self.root);install_package(cat,self.root/'update.qbank',result['sha256']);store=SourceStore(self.root,cat)
        for path in paths:store.import_file(path)
        renderer=Renderer(cat,store);preview=renderer.preview(q['question_id'],'answer');self.assertTrue(preview.startswith(b'RIFF'))
        out=renderer.export({'title':'Reading rotation','notes':'','question_ids':[q['question_id']]},'answers',self.root/'exports')
        with fitz.open(out) as d:self.assertIn('Authored first response',''.join(p.get_text() for p in d))
    def test_partial_tounicode_without_both_witnesses_is_not_guessed(self):
        path=self.root/'encoded.pdf'
        with fitz.open() as d:
            p=d.new_page();p.insert_text((50,80),'CHEMISTRY 9701/12 May/June 2023 INSTRUCTIONS');p.insert_text((50,110),'The total mark for this paper is 40.')
            font=p.get_fonts()[0][0];xref=d.get_new_xref();d.update_object(xref,'<<>>')
            mapping='\n'.join(f'<{n:02x}> <{n-29:04x}>' for n in range(32,127))
            cmap=f'/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n/CMapName /BadWitness def\n/CMapType 2 def\n1 begincodespacerange\n<00> <ff>\nendcodespacerange\n95 beginbfchar\n{mapping}\nendbfchar\nendcmap\nCMapName currentdict /CMap defineresource pop\nend end'
            d.update_stream(xref,cmap.encode());d.xref_set_key(font,'ToUnicode',f'{xref} 0 R');d.save(path)
        before=sha256(path)
        with fitz.open(path) as d:
            self.assertNotIn('CHEMISTRY',d[0].get_text());self.assertNotIn('CHEMISTRY',normalized_page(d,0).get_text())
        self.assertEqual(sha256(path),before)
        with self.assertRaises(DataError):identify(path)
    def test_inventory_special_series_duplicates_and_conflicts(self):
        qp,ms=legacy_mcq(self.root/'corpus/2019_M');copy=qp.with_name('9701_m19_qp_12_copy.pdf');shutil.copyfile(qp,copy)
        r,selected=scan(self.root/'corpus',self.base,self.manifest,self.root/'inventory');self.assertEqual(len(r['duplicate_files']),1);self.assertEqual(len(selected),1)
        future=[v for v in r['rows'] if v['year']==2026 and v['session_code']=='w'];self.assertEqual(len(future),6);self.assertTrue(all(v['issues']==['awaiting-series-completion'] for v in future))
        self.assertTrue(all(v['exam_status'].startswith('cancelled') for v in r['rows'] if v['year']==2020 and v['session_code']=='s'))
        with fitz.open(copy) as d:d[0].insert_text((50,170),'Different version');d.save(self.root/'different.pdf')
        shutil.copyfile(self.root/'different.pdf',copy);r,selected=scan(self.root/'corpus',self.base,self.manifest,self.root/'inventory2');self.assertFalse(selected)
    def test_syllabus_compatibility_never_inferred_for_old_questions(self):
        old=metadata(2018,['atomic','organic'],'May/June');self.assertEqual(old['current_syllabus']['compatibility'],'unknown');self.assertEqual(old['original_syllabus']['period'],'2016-2018')
        self.assertEqual(old['current_syllabus']['topic_mapping'][0]['current_sections'],['1']);self.assertIsNone(old['original_syllabus']['document_revision'])
        self.assertEqual(metadata(2020,['atomic'],'May/June')['exam_series_status'],'cancelled-published-practice-materials')
    def test_bulk_text_index_survives_sqlite_cache_spill(self):
        from unittest.mock import patch
        index=deepcopy(self.base)
        for n in range(200):
            q=deepcopy(index['questions'][0]);q['question_id']='bulk-'+str(n);index['questions'].append(q)
        from bank.format import write_json
        write_json(self.root/'indexes/question-index.json',index)
        cat=Catalog(self.root);store=SourceStore(self.root,cat)
        for path in self.files:store.import_file(path,extract=False)
        original=cat.connect
        def tiny_cache():
            c=original();c.execute('PRAGMA cache_size=2');c.execute('PRAGMA busy_timeout=50');return c
        with patch.object(cat,'connect',side_effect=tiny_cache):store.extract_local_content()
        self.assertEqual(cat.search({'search':'AUTHORED'})['total'],202)
    def test_equivalent_save_can_differ_only_in_display_rotation(self):
        from bank.importer.equivalence import fingerprint
        qp,ms=legacy_mcq(self.root/'corpus/2019_M');copy=qp.with_name('9701_m19_qp_12_copy.pdf')
        with fitz.open(qp) as d:d[-1].set_rotation(90);d.save(copy)
        self.assertNotEqual(sha256(qp),sha256(copy));self.assertEqual(fingerprint(qp,sha256(qp),self.root/'equiv'),fingerprint(copy,sha256(copy),self.root/'equiv'))
        r,selected=scan(self.root/'corpus',self.base,self.manifest,self.root/'inventory');self.assertEqual(len(selected),1);self.assertIn('content-equivalent-qp-versions-canonical-selected',next(v for v in r['rows'] if v['pair']=='9701-2019-m-12')['issues'])
    def test_public_historical_snapshot_preserves_original_bank(self):
        root=ROOT/'indexes/releases/v0.4-2018-2026';index=read_json(root/'question-index.json');manifest=read_json(root/'source-manifest.json')
        self.assertTrue(validate(index,manifest,ROOT/'schemas'));self.assertEqual(len(index['questions']),2523);self.assertEqual(len(manifest['sources']),231)
        final={q['question_id']:q for q in index['questions']};original=read_json(ROOT/'indexes/releases/v0.4-base-132/question-index.json')
        for q in original['questions']:
            self.assertIn(q['question_id'],final)
            for key in ['question','answer','marks','topics']:self.assertEqual(q[key],final[q['question_id']][key])
        self.assertEqual(len(final),len(index['questions']))
        identity=lambda q:tuple(q[k] for k in ['year','session','paper','variant','original_question_number'])
        self.assertEqual(len({identity(q) for q in index['questions']}),len(final))
        for q in index['questions']:
            if q['year']<2025:self.assertEqual(q['metadata']['current_syllabus']['compatibility'],'unknown')
            self.assertFalse(q['year']==2026 and q['session']=='October/November')
            self.assertNotIn('text',q)
            if q['year']==2020 and q['session']=='May/June':self.assertEqual(q['metadata']['exam_series_status'],'cancelled-published-practice-materials')
        self.assertNotIn('/Users/',json.dumps([index,manifest]))
    def test_new_package_minimum_reader_and_rotation_validation(self):
        index=deepcopy(self.base);index['revision']='minimum.2'
        build_package(self.root/'update.qbank',index,self.manifest,self.base,self.manifest,ROOT/'schemas','Reader version',minimum_app_version='0.4.0')
        self.assertEqual(inspect_package(self.root/'update.qbank',ROOT/'schemas')[0]['minimum_app_version'],'0.4.0')
        bad=deepcopy(self.manifest);bad['sources'][0]['metadata']['reading_rotations_clockwise']={'99':90}
        with self.assertRaises(DataError):validate(self.base,bad,ROOT/'schemas')


@unittest.skipUnless(os.environ.get('CIE_CORPUS'),'Set CIE_CORPUS to test supplied licensed historical PDFs')
class RealHistoricalRegression(unittest.TestCase):
    def test_actual_shifted_cmap_preserves_source(self):
        path=Path(os.environ['CIE_CORPUS'])/'2023_S/9701_s23_qp_11.pdf';before=sha256(path)
        with fitz.open(path) as d:
            self.assertNotIn('CHEMISTRY',d[0].get_text());self.assertIn('CHEMISTRY',normalized_page(d,0).get_text());self.assertIn('9701/11',normalized_page(d,0).get_text())
        self.assertEqual(identify(path)[0].year,2023);self.assertEqual(sha256(path),before)
    def test_four_historical_years_and_new_guidance_layout(self):
        root=Path(os.environ['CIE_CORPUS']);files=[]
        for y in [2018,2019,2020,2021]:
            for p in (root/f'{y}_M').glob('*.pdf'):
                if any(x in p.name for x in ['_qp_12','_ms_12','_qp_22','_ms_22']) or '9701-' in p.name and any(x in p.name for x in ['-12_','-22_']):files.append(p)
        files.extend([root/'2026_S/9701_s26_qp_21.pdf',root/'2026_S/9701_s26_ms_21.pdf'])
        with tempfile.TemporaryDirectory() as temp:
            base,manifest,_=make_fixture(Path(temp));index,_,r=analyze(files,Path(temp)/'work',base,manifest,ROOT/'schemas','real-regression.1')
            self.assertEqual(r['quarantined'],0,r);self.assertEqual(len(r['pairs']),9);self.assertEqual(r['accepted'],180)
