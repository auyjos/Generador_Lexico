"""
visualizer.py — Generador de imágenes para ASTs de expresiones regulares.

Usa la librería graphviz para producir un grafo visual del árbol de sintaxis
generado por el Parser y/o el Resolvedor.

Entrada:  ASTNode  (raíz de un árbol de expresión regular)
Salida:   archivo .png / .pdf en el directorio indicado
"""

from __future__ import annotations

import os
from typing import Iterator

import graphviz

from src.lexer.regex_parser import (
    ASTNode,
    CharClassNode,
    ConcatNode,
    DiffNode,
    EofNode,
    LiteralNode,
    PlusNode,
    QuestionNode,
    RefNode,
    StarNode,
    UnionNode,
    WildcardNode,
)
from src.lexer.resolver import ResolvedRule, ResolvedSpec

# ── Paleta de colores por tipo de nodo ───────────────────────────────────────

_NODE_STYLE: dict[type, dict[str, str]] = {
    LiteralNode:   {"shape": "ellipse",   "fillcolor": "#AED6F1", "style": "filled"},
    CharClassNode: {"shape": "ellipse",   "fillcolor": "#A9DFBF", "style": "filled"},
    WildcardNode:  {"shape": "ellipse",   "fillcolor": "#F9E79F", "style": "filled"},
    EofNode:       {"shape": "ellipse",   "fillcolor": "#F1948A", "style": "filled"},
    RefNode:       {"shape": "ellipse",   "fillcolor": "#D7BDE2", "style": "filled"},
    ConcatNode:    {"shape": "rectangle", "fillcolor": "#FDFEFE", "style": "filled,rounded"},
    UnionNode:     {"shape": "rectangle", "fillcolor": "#FDFEFE", "style": "filled,rounded"},
    StarNode:      {"shape": "diamond",   "fillcolor": "#FAD7A0", "style": "filled"},
    PlusNode:      {"shape": "diamond",   "fillcolor": "#FAD7A0", "style": "filled"},
    QuestionNode:  {"shape": "diamond",   "fillcolor": "#FAD7A0", "style": "filled"},
    DiffNode:      {"shape": "rectangle", "fillcolor": "#FDFEFE", "style": "filled,rounded"},
}

_DEFAULT_STYLE = {"shape": "ellipse", "fillcolor": "#ECF0F1", "style": "filled"}


# ══════════════════════════════════════════════════════════════════════════════
#  Función principal de renderizado
# ══════════════════════════════════════════════════════════════════════════════

