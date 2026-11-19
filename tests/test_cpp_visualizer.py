import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cpp_visualizer import analyze_cpp, tokenize_cpp

class CppVisualizationTests(unittest.TestCase):
    def test_tokenizer_reports_modulus_and_source_position(self):
        toks=tokenize_cpp('int main(){ return 7 % 4; }')
        token=next(t for t in toks if t['lexeme']=='%')
        self.assertEqual(token['type'],'OPERATOR')
        self.assertEqual(token['line'],1)
    def test_analysis_produces_visualization_data(self):
        source='#include <iostream>\nint main(){ int value=9; if(value>2){ value%=4; } return value; }\n'
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'sample.cpp';path.write_text(source)
            data=analyze_cpp(source,path)
        self.assertGreater(len(data['tokens']),0)
        self.assertTrue(data['ast_tree']['name'])
        self.assertGreaterEqual(len(data['cfg'].nodes),2)
        self.assertTrue(data['symbols'])
        self.assertIn('TranslationUnitDecl',str(data['ast_tree']) if data['clang'] else data['ast_tree']['name']) if data['clang'] else self.assertIn('approximate',data['ast_detail'].lower())
if __name__=='__main__': unittest.main()
