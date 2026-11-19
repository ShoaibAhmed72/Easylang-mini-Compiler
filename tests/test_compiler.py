import unittest,sys,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from easylang_studio import *
class CompilerTests(unittest.TestCase):
 def test_compile_run(self):
  p=Parser(Lexer("START\nint x = 2 + 3 * 4;\nprint(x);\nEND").scan()).parse()
  sem=SemanticAnalyzer();sem.analyze(p);self.assertEqual(Interpreter().run(p),"14\n")
 def test_loop(self):
  p=Parser(Lexer("START\nint x = 3;\nwhile (x > 0) { print(x); x = x - 1; }\nEND").scan()).parse()
  self.assertEqual(Interpreter().run(p),"3\n2\n1\n")
 def test_semantic(self):
  p=Parser(Lexer("START\nprint(x);\nEND").scan()).parse()
  with self.assertRaises(CompilerError):SemanticAnalyzer().analyze(p)
 def test_grammar(self):
  g=Grammar.parse("S -> a A | b\nA -> c | ε")
  ff=FirstFollow(g);self.assertIn("a",ff.first["S"])
 def test_left_recursion(self):
  g=Grammar.parse("E -> E + T | T\nT -> id")
  self.assertNotEqual(remove_left_recursion(g).format(),g.format())
 def test_factor(self):
  g=Grammar.parse("S -> a b | a c")
  self.assertIn("S'",left_factor(g).rules)
 def test_predictive_parse(self):
  g=Grammar.parse("S -> a A\nA -> b | ε")
  ok,trace,msg=predictive_parse(LL1Table(g),"a b")
  self.assertTrue(ok,msg)

