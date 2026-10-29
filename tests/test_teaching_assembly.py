"""Release assembly rejects lost AS work identities and stale crop judgments."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from fixtures import ROOT, make_fixture

sys.path.insert(0, str(ROOT / 'app'))
sys.path.insert(0, str(ROOT / 'scripts'))
from bank.format import read_json, write_json
from bank.teaching.decisions import fingerprint
from bank.teaching.taxonomy import BANK_ID, TAXONOMY_ID, A2_TAXONOMY_ID, topics
from assemble_teaching_extension import assemble


class AssemblyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        index, self.manifest, _ = make_fixture(self.root)
        index.update(bank_id=BANK_ID, revision='previous', topics=topics())
        for q in index['questions']:
            q['topics'] = ['ch01']
            q['metadata']['teaching'] = {
                'taxonomy_id': TAXONOMY_ID, 'status': 'ready',
                'primary_chapter': 1, 'required_chapters': [1],
                'prerequisites': [], 'parent_question_id': q['question_id'],
                'part_path': ['a'], 'source_order': 0,
                'own_regions': copy.deepcopy(q['question']['regions']),
                'contexts': [], 'evidence': [{'method': 'authored-fixture',
                                             'reason': 'Original synthetic task'}],
                'issues': [],
            }
        self.old = self.root / 'previous'
        write_json(self.old / 'question-index.json', index)
        write_json(self.old / 'source-manifest.json', self.manifest)
        self.as_folder = self.root / 'as'
        self.save(self.as_folder, index)
        a2 = copy.deepcopy(index)
        a2['topics'] += topics('A2')
        a2['questions'] = [copy.deepcopy(index['questions'][0])]
        q = a2['questions'][0]
        q.update(question_id='original-a2-fixture', paper=4, qualification='A2',
                 topics=['a2-ch06'])
        q['metadata']['teaching'].update(taxonomy_id=A2_TAXONOMY_ID,
            primary_chapter=6, required_chapters=[6],
            parent_question_id=q['question_id'])
        self.a2_folder = self.root / 'a2'
        self.save(self.a2_folder, a2)

    def save(self, folder, index):
        write_json(folder / 'question-index.json', index)
        write_json(folder / 'source-manifest.json', self.manifest)
        source_map = {s['source_id']: s for s in self.manifest['sources']}
        decisions, records = {}, []
        for q in index['questions']:
            fp = fingerprint(q, source_map)
            decisions[q['question_id']] = {
                'fingerprint': fp, 'required_chapters': q['metadata']['teaching']['required_chapters'],
                'evidence': q['metadata']['teaching']['evidence'], 'prerequisites': [],
            }
            records.append({'question_id': q['question_id'], 'fingerprint': fp,
                            'task': '', 'context': '', 'answer': '', 'material_issues': []})
        write_json(folder / 'decisions.json', decisions)
        write_json(folder / 'candidates.private.json', records)

    def tearDown(self):
        self.temp.cleanup()

    def run_assembly(self):
        return assemble(self.as_folder, self.a2_folder, self.old,
                        self.root / 'assembled', 'extension')

    def test_both_courses_preserved_and_private_material_separate(self):
        original = (self.old / 'question-index.json').read_bytes()
        report = self.run_assembly()
        self.assertEqual(report['candidate_units'], 3)
        self.assertEqual(report['unread_units'], 0)
        self.assertFalse((self.root / 'assembled/public/candidates.private.json').exists())
        self.assertEqual((self.old / 'question-index.json').read_bytes(), original)

    def test_cannot_drop_existing_as_id(self):
        index = read_json(self.as_folder / 'question-index.json')
        index['questions'].pop()
        self.save(self.as_folder, index)
        with self.assertRaisesRegex(ValueError, 'preserve every previous question ID'):
            self.run_assembly()
        self.assertFalse((self.root / 'assembled').exists())

    def test_changed_region_requires_new_judgment(self):
        index = read_json(self.a2_folder / 'question-index.json')
        index['questions'][0]['question']['regions'][0]['bbox'][1] += 1
        write_json(self.a2_folder / 'question-index.json', index)
        with self.assertRaisesRegex(ValueError, 'Stale input decision'):
            self.run_assembly()
        self.assertFalse((self.root / 'assembled').exists())
