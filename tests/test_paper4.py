"""A2 classification boundaries, preserved answer space, and AS coexistence."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
import fitz
from fixtures import ROOT
sys.path.insert(0,str(ROOT/'app'))
from bank.format import DataError
from bank.teaching.taxonomy import BANK_ID,A2_TAXONOMY_ID,topics,validate_teaching
from bank.teaching.whitespace import tighten
from test_teaching_bank import question

class Paper4Tests(unittest.TestCase):
    def test_stability_constant_candidates_belong_to_transition_elements(self):
        from bank.teaching.proposals import propose
        for spelling in ['Kstab', 'K stab', 'K_stab', 'K_{stab}', 'stability constant', '稳定常数']:
            record={'question_id':'cie-9701-m25-42-q1-a','task':'Calculate '+spelling,'context':'','answer':''}
            before=copy.deepcopy(record)
            self.assertEqual([hit['chapter'] for hit in propose(record)],[6])
            # Suggestions cannot approve or modify the underlying question.
            self.assertEqual(record,before)

    def test_separated_chemical_subscript_is_not_a_numbered_prior_part(self):
        sys.path.insert(0,str(ROOT/'scripts'))
        from rebuild_teaching_bank import dependencies
        row={'id':'q2-b-iii','path':('b','iii'),'label':'2(b)(iii)','order':0,
             'text':'(iii) Calculate a value for the lattice energy of MgCl 2(s).', 'issues':[]}
        dependencies([row])
        self.assertEqual(row['dependencies'],[])
        self.assertEqual(row['issues'],[])
        prior={'id':'q2-s','path':('s',),'label':'2(s)','order':0,'text':'(s) Calculate the amount.', 'issues':[]}
        current={**row,'order':1,'text':'Use your answer to 2(s).','issues':[]}
        dependencies([prior,current])
        self.assertEqual(current['dependencies'],['q2-s'])

    def test_rotated_ms_identity_proof_reads_the_actual_answer_region(self):
        sys.path.insert(0,str(ROOT/'scripts'))
        from reuse_paper4_judgments import region_raster,validate_reference_decision
        with self.assertRaisesRegex(ValueError,'Obsolete image-identity proof'):
            validate_reference_decision({'evidence':[{'method':'identical-task-context-and-official-ms-rgb-108dpi-v1'}]})
        from bank.pdf_layout import rotation,transform
        with fitz.open() as left,fitz.open() as right:
            for doc,word in [(left,'BLUE'),(right,'PINK')]:
                page=doc.new_page(width=600,height=800)
                page.insert_text((200,650),'Original authored marking instruction: cobalt colour '+word,rotate=90)
            region={'page_index':0,'bbox':[175,200,215,680]}
            self.assertEqual(rotation(left,0),90)
            a=region_raster(left,region);b=region_raster(right,region)
            self.assertGreater(a[0],a[1])
            self.assertNotEqual(a[-1],b[-1])
            self.assertEqual(a,region_raster(left,region))
            # The former logical-rectangle-as-native-clip bug saw only blank
            # paper and could miss different official answers completely.
            wrong=fitz.Rect(region['bbox'])*transform(left,0)
            self.assertEqual(left[0].get_pixmap(clip=wrong).samples,right[0].get_pixmap(clip=wrong).samples)
    def test_syllabus_period_does_not_hide_cancelled_practice_series(self):
        from bank.importer.syllabus import metadata
        m=metadata(2020,[],'May/June')
        self.assertEqual(m['exam_series_status'],'cancelled-published-practice-materials')
        self.assertEqual(m['original_syllabus']['period'],'2019-2021')
        self.assertEqual(m['current_syllabus']['compatibility'],'unknown')
        self.assertEqual(m['current_syllabus']['topic_mapping'],[])
    def test_measured_context_preserves_given_material_without_previous_score(self):
        from bank.teaching.parts import supplement_contexts
        with fitz.open() as doc:
            p=doc.new_page();p.insert_text((50,80),'Given equilibrium and data')
            p.insert_text((50,180),'Previous scored instruction [2]')
            origin={'id':'q1-a','own_regions':[{'page_index':0,'bbox':[25,40,550,220]}],'contexts':[]}
            target={'id':'q1-b','own_regions':[],'contexts':[]}
            item={'from_question_id':'q1-a','context_key':'given','regions':[{'page_index':0,'bbox':[25,40,550,110]}],'reason':'Keep supplied data only.'}
            supplement_contexts([origin,target],{'q1-b':[item]},doc)
            self.assertEqual(target['contexts'][0]['regions'],item['regions'])
            self.assertEqual(origin['contexts'],[])
            bad=copy.deepcopy(item);bad['regions'][0]['bbox'][3]=210
            with self.assertRaisesRegex(ValueError,'scored task'):
                supplement_contexts([origin,target],{'q1-b':[bad]},doc)
            bad=copy.deepcopy(item);bad['regions'][0]['bbox'][0]=0
            with self.assertRaisesRegex(ValueError,'within its source task'):
                supplement_contexts([origin,target],{'q1-b':[bad]},doc)
            with self.assertRaisesRegex(ValueError,'same parent'):
                supplement_contexts([target],{'q1-b':[item]},doc)
    def test_as_and_a2_chapters_have_distinct_identifiers(self):
        self.assertEqual(len(topics()),19);self.assertEqual(len(topics('A2')),12)
        self.assertFalse({t['id'] for t in topics()}&{t['id'] for t in topics('A2')})
        self.assertIn('phenylamine',topics('A2')[6]['english']);self.assertIn('Chromatography',topics('A2')[11]['english'])
    def test_a2_dependency_maximum_and_course_contract(self):
        a=question('a',[7]);b=question('b',[9],['a'],('b',))
        for q in [a,b]:q.update(paper=4);q['metadata']['teaching']['taxonomy_id']=A2_TAXONOMY_ID;q['topics']=['a2-ch'+str(q['metadata']['teaching']['primary_chapter']).zfill(2)]
        index={'bank_id':BANK_ID,'topics':topics()+topics('A2'),'questions':[a,b]}
        validate_teaching(index)
        b['metadata']['teaching']['primary_chapter']=7;b['topics']=['a2-ch07']
        with self.assertRaises(DataError):validate_teaching(index)
        b['metadata']['teaching']['required_chapters']=[19]
        with self.assertRaises(DataError):validate_teaching(index)
    def test_outer_blank_removed_but_answer_line_and_internal_gap_retained(self):
        with fitz.open() as doc:
            p=doc.new_page(width=600,height=800);p.insert_text((50,60),'Original authored stem')
            p.draw_line((60,350),(500,350));p.insert_text((520,380),'[2]')
            original={'page_index':0,'bbox':[25,25,575,750]};new,proof=tighten(doc,original)
            self.assertIsNotNone(proof);self.assertGreater(new['bbox'][3],380);self.assertLess(new['bbox'][3],410)
            self.assertEqual(new['bbox'][::2],original['bbox'][::2]);self.assertTrue(proof['discarded_bands_ink_free'])
            self.assertIn('stem',p.get_text(clip=fitz.Rect(new['bbox'])))
    def test_empty_answer_frame_and_chemical_bonds_are_protected(self):
        with fitz.open() as doc:
            p=doc.new_page(width=600,height=800);p.draw_rect(fitz.Rect(50,80,500,500));p.draw_line((100,530),(150,560))
            new,proof=tighten(doc,{'page_index':0,'bbox':[25,25,575,750]})
            self.assertLess(new['bbox'][1],80);self.assertGreater(new['bbox'][3],560)
            self.assertTrue(proof['internal_answer_space_preserved'])
    def test_entirely_blank_region_is_not_deleted(self):
        with fitz.open() as doc:
            doc.new_page();r={'page_index':0,'bbox':[25,30,500,700]}
            self.assertEqual(tighten(doc,r),(r,None))
    def test_overprinted_ms_label_does_not_change_parent_number(self):
        from bank.teaching.parts import ms_label
        row=[(70,80,76,91,'6'),(70,80,91,91,'6(c)'),(120,80,180,91,'answer')]
        self.assertEqual(ms_label(row)[0],(6,('c',)))
        row=[(70,80,76,91,'6'),(79,80,92,91,'(c)'),(94,80,110,91,'(ii)')]
        self.assertEqual(ms_label(row)[0],(6,('c','ii')))
    def test_single_unlabelled_task_is_an_independent_scored_unit(self):
        from bank.teaching.parts import qp_parts
        with fitz.open() as doc:
            p=doc.new_page();p.insert_text((50,80),'9 Draw the structures in the boxes.');p.draw_rect(fitz.Rect(70,100,200,220));p.insert_text((520,250),'[6]')
            parts,issues=qp_parts(doc,[{'page_index':0,'bbox':[25,50,575,300]}],9,allow_unlabelled=True)
            self.assertEqual(issues,[]);self.assertEqual(len(parts),1);self.assertEqual(parts[0]['marks'],6);self.assertEqual(parts[0]['path'],())
    def test_ms_compact_letter_label_starts_its_own_answer_row(self):
        from bank.teaching.parts import ms_label,ms_parts,label_path
        self.assertEqual(ms_label([(70,80,105,91,'4b(ii)')]),((4,('b','ii')),True))
        self.assertIsNone(label_path('4b(ii)'))
        self.assertIsNone(ms_label([(70,80,120,91,'4b(i)(ii)')])[0])
        with fitz.open() as doc:
            doc.new_page()
            page=doc.new_page(width=600,height=800)
            for y,label,answer,mark in [(100,'4(b)(i)','Draw the reference cell',3),(200,'4b(ii)','Potential decreases',1)]:
                page.insert_text((30,y),label);page.insert_text((140,y),answer);page.insert_text((550,y),str(mark))
                page.draw_line((25,y-20),(575,y-20))
            page.draw_line((25,240),(575,240))
            parts,_=ms_parts(doc)
            self.assertEqual(parts[(4,('b','i'))]['marks'],3)
            self.assertEqual(parts[(4,('b','ii'))]['marks'],1)
            self.assertNotIn('Potential',parts[(4,('b','i'))]['text'])
    def test_modern_merged_heading_recovers_question_ten(self):
        from bank.importer.parsing import question_starts
        with fitz.open() as doc:
            doc.new_page();p=doc.new_page();p.insert_text((50,80),'9',fontname='hebo');p.insert_text((75,80),'A separate heading')
            p=doc.new_page();p.insert_text((50,80),'10 Original authored continuous heading',fontname='helv')
            self.assertEqual([v[0] for v in question_starts(doc,include_text_run_numbers=True)],[9,10])
    def test_charged_species_state_symbol_is_not_a_prior_subpart(self):
        sys.path.insert(0,str(ROOT/'scripts'));from rebuild_teaching_bank import dependencies
        rows=[{'id':'a','path':('a',),'label':'1(a)','order':0,'text':'Compare Ag+(g) and O2-(g).','issues':[]}]
        dependencies(rows);self.assertEqual(rows[0]['dependencies'],[]);self.assertEqual(rows[0]['issues'],[])
    def test_answer_validation_accepts_proven_trim_and_rejects_lost_answer(self):
        from bank.teaching.parts import ms_parts
        from bank.importer.quality import answer_content_issues
        with fitz.open() as doc:
            doc.new_page(width=842,height=595);p=doc.new_page(width=842,height=595)
            for x,text in [(60,'Question'),(180,'Answer'),(750,'Marks')]:p.insert_text((x,60),text)
            p.insert_text((60,100),'1(a)');p.insert_text((180,100),'Authored response');p.insert_text((770,100),'2')
            entry=ms_parts(doc)[0][(1,('a',))]
            trimmed=[tighten(doc,r)[0] for r in entry['regions']]
            self.assertNotEqual(trimmed,entry['regions'])
            q={'paper':4,'original_question_number':'1(a)','marks':2,'answer':{'regions':trimmed},'metadata':{'teaching':{'status':'ready'}}}
            self.assertEqual(answer_content_issues(q,doc),[])
            q['answer']['regions'][0]['bbox'][3]-=12
            self.assertIn('ms_crop_subpart_region_mismatch',answer_content_issues(q,doc))
    def test_unruled_answer_area_below_inline_score_is_retained(self):
        with fitz.open() as doc:
            p=doc.new_page(width=600,height=800);p.insert_text((50,80),'Draw the structure of the product. [2]')
            region={'page_index':0,'bbox':[25,50,575,600]}
            guarded,_=tighten(doc,region,preserve_answer_space=True)
            self.assertEqual(guarded['bbox'][3],600)
            unguarded,_=tighten(doc,region)
            self.assertLess(unguarded['bbox'][3],110)
    def test_external_reference_requires_registered_hash_identity(self):
        from fixtures import make_fixture
        from bank.format import validate
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);index,manifest,_=make_fixture(root)
            manifest['sources'][0]['metadata']['required_external_documents']=[{'source_id':'missing-booklet','title':'Authored reference','delivery':'separate-reusable-reference'}]
            with self.assertRaisesRegex(DataError,'配套参考'):validate(index,manifest,root/'schemas')
            manifest['sources'][0]['metadata']['required_external_documents'][0]['source_id']='fixture-ms'
            validate(index,manifest,root/'schemas')

if __name__=='__main__':unittest.main()