class CompilerPipelineRegressionTests(unittest.TestCase):
 def parse(self,source):
  return Parser(Lexer(source).scan()).parse()
 def compile(self,source):
  program=self.parse(source);semantic=SemanticAnalyzer();semantic.analyze(program)
  return program,semantic
 def test_valid_program_and_variable_output(self):
  program,semantic=self.compile("START\nint total = 6 * 7;\nprint(total);\nEND")
  self.assertEqual(Interpreter().run(program),"42\n")
  self.assertIn("total = ",CodeGenerator().generate(program))
  self.assertEqual(semantic.symbols["total"]["type"],"int")
 def test_if_else_true_and_false_branches(self):
  for value,expected in ((1,"yes\n"),(0,"no\n")):
   program,_=self.compile(f'START\nint flag = {value};\nif (flag == 1) {{ print("yes"); }} else {{ print("no"); }}\nEND')
   self.assertEqual(Interpreter().run(program),expected)
 def test_nested_if_and_loop(self):
  program,_=self.compile(
   "START\nint x = 3;\nwhile (x > 0) { if (x > 1) { print(x); } else { print(0); } x = x - 1; }\nEND"
  )
  self.assertEqual(Interpreter().run(program),"3\n2\n0\n")
 def test_missing_start_and_end_are_reported(self):
  with self.assertRaises(CompilerErrors) as missing_start:
   self.parse("int x = 1;\nEND")
  self.assertIn("Expected START",str(missing_start.exception))
  with self.assertRaises(CompilerErrors) as missing_end:
   self.parse("START\nint x = 1;")
  self.assertIn("Expected END",str(missing_end.exception))
 def test_empty_file_reports_both_program_delimiters(self):
  with self.assertRaises(CompilerErrors) as caught:
   self.parse("")
  self.assertGreaterEqual(len(caught.exception.errors),2)
 def test_parser_recovers_and_reports_multiple_errors(self):
  with self.assertRaises(CompilerErrors) as caught:
   self.parse("START\nint = ;\nprint(; \nint y = 2;\nEND")
  self.assertGreaterEqual(len(caught.exception.errors),2)
  self.assertTrue(all(error.column > 0 and error.hint for error in caught.exception.errors))
 def test_missing_semicolon_and_brace_have_positions(self):
  for source in ("START\nint x = 1\nEND", "START\nif (1 == 1) { print(1);\nEND"):
   with self.assertRaises(CompilerErrors) as caught:
    self.parse(source)
   self.assertGreater(caught.exception.errors[0].line,0)
   self.assertGreater(caught.exception.errors[0].column,0)
 def test_undeclared_variable_is_semantic_error(self):
  with self.assertRaises(CompilerError) as caught:
   self.compile("START\nprint(missing);\nEND")
  self.assertIn("not declared",str(caught.exception))
 def test_redeclaration_is_semantic_error(self):
  with self.assertRaises(CompilerError) as caught:
   self.compile("START\nint x = 1;\nint x = 2;\nEND")
  self.assertIn("already declared",str(caught.exception))
 def test_type_mismatch_is_semantic_error(self):
  with self.assertRaises(CompilerError) as caught:
   self.compile('START\nint x = "abc";\nEND')
  self.assertIn("Cannot assign string to int",str(caught.exception))
 def test_use_before_assignment_is_semantic_error(self):
  with self.assertRaises(CompilerError) as caught:
   self.compile("START\nint x;\nprint(x);\nEND")
  self.assertIn("before assignment",str(caught.exception))
 def test_constant_division_by_zero_is_semantic_error(self):
  with self.assertRaises(CompilerError) as caught:
   self.compile("START\nint x = 5 / (3 - 3);\nEND")
  self.assertIn("Division by zero",str(caught.exception))
 def test_dynamic_division_by_zero_is_runtime_error(self):
  program,_=self.compile("START\nint zero = 0;\nint x = 5 / zero;\nEND")
  with self.assertRaises(CompilerError) as caught:
   Interpreter().run(program)
  self.assertIn("Division by zero",str(caught.exception))
 def test_unterminated_string_has_line_column_and_hint(self):
  with self.assertRaises(CompilerError) as caught:
   Lexer('START\nprint("unterminated\nEND').scan()
  error=caught.exception
  self.assertEqual((error.line,error.column),(2,20))
  self.assertTrue(error.hint)
 def test_unknown_character_reports_source_column(self):
  with self.assertRaises(CompilerError) as caught:
   Lexer("START\n  @\nEND").scan()
  self.assertEqual((caught.exception.line,caught.exception.column),(2,3))
 def test_comments_line_tracking_negative_integer_and_float_rejection(self):
  tokens=Lexer("START // comment\nint x = -2; // tail\nEND").scan()
  self.assertEqual(tokens[-1].line,3)
  self.assertEqual([token.type for token in tokens if token.type in ("MINUS","NUMBER")],["MINUS","NUMBER"])
  with self.assertRaises(CompilerError) as caught:
   Lexer("START\nprint(1.5);\nEND").scan()
  self.assertEqual((caught.exception.line,caught.exception.column),(2,8))
 def test_large_program(self):
  source="START\n"+"print(1);\n"*2500+"END"
  program,_=self.compile(source)
  self.assertEqual(len(program.yes),2500)
  self.assertEqual(Interpreter().run(program).count("\n"),2500)
 def test_infinite_loop_stops_at_step_limit(self):
  program,_=self.compile("START\nwhile (1 == 1) { }\nEND")
  with self.assertRaises(CompilerError) as caught:
   Interpreter(timeout=None).run(program)
  self.assertIn("Execution limit exceeded",str(caught.exception))
 def test_timeout_and_stop_event(self):
  program,_=self.compile("START\nprint(1);\nEND")
  with self.assertRaises(CompilerError):
   Interpreter(timeout=0).run(program)
  stopped=threading.Event();stopped.set()
  with self.assertRaises(CompilerError) as caught:
   Interpreter(stop=stopped).run(program)
  self.assertIn("stopped by the user",str(caught.exception))
if __name__=="__main__":unittest.main()

