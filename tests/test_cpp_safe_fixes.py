import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cpp_safe_fixes import CppSafeFixer

class CppSafeFixTests(unittest.TestCase):
    def test_header_and_simple_semicolon_suggestions(self):
        source='int main() {\n  std::cout << "hi"\n}\n'
        fixes=CppSafeFixer(source).suggestions()
        self.assertTrue(any('header' in d.lower() for _,d,_ in fixes))
        self.assertTrue(any('semicolon' in d.lower() for _,d,_ in fixes))
    def test_known_typo_suggestion(self):
        fixes=CppSafeFixer('int main(){\n coutt << 1;\n}\n').suggestions()
        self.assertTrue(any('typo' in d.lower() for _,d,_ in fixes))
    def test_preview_apply_keeps_original(self):
        source='int main(){\n std::cout << 1\n}\n'
        fixer=CppSafeFixer(source)
        fixed=fixer.apply()
        self.assertIn('#include <iostream>', fixed)
        self.assertIn('std::cout << 1;', fixed)
        self.assertEqual(fixer.original, source)
    def test_combines_typo_and_semicolon_on_same_line(self):
        source='int main(){\n coutt << 1\n}\n'
        fixer=CppSafeFixer(source)
        fixed=fixer.apply()
        self.assertIn('cout << 1;', fixed)
        self.assertNotIn('coutt', fixed)
    def test_does_not_change_typos_inside_strings(self):
        source='int main(){\n std::cout << "coutt retrun";\n}\n'
        fixed=CppSafeFixer(source).apply()
        self.assertIn('"coutt retrun"', fixed)
    def test_corrects_unqualified_stream_and_adds_header_after_typo(self):
        source='int main(){\n coutt << 7\n}\n'
        fixed=CppSafeFixer(source).apply()
        self.assertIn('#include <iostream>', fixed)
        self.assertIn('std::cout << 7;', fixed)
        self.assertNotIn('coutt', fixed)
    def test_missing_return_inserted_inside_main(self):
        source='int main(){\n std::cout << 1;\n}\n'
        fixed=CppSafeFixer(source).apply()
        self.assertIn('return 0;', fixed)
    def test_no_fix_for_control_header(self):
        self.assertFalse(any('semicolon' in d.lower() for _,d,_ in CppSafeFixer('if (x) {\n').suggestions()))

if __name__=='__main__': unittest.main()
