"""Exercise the same offline condition parser loaded by the browser."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('node'), 'Node is required for the browser parser')
class PromptTests(unittest.TestCase):
    def parse(self, text, teaching=True,course='AS'):
        script = "const p=require('./app/prompt.js');const args=process.argv.slice(1).map(x=>JSON.parse(x));process.stdout.write(JSON.stringify(p.parseAssignmentDescription(...args)));"
        return json.loads(subprocess.check_output(
            ['node', '-e', script, json.dumps(text), json.dumps(teaching),json.dumps(course)], cwd=ROOT))

    def test_explicit_chapter_count_year_and_paper(self):
        self.assertEqual(self.parse('第17章，8个小问，2025年'),
                         dict(topics=['ch17'], count=8, paper=2, year='2025',course='AS'))

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

    def test_a2_scope_and_special_topics(self):
        self.assertEqual(self.parse('A2 redox equation balancing')['topics'], ['a2-ch03'])
        self.assertEqual(self.parse('A2 滴定计量')['topics'], ['a2-ch03'])
        self.assertEqual(self.parse('A2 VSEPR 分子形状')['topics'], ['a2-ch06'])
        self.assertEqual(self.parse('A2 benzene hybridisation count')['topics'], ['a2-ch07'])
        self.assertEqual(self.parse('A2 有机命名和碘仿检验')['topics'], ['a2-ch11'])
        self.assertEqual(self.parse('Paper 4 第12章 NMR 6个小问')['topics'], ['a2-ch12'])
        self.assertEqual(self.parse('A2 苯胺')['topics'], ['a2-ch07'])
        self.assertEqual(self.parse('A2 脂肪胺和苯胺')['topics'], ['a2-ch07','a2-ch09'])
        self.assertEqual(self.parse('A2 lattice energy')['topics'], ['a2-ch01'])
        for description in ['A2 Kstab', 'A2 K stab', 'A2 K_stab', 'A2 K_{stab}', 'A2 stability constant', 'A2 配合物稳定常数']:
            self.assertEqual(self.parse(description)['topics'], ['a2-ch06'])
        self.assertEqual(self.parse('A2 Kstab equilibrium 10 questions')['topics'], ['a2-ch06'])
        self.assertEqual(self.parse('A2 配合物稳定常数平衡')['topics'], ['a2-ch06'])
        self.assertEqual(self.parse('A2 Kstab and Ksp')['topics'], ['a2-ch04','a2-ch06'])
        self.assertEqual(self.parse('A2 Kstab and partition coefficient')['topics'], ['a2-ch04','a2-ch06'])
        self.assertEqual(self.parse('A2 第4章和第6章 Kstab equilibrium')['topics'], ['a2-ch04','a2-ch06'])
        self.assertEqual(self.parse('A2 有机多步合成')['topics'], ['a2-ch11'])
        self.assertEqual(self.parse('Paper 4 10小问')['paper'],4)
        self.assertEqual(self.parse('第3章 5个小问',course='A2')['topics'],['a2-ch03'])
        self.assertEqual(self.parse('AS 第3章',course='A2')['topics'],['ch03'])
        self.assertEqual(self.parse('A2 pH buffer')['topics'],['a2-ch04'])

    def test_confirmed_organic_methods_do_not_move_coordination_stereoisomers(self):
        for description in ['A2 有机手性', 'A2 stereoisomers', 'A2 enantiomers', 'A2 外消旋',
                            'A2 Diels-Alder', 'A2 臭氧化', 'A2 醛酮还原', 'A2 NaBH4还原酮']:
            self.assertEqual(self.parse(description)['topics'], ['a2-ch11'])
        self.assertEqual(self.parse('A2 配合物光学异构')['topics'], ['a2-ch06'])
        self.assertEqual(self.parse('A2 complex stereoisomers')['topics'], ['a2-ch06'])
        self.assertEqual(self.parse('A2 酰胺还原')['topics'], ['a2-ch09'])
        self.assertNotIn('a2-ch11', self.parse('A2 NaBH4')['topics'])
        self.assertEqual(self.parse('AS 手性')['topics'], ['ch13'])
