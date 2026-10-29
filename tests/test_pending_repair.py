"""Conservative visible-ink and physical-source regression cases."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
import fitz
from fixtures import ROOT, make_fixture
from bank.importer.quality import region_issues
from bank.importer.source_audit import audit_pagination
from bank.format import sha256


class PendingRepairTests(unittest.TestCase):
    def test_font_box_overlap_is_safe_only_when_excluded_area_has_no_ink(self):
        with fitz.open() as doc:
            page = doc.new_page(width=600, height=800)
            page.insert_text((60, 100), 'Authored chemical question', fontsize=12)
            # Helvetica's font box extends far above visible capitals and
            # below the actual descenders. A cut through the glyph is unsafe.
            full = {'page_index': 0, 'bbox': [25, 80, 575, 104]}
            self.assertEqual(region_issues(doc, [full]), [])
            self.assertIn('text_crosses_crop_edge', region_issues(doc, [dict(full, bbox=[25, 95, 575, 104])]))
            # Bounding box ends below 103, but the last visible glyph does not.
            self.assertEqual(region_issues(doc, [dict(full, bbox=[25, 80, 575, 102.8])]), [])

    def test_chemical_stroke_in_excluded_box_cannot_be_excused(self):
        from bank.importer.crop_edges import excluded_ink_free
        with fitz.open() as doc:
            page = doc.new_page(width=600, height=800)
            page.draw_line((65, 101), (100, 101), width=.2)
            self.assertFalse(excluded_ink_free(doc, 0, fitz.Rect(60, 90, 110, 105), fitz.Rect(25, 80, 575, 100)))
            self.assertTrue(excluded_ink_free(doc, 0, fitz.Rect(60, 90, 110, 105), fitz.Rect(25, 80, 575, 102)))

    def test_rotated_native_ink_is_not_checked_at_an_unrelated_blank_location(self):
        from bank.importer.crop_edges import excluded_ink_free
        from bank.pdf_layout import transform, rotation
        with fitz.open() as doc:
            page = doc.new_page(width=600, height=800)
            page.insert_text((200, 650), 'Authored marking instruction cobalt blue colour', rotate=90)
            self.assertEqual(rotation(doc, 0), 90)
            matrix = transform(doc, 0)
            rect = fitz.Rect(185, 380, 205, 655) * matrix
            clip = fitz.Rect(185, 400, 205, 600) * matrix
            self.assertFalse(excluded_ink_free(doc, 0, rect, clip))

    def test_deleted_physical_page_is_not_a_reader_error_or_implicitly_blank(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'authored.pdf'
            with fitz.open() as doc:
                page = doc.new_page();page.insert_text((50, 100), 'This document has 4 pages.')
                for label in (3, 4):
                    page = doc.new_page();page.insert_text((290, 40), str(label))
                    page.insert_text((290, 65), '1')  # number in the task, not a second header
                    page.insert_text((50, 100), 'Authored source content')
                doc.save(path)
            source = {'source_id': 'authored', 'sha256': sha256(path)}
            report = audit_pagination(path, source)
            self.assertEqual(report['missing_printed_pages'], [2])
            self.assertEqual(report['page_tree_count'], 3)
            self.assertFalse(report['repaired_on_open'])
            self.assertEqual(report['conclusion'], 'incomplete-physical-source-not-parser-count-error')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                audit_pagination(path, dict(source, sha256='0' * 64))


class ExactMSRepairTests(unittest.TestCase):
    def setUp(self):
        from bank.format import geometry, write_json
        from bank.teaching.taxonomy import BANK_ID, TAXONOMY_ID, topics
        from bank.teaching.decisions import fingerprint
        sys.path.insert(0, str(ROOT / 'scripts'))
        self.temp = tempfile.TemporaryDirectory();self.root = Path(self.temp.name)
        self.index, self.manifest, files = make_fixture(self.root)
        ms = files[1]
        with fitz.open() as doc:
            doc.new_page();page = doc.new_page(width=600, height=800)
            for x, text in [(30, 'Question'), (140, 'Answer'), (550, 'Marks')]:
                page.insert_text((x, 60), text)
            for x, text in [(30, '1a(i)'), (140, 'Original authored rubric'), (550, '5')]:
                page.insert_text((x, 100), text)
            for y in (80, 130):page.draw_line((25, y), (575, y))
            doc.save(ms)
        with fitz.open(ms) as doc:
            self.manifest['sources'][1].update(sha256=sha256(ms), pages=geometry(doc), page_count=len(doc))
        q = self.index['questions'][0]
        q['original_question_number'] = '1(a)(i)';q['answer']['regions'] = [];q['topics'] = []
        q['metadata']['automatic_qa'] = {'status': 'quarantined', 'issues': ['exact_ms_label_missing', 'subpart_marks_mismatch']}
        q['metadata']['teaching'] = dict(taxonomy_id=TAXONOMY_ID, status='pending', primary_chapter=None,
            required_chapters=[1], prerequisites=[], parent_question_id='fixture-parent', part_path=['a', 'i'], source_order=0,
            own_regions=copy.deepcopy(q['question']['regions']), contexts=[],
            evidence=[{'method': 'authored-fixture', 'reason': 'An original authored task.'}],
            issues=['exact_ms_label_missing', 'subpart_marks_mismatch'])
        self.index.update(bank_id=BANK_ID, topics=topics(), questions=[q])
        self.sources = {s['source_id']: s for s in self.manifest['sources']}
        self.paths = {s['source_id']: str(f) for s, f in zip(self.manifest['sources'], files)}
        self.decisions = {q['question_id']: dict(fingerprint=fingerprint(q, self.sources),
                           required_chapters=[1], evidence=copy.deepcopy(q['metadata']['teaching']['evidence']))}
        from bank.teaching.parts import ms_parts
        with fitz.open(ms) as doc:new = copy.deepcopy(q);new['answer']['regions'] = ms_parts(doc)[0][(1, ('a', 'i'))]['regions']
        self.approvals = {'schema_version': '1.0.0', 'repairs': [dict(question_id=q['question_id'],
            before_fingerprint=fingerprint(q, self.sources), after_fingerprint=fingerprint(new, self.sources),
            reason='Read the authored task and exact synthetic official row including all five marks.') ]}
        self.save()

    def save(self):
        from bank.format import write_json
        for name, obj in [('question-index', self.index), ('source-manifest', self.manifest),
                          ('decisions', self.decisions), ('paths', self.paths), ('approvals', self.approvals)]:
            write_json(self.root / (name + '.json'), obj)

    def tearDown(self):self.temp.cleanup()

    def run_repair(self, suffix='out'):
        from repair_pending_ms import repair
        return repair(self.root, self.root / 'paths.json', self.root / 'decisions.json',
                      self.root / 'approvals.json', self.root / suffix, 'repair.2')

    def test_exact_label_repair_rebinds_evidence_without_changing_qp_or_sources(self):
        from bank.format import read_json
        before = (self.root / 'question-index.json').read_bytes()
        self.assertEqual(self.run_repair()['remaining_pending'], 0)
        repaired = read_json(self.root / 'out/question-index.json')['questions'][0]
        self.assertEqual(repaired['question'], self.index['questions'][0]['question'])
        self.assertEqual(repaired['metadata']['teaching']['primary_chapter'], 1)
        self.assertEqual((self.root / 'question-index.json').read_bytes(), before)
        self.assertEqual(read_json(self.root / 'out/source-manifest.json'), self.manifest)
        with self.assertRaisesRegex(ValueError, 'fresh output'):self.run_repair()
        self.assertEqual(self.run_repair('repeat')['direct_ms_repairs'], 1)

    def test_stale_before_or_after_approval_cannot_rebind(self):
        for field in ['before_fingerprint', 'after_fingerprint']:
            with self.subTest(field=field):
                original = copy.deepcopy(self.approvals)
                self.approvals['repairs'][0][field] = '0' * 64;self.save()
                with self.assertRaisesRegex(ValueError, 'Stale'):self.run_repair()
                self.assertFalse((self.root / 'out').exists())
                self.approvals = original

    def test_other_pending_reason_or_source_integrity_cannot_be_waived(self):
        q = self.index['questions'][0]
        q['metadata']['teaching']['issues'].append('official_question_withdrawn');self.save()
        with self.assertRaisesRegex(ValueError, 'cannot waive'):self.run_repair()
        q['metadata']['teaching']['issues'].pop()
        self.manifest['sources'][0]['metadata']['source_integrity_issues'] = ['physical_page_count_mismatch'];self.save()
        with self.assertRaisesRegex(ValueError, 'integrity unresolved'):self.run_repair()

    def test_changed_source_file_fails_before_any_output(self):
        Path(self.paths['fixture-ms']).write_bytes(b'broken source')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):self.run_repair()
        self.assertFalse((self.root / 'out').exists())


class ScopeExtensionTests(unittest.TestCase):
    save = ExactMSRepairTests.save
    tearDown = ExactMSRepairTests.tearDown

    def setUp(self):
        from bank.format import write_json
        from bank.teaching.taxonomy import A2_LEGACY_TAXONOMY_ID, topics
        from bank.teaching.decisions import fingerprint
        from bank.teaching.parts import ms_parts
        ExactMSRepairTests.setUp(self)
        q = self.index['questions'][0]
        with fitz.open(self.paths['fixture-ms']) as doc:
            q['answer']['regions'] = ms_parts(doc)[0][(1, ('a', 'i'))]['regions']
        q.update(paper=4, qualification='A2')
        q['metadata']['automatic_qa'] = {'status': 'passed', 'issues': []}
        q['metadata']['teaching'].update(taxonomy_id=A2_LEGACY_TAXONOMY_ID, required_chapters=[],
            issues=['no_reliable_primary_chapter', 'single_step_cycloaddition_without_reliable_taxonomy_fit'])
        self.index['topics'] = topics() + topics('A2', legacy=True)
        fp = fingerprint(q, self.sources);self.decisions[q['question_id']]['fingerprint'] = fp
        self.decisions[q['question_id']]['required_chapters'] = []
        self.approvals = dict(schema_version='1.0.0', policy_id='a2-ch11-selected-single-step-methods-2026-10-29',
            confirmation_basis='Direct teacher decision recorded for the original authored fixture.',
            questions=[dict(question_id=q['question_id'], fingerprint=fp,
                reason='The authored single-step cycloaddition belongs to the teacher-confirmed chapter 11 scope.',
                knowledge_tags=['organic.diels-alder', 'synthesis.single-step'])])
        self.save()

    def run_scope(self):
        from apply_organic_scope_extension import apply
        return apply(self.root, self.root / 'paths.json', self.root / 'decisions.json',
                     self.root / 'approvals.json', self.root / 'out', 'scope.2')

    def test_scope_extension_keeps_paper4_a2_identity_and_single_step_tags(self):
        from bank.format import read_json
        self.assertEqual(self.run_scope()['newly_ready'], 1)
        q = read_json(self.root / 'out/question-index.json')['questions'][0]
        self.assertEqual((q['paper'], q['qualification']), (4, 'A2'))
        self.assertEqual(q['metadata']['teaching']['primary_chapter'], 11)
        self.assertIn('synthesis.single-step', q['metadata']['knowledge_tags'])
        self.assertEqual(q['question'], self.index['questions'][0]['question'])

    def test_curriculum_confirmation_does_not_clear_missing_source_or_crop_alarm(self):
        q = self.index['questions'][0]
        q['metadata']['teaching']['issues'].append('question:text_crosses_crop_edge')
        self.manifest['sources'][0]['metadata']['source_integrity_issues'] = ['physical_page_count_mismatch']
        self.save();report = self.run_scope()
        self.assertEqual(report['newly_ready'], 0)
        self.assertIn('source:physical_page_count_mismatch', report['questions'][0]['remaining_issues'])
        self.assertIn('question:text_crosses_crop_edge', report['questions'][0]['remaining_issues'])

    def test_new_semantics_cannot_be_packaged_for_old_reader(self):
        from bank.updates import build_package
        from bank.format import read_json, DataError
        self.run_scope();index = read_json(self.root / 'out/question-index.json')
        with self.assertRaisesRegex(DataError, '最低 App'):
            build_package(self.root / 'wrong.qbank', index, self.manifest, self.index,
                          self.manifest, ROOT / 'schemas', 'Original authored scope update', minimum_app_version='0.5.1')


class TeachingRepairTests(unittest.TestCase):
    save = ExactMSRepairTests.save
    tearDown = ExactMSRepairTests.tearDown

    def setUp(self):
        from bank.teaching.decisions import fingerprint
        from apply_teaching_repairs import teaching_fingerprint
        ScopeExtensionTests.setUp(self)
        q = self.index['questions'][0]
        q['metadata']['teaching'].update(status='ready', primary_chapter=9, required_chapters=[9], issues=[])
        q['topics'] = ['a2-ch09']
        self.approvals = dict(schema_version='1.0.0',
            policy_id='a2-organic-stereochemistry-and-carbonyl-reduction-2026-10-29',
            confirmation_basis='Original authored test for the teacher-confirmed organic stereochemistry rule.',
            questions=[dict(question_id=q['question_id'], material_fingerprint=fingerprint(q, self.sources),
                before_teaching_fingerprint=teaching_fingerprint(q), required_chapters=[11],
                knowledge_tags=['organic.stereochemistry'],
                reason='The original authored organic stereochemistry task uses the teacher-confirmed chapter eleven rule.')])
        self.save()

    def run_teaching(self):
        from apply_teaching_repairs import apply
        return apply(self.root, self.root / 'paths.json', self.root / 'decisions.json',
                     self.root / 'approvals.json', self.root / 'out', 'teaching.2')

    def test_changed_prerequisite_recomputes_existing_ready_child_primary_chapter(self):
        from bank.format import read_json
        parent = self.index['questions'][0];child = copy.deepcopy(parent)
        child['question_id'] = 'authored-dependent-child';child['original_question_number'] = '1(b)'
        child['metadata']['teaching'].update(required_chapters=[7], source_order=1, part_path=['b'],
            prerequisites=[parent['question_id']])
        self.index['questions'].append(child);self.save()
        report = self.run_teaching()
        self.assertEqual(report['newly_pending'], [])
        qs = read_json(self.root / 'out/question-index.json')['questions']
        self.assertEqual([q['metadata']['teaching']['primary_chapter'] for q in qs], [11, 11])
        self.assertEqual(report['dependent_chapter_changes'][0]['question_id'], child['question_id'])
        self.assertEqual(qs[0]['qualification'], 'A2')

    def test_material_bound_but_changed_prior_judgment_is_rejected(self):
        q = self.index['questions'][0]
        q['metadata']['teaching'].update(required_chapters=[8], primary_chapter=8)
        q['topics'] = ['a2-ch08'];self.save()
        with self.assertRaisesRegex(ValueError, 'Stale teaching'):self.run_teaching()
        self.assertFalse((self.root / 'out').exists())

    def test_official_scoring_alarm_cannot_be_resolved_by_classification(self):
        from apply_teaching_repairs import teaching_fingerprint
        q = self.index['questions'][0]
        q['metadata']['teaching'].update(status='pending', primary_chapter=None,
            issues=['no_reliable_primary_chapter', 'official_question_withdrawn'])
        q['topics'] = []
        self.approvals['questions'][0]['before_teaching_fingerprint'] = teaching_fingerprint(q)
        self.save();report = self.run_teaching()
        self.assertEqual(report['newly_ready'], [])
        self.assertIn('official_question_withdrawn', report['changes'][0]['remaining_issues'])
