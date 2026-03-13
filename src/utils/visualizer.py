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

# ── Fuente manuscrita (GoodNotes / lapiz) ────────────────────────────────────
# Prioridad: Segoe Print (Windows) → Comic Sans MS → Sans
_HAND_FONT = "Segoe Print"

# ── Paleta de colores pastel estilo GoodNotes ─────────────────────────────────
# Todos los nodos son círculos diferenciados por color pastel + borde grueso

_NODE_STYLE: dict[type, dict[str, str]] = {
    # Operadores binarios
    ConcatNode:    {"shape": "circle", "style": "filled", "fillcolor": "#C8E6FA", "color": "#4A90C4", "fontcolor": "#1A3A5C", "width": "0.65", "fixedsize": "true", "penwidth": "2.2"},
    UnionNode:     {"shape": "circle", "style": "filled", "fillcolor": "#FAC8C8", "color": "#C0504D", "fontcolor": "#5C1A1A", "width": "0.65", "fixedsize": "true", "penwidth": "2.2"},
    DiffNode:      {"shape": "circle", "style": "filled", "fillcolor": "#E8D5F5", "color": "#8B5CA8", "fontcolor": "#3D1A5C", "width": "0.65", "fixedsize": "true", "penwidth": "2.2"},
    # Operadores unarios
    StarNode:      {"shape": "circle", "style": "filled", "fillcolor": "#FFE8B8", "color": "#D4860A", "fontcolor": "#5C3800", "width": "0.65", "fixedsize": "true", "penwidth": "2.2"},
    PlusNode:      {"shape": "circle", "style": "filled", "fillcolor": "#FFE8B8", "color": "#D4860A", "fontcolor": "#5C3800", "width": "0.65", "fixedsize": "true", "penwidth": "2.2"},
    QuestionNode:  {"shape": "circle", "style": "filled", "fillcolor": "#FFE8B8", "color": "#D4860A", "fontcolor": "#5C3800", "width": "0.65", "fixedsize": "true", "penwidth": "2.2"},
    # Hojas terminales
    LiteralNode:   {"shape": "circle", "style": "filled", "fillcolor": "#C8F5DA", "color": "#2E8B57", "fontcolor": "#0A3D1F", "width": "0.65", "fixedsize": "true", "penwidth": "2.2"},
    CharClassNode: {"shape": "circle", "style": "filled", "fillcolor": "#C8F5DA", "color": "#2E8B57", "fontcolor": "#0A3D1F", "width": "0.85", "fixedsize": "true", "penwidth": "2.2"},
    WildcardNode:  {"shape": "circle", "style": "filled", "fillcolor": "#C8F5DA", "color": "#2E8B57", "fontcolor": "#0A3D1F", "width": "0.65", "fixedsize": "true", "penwidth": "2.2"},
    EofNode:       {"shape": "circle", "style": "filled", "fillcolor": "#FAD5D5", "color": "#922B21", "fontcolor": "#5C0A0A", "width": "0.65", "fixedsize": "true", "penwidth": "2.2"},
    RefNode:       {"shape": "circle", "style": "filled", "fillcolor": "#D5EAF5", "color": "#4A90C4", "fontcolor": "#1A3A5C", "width": "0.85", "fixedsize": "true", "penwidth": "2.2"},
}

_DEFAULT_STYLE = {"shape": "circle", "style": "filled", "fillcolor": "#EDEDED", "color": "#888888", "width": "0.65", "fixedsize": "true", "penwidth": "2.2"}


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
            "fontname": _HAND_FONT,
            "fontcolor": "#2D2D2D",
            "bgcolor": "#FDFCF5",
            "rankdir": "TB",
            "splines": "line",
            "nodesep": "0.5",
            "ranksep": "0.7",
        },
        node_attr={"fontname": _HAND_FONT, "fontsize": "11"},
        edge_attr={"color": "#3D3D3D", "arrowsize": "0.8", "penwidth": "1.8"},
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
            "rankdir": "TB",
            "splines": "line",
            "nodesep": "0.5",
            "ranksep": "0.75",
            "bgcolor": "#FDFCF5",
            "fontname": _HAND_FONT,
        },
        node_attr={"fontname": _HAND_FONT, "fontsize": "11"},
        edge_attr={"color": "#3D3D3D", "arrowsize": "0.8", "penwidth": "1.8"},
    )

    counter = _Counter()

    # ── Definiciones expandidas ──
    for name in spec.topo_order:
        ast = spec.resolved_defs[name]
        # Nodo título de la definición
        title_id = counter.next()
        dot.node(
            title_id,
            label=f"let {name}",
            shape="plaintext",
            fontsize="14",
            fontname=_HAND_FONT,
            fontcolor="#2E6DA4",
        )
        root_id = _add_node(dot, ast, counter)
        dot.edge(title_id, root_id, style="dashed", color="#2E6DA4",
                 arrowhead="none", penwidth="1.5")

    # ── Reglas de token ──
    for rule in spec.rules:
        title_id = counter.next()
        dot.node(
            title_id,
            label=f"[{rule.order}]  {rule.action}",
            shape="plaintext",
            fontsize="13",
            fontname=_HAND_FONT,
            fontcolor="#1E6B3C",
        )
        root_id = _add_node(dot, rule.pattern_ast, counter)
        dot.edge(title_id, root_id, style="dashed", color="#1E6B3C",
                 arrowhead="none", penwidth="1.5")

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
        return f"'{display}'"
    if isinstance(node, CharClassNode):
        neg = "^" if node.negated else ""
        chars = sorted(node.chars)
        ranges = _compact_ranges(chars)
        return f"[{neg}{ranges}]"
    if isinstance(node, WildcardNode):
        return "."
    if isinstance(node, EofNode):
        return "EOF"
    if isinstance(node, RefNode):
        return f"@ {node.name}"
    if isinstance(node, ConcatNode):
        return "·"
    if isinstance(node, UnionNode):
        return "|"
    if isinstance(node, StarNode):
        return "*"
    if isinstance(node, PlusNode):
        return "+"
    if isinstance(node, QuestionNode):
        return "?"
    if isinstance(node, DiffNode):
        return "#"
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
        dot.edge(node_id, left_id)
        dot.edge(node_id, right_id)

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


