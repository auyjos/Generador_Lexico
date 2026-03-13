"""
nfa.py — Módulo 4: Constructor de NFA (Thompson's Construction)

Responsabilidades (arquitectura §10.5):
  - Construye un NFA por cada regla usando construcción de Thompson
    directamente desde el AST expandido (ResolvedRule.pattern_ast).
  - Une todos los NFA parciales a un estado inicial común mediante
    transiciones-épsilon (NFA global).
  - Cada estado de aceptación queda etiquetado con:
      · el token (acción semántica) de su regla
      · la prioridad (order) para resolver conflictos (maximal munch)
  - No existe paso intermedio de "árbol de expresión aumentado"; el AST
    del resolver se consume directamente.

Entrada:  ResolvedSpec  (salida del DefinitionResolver)
Salida:   NFA           (objeto con estado inicial, conjunto de estados,
                         tabla de transiciones y estados de aceptación)

Algoritmo de Thompson — fragmentos utilizados:
  LITERAL / CHAR_CLASS / WILDCARD
        i --a--> f

  CONCAT(A, B)
        nfa_A  concatenado con  nfa_B
        (estado final de A = estado inicial de B mediante ε)

  UNION(A, B)
        nuevo i --ε--> start_A,  nuevo i --ε--> start_B
        end_A --ε--> nuevo f,    end_B --ε--> nuevo f

  STAR(A)
        nuevo i --ε--> start_A,  nuevo i --ε--> nuevo f
        end_A  --ε--> start_A,   end_A  --ε--> nuevo f

  PLUS(A)
        nuevo i --ε--> start_A
        end_A  --ε--> start_A,   end_A  --ε--> nuevo f

  QUESTION(A)
        nuevo i --ε--> start_A,  nuevo i --ε--> nuevo f
        end_A  --ε--> nuevo f

  DIFF(A, B)   [aproximación: A ∩ ¬B]
        Se implementa como CharClass restando los conjuntos.
        Solo funciona cuando ambos operandos son CharClassNode o
        LiteralNode; en caso contrario lanza NFAError.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import FrozenSet, Optional

from src.lexer.regex_parser import (
    ASTNode,
    CharClassNode,
    ConcatNode,
    DiffNode,
    EofNode,
    LiteralNode,
    PlusNode,
    QuestionNode,
    StarNode,
    UnionNode,
    WildcardNode,
)
from src.lexer.resolver import ResolvedSpec

# ══════════════════════════════════════════════════════════════════════════════
#  Constantes
# ══════════════════════════════════════════════════════════════════════════════

EPSILON = None          # Representación de la transición-ε
ALL_CHARS = frozenset(range(256))   # universo de caracteres ASCII

# ══════════════════════════════════════════════════════════════════════════════
#  Excepciones
# ══════════════════════════════════════════════════════════════════════════════


class NFAError(Exception):
    """Error durante la construcción del NFA."""


# ══════════════════════════════════════════════════════════════════════════════
#  Estado del NFA
# ══════════════════════════════════════════════════════════════════════════════


@dataclass
class NFAState:
    """
    Un estado del NFA.

    Campos:
        state_id   — identificador único (entero asignado por el builder)
        is_accept  — True si es estado de aceptación
        token      — nombre del token si is_accept, None en caso contrario
        priority   — prioridad (order) de la regla si is_accept; menor = mayor prioridad
        transitions — dict[symbol → set[NFAState]]
                      symbol puede ser:
                        · int (ord del carácter)
                        · frozenset[int] (clase de caracteres)
                        · None (transición-ε)
    """

    state_id: int
    is_accept: bool = False
    token: Optional[str] = None
    priority: int = 0

    # Las transiciones se representan como:
    #   symbol (int | frozenset | None)  →  list[NFAState]
    transitions: dict = field(default_factory=dict)

    def add_transition(self, symbol, target: "NFAState") -> None:
        """Agrega una transición desde este estado."""
        if symbol not in self.transitions:
            self.transitions[symbol] = []
        self.transitions[symbol].append(target)

    def __repr__(self) -> str:
        accept_info = f", token={self.token!r}" if self.is_accept else ""
        return f"NFAState(id={self.state_id}{accept_info})"

    def __hash__(self):
        return hash(self.state_id)

    def __eq__(self, other):
        return isinstance(other, NFAState) and self.state_id == other.state_id


# ══════════════════════════════════════════════════════════════════════════════
#  NFA global
# ══════════════════════════════════════════════════════════════════════════════


@dataclass
class NFA:
    """
    Autómata Finito No Determinista resultante.

    Campos:
        start      — estado inicial del NFA global
        states     — todos los estados (en orden de creación)
        accept_states — estados de aceptación con su token y prioridad
    """

    start: NFAState
    states: list[NFAState]
    accept_states: list[NFAState]

    # ── Representación ────────────────────────────────────────────────────────

    def pretty_print(self) -> str:
        lines: list[str] = []
        lines.append("=" * 60)
        lines.append("  RESULTADO DEL CONSTRUCTOR DE NFA (Thompson)")
        lines.append("=" * 60)
        lines.append(f"\n  Total de estados : {len(self.states)}")
        lines.append(f"  Estado inicial   : q{self.start.state_id}")
        lines.append(f"  Estados de aceptación: "
                     f"{[f'q{s.state_id}({s.token})' for s in self.accept_states]}")

        lines.append("\n-- Tabla de Transiciones --")
        lines.append(f"  {'Estado':<10}  {'Símbolo':<20}  {'Destinos'}")
        lines.append(f"  {'-'*10}  {'-'*20}  {'-'*30}")

        for state in self.states:
            state_label = f"q{state.state_id}"
            if state.is_accept:
                state_label += f"*({state.token})"
            if state == self.start:
                state_label = "->" + state_label

            if not state.transitions:
                lines.append(f"  {state_label:<10}  {'(ninguna)':<20}  —")
                continue

            first = True
            for symbol, targets in state.transitions.items():
                sym_str = _symbol_str(symbol)
                tgt_str = ", ".join(f"q{t.state_id}" for t in targets)
                label = state_label if first else ""
                lines.append(f"  {label:<10}  {sym_str:<20}  {tgt_str}")
                first = False

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)


def _symbol_str(symbol) -> str:
    """Representación legible de un símbolo de transición."""
    if symbol is EPSILON:
        return "eps"
    if isinstance(symbol, int):
        if symbol == -1:
            return "EOF"
        c = chr(symbol)
        if c.isprintable() and c != " ":
            return f"'{c}'"
        return f"\\x{symbol:02x}"
    if isinstance(symbol, frozenset):
        # Mostrar como rangos compactos
        sorted_chars = sorted(symbol)
        if not sorted_chars:
            return "[∅]"
        # Calcular rangos
        ranges: list[str] = []
        i = 0
        while i < len(sorted_chars):
            start = sorted_chars[i]
            end = start
            while (i + 1 < len(sorted_chars)
                   and sorted_chars[i + 1] == end + 1):
                end = sorted_chars[i + 1]
                i += 1
            if start == end:
                c = chr(start)
                ranges.append(c if c.isprintable() and c != " " else f"\\x{start:02x}")
            else:
                cs = chr(start) if chr(start).isprintable() and chr(start) != " " else f"\\x{start:02x}"
                ce = chr(end)   if chr(end).isprintable()   and chr(end)   != " " else f"\\x{end:02x}"
                ranges.append(f"{cs}-{ce}")
            i += 1
        return f"[{''.join(ranges)}]"
    return repr(symbol)


# ══════════════════════════════════════════════════════════════════════════════
#  Fragmento de NFA (par inicio/fin usado durante la construcción)
# ══════════════════════════════════════════════════════════════════════════════


@dataclass
class _Fragment:
    """Fragmento NFA con un solo estado inicial y uno final."""
    start: NFAState
    end: NFAState


# ══════════════════════════════════════════════════════════════════════════════
#  Builder — construcción de Thompson
# ══════════════════════════════════════════════════════════════════════════════


class NFABuilder:
    """
    Construye el NFA global a partir de un ResolvedSpec.

    Uso:
        builder = NFABuilder(resolved_spec)
        nfa     = builder.build()
    """

    def __init__(self, resolved_spec: ResolvedSpec) -> None:
        self._spec = resolved_spec
        self._counter = 0          # generador de IDs de estado
        self._all_states: list[NFAState] = []

    # ── API pública ───────────────────────────────────────────────────────────

    def build(self) -> NFA:
        """Construye y devuelve el NFA global."""
        if not self._spec.rules:
            raise NFAError("No hay reglas para construir el NFA.")

        # Estado inicial global
        global_start = self._new_state()

        accept_states: list[NFAState] = []

        for rule in self._spec.rules:
            # Construir NFA para esta regla
            frag = self._build_fragment(rule.pattern_ast)

            # Conectar estado inicial global → inicio del fragmento (ε)
            global_start.add_transition(EPSILON, frag.start)

            # Marcar estado final del fragmento como aceptación
            frag.end.is_accept = True
            frag.end.token = rule.action.strip()
            frag.end.priority = rule.order

            accept_states.append(frag.end)

        return NFA(
            start=global_start,
            states=list(self._all_states),
            accept_states=accept_states,
        )

    # ── Creación de estados ───────────────────────────────────────────────────

    def _new_state(self, *, is_accept: bool = False,
                   token: str | None = None,
                   priority: int = 0) -> NFAState:
        state = NFAState(
            state_id=self._counter,
            is_accept=is_accept,
            token=token,
            priority=priority,
        )
        self._counter += 1
        self._all_states.append(state)
        return state

    # ── Dispatch por tipo de nodo AST ─────────────────────────────────────────

    def _build_fragment(self, node: ASTNode) -> _Fragment:
        """Convierte un nodo AST en un fragmento NFA (Thompson)."""

        if isinstance(node, LiteralNode):
            return self._frag_literal(node.value)

        if isinstance(node, CharClassNode):
            chars = node.chars
            if node.negated:
                chars = ALL_CHARS - chars
            return self._frag_char_set(chars)

        if isinstance(node, WildcardNode):
            # Cualquier carácter ASCII imprimible + control comunes
            return self._frag_char_set(ALL_CHARS)

        if isinstance(node, EofNode):
            # EOF se trata como un literal especial (ord 0 = NUL, reservado)
            # Usamos un símbolo sentinel: -1
            return self._frag_literal(-1)

        if isinstance(node, ConcatNode):
            return self._frag_concat(node)

        if isinstance(node, UnionNode):
            return self._frag_union(node)

        if isinstance(node, StarNode):
            return self._frag_star(node)

        if isinstance(node, PlusNode):
            return self._frag_plus(node)

        if isinstance(node, QuestionNode):
            return self._frag_question(node)

        if isinstance(node, DiffNode):
            return self._frag_diff(node)

        raise NFAError(f"Nodo AST no soportado: {type(node).__name__}")

    # ── Fragmentos de Thompson ────────────────────────────────────────────────

    def _frag_literal(self, char_ord: int) -> _Fragment:
        """i --char_ord--> f"""
        i = self._new_state()
        f = self._new_state()
        i.add_transition(char_ord, f)
        return _Fragment(i, f)

    def _frag_char_set(self, chars: frozenset) -> _Fragment:
        """i --[chars]--> f  (una sola transición con frozenset)"""
        i = self._new_state()
        f = self._new_state()
        i.add_transition(frozenset(chars), f)
        return _Fragment(i, f)

    def _frag_concat(self, node: ConcatNode) -> _Fragment:
        """
        Concatenación: A·B
        start_A --...-- end_A --ε--> start_B --...-- end_B
        Devuelve Fragment(start_A, end_B)
        """
        left = self._build_fragment(node.left)
        right = self._build_fragment(node.right)
        left.end.add_transition(EPSILON, right.start)
        return _Fragment(left.start, right.end)

    def _frag_union(self, node: UnionNode) -> _Fragment:
        """
        Alternancia: A|B
             ε→ start_A --...-- end_A ─ε→
        new_i                              new_f
             ε→ start_B --...-- end_B ─ε→
        """
        new_i = self._new_state()
        new_f = self._new_state()
        left  = self._build_fragment(node.left)
        right = self._build_fragment(node.right)

        new_i.add_transition(EPSILON, left.start)
        new_i.add_transition(EPSILON, right.start)
        left.end.add_transition(EPSILON, new_f)
        right.end.add_transition(EPSILON, new_f)

        return _Fragment(new_i, new_f)

    def _frag_star(self, node: StarNode) -> _Fragment:
        """
        Kleene: A*
        new_i ─ε→ start_A --...-- end_A ─ε→ new_f
          │                        │
          └────────────ε───────────┘  (loop)
          new_i ─ε──────────────────────────→ new_f  (ε directo)
        """
        new_i = self._new_state()
        new_f = self._new_state()
        inner = self._build_fragment(node.child)

        new_i.add_transition(EPSILON, inner.start)
        new_i.add_transition(EPSILON, new_f)
        inner.end.add_transition(EPSILON, inner.start)   # loop
        inner.end.add_transition(EPSILON, new_f)

        return _Fragment(new_i, new_f)

    def _frag_plus(self, node: PlusNode) -> _Fragment:
        """
        Positiva: A+  ≡  A·A*
        new_i ─ε→ start_A --...-- end_A ─ε→ new_f
                              │       ↑
                              └──ε────┘  (loop)
        Sin ε directo new_i → new_f (al menos una ocurrencia).
        """
        new_i = self._new_state()
        new_f = self._new_state()
        inner = self._build_fragment(node.child)

        new_i.add_transition(EPSILON, inner.start)
        inner.end.add_transition(EPSILON, inner.start)   # loop
        inner.end.add_transition(EPSILON, new_f)

        return _Fragment(new_i, new_f)

    def _frag_question(self, node: QuestionNode) -> _Fragment:
        """
        Opcional: A?
        new_i ─ε→ start_A --...-- end_A ─ε→ new_f
          └──────────────────ε──────────────→ new_f
        """
        new_i = self._new_state()
        new_f = self._new_state()
        inner = self._build_fragment(node.child)

        new_i.add_transition(EPSILON, inner.start)
        new_i.add_transition(EPSILON, new_f)             # saltar A
        inner.end.add_transition(EPSILON, new_f)

        return _Fragment(new_i, new_f)

    def _frag_diff(self, node: DiffNode) -> _Fragment:
        """
        Diferencia: A # B
        Solo está bien definida cuando ambos operandos se reducen a
        conjuntos de caracteres (CharClassNode o LiteralNode en el nivel
        inmediato del AST, ya que el resolver expandió las macros).
        Resultado: CharClass(chars_A - chars_B).
        """
        left_chars  = self._extract_char_set(node.left,  side="izquierdo")
        right_chars = self._extract_char_set(node.right, side="derecho")
        diff = left_chars - right_chars
        if not diff:
            raise NFAError(
                "La diferencia A # B produce un conjunto vacío; "
                "la expresión no puede reconocer ningún carácter."
            )
        return self._frag_char_set(diff)

    def _extract_char_set(self, node: ASTNode, *, side: str) -> frozenset:
        """
        Extrae el frozenset de caracteres de un nodo simple.
        Lanza NFAError si el nodo no es una clase de caracteres directa.
        """
        if isinstance(node, LiteralNode):
            return frozenset({node.value})
        if isinstance(node, CharClassNode):
            chars = node.chars
            if node.negated:
                chars = ALL_CHARS - chars
            return chars
        if isinstance(node, WildcardNode):
            return ALL_CHARS
        raise NFAError(
            f"El operando {side} de '#' no es una clase de caracteres simple. "
            f"El operador '#' solo admite CharClass, Literal o Wildcard directos. "
            f"Nodo recibido: {type(node).__name__}"
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Función de conveniencia
# ══════════════════════════════════════════════════════════════════════════════


def build_nfa(resolved_spec: ResolvedSpec) -> NFA:
    """
    Construye el NFA global a partir de la especificación resuelta.

    Parámetros:
        resolved_spec — salida del DefinitionResolver

    Retorna:
        NFA listo para ser consumido por el constructor de DFA.
    """
    builder = NFABuilder(resolved_spec)
    return builder.build()
