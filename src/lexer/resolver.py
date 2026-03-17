"""
resolver.py — Módulo 3: Resolvedor de Definiciones y Validador Semántico

Responsabilidades (arquitectura §6.4):
  - Sustitución ESTRUCTURAL de referencias (RefNode → copia del AST de la
    definición), sin reemplazo textual; la precedencia queda preservada por
    la estructura misma del árbol.
  - Detección de referencias no definidas (fase 1).
  - Detección de ciclos entre definiciones mediante DFS con coloreo
    BLANCO / GRIS / NEGRO (fase 2).
  - Orden topológico de resolución: cada definición se resuelve solo después
    de que todas sus dependencias ya lo están (fase 2).
  - Sustitución de referencias en las reglas de token (fase 3).
  - Validación semántica: acción no vacía, sin RefNodes residuales (fase 4).
  - Detección de acciones duplicadas (advertencia, no error fatal) (fase 5).

Regla de parada:
  Si se detecta cualquier error en esta fase el proceso se detiene con
  ResolverError y NO se inicia la construcción del NFA.

Entrada:  LexerSpec   (salida del YALexParser — AST Léxico)
Salida:   ResolvedSpec (AST completamente expandido, sin RefNodes)
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from src.lexer.regex_parser import (
    ASTNode,
    CharClassNode,
    ConcatNode,
    DefinitionAST,
    DiffNode,
    EofNode,
    LexerSpec,
    LiteralNode,
    PlusNode,
    QuestionNode,
    RefNode,
    RuleAST,
    StarNode,
    UnionNode,
    WildcardNode,
    ast_to_string,
)

#  Excepción propia del Resolvedor


class ResolverError(Exception):
    """Error semántico detectado durante la resolución de definiciones."""

    def __init__(
        self,
        message: str,
        *,
        line: int | None = None,
        name: str = "",
    ):
        self.line = line
        self.ref_name = name
        prefix = f"[línea {line}] " if line is not None else ""
        context = f" en '{name}'" if name else ""
        super().__init__(f"{prefix}{message}{context}")


# 
#  Estructuras de salida
# 


@dataclass
class ResolvedRule:
    """Una regla de token con el AST completamente expandido (sin RefNodes)."""

    pattern_ast: ASTNode    # AST expandido, listo para Thompson
    action: str             # Código de la acción semántica
    raw_pattern: str        # Texto original del patrón (para mensajes)
    line_number: int        # Línea de origen en el .yal
    order: int              # Prioridad (orden de aparición)


@dataclass
class ResolvedSpec:
    """
    Especificación léxica completamente resuelta y validada semánticamente.

    - resolved_defs: definiciones expandidas (sin RefNodes), en orden
      topológico.  Útil para graficación y depuración.
    - rules: reglas de token con AST totalmente expandido.
    - Ningún nodo RefNode subsiste en esta estructura.
    """

    header: str | None
    resolved_defs: dict[str, ASTNode]   # nombre → AST expandido
    topo_order: list[str]               # orden topológico de resolución
    rules: list[ResolvedRule]
    rule_name: str
    trailer: str | None

    # ── Visualización ────────────────────────────────────────────────────────

    def pretty_print(self) -> str:
        lines: list[str] = []
        lines.append("=" * 60)
        lines.append("  RESULTADO DEL RESOLVEDOR DE DEFINICIONES")
        lines.append("=" * 60)

        # ── Header ──
        lines.append("\n-- Header --")
        if self.header:
            for h in self.header.strip().splitlines():
                lines.append(f"  {h}")
        else:
            lines.append("  (vacío)")

        # ── Definiciones expandidas ──
        lines.append("\n-- Definiciones Expandidas (orden topológico) --")
        if self.resolved_defs:
            for name in self.topo_order:
                ast = self.resolved_defs[name]
                lines.append(f"\n  let {name}  =>")
                for ast_line in ast_to_string(ast, indent=2).splitlines():
                    lines.append(f"  {ast_line}")
        else:
            lines.append("  (ninguna)")

        # ── Reglas normalizadas ──
        lines.append(
            f"\n-- Reglas Normalizadas  (entrypoint: {self.rule_name}) --"
        )
        if self.rules:
            for r in self.rules:
                lines.append(
                    f"\n  [{r.order}] línea {r.line_number}: "
                    f"{r.raw_pattern!r}"
                )
                lines.append(f"        Acción : {r.action!r}")
                lines.append(f"        AST expandido:")
                for ast_line in ast_to_string(r.pattern_ast, indent=3).splitlines():
                    lines.append(f"  {ast_line}")
        else:
            lines.append("  (ninguna)")

        # ── Trailer ──
        lines.append("\n-- Trailer --")
        if self.trailer:
            for t in self.trailer.strip().splitlines():
                lines.append(f"  {t}")
        else:
            lines.append("  (vacío)")

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)


# 
#  Funciones auxiliares sobre el AST
# 


def _collect_refs(node: ASTNode) -> set[str]:
    """Devuelve el conjunto de nombres referenciados (RefNode) en el árbol."""
    if isinstance(node, RefNode):
        return {node.name}
    if isinstance(node, (ConcatNode, UnionNode, DiffNode)):
        return _collect_refs(node.left) | _collect_refs(node.right)
    if isinstance(node, (StarNode, PlusNode, QuestionNode)):
        return _collect_refs(node.child)
    return set()  # LiteralNode, CharClassNode, WildcardNode, EofNode → hojas


def _substitute(node: ASTNode, env: dict[str, ASTNode]) -> ASTNode:
    """
    Sustituye ESTRUCTURALMENTE cada RefNode con una copia profunda del AST
    correspondiente en env.  La precedencia queda intacta porque trabajamos
    sobre la estructura del árbol, no sobre texto.

    Raises:
        ResolverError si se encuentra una referencia no presente en env.
    """
    if isinstance(node, RefNode):
        if node.name not in env:
            raise ResolverError(
                f"Referencia no definida: '{node.name}'",
                name=node.name,
            )
        # Copia profunda para evitar aliasing entre ramas del árbol final
        return copy.deepcopy(env[node.name])

    if isinstance(node, ConcatNode):
        return ConcatNode(
            _substitute(node.left, env),
            _substitute(node.right, env),
        )
    if isinstance(node, UnionNode):
        return UnionNode(
            _substitute(node.left, env),
            _substitute(node.right, env),
        )
    if isinstance(node, DiffNode):
        return DiffNode(
            _substitute(node.left, env),
            _substitute(node.right, env),
        )
    if isinstance(node, StarNode):
        return StarNode(_substitute(node.child, env))
    if isinstance(node, PlusNode):
        return PlusNode(_substitute(node.child, env))
    if isinstance(node, QuestionNode):
        return QuestionNode(_substitute(node.child, env))

    # Nodos hoja: LiteralNode, CharClassNode, WildcardNode, EofNode
    return copy.deepcopy(node)


# 
#  Resolvedor principal
# 


class DefinitionResolver:
    """
    Orquesta las cinco fases de resolución y validación semántica.

    Uso:
        resolver = DefinitionResolver(lexer_spec)
        resolved  = resolver.resolve()   # lanza ResolverError si hay error
    """

    # Colores para DFS de detección de ciclos
    _WHITE = 0   # no visitado
    _GRAY  = 1   # en la pila de recursión actual
    _BLACK = 2   # completamente procesado

    def __init__(self, lexer_spec: LexerSpec) -> None:
        self.spec = lexer_spec

        # Índice de definiciones crudas (no resueltas)
        self._raw_defs: dict[str, DefinitionAST] = {
            d.name: d for d in lexer_spec.definitions
        }

        # Definiciones ya resueltas (se llena en fase 2)
        self._resolved: dict[str, ASTNode] = {}

        # Orden topológico de resolución (se llena en fase 2)
        self._topo_order: list[str] = []

        # Estado de coloreo para DFS
        self._color: dict[str, int] = {
            name: self._WHITE for name in self._raw_defs
        }

    # ── API pública ──────────────────────────────────────────────────────────

    def resolve(self) -> ResolvedSpec:
        """
        Ejecuta las cinco fases y devuelve el ResolvedSpec.
        Lanza ResolverError ante cualquier error semántico.
        """
        self._phase1_check_undefined_refs()
        self._phase2_resolve_definitions()       # detecta ciclos + topo-sort
        resolved_rules = self._phase3_resolve_rules()
        self._phase4_validate_rules(resolved_rules)
        self._phase5_check_duplicate_actions(resolved_rules)

        return ResolvedSpec(
            header=self.spec.header,
            resolved_defs=dict(self._resolved),
            topo_order=list(self._topo_order),
            rules=resolved_rules,
            rule_name=self.spec.rule_name,
            trailer=self.spec.trailer,
        )

    # ── Fase 1: Detección de referencias no definidas ────────────────────────

    def _phase1_check_undefined_refs(self) -> None:
        """
        Comprueba que TODAS las referencias usadas en definiciones y reglas
        estén declaradas como let-definitions.  Detiene el proceso si no.
        """
        known = set(self._raw_defs.keys())

        for defn in self.spec.definitions:
            for ref in _collect_refs(defn.regex_ast):
                if ref not in known:
                    raise ResolverError(
                        f"Referencia no definida: '{ref}'",
                        name=defn.name,
                    )

        for rule in self.spec.rules:
            for ref in _collect_refs(rule.pattern_ast):
                if ref not in known:
                    raise ResolverError(
                        f"Referencia no definida: '{ref}'",
                        line=rule.line_number,
                    )

    # ── Fase 2: Resolución con detección de ciclos (DFS) ────────────────────

    def _phase2_resolve_definitions(self) -> None:
        """
        Visita cada definición no resuelta; la resolución sigue el orden
        topológico natural de las dependencias.  Un ciclo se detecta cuando
        durante el DFS encontramos un nodo GRIS (ya en la pila actual).
        """
        for name in list(self._raw_defs.keys()):
            if self._color[name] == self._WHITE:
                self._dfs_resolve(name, [])

    def _dfs_resolve(self, name: str, chain: list[str]) -> None:
        """
        DFS recursivo para resolver 'name'.
        chain: lista de nombres en la pila de recursión actual (para el
               mensaje de error de ciclo).
        """
        self._color[name] = self._GRAY
        chain.append(name)

        for dep in _collect_refs(self._raw_defs[name].regex_ast):
            if self._color[dep] == self._GRAY:
                # Ciclo detectado: dep ya está en la pila
                cycle_path = " → ".join(chain + [dep])
                raise ResolverError(
                    f"Ciclo detectado entre definiciones: {cycle_path}",
                    name=name,
                )
            if self._color[dep] == self._WHITE:
                self._dfs_resolve(dep, chain)

        # Todas las dependencias están resueltas; sustituir ahora
        self._resolved[name] = _substitute(
            self._raw_defs[name].regex_ast, self._resolved
        )
        self._topo_order.append(name)

        chain.pop()
        self._color[name] = self._BLACK

    # ── Fase 3: Resolución de las reglas ────────────────────────────────────

    def _phase3_resolve_rules(self) -> list[ResolvedRule]:
        """
        Expande las referencias dentro de cada regla usando las definiciones
        ya completamente resueltas.
        """
        result: list[ResolvedRule] = []
        for rule in self.spec.rules:
            try:
                resolved_ast = _substitute(rule.pattern_ast, self._resolved)
            except ResolverError as e:
                raise ResolverError(
                    f"Error en regla [{rule.order}] "
                    f"(línea {rule.line_number}): {e}",
                    line=rule.line_number,
                ) from e

            result.append(
                ResolvedRule(
                    pattern_ast=resolved_ast,
                    action=rule.action,
                    raw_pattern=rule.raw_pattern,
                    line_number=rule.line_number,
                    order=rule.order,
                )
            )
        return result

    # ── Fase 4: Validación semántica ─────────────────────────────────────────

    def _phase4_validate_rules(self, rules: list[ResolvedRule]) -> None:
        """
        Para cada regla verifica:
          - No quedaron RefNodes sin expandir (post-condición de integridad).
        Nota: acciones vacías son válidas (significan "saltar este token").
        """
        for rule in rules:
            residual = _collect_refs(rule.pattern_ast)
            if residual:
                # Esto indicaría un bug interno del resolvedor
                raise ResolverError(
                    f"Referencias sin expandir en regla [{rule.order}]: "
                    f"{', '.join(sorted(residual))}",
                    line=rule.line_number,
                )

    # ── Fase 5: Detección de acciones duplicadas ─────────────────────────────

    def _phase5_check_duplicate_actions(
        self, rules: list[ResolvedRule]
    ) -> None:
        """
        Advierte (sin detener el proceso) cuando dos o más reglas tienen
        exactamente la misma acción semántica.  En YALex esto es válido
        (ej. múltiples patrones de espacio en blanco que emiten 'skip'),
        pero puede indicar un error de diseño en otros casos.
        """
        seen: dict[str, int] = {}   # acción normalizada → primer orden
        for rule in rules:
            key = rule.action.strip()
            if key in seen:
                print(
                    f"  [ADVERTENCIA] La acción '{key}' ya fue definida en "
                    f"la regla [{seen[key]}]; "
                    f"la regla [{rule.order}] también la usa. "
                    f"Ante empate gana la de menor orden (maximal munch)."
                )
            else:
                seen[key] = rule.order
