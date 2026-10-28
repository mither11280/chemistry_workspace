"""Teaching order, prerequisite closure, independent scoring and recoverable generation switch."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from bank.format import DataError,write_json
from bank.teaching.taxonomy import BANK_ID,TAXONOMY_ID,topics,validate_teaching
from bank.teaching.worksheet import resolve,export_regions
from bank.teaching.generation import prepare,restore,recover
from bank.teaching.parts import label_path


def question(qid,chapters,deps=(),part=('a',)):
    return {'question_id':qid,'original_question_number':'1(a)','marks':2,'topics':[f'ch{max(chapters):02}'],'question':{'source_id':'qp','regions':[{'page_index':0,'bbox':[0,0,10,20]},{'page_index':0,'bbox':[0,100,10,200]}]},'answer':{'source_id':'ms','regions':[]},'metadata':{'teaching':{'taxonomy_id':TAXONOMY_ID,'status':'ready','primary_chapter':max(chapters),'required_chapters':list(chapters),'prerequisites':list(deps),'parent_question_id':'p','part_path':list(part),'source_order':{'a':0,'b':1,'c':2}.get(qid,0),'own_regions':[{'page_index':0,'bbox':[0,100,10,200]}],'contexts':[{'key':'shared','regions':[{'page_index':0,'bbox':[0,0,10,20]}]}],'evidence':[{'reason':'Synthetic requirement fixture','method':'test-fixture'}],'issues':[]}}}

class TeachingTests(unittest.TestCase):
    def test_unknown_source_subset_does_not_create_empty_bank(self):
        sys.path.insert(0,str(ROOT/'scripts'))
        from rebuild_teaching_bank import build
        with tempfile.TemporaryDirectory() as t:
            output=Path(t)/'bank'
            with self.assertRaisesRegex(ValueError,'Unknown QP source IDs'):
                build({}, {'sources':[]}, {}, output, pairs=['mistyped-source'])
            self.assertFalse(output.exists())
    def test_reuse_requires_matching_diagrams_not_just_text(self):
        import fitz
        sys.path.insert(0,str(ROOT/'scripts'))
        from reuse_teaching_decisions import material_key
        q={'question':{'regions':[{'page_index':0,'bbox':[0,0,200,200]}]}}
        keys=[]
        for colour in [(0,0,0),(0,0,0),(1,0,0)]:
            with fitz.open() as doc:
                page=doc.new_page(width=200,height=200)
                page.insert_text((20,30),'Same extracted words')
                page.draw_circle((80,80),20,color=colour)
                keys.append(material_key(q,{'task':'Same extracted words'},doc))
        self.assertEqual(keys[0],keys[1])
        self.assertNotEqual(keys[0],keys[2])
    def test_nineteen_chapters_and_swapped_order(self):
        self.assertEqual(len(topics()),19);self.assertIn('nitrile',topics()[16]['english']);self.assertIn('functional group tests',topics()[17]['english']);self.assertEqual(topics()[18]['english'],'Analytical techniques')
    def test_legacy_parent_mapping_is_not_claimed_as_child_classification(self):
        from bank.teaching.taxonomy import normalize_provenance
        q={'paper':2,'metadata':{'granularity':'whole_question','current_syllabus':{'topic_mapping':[{'topic_id':'old-parent'}]}}}
        normalize_provenance(q);normalize_provenance(q)
        self.assertEqual(q['metadata']['granularity'],'independently_scored_subpart')
        self.assertEqual(q['metadata']['current_syllabus']['topic_mapping'],[])
        self.assertEqual(q['metadata']['legacy_parent_topic_mapping'],[{'topic_id':'old-parent'}])
    def test_last_required_chapter_not_all_tags(self):
        a=question('a',[3,6]);i={'bank_id':BANK_ID,'topics':topics(),'questions':[a]};validate_teaching(i)
        a['topics']=['ch03'];self.assertRaises(DataError,validate_teaching,i)
    def test_dependency_lifts_primary_and_detects_cycle(self):
        a=question('a',[18]);b=question('b',[2],['a']);b['metadata']['teaching']['primary_chapter']=18;b['topics']=['ch18'];i={'bank_id':BANK_ID,'topics':topics(),'questions':[a,b]};validate_teaching(i)
        a['metadata']['teaching']['prerequisites']=['b'];self.assertRaises(DataError,validate_teaching,i)
    def test_prerequisites_order_marks_and_dedup(self):
        rows={'a':question('a',[2]),'b':question('b',[3],['a']),'c':question('c',[4],['a'])}
        class Catalog:
            def question(self,qid):return rows[qid]
        r=resolve(Catalog(),['b','c']);self.assertEqual(r['question_ids'],['a','b','c']);self.assertEqual(r['marks'],6);self.assertEqual(r['group_count'],1)
        rows['a']['metadata']['teaching']['status']='pending';self.assertRaises(DataError,resolve,Catalog(),['b'])
    def test_shared_context_exported_once_not_answers(self):
        a=question('a',[1]);seen=set();self.assertEqual(len(export_regions(a,'question',seen)),2);self.assertEqual(len(export_regions(a,'question',seen)),1);self.assertEqual(export_regions(a,'answer',seen),[])
    def test_tall_vector_unit_does_not_create_empty_question_page(self):
        import fitz
        from bank.render import Renderer
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);source=root/'source.pdf'
            with fitz.open() as doc:
                p=doc.new_page();p.insert_text((50,90),'Authored tall unit');doc.save(source)
            q=question('a',[1]);q.update(year=2024,paper=2,variant=2,session='March')
            region={'page_index':0,'bbox':[40,40,550,800]}
            q['question']['regions']=[region];q['metadata']['teaching'].update(contexts=[],own_regions=[region])
            class Catalog:
                data=root
                def question(self,qid):return q
                def source(self,sid):return {'sha256':'a'*64,'metadata':{}}
            class Sources:
                def resolve(self,sid):return source
            out=Renderer(Catalog(),Sources()).export({'title':'Tall unit','question_ids':['a'],'notes':''},'questions',root/'exports')
            with fitz.open(out) as doc:
                self.assertEqual(len(doc),2)
                self.assertIn('Authored tall unit',doc[1].get_text())
                self.assertEqual(doc[1].get_text().count('Assignment 1'),1)
                self.assertTrue(all(not page.get_images() for page in doc))
    def test_cross_letter_context_correction_never_copies_scored_task(self):
        from bank.teaching.parts import supplement_contexts
        intro={'key':'4(c)','regions':[{'page_index':1,'bbox':[40,90,500,150]}]}
        parts=[{'id':'c-i','contexts':[intro],'own_regions':[{'page_index':1,'bbox':[40,160,500,250]}]}, {'id':'d-i','contexts':[]}]
        rule={'d-i':[{'from_question_id':'c-i','context_key':'4(c)','reason':'Defines the symbols used in d.'}]}
        supplement_contexts(parts,rule);supplement_contexts(parts,rule)
        self.assertEqual(parts[1]['contexts'],[intro])
        with self.assertRaises(ValueError):supplement_contexts(parts,{'d-i':[dict(rule['d-i'][0],context_key='own_regions')]})
        with self.assertRaises(ValueError):supplement_contexts(parts,{'d-i':[dict(rule['d-i'][0],from_question_id='another-parent')]})
    def test_context_correction_schema(self):
        from jsonschema import Draft202012Validator,ValidationError
        schema=json.loads((ROOT/'schemas/teaching-context-overrides.schema.json').read_text())
        validator=Draft202012Validator(schema)
        value=json.loads((ROOT/'indexes/teaching19-context-overrides.json').read_text());validator.validate(value)
        value['questions']['invalid']=[{'from_question_id':'a','context_key':'x','reason':''}]
        with self.assertRaises(ValidationError):validator.validate(value)
    def test_labels_are_exact_and_not_integer_prefixes(self):
        self.assertEqual(label_path('2(a)(ii)'),(2,('a','ii')));self.assertNotEqual(label_path('2(a)(i)'),label_path('2(a)(ii)'));self.assertIsNone(label_path('2(a)(ii) garbage'))
    def test_state_symbols_are_not_prerequisites(self):
        sys.path.insert(0,str(ROOT/'scripts'))
        from rebuild_teaching_bank import dependencies
        first={'id':'g','label':'2(g)','path':('g',),'order':0,'issues':[],'text':'Define a term.'}
        current={'id':'h','label':'2(h)','path':('h',),'order':1,'issues':[],
                 'text':'Calculate a value for O2(g), Na2O2(s), C4H4S(l). Give units in your answer: O2(g).'}
        dependencies([first,current]);self.assertEqual(current['dependencies'],[]);self.assertEqual(current['issues'],[])
        current['text']='Use your answer to 2(g).';dependencies([first,current]);self.assertEqual(current['dependencies'],['g'])
    def test_rounding_instruction_is_not_prior_answer_reference(self):
        sys.path.insert(0,str(ROOT/'scripts'))
        from rebuild_teaching_bank import dependencies
        for instruction in ['Give your answer to 3 significant figures.', 'Give your answer to 2 decimal places.', 'Give your answer to one decimal place.', 'Give your answer to two significant figures.']:
            row={'id':'a-i','label':'3(a)(i)','path':('a','i'),'order':0,'issues':[],'text':'Calculate pV/nRT. '+instruction}
            dependencies([row]);self.assertEqual(row['dependencies'],[]);self.assertEqual(row['issues'],[])
    def test_hence_within_a_complete_task_does_not_require_previous_question(self):
        sys.path.insert(0,str(ROOT/'scripts'))
        from rebuild_teaching_bank import dependencies
        row={'id':'b','label':'3(b)','path':('b',),'order':0,'issues':[],'text':'(b) Complete the supplied Hess cycle and hence calculate its enthalpy.'}
        dependencies([row]);self.assertEqual(row['dependencies'],[]);self.assertEqual(row['issues'],[])
        first={'id':'a-i','label':'3(a)(i)','path':('a','i'),'order':0,'issues':[],'text':'Calculate x.'}
        second={'id':'a-ii','label':'3(a)(ii)','path':('a','ii'),'order':1,'issues':[],'text':'(ii) Hence calculate y.'}
        dependencies([first,second]);self.assertEqual(second['dependencies'],['a-i'])
    def test_malformed_ms_label_does_not_enlarge_previous_answer(self):
        import fitz
        from bank.teaching.parts import ms_parts
        with fitz.open() as doc:
            doc.new_page();p=doc.new_page(width=842,height=595)
            for x,text in [(60,'Question'),(180,'Answer'),(740,'Marks')]:p.insert_text((x,65),text)
            for y,label,text,score in [(100,'3(a)(i)','First response',1),(200,'4(a(i)','Unmatched typo response',2),(300,'4(a)(ii)','Second response',3)]:
                p.insert_text((60,y),label);p.insert_text((180,y),text);p.insert_text((770,y),str(score))
            for y in [75,175,275,375]:p.draw_line((55,y),(800,y))
            parts,issues=ms_parts(doc)
            self.assertEqual(parts[(3,('a','i'))]['marks'],1)
            self.assertNotIn('typo',parts[(3,('a','i'))]['text'])
            self.assertNotIn((4,('a','i')),parts)
            self.assertEqual(parts[(4,('a','ii'))]['marks'],3)
    def test_ms_label_excludes_parenthesised_answer_prose(self):
        from bank.teaching.parts import ms_label
        self.assertEqual(ms_label([(30,90,75,100,'1(a)(ii)'),(90,90,160,100,'(the')]),((1,('a','ii')),True))
        self.assertEqual(ms_label([(30,90,100,100,'1(b)(i)(v)')]),(None,True))
        self.assertEqual(ms_label([(30,90,100,100,'9(.03)')]),(None,False))
    def test_total_electron_row_is_scored_but_subtotal_is_not(self):
        import fitz
        from bank.importer.ms_layout import count_marks
        with fitz.open() as doc:
            p=doc.new_page(width=842,height=595)
            for x,text in [(60,'Question'),(180,'Answer'),(740,'Marks')]:p.insert_text((x,65),text)
            for y,text,score in [(100,'total electrons in s subshell',1),(140,'total electrons in p subshell',1),(180,'Total:',2)]:
                p.insert_text((180,y),text);p.insert_text((770,y),str(score))
            self.assertEqual(count_marks(p,p.get_text('words')),2)
    def test_overlapping_old_font_label_keeps_roman_identity(self):
        import fitz
        from bank.teaching.parts import ms_parts
        with fitz.open() as doc:
            doc.new_page()
            p=doc.new_page(width=842,height=595)
            for x,text in [(60,'Question'),(180,'Answer'),(740,'Marks')]:p.insert_text((x,65),text)
            for y,roman,score in [(100,'i',1),(200,'ii',2)]:
                p.insert_text((70,y),'3(');p.insert_text((76,y),'(b)('+roman+')')
                p.insert_text((180,y),'Authored response');p.insert_text((770,y),str(score))
            for y in [75,175,260]:p.draw_line((55,y),(800,y))
            parts,issues=ms_parts(doc)
            self.assertEqual(issues,[])
            self.assertEqual(parts[(3,('b','i'))]['marks'],1)
            self.assertEqual(parts[(3,('b','ii'))]['marks'],2)
    def test_fingerprint_includes_shared_context_not_only_stem(self):
        from bank.teaching.decisions import fingerprint
        q=question('a',[1]);sources={'qp':{'sha256':'a'*64},'ms':{'sha256':'b'*64}};first=fingerprint(q,sources)
        q['question']['regions'][0]['bbox'][3]+=1;self.assertNotEqual(first,fingerprint(q,sources))
    def test_interpart_table_is_context_for_following_task(self):
        import fitz
        from bank.teaching.parts import qp_parts
        with fitz.open() as doc:
            page=doc.new_page();page.insert_text((50,75),'1 Shared root')
            page.insert_text((72,110),'(a) Information for part a.')
            page.insert_text((95,140),'(i) Give a definition.')
            page.insert_text((535,175),'[1]')
            page.insert_text((95,205),'A shared table for the following questions.')
            page.draw_rect(fitz.Rect(95,215,400,250));page.insert_text((110,235),'given data: 123')
            page.insert_text((92,290),'(ii) Use the given table.')
            page.insert_text((535,350),'[2]')
            parts,issues=qp_parts(doc,[{'page_index':0,'bbox':[25,60,575,380]}],1)
            self.assertEqual(issues,[]);self.assertEqual([p['marks'] for p in parts],[1,2])
            self.assertNotIn('shared table',parts[0]['text'])
            text=' '.join(page.get_text(clip=fitz.Rect(r['bbox'])) for c in parts[1]['contexts'] for r in c['regions'])
            self.assertIn('shared table',text);self.assertIn('123',text)
    def test_referenced_appendix_stays_with_scored_task(self):
        import fitz
        from bank.teaching.parts import qp_parts
        with fitz.open() as doc:
            page=doc.new_page();page.insert_text((50,75),'1 Shared root')
            page.insert_text((72,110),'(a) Shared introduction.')
            page.insert_text((95,140),'(i) Use Table 4.2 to compare the spectra.')
            page.insert_text((535,175),'[1]')
            page.insert_text((95,205),'Table 4.2')
            page.insert_text((110,235),'Infrared data')
            page.insert_text((92,290),'(ii) Calculate relative mass.')
            page.insert_text((535,350),'[2]')
            parts,issues=qp_parts(doc,[{'page_index':0,'bbox':[25,60,575,380]}],1)
            self.assertEqual(issues,[])
            self.assertIn('Infrared data',parts[0]['text'])
            self.assertFalse(any('lead-after' in c['key'] for c in parts[1]['contexts']))
    def test_labelled_compound_after_score_is_shared_context(self):
        import fitz
        from bank.teaching.parts import qp_parts
        with fitz.open() as doc:
            page=doc.new_page();page.insert_text((50,75),'1 Shared root')
            page.insert_text((72,110),'(a) Shared introduction.')
            page.insert_text((95,140),'(i) Draw compound Y.')
            page.insert_text((535,175),'[2]')
            page.insert_text((95,205),'Z, C5H10O, has a branched carbon chain.')
            page.insert_text((92,290),'(ii) Draw compound Z.')
            page.insert_text((535,350),'[3]')
            parts,issues=qp_parts(doc,[{'page_index':0,'bbox':[25,60,575,380]}],1)
            self.assertEqual(issues,[])
            self.assertNotIn('branched',parts[0]['text'])
            text=' '.join(page.get_text(clip=fitz.Rect(r['bbox'])) for c in parts[1]['contexts'] for r in c['regions'])
            self.assertIn('branched carbon chain',text)
    def test_archive_once_preserves_old_jobs_and_local_overlays(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'profile';res=Path(t)/'resources';write_json(res/'indexes/question-index.json',{'bank_id':BANK_ID});write_json(root/'data/jobs.local.json',{'old':'work'});write_json(root/'data/bank-updates/current.json',{'generation':'generations/old'});write_json(root/'data/question-index.local.json',{'calibrated':True})
            archive=prepare(root,res);self.assertIsNotNone(archive);self.assertFalse((root/'data/jobs.local.json').exists());self.assertTrue((root/'generation-archives'/archive/'data/question-index.local.json').exists())
            write_json(root/'data/new-work.json',{'new':'work'});self.assertIsNone(prepare(root,res));self.assertTrue((root/'data/new-work.json').exists())
            result=restore(root,archive);self.assertEqual(json.loads((root/'data/jobs.local.json').read_text()),{'old':'work'});self.assertTrue((root/'generation-archives'/result['new_generation_archived_as']/'data/new-work.json').exists())
    def test_interrupted_switch_recovers_old_generation(self):
        with tempfile.TemporaryDirectory() as t:
            r=Path(t);a='a'*32;write_json(r/'generation-archives'/a/'data/old.json',{'old':1});write_json(r/'data/incomplete.json',{});write_json(r/'.teaching-transition.json',{'archive_id':a});recover(r);self.assertTrue((r/'data/old.json').exists());self.assertFalse((r/'.teaching-transition.json').exists())
    def test_fresh_profile_has_no_redundant_archive(self):
        with tempfile.TemporaryDirectory() as t:
            r=Path(t);write_json(r/'resources/indexes/question-index.json',{'bank_id':BANK_ID});self.assertIsNone(prepare(r/'profile',r/'resources'));self.assertFalse((r/'profile/generation-archives').exists())

if __name__=='__main__':unittest.main()
