import unittest

import easylang_studio as core
from visualizations.cfg_builder import build_cfg


def parse(source: str):
    return core.Parser(core.Lexer(source).scan()).parse()


class CFGBuilderTests(unittest.TestCase):
    def test_sequential_statements_form_basic_block(self):
        program = parse("START\nint x = 1;\nx = x + 2;\nprint(x);\nEND")
        graph = build_cfg(program)
        blocks = [node for node in graph.nodes.values() if node.kind == "block"]
        self.assertEqual(len(blocks), 1)
        self.assertEqual(len(blocks[0].statements), 3)
        self.assertIn("int x", blocks[0].label)
        self.assertTrue(any(edge.source == graph.entry for edge in graph.edges))
        self.assertTrue(any(edge.target == graph.exit for edge in graph.edges))

    def test_if_else_has_true_and_false_edges(self):
        program = parse(
            "START\nint x = 1;\nif (x > 0) { print(x); } else { print(0); }\nEND"
        )
        graph = build_cfg(program)
        decisions = [node for node in graph.nodes.values() if node.kind == "decision"]
        self.assertEqual(len(decisions), 1)
        outgoing = [edge for edge in graph.edges if edge.source == decisions[0].id]
        self.assertEqual({edge.label for edge in outgoing}, {"True", "False"})
        self.assertEqual(len({edge.target for edge in outgoing}), 2)

    def test_while_has_true_body_false_exit_and_back_edge(self):
        program = parse("START\nint x = 0;\nwhile (x < 3) { x = x + 1; }\nprint(x);\nEND")
        graph = build_cfg(program)
        decision = next(node for node in graph.nodes.values() if node.kind == "decision")
        outgoing = [edge for edge in graph.edges if edge.source == decision.id]
        self.assertEqual({edge.label for edge in outgoing}, {"True", "False"})
        true_target = next(edge.target for edge in outgoing if edge.label == "True")
        self.assertTrue(any(edge.target == decision.id and edge.source != decision.id
                            for edge in graph.edges))
        self.assertNotEqual(true_target, decision.id)


    def test_codegen_source_map_aligns_with_generated_lines(self):
        program = parse(
            "START\nint x = 1;\nif (x > 0) { print(x + 2); }\nEND"
        )
        generator = core.CodeGenerator()
        tac = generator.generate(program)
        self.assertEqual(len(generator.source_map), len(tac.splitlines()))
        self.assertTrue(all(isinstance(line, int) and line > 0 for line in generator.source_map))

    def test_codegen_text_is_preserved_with_source_mapping(self):
        program = parse(
            "START\nint n = 3;\nwhile (n > 0) { print(n); n = n - 1; }\nEND"
        )
        generator = core.CodeGenerator()
        tac = generator.generate(program)
        expected = (
            "n = 3\n"
            "t1 = n > 0\n"
            "L1:\n"
            "IF_FALSE t1 GOTO L2\n"
            "PRINT n\n"
            "t2 = n - 1\n"
            "n = t2\n"
            "GOTO L1\n"
            "L2:\n"
        )
        self.assertEqual(tac, expected)
        self.assertEqual(len(generator.source_map), len(tac.splitlines()))

    def test_nested_control_flow_is_represented(self):
        program = parse(
            "START\nint x = 0;\nwhile (x < 4) { if (x > 1) { print(x); } else { x = x + 1; } }\nEND"
        )
        graph = build_cfg(program)
        decisions = [node for node in graph.nodes.values() if node.kind == "decision"]
        self.assertEqual(len(decisions), 2)
        self.assertGreaterEqual(len(graph.edges), 6)


if __name__ == "__main__":
    unittest.main()