class AutoCorrectionSafetyTests(unittest.TestCase):
 def test_adds_missing_start_and_end_without_rewriting_statements(self):
  source='int total = 4;\nprint(total);'
  corrector=AutoCorrector(source)
  fixed=corrector.apply()
  self.assertEqual(fixed,'START\nint total = 4;\nprint(total);\nEND')
  self.assertEqual(corrector.undo(),source)

 def test_corrects_known_keyword_typo_and_missing_semicolon_together(self):
  corrector=AutoCorrector('START\nprnt("hello")\nEND')
  fixes=corrector.suggestions()
  self.assertTrue(any('Correct' in description and 'semicolon' in description for _,description,_ in fixes))
  self.assertEqual(corrector.apply(),'START\nprint("hello");\nEND')

 def test_adds_missing_closing_brace_only_when_lexer_confirms_imbalance(self):
  source='START\nif (1 == 1) {\n    print(1);\nEND'
  corrector=AutoCorrector(source)
  self.assertTrue(any(description == "Insert missing '}' before END" for _,description,_ in corrector.suggestions()))
  self.assertEqual(corrector.apply(),'START\nif (1 == 1) {\n    print(1);\n}\nEND')

 def test_error_specific_suggestions_include_nearest_missing_semicolon(self):
  source='START\nint value = 3\nEND'
  with self.assertRaises(CompilerErrors) as caught:
   Parser(Lexer(source).scan()).parse()
  fixes=AutoCorrector(source).suggestions_for_error(caught.exception)
  self.assertTrue(any('semicolon' in description.lower() for _,description,_ in fixes))

 def test_does_not_guess_semantic_repairs(self):
  source='START\nprint(unknown);\nEND'
  program=Parser(Lexer(source).scan()).parse()
  with self.assertRaises(CompilerError) as caught:
   SemanticAnalyzer().analyze(program)
  self.assertEqual(AutoCorrector(source).suggestions_for_error(caught.exception),[])

 def test_adds_missing_closing_quote_only_for_lexer_reported_unterminated_string(self):
  source='START\nprint("unfinished);\nEND'
  corrector=AutoCorrector(source)
  self.assertTrue(any(description == "Insert missing closing quote" for _,description,_ in corrector.suggestions()))
  self.assertEqual(corrector.apply(),'START\nprint("unfinished);"\nEND')

class ModulusRegressionTests(unittest.TestCase):
 def compile_run(self,source):
  program=Parser(Lexer(source).scan()).parse();SemanticAnalyzer().analyze(program);return Interpreter().run(program),CodeGenerator().generate(program)
 def test_percent_modulus(self):
  out,tac=self.compile_run("START\nint r = 17 % 5;\nprint(r);\nEND")
  self.assertEqual(out,"2\n");self.assertIn("%",tac)
 def test_mod_keyword_alias(self):
  out,_=self.compile_run("START\nprint(17 mod 5);\nEND")
  self.assertEqual(out,"2\n")
 def test_negative_modulus_matches_truncation_remainder(self):
  out,_=self.compile_run("START\nprint(-17 % 5);\nprint(17 % -5);\nEND")
  self.assertEqual(out,"-2\n2\n")
 def test_modulus_zero_constant_error(self):
  with self.assertRaises(CompilerError) as caught:
   p=Parser(Lexer("START\nprint(5 % 0);\nEND").scan()).parse();SemanticAnalyzer().analyze(p)
  self.assertIn("modulus by zero",str(caught.exception).lower())
 def test_modulus_zero_runtime_error(self):
  p=Parser(Lexer("START\nint z = 0;\nprint(5 % z);\nEND").scan()).parse();SemanticAnalyzer().analyze(p)
  with self.assertRaises(CompilerError) as caught: Interpreter().run(p)
  self.assertIn("Modulus by zero",str(caught.exception))
 def test_safe_fix_modulus_typo(self):
  source="START\nprint(17 modulas 5);\nEND"
  fixer=AutoCorrector(source)
  self.assertTrue(any("modulus" in d.lower() for _,d,_ in fixer.suggestions()))
  self.assertEqual(fixer.apply(),"START\nprint(17 mod 5);\nEND")

class ScreenshotSafeFixRegressionTests(unittest.TestCase):
    def test_adds_missing_opening_brace_for_if_even_odd_program(self):
        source = 'START\nint num = 14;\nif (num % 2 == 0)\nprint("Even");\n} else {\nprint("Odd");\n}\nEND'
        fixed = AutoCorrector(source).apply()
        self.assertIn('if (num % 2 == 0) {', fixed)
        program = Parser(Lexer(fixed).scan()).parse()
        SemanticAnalyzer().analyze(program)
        self.assertEqual(Interpreter().run(program), 'Even\n')

    def test_modulas_typo_safe_fix_and_execution(self):
        source = 'START\nint num = 15;\nif (num modulas 2 == 0) {\nprint("Even");\n} else {\nprint("Odd");\n}\nEND'
        fixed = AutoCorrector(source).apply()
        self.assertIn('num mod 2', fixed)
        program = Parser(Lexer(fixed).scan()).parse()
        SemanticAnalyzer().analyze(program)
        self.assertEqual(Interpreter().run(program), 'Odd\n')