# ══════════════════════════════════════════════════════════════════════════════
#  Visualización del NFA
# ══════════════════════════════════════════════════════════════════════════════

def render_nfa(
    nfa,
    title: str = "NFA (Thompson)",
    output_path: str = "output/nfa",
    fmt: str = "png",
    view: bool = False,
) -> str:
    """
    Renderiza el NFA como imagen con graphviz.

    Convenciones visuales:
      · Estado inicial  → flecha entrante desde un nodo invisible
      · Estado normal   → círculo blanco
      · Estado aceptante→ doble círculo, color por token (paleta rotativa)
      · Transición-ε    → arista punteada con etiqueta "ε"
      · Transición char → arista sólida con el símbolo
      · Transición class→ arista sólida con la clase compacta [a-z]
    """
    from src.lexer.nfa import EPSILON

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    dot = graphviz.Digraph(
        name=title,
        graph_attr={
            "label": title,
            "labelloc": "t",
            "fontsize": "14",
            "fontname": "Helvetica",
            "rankdir": "LR",          # izquierda → derecha (convención autómatas)
            "splines": "true",
            "nodesep": "0.5",
            "ranksep": "0.8",
        },
        node_attr={"fontname": "Helvetica", "fontsize": "11"},
        edge_attr={"fontname": "Helvetica", "fontsize": "10"},
    )

    # Paleta de colores para tokens distintos
    _TOKEN_COLORS = [
        "#AED6F1", "#A9DFBF", "#FAD7A0", "#F1948A",
        "#D7BDE2", "#A2D9CE", "#F9E79F", "#CACFD2",
    ]
    token_color: dict[str, str] = {}
    color_idx = [0]

    def _get_token_color(token: str) -> str:
        if token not in token_color:
            token_color[token] = _TOKEN_COLORS[color_idx[0] % len(_TOKEN_COLORS)]
            color_idx[0] += 1
        return token_color[token]

    # Nodo ficticio de entrada
    dot.node("__start__", label="", shape="none", width="0", height="0")
    dot.edge("__start__", f"q{nfa.start.state_id}", arrowhead="vee")

    # Agregar todos los estados
    for state in nfa.states:
        sid = f"q{state.state_id}"
        if state.is_accept:
            color = _get_token_color(state.token or "?")
            dot.node(
                sid,
                label=f"q{state.state_id}\n{state.token}",
                shape="doublecircle",
                style="filled",
                fillcolor=color,
                fontname="Helvetica",
                fontsize="10",
            )
        else:
            is_start = (state.state_id == nfa.start.state_id)
            dot.node(
                sid,
                label=f"q{state.state_id}",
                shape="circle",
                style="filled",
                fillcolor="#F0F3F4" if not is_start else "#D5EAF5",
            )

    # Agregar transiciones
    for state in nfa.states:
        src = f"q{state.state_id}"
        for symbol, targets in state.transitions.items():
            label = _edge_label_nfa(symbol)
            is_eps = (symbol is EPSILON)
            for target in targets:
                tgt = f"q{target.state_id}"
                if is_eps:
                    dot.edge(src, tgt, label=label,
                             style="dashed", color="#7F8C8D", fontcolor="#7F8C8D")
                else:
                    dot.edge(src, tgt, label=label, color="#2C3E50")

    rendered = dot.render(filename=output_path, format=fmt, cleanup=True, view=view)
    return rendered


def _edge_label_nfa(symbol) -> str:
    """Etiqueta legible para una transición del NFA."""
    from src.lexer.nfa import EPSILON
    if symbol is EPSILON:
        return "ε"
    if isinstance(symbol, int):
        if symbol == -1:
            return "EOF"
        c = chr(symbol)
        if c.isprintable() and c not in (" ", "\t", "\n"):
            return c
        return f"\\x{symbol:02x}"
    if isinstance(symbol, frozenset):
        return "[" + _compact_ranges(sorted(symbol)) + "]"
    return repr(symbol)


