#!/usr/bin/env python3
import re
from typing import List, Optional, Tuple


GRAMMAR_VERSION = "2026-06-06-unified-grammar-v1"
ASSERT_COUNT_RE = re.compile(r"\bassert\s+property\b", re.IGNORECASE)


def normalize_sva_text(text: str) -> str:
    return " ".join((text or "").strip().split())


def consume_parenthesized(text: str) -> Tuple[str, str]:
    if not text or text[0] != "(":
        raise ValueError("Expected parenthesized expression.")
    depth = 0
    for idx, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[1:idx], text[idx + 1 :]
    raise ValueError("Unbalanced parentheses in assertion.")


def strip_outer_parens(expr: str) -> str:
    text = (expr or "").strip()
    while text.startswith("(") and text.endswith(")"):
        depth = 0
        balanced = True
        for idx, ch in enumerate(text):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and idx != len(text) - 1:
                    balanced = False
                    break
        if not balanced or depth != 0:
            break
        text = text[1:-1].strip()
    return text


def find_top_level_operator(expr: str, operators: List[str]) -> Optional[Tuple[str, str, str]]:
    depth = 0
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0:
            for op in operators:
                if expr.startswith(op, i):
                    return expr[:i].strip(), op, expr[i + len(op) :].strip()
        i += 1
    return None


def extract_single_assertion(sva_text: str) -> Tuple[str, str, str, str, str]:
    text = normalize_sva_text(sva_text)
    if len(ASSERT_COUNT_RE.findall(text)) != 1:
        raise ValueError("Expected exactly one `assert property` statement.")

    prefix = re.match(r"assert\s+property\s*\(", text, re.IGNORECASE)
    if not prefix:
        raise ValueError("Unsupported SVA format. Expected one `assert property (...)` statement.")

    body, tail = consume_parenthesized(text[prefix.end() - 1 :])
    if tail.strip() != ";":
        raise ValueError("Unexpected trailing content after assertion.")

    inner = body.strip()
    if not inner.startswith("@"):
        raise ValueError("Expected sampling event `@(posedge clk)`.")
    event_expr, rest = consume_parenthesized(inner[1:].lstrip())
    if normalize_sva_text(event_expr).lower() != "posedge clk":
        raise ValueError("Only `@(posedge clk)` assertions are supported.")

    property_body = rest.strip()
    disable_expr = ""
    if property_body.lower().startswith("disable iff"):
        disable_body = property_body[len("disable iff") :].lstrip()
        disable_expr, property_body = consume_parenthesized(disable_body)
        disable_expr = strip_outer_parens(disable_expr)
        property_body = property_body.strip()

    split = find_top_level_operator(property_body, ["|->", "|=>"])
    if not split:
        raise ValueError("Cannot find top-level property implication operator.")

    ante, op, cons = split
    ante = strip_outer_parens(ante)
    cons = strip_outer_parens(cons)
    if not ante or not cons:
        raise ValueError("Antecedent and consequent must both be non-empty.")

    return text, disable_expr, ante, op, cons
