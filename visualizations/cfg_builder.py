"""Control-flow graph construction from the real EasyLang parser AST.

The builder supports the constructs implemented by the bundled language:
declarations, assignments, print, if/else, and while. It does not parse source
text and it does not claim support for constructs absent from the grammar.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class CFGNode:
    id: int
    kind: str
    label: str
    line: int | None = None
    column: int | None = None
    statements: tuple[object, ...] = ()


@dataclass(frozen=True)
class CFGEdge:
    source: int
    target: int
    label: str = ""


@dataclass
class ControlFlowGraph:
    nodes: dict[int, CFGNode] = field(default_factory=dict)
    edges: list[CFGEdge] = field(default_factory=list)
    entry: int = 0
    exit: int = 1


def _expr_text(expr) -> str:
    if expr is None:
        return ""
    if expr.kind == "literal":
        return repr(expr.value)
    if expr.kind == "variable":
        return str(expr.value)
    if expr.kind == "unary":
        return "-" + _expr_text(expr.right)
    operators = {
        "PLUS": "+", "MINUS": "-", "STAR": "*", "SLASH": "/", "MOD": "%",
        "EQ": "==", "NE": "!=", "GT": ">", "GE": ">=",
        "LT": "<", "LE": "<=",
    }
    return f"({_expr_text(expr.left)} {operators.get(expr.op, expr.op)} {_expr_text(expr.right)})"


def _stmt_text(stmt) -> str:
    if stmt.kind == "decl":
        suffix = f" = {_expr_text(stmt.expr)}" if stmt.expr is not None else ""
        return f"{stmt.typ} {stmt.name}{suffix}"
    if stmt.kind == "assign":
        return f"{stmt.name} = {_expr_text(stmt.expr)}"
    if stmt.kind == "print":
        return f"print({_expr_text(stmt.expr)})"
    return f"{stmt.kind} {_expr_text(stmt.expr)}"


def build_cfg(program) -> ControlFlowGraph:
    """Build a directed CFG from a parser-produced program AST."""
    graph = ControlFlowGraph()
    graph.nodes[graph.entry] = CFGNode(graph.entry, "entry", "Entry")
    graph.nodes[graph.exit] = CFGNode(graph.exit, "exit", "Exit")
    next_id = 2

    def node(kind: str, label: str, line=None, column=None, statements=()) -> int:
        nonlocal next_id
        ident = next_id
        next_id += 1
        graph.nodes[ident] = CFGNode(ident, kind, label, line, column, tuple(statements))
        return ident

    def edge(source: int, target: int, label: str = "") -> None:
        graph.edges.append(CFGEdge(source, target, label))

    def sequence(statements: Iterable[object], continuation: int) -> int:
        items = list(statements)
        current = continuation
        index = len(items) - 1
        while index >= 0:
            stmt = items[index]
            if stmt.kind not in ("if", "while"):
                run = [stmt]
                index -= 1
                while index >= 0 and items[index].kind not in ("if", "while"):
                    run.append(items[index])
                    index -= 1
                run.reverse()
                first = run[0]
                label = "\\n".join(_stmt_text(item) for item in run)
                block = node("block", label, first.line, first.column, run)
                edge(block, current)
                current = block
                continue

            index -= 1
            decision = node(
                "decision", _expr_text(stmt.expr), stmt.line,
                getattr(stmt, "column", 1), (stmt,),
            )
            if stmt.kind == "if":
                yes_entry = sequence(stmt.yes, current) if stmt.yes else current
                no_entry = sequence(stmt.no, current) if stmt.no else current
                edge(decision, yes_entry, "True")
                edge(decision, no_entry, "False")
            else:
                body_entry = sequence(stmt.yes, decision) if stmt.yes else decision
                edge(decision, body_entry, "True")
                edge(decision, current, "False")
            current = decision
        return current

    body_entry = sequence(getattr(program, "yes", ()), graph.exit)
    edge(graph.entry, body_entry)
    return graph
