"""Built-in tool executor(s) for the `--agent-backend claude` (direct)
backend -- a quiz's `tools:` block declares the schema, this is where its
name gets resolved to actual Python code to run when Claude calls it (see
`ClaudeAgentClient` in agent_runner.py).

Real users will register their own tool executors (whatever their analytics
agent actually calls — a warehouse query tool, a metrics-layer lookup, etc.).
`calculator` here is a trivial, safely-executable stand-in for that, kept as
a minimal working reference; `example_project`'s own quizzes currently use
the MCP backend instead (see example_project/mcp_server/server.py), which
sources its tools from a live MCP server rather than this module.
"""

from __future__ import annotations

import ast
import operator

_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPERATORS:
        return _ALLOWED_OPERATORS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPERATORS:
        return _ALLOWED_OPERATORS[type(node.op)](_safe_eval(node.operand))
    raise ValueError(f"Unsupported expression node: {ast.dump(node)}")


def evaluate_expression(expression: str) -> float:
    """Shared by the local `calculator` tool executor below and by
    example_project/mcp_server/server.py, so the same safe-eval logic backs
    the tool whether it's called directly or via MCP.
    """
    tree = ast.parse(expression, mode="eval")
    return _safe_eval(tree.body)


def calculator(tool_input: dict) -> str:
    return str(evaluate_expression(tool_input.get("expression", "")))


BUILTIN_TOOL_EXECUTORS = {
    "calculator": calculator,
}