def render_ast(
    node: ASTNode,
    title: str = "AST",
    output_path: str = "output/ast",
    fmt: str = "png",
    view: bool = False,
) -> str:
    """
    Renderiza el AST como imagen.

    Args:
        node:        raíz del árbol a visualizar.
        title:       etiqueta del grafo (aparece como título).
        output_path: ruta de salida sin extensión (ej. 'output/ast_id').
        fmt:         formato de imagen ('png', 'pdf', 'svg').
        view:        si True, abre la imagen automáticamente.

    Returns:
        Ruta del archivo generado.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    dot = graphviz.Digraph(
        name=title,
        comment=title,
        graph_attr={
            "label": title,
            "labelloc": "t",
            "fontsize": "14",
            "fontname": "Helvetica",
            "rankdir": "TB",
            "splines": "ortho",
        },
        node_attr={"fontname": "Helvetica", "fontsize": "11"},
        edge_attr={"fontname": "Helvetica", "fontsize": "9"},
    )

    counter = _Counter()
    _add_node(dot, node, counter)

    rendered = dot.render(
        filename=output_path,
        format=fmt,
        cleanup=True,
        view=view,
    )
    return rendered


def render_resolved_spec(
    spec: ResolvedSpec,
    output_dir: str = "output",
    fmt: str = "png",
) -> str:
    """
    Genera UNA SOLA imagen con todos los árboles del ResolvedSpec.
    Las definiciones y reglas aparecen como clusters (recuadros) separados.

    Returns:
        Ruta del archivo generado.
    """
    os.makedirs(output_dir, exist_ok=True)

    dot = graphviz.Digraph(
        name="AST_Lexico",
        graph_attr={
            "label": "AST Lexico — Especificacion Resuelta",
            "labelloc": "t",
            "fontsize": "16",
            "fontname": "Helvetica",
            "rankdir": "TB",
            "compound": "true",
            "newrank": "true",
        },
        node_attr={"fontname": "Helvetica", "fontsize": "11"},
        edge_attr={"fontname": "Helvetica", "fontsize": "9"},
    )

    counter = _Counter()

    # ── Reglas de token ──
    for rule in spec.rules:
        cluster_name = f"cluster_rule_{rule.order}"
        label = f"Regla [{rule.order}]: {rule.raw_pattern}\\n{{ {rule.action} }}"
        with dot.subgraph(name=cluster_name) as sub:
            sub.attr(
                label=label,
                style="filled,rounded",
                fillcolor="#EAFAF1",
                color="#1E8449",
                fontsize="11",
                fontname="Helvetica",
            )
            _add_node(sub, rule.pattern_ast, counter)

    out_path = os.path.join(output_dir, "ast_lexico")
    rendered = dot.render(filename=out_path, format=fmt, cleanup=True)
    return rendered


# ══════════════════════════════════════════════════════════════════════════════
#  Construcción recursiva del grafo
# ══════════════════════════════════════════════════════════════════════════════

class _Counter:
    """Contador de nodos para generar IDs únicos."""
    def __init__(self) -> None:
        self._n = 0

    def next(self) -> str:
        self._n += 1
        return f"n{self._n}"


def _node_label(node: ASTNode) -> str:
    """Etiqueta legible para un nodo del AST."""
    if isinstance(node, LiteralNode):
        ch = chr(node.value)
        display = repr(ch) if not ch.isprintable() or ch == " " else ch
        return f"CHAR\n{display}"
    if isinstance(node, CharClassNode):
        neg = "^" if node.negated else ""
        chars = sorted(node.chars)
        # Mostrar rangos compactos
        ranges = _compact_ranges(chars)
        return f"CLASS\n[{neg}{ranges}]"
    if isinstance(node, WildcardNode):
        return "ANY\n_"
    if isinstance(node, EofNode):
        return "EOF"
    if isinstance(node, RefNode):
        return f"REF\n{node.name}"
    if isinstance(node, ConcatNode):
        return "CONCAT\n·"
    if isinstance(node, UnionNode):
        return "UNION\n|"
    if isinstance(node, StarNode):
        return "STAR\n*"
    if isinstance(node, PlusNode):
        return "PLUS\n+"
    if isinstance(node, QuestionNode):
        return "OPT\n?"
    if isinstance(node, DiffNode):
        return "DIFF\n#"
    return type(node).__name__


def _add_node(dot: graphviz.Digraph, node: ASTNode, counter: _Counter) -> str:
    """
    Añade recursivamente el nodo y sus hijos al grafo.
    Devuelve el ID del nodo raíz creado.
    """
    node_id = counter.next()
    label = _node_label(node)
    style = _NODE_STYLE.get(type(node), _DEFAULT_STYLE)
    dot.node(node_id, label=label, **style)

    # Nodos binarios
    if isinstance(node, (ConcatNode, UnionNode, DiffNode)):
        left_id  = _add_node(dot, node.left,  counter)
        right_id = _add_node(dot, node.right, counter)
        dot.edge(node_id, left_id,  label="L")
        dot.edge(node_id, right_id, label="R")

    # Nodos unarios
    elif isinstance(node, (StarNode, PlusNode, QuestionNode)):
        child_id = _add_node(dot, node.child, counter)
        dot.edge(node_id, child_id)

    # Nodos hoja: LiteralNode, CharClassNode, WildcardNode, EofNode, RefNode
    # → no tienen hijos, no se añaden aristas

    return node_id


# ── Utilidad: rangos compactos de caracteres ─────────────────────────────────

def _compact_ranges(codes: list[int]) -> str:
    """Convierte lista de ords ordenados en representación compacta (a-z)."""
    if not codes:
        return ""
    parts: list[str] = []
    i = 0
    while i < len(codes):
        start = end = codes[i]
        while i + 1 < len(codes) and codes[i + 1] == end + 1:
            end = codes[i + 1]
            i += 1
        s = _safe_char(start)
        if start == end:
            parts.append(s)
        elif end == start + 1:
            parts.append(f"{s}{_safe_char(end)}")
        else:
            parts.append(f"{s}-{_safe_char(end)}")
        i += 1
    result = "".join(parts)
    # Truncar si es muy largo para que el nodo no sea enorme
    return result if len(result) <= 20 else result[:17] + "..."


def _safe_char(code: int) -> str:
    ch = chr(code)
    if ch == "\n": return "\\n"
    if ch == "\t": return "\\t"
    if ch == "\r": return "\\r"
    if ch == " ":  return "' '"
    if ch.isprintable(): return ch
    return f"\\x{code:02x}"
