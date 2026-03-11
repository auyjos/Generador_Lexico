"""
dfa.py — Módulo 5: Constructor de DFA + Módulo 6: Minimización de Hopcroft

Responsabilidades (arquitectura §10.6 y §10.7):

  Constructor de DFA (construcción de subconjuntos):
    - Calcula la cerradura-ε del estado inicial del NFA.
    - Crea estados del DFA como conjuntos de estados del NFA.
    - Construye la tabla de transiciones determinista.
    - Si un estado DFA contiene múltiples estados de aceptación del NFA,
      selecciona el token con menor priority (maximal munch / orden).

  Minimizador de Hopcroft:
    - Aplica el algoritmo de Hopcroft para obtener el DFA mínimo.
    - Preserva las etiquetas de token y prioridad de los estados de aceptación.

Entrada:  NFA          (salida del NFABuilder)
Salida:   DFA          (objeto con tabla de transiciones determinista,
                        listo para el generador de código)
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import FrozenSet, Optional

from src.lexer.nfa import EPSILON, NFA, NFAState

# ══════════════════════════════════════════════════════════════════════════════
#  Excepciones
# ══════════════════════════════════════════════════════════════════════════════


class DFAError(Exception):
    """Error durante la construcción o minimización del DFA."""


# ══════════════════════════════════════════════════════════════════════════════
#  Estado del DFA
# ══════════════════════════════════════════════════════════════════════════════


@dataclass
class DFAState:
    """
    Un estado del DFA.

    Campos:
        state_id   — identificador único
        nfa_states — frozenset de NFAState que forman este estado DFA
        is_accept  — True si es estado de aceptación
        token      — nombre del token si is_accept
        priority   — prioridad de la regla ganadora (menor = más alta)
        transitions — dict[symbol → DFAState]
                      symbol: int (char) o frozenset[int] (class)
                      NOTA: en el DFA las clases se expanden; cada símbolo
                      en la tabla es un int individual.
    """

    state_id: int
    nfa_states: frozenset
    is_accept: bool = False
    token: Optional[str] = None
    priority: int = 0
    transitions: dict = field(default_factory=dict)   # int → DFAState

    def __repr__(self) -> str:
        accept = f", token={self.token!r}" if self.is_accept else ""
        return f"DFAState(id={self.state_id}{accept})"

    def __hash__(self):
        return hash(self.state_id)

    def __eq__(self, other):
        return isinstance(other, DFAState) and self.state_id == other.state_id


# ══════════════════════════════════════════════════════════════════════════════
#  DFA
# ══════════════════════════════════════════════════════════════════════════════


@dataclass
class DFA:
    """
    Autómata Finito Determinista.

    Campos:
        start         — estado inicial
        states        — todos los estados (en orden de creación)
        accept_states — estados de aceptación
        alphabet      — conjunto de símbolos (ints) que aparecen en transiciones
    """

    start: DFAState
    states: list[DFAState]
    accept_states: list[DFAState]
    alphabet: frozenset

    # ── Representación ────────────────────────────────────────────────────────

    def pretty_print(self, *, title: str = "DFA") -> str:
        lines: list[str] = []
        lines.append("=" * 60)
        lines.append(f"  RESULTADO: {title}")
        lines.append("=" * 60)
        lines.append(f"\n  Total de estados : {len(self.states)}")
        lines.append(f"  Estado inicial   : D{self.start.state_id}")
        lines.append(
            f"  Estados de aceptación: "
            + str([f"D{s.state_id}({s.token})" for s in self.accept_states])
        )
        lines.append(
            f"  Alfabeto         : {len(self.alphabet)} símbolos"
        )

        lines.append("\n-- Tabla de Transiciones (DFA) --")
        # Mostrar los primeros 30 símbolos del alfabeto para no saturar
        alpha_sample = sorted(self.alphabet)[:40]
        col = 8

        # Encabezado
        header = f"  {'Estado':<14}" + "".join(
            f"{_sym_label(s):>{col}}" for s in alpha_sample
        )
        lines.append(header)
        lines.append("  " + "-" * (14 + col * len(alpha_sample)))

        for state in self.states:
            label = f"D{state.state_id}"
            if state.is_accept:
                label += f"*({state.token[:6] if state.token else '?'})"
            if state == self.start:
                label = "->" + label

            row = f"  {label:<14}"
            for sym in alpha_sample:
                target = state.transitions.get(sym)
                row += f"{'D' + str(target.state_id) if target else '-':>{col}}"
            lines.append(row)

        if len(self.alphabet) > 40:
            lines.append(f"  ... (se muestran solo 40 de {len(self.alphabet)} símbolos)")

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)


def _sym_label(sym: int) -> str:
    c = chr(sym)
    if c.isprintable() and c not in (" ", "\t", "\n"):
        return c
    return f"\\x{sym:02x}"


# ══════════════════════════════════════════════════════════════════════════════
#  Funciones auxiliares — cerradura-ε y move
# ══════════════════════════════════════════════════════════════════════════════


def epsilon_closure(states: frozenset) -> frozenset:
    """
    Calcula la cerradura-ε de un conjunto de estados NFA.
    Devuelve el frozenset de todos los estados alcanzables por ε* desde
    cualquier estado del conjunto de entrada.
    """
    closure = set(states)
    stack = list(states)

    while stack:
        s = stack.pop()
        for target in s.transitions.get(EPSILON, []):
            if target not in closure:
                closure.add(target)
                stack.append(target)

    return frozenset(closure)


def move(states: frozenset, symbol: int) -> frozenset:
    """
    Calcula move(states, symbol): conjunto de estados NFA alcanzables
    consumiendo el símbolo 'symbol' (int) desde cualquier estado de 'states'.

    Las transiciones del NFA pueden ser:
      · int exacto  → coincide si symbol == int
      · frozenset   → coincide si symbol está en el frozenset
    """
    result: set[NFAState] = set()
    for s in states:
        for sym, targets in s.transitions.items():
            if sym is EPSILON:
                continue
            if isinstance(sym, int) and sym == symbol:
                result.update(targets)
            elif isinstance(sym, frozenset) and symbol in sym:
                result.update(targets)
    return frozenset(result)


def _collect_alphabet(nfa: NFA) -> frozenset:
    """
    Reúne todos los símbolos del alfabeto que aparecen en el NFA
    (excluyendo ε).  Los frozenset se expanden a ints individuales.
    """
    alphabet: set[int] = set()
    for state in nfa.states:
        for sym in state.transitions:
            if sym is EPSILON:
                continue
            if isinstance(sym, int):
                alphabet.add(sym)
            elif isinstance(sym, frozenset):
                alphabet.update(sym)
    return frozenset(alphabet)


def _accept_info(nfa_states: frozenset) -> tuple[bool, str | None, int]:
    """
    Determina si un conjunto de estados NFA es de aceptación.
    Si hay varios estados aceptantes, gana el de menor prioridad (order).
    Retorna (is_accept, token, priority).
    """
    accepting = [s for s in nfa_states if s.is_accept]
    if not accepting:
        return False, None, 0
    winner = min(accepting, key=lambda s: s.priority)
    return True, winner.token, winner.priority


# ══════════════════════════════════════════════════════════════════════════════
#  Constructor de DFA (construcción de subconjuntos)
# ══════════════════════════════════════════════════════════════════════════════


class SubsetConstructor:
    """
    Transforma el NFA en un DFA usando el algoritmo de construcción de
    subconjuntos (subset construction / powerset construction).

    Uso:
        sc  = SubsetConstructor(nfa)
        dfa = sc.build()
    """

    def __init__(self, nfa: NFA) -> None:
        self._nfa = nfa
        self._alphabet = _collect_alphabet(nfa)
        self._counter = 0
        self._dfa_states: list[DFAState] = []
        # Mapeo frozenset(NFAStates) → DFAState para evitar duplicados
        self._state_map: dict[frozenset, DFAState] = {}

    # ── API pública ───────────────────────────────────────────────────────────

    def build(self) -> DFA:
        # Estado inicial DFA = ε-clausura del estado inicial NFA
        start_closure = epsilon_closure(frozenset({self._nfa.start}))
        start_dfa = self._get_or_create(start_closure)

        # BFS sobre los estados DFA no procesados
        worklist: deque[DFAState] = deque([start_dfa])
        visited: set[int] = set()

        while worklist:
            dfa_state = worklist.popleft()
            if dfa_state.state_id in visited:
                continue
            visited.add(dfa_state.state_id)

            for symbol in self._alphabet:
                nfa_targets = move(dfa_state.nfa_states, symbol)
                if not nfa_targets:
                    continue
                closure = epsilon_closure(nfa_targets)
                target_dfa = self._get_or_create(closure)
                dfa_state.transitions[symbol] = target_dfa
                if target_dfa.state_id not in visited:
                    worklist.append(target_dfa)

        accept_states = [s for s in self._dfa_states if s.is_accept]

        return DFA(
            start=start_dfa,
            states=list(self._dfa_states),
            accept_states=accept_states,
            alphabet=self._alphabet,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_or_create(self, nfa_states: frozenset) -> DFAState:
        if nfa_states in self._state_map:
            return self._state_map[nfa_states]

        is_acc, token, prio = _accept_info(nfa_states)
        dfa_state = DFAState(
            state_id=self._counter,
            nfa_states=nfa_states,
            is_accept=is_acc,
            token=token,
            priority=prio,
        )
        self._counter += 1
        self._dfa_states.append(dfa_state)
        self._state_map[nfa_states] = dfa_state
        return dfa_state


# ══════════════════════════════════════════════════════════════════════════════
#  Minimización de Hopcroft
# ══════════════════════════════════════════════════════════════════════════════


class HopcroftMinimizer:
    """
    Minimiza un DFA usando el algoritmo de Hopcroft (partición de estados).

    Pasos:
      1. Partición inicial: estados de aceptación agrupados por token,
         más el grupo de estados de no-aceptación.
      2. Refinar particiones mientras sea posible.
      3. Construir el DFA minimizado eligiendo un representante por partición.

    Uso:
        minimizer = HopcroftMinimizer(dfa)
        min_dfa   = minimizer.minimize()
    """

    def __init__(self, dfa: DFA) -> None:
        self._dfa = dfa

    # ── API pública ───────────────────────────────────────────────────────────

    def minimize(self) -> DFA:
        dfa = self._dfa

        if not dfa.states:
            return dfa

        # ── Paso 1: partición inicial ──────────────────────────────────────
        # Agrupa los estados aceptantes por token (estados con el mismo token
        # van juntos) + un grupo para los no-aceptantes.

        groups: dict[str, set[DFAState]] = {}
        non_accept: set[DFAState] = set()

        for state in dfa.states:
            if state.is_accept:
                key = state.token or "__accept__"
                groups.setdefault(key, set()).add(state)
            else:
                non_accept.add(state)

        partitions: list[set[DFAState]] = list(groups.values())
        if non_accept:
            partitions.append(non_accept)

        # ── Paso 2: refinamiento ──────────────────────────────────────────
        changed = True
        while changed:
            changed = False
            new_partitions: list[set[DFAState]] = []

            for part in partitions:
                splits = self._split(part, partitions, dfa.alphabet)
                if len(splits) > 1:
                    changed = True
                new_partitions.extend(splits)

            partitions = new_partitions

        # ── Paso 3: construir DFA minimizado ──────────────────────────────
        return self._build_minimized(partitions, dfa)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _partition_of(self, state: DFAState,
                      partitions: list[set]) -> int:
        """Devuelve el índice de la partición a la que pertenece state."""
        for i, part in enumerate(partitions):
            if state in part:
                return i
        raise DFAError(f"Estado {state} no encontrado en ninguna partición.")

    def _split(self, group: set[DFAState],
               partitions: list[set],
               alphabet: frozenset) -> list[set[DFAState]]:
        """
        Intenta dividir 'group' en sub-grupos más refinados.
        Dos estados son distinguibles si para algún símbolo van a
        particiones distintas.
        """
        if len(group) <= 1:
            return [group]

        # Usamos el primer estado como referencia
        states = list(group)
        ref = states[0]

        same: set[DFAState] = {ref}
        different: set[DFAState] = set()

        ref_sig = self._signature(ref, partitions, alphabet)

        for state in states[1:]:
            if self._signature(state, partitions, alphabet) == ref_sig:
                same.add(state)
            else:
                different.add(state)

        if not different:
            return [group]

        result = [same]
        # Los diferentes pueden necesitar subdivisiones recursivas en la
        # siguiente iteración; por ahora los devolvemos como un solo grupo.
        result.append(different)
        return result

    def _signature(self, state: DFAState,
                   partitions: list[set],
                   alphabet: frozenset) -> tuple:
        """
        Firma de un estado: tupla de (símbolo, índice_partición_destino)
        para cada símbolo del alfabeto (o -1 si no hay transición).
        """
        sig = []
        for sym in sorted(alphabet):
            target = state.transitions.get(sym)
            if target is None:
                sig.append((sym, -1))
            else:
                sig.append((sym, self._partition_of(target, partitions)))
        return tuple(sig)

    def _build_minimized(self,
                         partitions: list[set[DFAState]],
                         original: DFA) -> DFA:
        """Construye el DFA minimizado a partir de las particiones finales."""
        # Elegir representante por partición (primero en orden de id)
        reps: list[DFAState] = [
            min(part, key=lambda s: s.state_id) for part in partitions
        ]

        # Mapeo estado original → representante de su partición
        state_to_rep: dict[int, DFAState] = {}
        for i, part in enumerate(partitions):
            rep = reps[i]
            for s in part:
                state_to_rep[s.state_id] = rep

        # Crear nuevos estados minimizados (re-numerados)
        new_id = 0
        rep_to_new: dict[int, DFAState] = {}

        for rep in reps:
            new_state = DFAState(
                state_id=new_id,
                nfa_states=rep.nfa_states,
                is_accept=rep.is_accept,
                token=rep.token,
                priority=rep.priority,
            )
            rep_to_new[rep.state_id] = new_state
            new_id += 1

        # Reconstruir transiciones
        for i, rep in enumerate(reps):
            new_state = rep_to_new[rep.state_id]
            for sym, target in rep.transitions.items():
                target_rep = state_to_rep[target.state_id]
                new_state.transitions[sym] = rep_to_new[target_rep.state_id]

        # Estado inicial minimizado
        start_rep = state_to_rep[original.start.state_id]
        new_start = rep_to_new[start_rep.state_id]

        all_new = list(rep_to_new.values())
        accept_new = [s for s in all_new if s.is_accept]

        return DFA(
            start=new_start,
            states=all_new,
            accept_states=accept_new,
            alphabet=original.alphabet,
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Funciones de conveniencia
# ══════════════════════════════════════════════════════════════════════════════


def build_dfa(nfa: NFA) -> DFA:
    """
    Construye el DFA desde el NFA usando construcción de subconjuntos.

    Parámetros:
        nfa — NFA global construido por NFABuilder

    Retorna:
        DFA sin minimizar.
    """
    sc = SubsetConstructor(nfa)
    return sc.build()


def minimize_dfa(dfa: DFA) -> DFA:
    """
    Minimiza el DFA usando el algoritmo de Hopcroft.

    Parámetros:
        dfa — DFA construido por build_dfa (o cualquier DFA válido)

    Retorna:
        DFA minimizado.
    """
    minimizer = HopcroftMinimizer(dfa)
    return minimizer.minimize()
