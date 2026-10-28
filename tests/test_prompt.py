"""Exercise the same offline condition parser loaded by the browser."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('node'), 'Node is required for the browser parser')
class PromptTests(unittest.TestCase):
    def parse(self, text, teaching=True):
        script = "const p=require('./app/prompt.js');process.stdout.write(JSON.stringify(p.parseAssignmentDescription(JSON.parse(process.argv[1]),JSON.parse(process.argv[2]))));"
        return json.loads(subprocess.check_output(
            ['node', '-e', script, json.dumps(text), json.dumps(teaching)], cwd=ROOT))

    def test_explicit_chapter_count_year_and_paper(self):
        self.assertEqual(self.parse('第17章，8个小问，2025年'),
                         dict(topics=['ch17'], count=8, paper=2, year='2025'))

    def test_mass_spectrum_boundaries(self):
        self.assertEqual(self.parse('质谱计算相对原子质量')['topics'], ['ch01'])
        self.assertEqual(self.parse('isotope mass spectrum')['topics'], ['ch01'])
        self.assertEqual(self.parse('mass spectrum fragmentation')['topics'], ['ch19'])
        self.assertEqual(self.parse('M+1 推算碳原子数')['topics'], ['ch19'])

    def test_infrared_and_explicit_scope(self):
        self.assertEqual(self.parse('羧酸的红外光谱')['topics'], ['ch19'])
        self.assertEqual(self.parse('第13章 alcohol nomenclature')['topics'], ['ch13'])
        self.assertEqual(self.parse('chapter 13 and 第17章')['topics'], ['ch13', 'ch17'])

    def test_english_count_and_legacy_parser(self):
        self.assertEqual(self.parse('alcohols 20 questions Paper 1')['topics'], ['ch16'])
        self.assertEqual(self.parse('alcohols 20 questions Paper 1')['count'], 20)
        self.assertEqual(self.parse('原子 5题', False)['topics'], ['atomic'])
        self.assertEqual(self.parse('999 questions')['count'], 200)