# ══════════════════════════════════════════════════════════════════════════════
#  Visualización del DFA
# ══════════════════════════════════════════════════════════════════════════════

def render_dfa(
    dfa,
    title: str = "DFA",
    output_path: str = "output/dfa",
    fmt: str = "png",
    view: bool = False,
) -> str:
    """
    Renderiza el DFA como imagen con graphviz.

    Convenciones visuales (mismas que el NFA):
      · Estado inicial   → flecha entrante desde nodo invisible
      · Estado normal    → círculo blanco/gris
      · Estado aceptante → doble círculo con color por token
      · Transiciones con el mismo destino se agrupan en una sola arista
        con etiqueta combinada (ej. "a-z, A-Z") para mayor legibilidad.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    dot = graphviz.Digraph(
        name=title,
        graph_attr={
            "label": title,
            "labelloc": "t",
            "fontsize": "14",
            "fontname": "Helvetica",
            "rankdir": "LR",
            "splines": "true",
            "nodesep": "0.6",
            "ranksep": "1.0",
        },
        node_attr={"fontname": "Helvetica", "fontsize": "11"},
        edge_attr={"fontname": "Helvetica", "fontsize": "10"},
    )

    _TOKEN_COLORS = [
        "#AED6F1", "#A9DFBF", "#FAD7A0", "#F1948A",
        "#D7BDE2", "#A2D9CE", "#F9E79F", "#CACFD2",
    ]
    token_color: dict[str, str] = {}
    color_idx = [0]

    def _get_token_color(token: str) -> str:
        if token not in token_color:
            token_color[token] = _TOKEN_COLORS[color_idx[0] % len(_TOKEN_COLORS)]
            color_idx[0] += 1
        return token_color[token]

    # Nodo ficticio de entrada
    dot.node("__start__", label="", shape="none", width="0", height="0")
    dot.edge("__start__", f"D{dfa.start.state_id}", arrowhead="vee")

    # Agregar todos los estados
    for state in dfa.states:
        sid = f"D{state.state_id}"
        if state.is_accept:
            color = _get_token_color(state.token or "?")
            dot.node(
                sid,
                label=f"D{state.state_id}\n{state.token}",
                shape="doublecircle",
                style="filled",
                fillcolor=color,
                fontsize="10",
            )
        else:
            is_start = (state.state_id == dfa.start.state_id)
            dot.node(
                sid,
                label=f"D{state.state_id}",
                shape="circle",
                style="filled",
                fillcolor="#F0F3F4" if not is_start else "#D5EAF5",
            )

    # Agrupar transiciones por (src, dst) para combinar etiquetas
    for state in dfa.states:
        src = f"D{state.state_id}"

        # Agrupar: dst → lista de símbolos
        grouped: dict[str, list[int]] = {}
        for symbol, target in state.transitions.items():
            tgt = f"D{target.state_id}"
            grouped.setdefault(tgt, []).append(symbol)

        for tgt, symbols in grouped.items():
            label = _edge_label_dfa(symbols)
            dot.edge(src, tgt, label=label, color="#2C3E50")

    rendered = dot.render(filename=output_path, format=fmt, cleanup=True, view=view)
    return rendered


def _edge_label_dfa(symbols: list[int]) -> str:
    """
    Genera la etiqueta de una arista DFA a partir de una lista de símbolos.
    Los símbolos consecutivos se muestran como rangos (a-z).
    Si la etiqueta resultante es muy larga, se trunca.
    """
    if not symbols:
        return "∅"
    label = "[" + _compact_ranges(sorted(symbols)) + "]"
    # Para etiquetas muy largas truncar para no saturar el grafo
    if len(label) > 25:
        label = label[:22] + "…]"
    return label


# ══════════════════════════════════════════════════════════════════════════════
#  Función de conveniencia: renderizar NFA + DFA + DFA minimizado de una vez
# ══════════════════════════════════════════════════════════════════════════════

def render_automata(
    nfa,
    dfa,
    min_dfa,
    output_dir: str = "output",
    fmt: str = "png",
) -> dict[str, str]:
    """
    Genera las tres imágenes de autómatas en output_dir.

    Returns:
        dict con claves 'nfa', 'dfa', 'min_dfa' apuntando a las rutas generadas.
    """
    paths = {}
    paths["nfa"] = render_nfa(
        nfa,
        title="NFA (Construccion de Thompson)",
        output_path=os.path.join(output_dir, "nfa"),
        fmt=fmt,
    )
    paths["dfa"] = render_dfa(
        dfa,
        title="DFA (Construccion de Subconjuntos)",
        output_path=os.path.join(output_dir, "dfa"),
        fmt=fmt,
    )
    paths["min_dfa"] = render_dfa(
        min_dfa,
        title="DFA Minimizado (Hopcroft)",
        output_path=os.path.join(output_dir, "dfa_min"),
        fmt=fmt,
    )
    return paths
