"""
Parser de Especificación (regex_parser.py) — Módulo 2 del Generador de
Analizadores Léxicos.

Responsabilidades (arquitectura §6.2 y §6.3):
  - Parseo de las definiciones y reglas provenientes del Procesador
  - Tokenización de expresiones regulares YALex
  - Inserción de operadores de concatenación explícitos
  - Construcción de un AST (Árbol de Sintaxis) por cada expresión regular
  - Generación de errores sintácticos con posición
  - Salida en consola del resultado del parseo

Entrada:  ScannerResult (salida del Procesador)
Salida:   LexerSpec (AST Léxico) — representación estructurada lista para
          el Resolvedor de Definiciones (siguiente módulo)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from src.lexer.scanner import ScannerResult

# ══════════════════════════════════════════════════════════════════════════════
#  Excepciones
# ══════════════════════════════════════════════════════════════════════════════

class ParserError(Exception):
    """Error sintáctico durante el parseo de expresiones regulares."""

    def __init__(self, message: str, *, pos: int | None = None,
                 line: int | None = None, context: str = ""):
        self.pos = pos
        self.line = line
        parts: list[str] = []
        if line is not None:
            parts.append(f"línea {line}")
        if pos is not None:
            parts.append(f"pos {pos}")
        prefix = f"[{', '.join(parts)}] " if parts else ""
        detail = f" en '{context}'" if context else ""
        super().__init__(f"{prefix}{message}{detail}")


# ══════════════════════════════════════════════════════════════════════════════
#  Tokens del tokenizador de regex
# ══════════════════════════════════════════════════════════════════════════════

class TokType(Enum):
    CHAR       = auto()   # Literal de un carácter  (value = ord)
    CHAR_CLASS = auto()   # Clase de caracteres     (value = frozenset[int])
    REF        = auto()   # Referencia a definición (value = nombre)
    WILDCARD   = auto()   # _  (cualquier símbolo)
    EOF_TOK    = auto()   # Palabra clave 'eof'
    STAR       = auto()   # *
    PLUS_OP    = auto()   # +
    QUESTION   = auto()   # ?
    PIPE       = auto()   # |
    HASH       = auto()   # #
    LPAREN     = auto()   # (
    RPAREN     = auto()   # )
    CONCAT     = auto()   # · (insertado explícitamente)


@dataclass
class Token:
    type: TokType
    value: Any = None        # depende del tipo
    negated: bool = False    # solo para CHAR_CLASS
    pos: int = 0             # posición en el string fuente

    def __repr__(self) -> str:
        if self.type == TokType.CHAR:
            ch = chr(self.value)
            display = repr(ch) if not ch.isprintable() or ch == " " else f"'{ch}'"
            return f"CHAR({display})"
        if self.type == TokType.CHAR_CLASS:
            neg = "^" if self.negated else ""
            return f"CLASS([{neg}…{len(self.value)} chars])"
        if self.type == TokType.REF:
            return f"REF({self.value})"
        return self.type.name


# ══════════════════════════════════════════════════════════════════════════════
#  Nodos del AST de expresiones regulares
# ══════════════════════════════════════════════════════════════════════════════

class ASTNode:
    """Clase base para los nodos del árbol de sintaxis."""


@dataclass
class LiteralNode(ASTNode):
    """Un carácter literal."""
    value: int                  # ord del carácter


@dataclass
class CharClassNode(ASTNode):
    """Clase de caracteres [set] o [^set]."""
    chars: frozenset            # frozenset de ords
    negated: bool = False


@dataclass
class WildcardNode(ASTNode):
    """Cualquier carácter ( _ )."""


@dataclass
class EofNode(ASTNode):
    """Fin de entrada (eof)."""


@dataclass
class RefNode(ASTNode):
    """Referencia a una definición 'let'."""
    name: str


@dataclass
class ConcatNode(ASTNode):
    """Concatenación de dos sub-expresiones."""
    left: ASTNode
    right: ASTNode


@dataclass
class UnionNode(ASTNode):
    """Alternancia  ( | )."""
    left: ASTNode
    right: ASTNode


@dataclass
class StarNode(ASTNode):
    """Cerradura de Kleene ( * )."""
    child: ASTNode


@dataclass
class PlusNode(ASTNode):
    """Cerradura positiva ( + )."""
    child: ASTNode


@dataclass
class QuestionNode(ASTNode):
    """Opcional ( ? )."""
    child: ASTNode


@dataclass
class DiffNode(ASTNode):
    """Diferencia de conjuntos ( # )."""
    left: ASTNode
    right: ASTNode


# ══════════════════════════════════════════════════════════════════════════════
#  Tokenizador de expresiones regulares YALex
# ══════════════════════════════════════════════════════════════════════════════

class RegexTokenizer:
    """
    Convierte una cadena de expresión regular YALex en una lista de Token.

    Maneja:
      - Literales entre comillas simples: 'a', '\\n', '\\t'
      - Literales entre comillas dobles: "abc" → secuencia de CHAR
      - Clases de caracteres: ['0'-'9'], [^'a'-'z'], [a-z] (estilo bare)
      - Operadores: * + ? | #
      - Agrupación: ( )
      - Identificadores: referencias a let-definitions
      - Palabras clave: eof, _
    """

    def __init__(self, text: str, *, context: str = ""):
        self.text = text
        self.pos = 0
        self.context = context   # para mensajes de error
        self.tokens: list[Token] = []

    # ── API ───────────────────────────────────────────────────────────────

    def tokenize(self) -> list[Token]:
        self.tokens = []
        self.pos = 0

        while self.pos < len(self.text):
            self._skip_spaces()
            if self.pos >= len(self.text):
                break

            ch = self.text[self.pos]

            if ch == "'":
                self._read_char_literal()
            elif ch == '"':
                self._read_string_literal()
            elif ch == "[":
                self._read_char_class()
            elif ch == "(":
                self.tokens.append(Token(TokType.LPAREN, pos=self.pos))
                self.pos += 1
            elif ch == ")":
                self.tokens.append(Token(TokType.RPAREN, pos=self.pos))
                self.pos += 1
            elif ch == "*":
                self.tokens.append(Token(TokType.STAR, pos=self.pos))
                self.pos += 1
            elif ch == "+":
                self.tokens.append(Token(TokType.PLUS_OP, pos=self.pos))
                self.pos += 1
            elif ch == "?":
                self.tokens.append(Token(TokType.QUESTION, pos=self.pos))
                self.pos += 1
            elif ch == "|":
                self.tokens.append(Token(TokType.PIPE, pos=self.pos))
                self.pos += 1
            elif ch == "#":
                self.tokens.append(Token(TokType.HASH, pos=self.pos))
                self.pos += 1
            elif ch.isalpha() or ch == "_":
                self._read_identifier()
            else:
                raise ParserError(
                    f"Carácter inesperado: {ch!r}",
                    pos=self.pos,
                    context=self.context,
                )

        return self.tokens

    # ── Helpers internos ──────────────────────────────────────────────────

    def _skip_spaces(self) -> None:
        while self.pos < len(self.text) and self.text[self.pos] in " \t\r\n":
            self.pos += 1

    def _read_escaped_char(self) -> str:
        """Lee un carácter posiblemente escapado y avanza pos."""
        ch = self.text[self.pos]
        self.pos += 1
        if ch == "\\":
            if self.pos >= len(self.text):
                raise ParserError("Escape sin carácter", pos=self.pos - 1,
                                  context=self.context)
            esc = self.text[self.pos]
            self.pos += 1
            return {
                "n": "\n", "t": "\t", "r": "\r",
                "s": " ", "0": "\0",
                "\\": "\\", "'": "'", '"': '"',
            }.get(esc, esc)
        return ch

    # ── Literal de carácter 'c' ──────────────────────────────────────────

    def _read_char_literal(self) -> None:
        start = self.pos
        self.pos += 1  # saltar '
        if self.pos >= len(self.text):
            raise ParserError("Literal de carácter sin cerrar",
                              pos=start, context=self.context)
        ch = self._read_escaped_char()
        if self.pos >= len(self.text) or self.text[self.pos] != "'":
            raise ParserError("Se esperaba comilla simple de cierre",
                              pos=start, context=self.context)
        self.pos += 1  # saltar '
        self.tokens.append(Token(TokType.CHAR, value=ord(ch), pos=start))

    # ── Literal de cadena "abc" ──────────────────────────────────────────

    def _read_string_literal(self) -> None:
        start = self.pos
        self.pos += 1  # saltar "
        chars: list[str] = []
        while self.pos < len(self.text) and self.text[self.pos] != '"':
            chars.append(self._read_escaped_char())
        if self.pos >= len(self.text):
            raise ParserError("Literal de cadena sin cerrar",
                              pos=start, context=self.context)
        self.pos += 1  # saltar "
        for c in chars:
            self.tokens.append(Token(TokType.CHAR, value=ord(c), pos=start))

    # ── Clase de caracteres [ … ] ────────────────────────────────────────

    def _read_char_class(self) -> None:
        start = self.pos
        self.pos += 1  # saltar [

        negated = False
        if self.pos < len(self.text) and self.text[self.pos] == "^":
            negated = True
            self.pos += 1

        chars: set[int] = set()

        while self.pos < len(self.text) and self.text[self.pos] != "]":
            # Saltar espacios separadores
            if self.text[self.pos] in " \t":
                self.pos += 1
                continue

            # Leer un carácter (quoted o bare)
            ch_ord = self._read_class_element()

            # ¿Rango c1-c2?
            if self.pos < len(self.text) and self.text[self.pos] == "-":
                self.pos += 1  # saltar -
                while self.pos < len(self.text) and self.text[self.pos] in " \t":
                    self.pos += 1
                ch2_ord = self._read_class_element()
                if ch2_ord < ch_ord:
                    raise ParserError(
                        f"Rango inválido: {chr(ch_ord)!r}-{chr(ch2_ord)!r}",
                        pos=start, context=self.context,
                    )
                for c in range(ch_ord, ch2_ord + 1):
                    chars.add(c)
            else:
                chars.add(ch_ord)

        if self.pos >= len(self.text):
            raise ParserError("Clase de caracteres sin cerrar ']'",
                              pos=start, context=self.context)
        self.pos += 1  # saltar ]

        self.tokens.append(
            Token(TokType.CHAR_CLASS, value=frozenset(chars),
                  negated=negated, pos=start)
        )

    def _read_class_element(self) -> int:
        """Lee un solo carácter dentro de una clase (quoted o bare)."""
        if self.text[self.pos] == "'":
            return self._read_quoted_char_in_class()
        # Carácter bare (estilo [a-z])
        ch = self._read_escaped_char()
        return ord(ch)

    def _read_quoted_char_in_class(self) -> int:
        """Lee 'c' dentro de una clase de caracteres, retorna ord(c)."""
        start = self.pos
        self.pos += 1  # saltar '
        if self.pos >= len(self.text):
            raise ParserError("Literal sin cerrar en clase de caracteres",
                              pos=start, context=self.context)
        ch = self._read_escaped_char()
        if self.pos >= len(self.text) or self.text[self.pos] != "'":
            raise ParserError("Se esperaba comilla de cierre en clase",
                              pos=start, context=self.context)
        self.pos += 1  # saltar '
        return ord(ch)

    # ── Identificadores y palabras clave ─────────────────────────────────

    def _read_identifier(self) -> None:
        start = self.pos
        while (self.pos < len(self.text)
               and (self.text[self.pos].isalnum() or self.text[self.pos] == "_")):
            self.pos += 1
        name = self.text[start:self.pos]

        if name == "eof":
            self.tokens.append(Token(TokType.EOF_TOK, pos=start))
        elif name == "_":
            self.tokens.append(Token(TokType.WILDCARD, pos=start))
        else:
            self.tokens.append(Token(TokType.REF, value=name, pos=start))


# ══════════════════════════════════════════════════════════════════════════════
#  Inserción de operadores de concatenación explícitos
# ══════════════════════════════════════════════════════════════════════════════

# Tokens después de los cuales puede haber concatenación implícita
_CONCAT_AFTER = frozenset({
    TokType.CHAR, TokType.CHAR_CLASS, TokType.REF,
    TokType.WILDCARD, TokType.EOF_TOK,
    TokType.RPAREN,
    TokType.STAR, TokType.PLUS_OP, TokType.QUESTION,
})

# Tokens que pueden iniciar un operando (y por tanto recibir concatenación)
_CONCAT_BEFORE = frozenset({
    TokType.CHAR, TokType.CHAR_CLASS, TokType.REF,
    TokType.WILDCARD, TokType.EOF_TOK,
    TokType.LPAREN,
})


def insert_explicit_concat(tokens: list[Token]) -> list[Token]:
    """
    Recorre la lista de tokens e inserta un token CONCAT explícito
    entre cada par de tokens que admiten concatenación implícita.
    """
    if not tokens:
        return tokens

    result: list[Token] = [tokens[0]]
    for i in range(1, len(tokens)):
        prev = tokens[i - 1]
        curr = tokens[i]
        if prev.type in _CONCAT_AFTER and curr.type in _CONCAT_BEFORE:
            result.append(Token(TokType.CONCAT, pos=prev.pos))
        result.append(curr)
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  Parser de descenso recursivo  (tokens → AST)
# ══════════════════════════════════════════════════════════════════════════════

class RegexASTParser:
    """
    Gramática implementada (de menor a mayor precedencia):

        union     →  concat  ( '|'    concat  )*
        concat    →  diff    ( CONCAT diff    )*
        diff      →  postfix ( '#'    postfix )*
        postfix   →  atom    ( '*' | '+' | '?' )*
        atom      →  CHAR | CHAR_CLASS | REF | WILDCARD | EOF
                   |  '(' union ')'

    Precedencia resultante:  |  <  concat  <  #  <  * + ?  <  atoms
    (coincide con §4.5 de la especificación YALex)
    """

    def __init__(self, tokens: list[Token], *, context: str = ""):
        self.tokens = tokens
        self.pos = 0
        self.context = context

    def parse(self) -> ASTNode:
        if not self.tokens:
            raise ParserError("Expresión regular vacía", context=self.context)
        node = self._parse_union()
        if self.pos < len(self.tokens):
            tok = self.tokens[self.pos]
            raise ParserError(
                f"Token inesperado después de la expresión: {tok}",
                pos=tok.pos, context=self.context,
            )
        return node

    # ── Navegación ────────────────────────────────────────────────────────

    def _peek(self) -> Token | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _advance(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    # ── Reglas de la gramática ────────────────────────────────────────────

    def _parse_union(self) -> ASTNode:
        left = self._parse_concat()
        while self._peek() and self._peek().type == TokType.PIPE:
            self._advance()
            right = self._parse_concat()
            left = UnionNode(left, right)
        return left

    def _parse_concat(self) -> ASTNode:
        left = self._parse_diff()
        while self._peek() and self._peek().type == TokType.CONCAT:
            self._advance()
            right = self._parse_diff()
            left = ConcatNode(left, right)
        return left

    def _parse_diff(self) -> ASTNode:
        left = self._parse_postfix()
        while self._peek() and self._peek().type == TokType.HASH:
            self._advance()
            right = self._parse_postfix()
            left = DiffNode(left, right)
        return left

    def _parse_postfix(self) -> ASTNode:
        node = self._parse_atom()
        while self._peek() and self._peek().type in (
            TokType.STAR, TokType.PLUS_OP, TokType.QUESTION
        ):
            tok = self._advance()
            if tok.type == TokType.STAR:
                node = StarNode(node)
            elif tok.type == TokType.PLUS_OP:
                node = PlusNode(node)
            else:
                node = QuestionNode(node)
        return node

    def _parse_atom(self) -> ASTNode:
        tok = self._peek()
        if tok is None:
            raise ParserError("Fin inesperado de la expresión",
                              context=self.context)

        if tok.type == TokType.CHAR:
            self._advance()
            return LiteralNode(tok.value)

        if tok.type == TokType.CHAR_CLASS:
            self._advance()
            return CharClassNode(tok.value, tok.negated)

        if tok.type == TokType.REF:
            self._advance()
            return RefNode(tok.value)

        if tok.type == TokType.WILDCARD:
            self._advance()
            return WildcardNode()

        if tok.type == TokType.EOF_TOK:
            self._advance()
            return EofNode()

        if tok.type == TokType.LPAREN:
            self._advance()
            node = self._parse_union()
            closing = self._peek()
            if closing is None or closing.type != TokType.RPAREN:
                raise ParserError("Se esperaba ')' de cierre",
                                  pos=tok.pos, context=self.context)
            self._advance()
            return node

        raise ParserError(
            f"Token inesperado: {tok}",
            pos=tok.pos, context=self.context,
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Función de conveniencia: string → AST
# ══════════════════════════════════════════════════════════════════════════════

def parse_regex(text: str, *, context: str = "") -> ASTNode:
    """Tokeniza, inserta concatenaciones y construye el AST de una regex."""
    tokenizer = RegexTokenizer(text, context=context)
    tokens = tokenizer.tokenize()
    tokens = insert_explicit_concat(tokens)
    parser = RegexASTParser(tokens, context=context)
    return parser.parse()


# ══════════════════════════════════════════════════════════════════════════════
#  Estructuras de salida — AST Léxico  (arquitectura §6.3)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class DefinitionAST:
    """Una definición 'let' con su AST de regex."""
    name: str
    regex_ast: ASTNode
    raw_text: str


@dataclass
class RuleAST:
    """Una regla de token con su AST de patrón."""
    pattern_ast: ASTNode
    action: str
    raw_pattern: str
    line_number: int
    order: int


@dataclass
class LexerSpec:
    """
    Modelo intermedio completo — el AST Léxico.

    Almacena definiciones, reglas, acciones semánticas, prioridades y
    metadatos. Es la salida del Parser y la entrada del Resolvedor de
    Definiciones (siguiente módulo).
    """
    header: str | None
    definitions: list[DefinitionAST]
    rule_name: str
    rules: list[RuleAST]
    trailer: str | None

    def pretty_print(self) -> str:
        lines: list[str] = []
        lines.append("=" * 60)
        lines.append("  RESULTADO DEL PARSER (YALex Parser)")
        lines.append("=" * 60)

        # -- Header --
        lines.append("\n-- Header --")
        if self.header:
            for h in self.header.strip().splitlines():
                lines.append(f"  {h}")
        else:
            lines.append("  (vacío)")

        # -- Definiciones --
        lines.append("\n-- Definiciones --")
        if self.definitions:
            for d in self.definitions:
                lines.append(f"\n  let {d.name} = {d.raw_text}")
                lines.append(f"  AST:")
                for ast_line in ast_to_string(d.regex_ast, indent=2).splitlines():
                    lines.append(f"  {ast_line}")
        else:
            lines.append("  (ninguna)")

        # -- Tabla resumen de reglas (estilo Flex) --
        lines.append(f"\n-- Tabla de Reglas  (entrypoint: {self.rule_name}) --")
        if self.rules:
            # Calcular anchos de columnas
            col_pat = max(len(r.raw_pattern) for r in self.rules)
            col_pat = max(col_pat, 7)  # mínimo "Patrón"
            col_act = max(len(r.action) for r in self.rules)
            col_act = max(col_act, 6)  # mínimo "Acción"

            hdr = f"  {'#':>3}  {'Patrón':<{col_pat}}  {'Acción':<{col_act}}  {'Línea':>5}"
            sep = f"  {'-'*3}  {'-'*col_pat}  {'-'*col_act}  {'-'*5}"
            lines.append(hdr)
            lines.append(sep)
            for r in self.rules:
                lines.append(
                    f"  {r.order:>3}  {r.raw_pattern:<{col_pat}}"
                    f"  {r.action:<{col_act}}  {r.line_number:>5}"
                )
            lines.append(sep)
            lines.append(f"  Total: {len(self.rules)} reglas")
        else:
            lines.append("  (ninguna)")

        # ── Detalle AST por regla ──
        if self.rules:
            lines.append(f"\n-- AST por Regla --")
            for r in self.rules:
                lines.append(f"\n  [{r.order}] {r.raw_pattern}")
                for ast_line in ast_to_string(r.pattern_ast, indent=2).splitlines():
                    lines.append(f"  {ast_line}")

        # -- Trailer --
        lines.append("\n-- Trailer --")
        if self.trailer:
            for t in self.trailer.strip().splitlines():
                lines.append(f"  {t}")
        else:
            lines.append("  (vacío)")

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  YALex Parser  — orquestador de alto nivel
# ══════════════════════════════════════════════════════════════════════════════

class YALexParser:
    """
    Toma el ScannerResult y parsea cada regex de definiciones y reglas
    para construir el LexerSpec (AST Léxico).
    """

    def __init__(self, scanner_result: ScannerResult):
        self.scanner_result = scanner_result

    def parse(self) -> LexerSpec:
        definitions = self._parse_definitions()
        rules = self._parse_rules()

        return LexerSpec(
            header=self.scanner_result.header,
            definitions=definitions,
            rule_name=self.scanner_result.rule_name or "?",
            rules=rules,
            trailer=self.scanner_result.trailer,
        )

    def _parse_definitions(self) -> list[DefinitionAST]:
        result: list[DefinitionAST] = []
        for name, raw_regex in self.scanner_result.definitions:
            try:
                ast = parse_regex(raw_regex, context=f"let {name}")
            except ParserError as e:
                raise ParserError(
                    f"Error en definición '{name}': {e}",
                    context=f"let {name} = {raw_regex}",
                ) from e
            result.append(DefinitionAST(name=name, regex_ast=ast,
                                        raw_text=raw_regex))
        return result

    def _parse_rules(self) -> list[RuleAST]:
        result: list[RuleAST] = []
        for entry in self.scanner_result.rules:
            try:
                ast = parse_regex(entry.pattern,
                                  context=f"regla [{entry.order}]")
            except ParserError as e:
                raise ParserError(
                    f"Error en regla [{entry.order}] (línea {entry.line_number}): {e}",
                    line=entry.line_number,
                    context=entry.pattern,
                ) from e
            result.append(RuleAST(
                pattern_ast=ast,
                action=entry.action,
                raw_pattern=entry.pattern,
                line_number=entry.line_number,
                order=entry.order,
            ))
        return result


# ══════════════════════════════════════════════════════════════════════════════
#  Utilidades de visualización y conversión
# ══════════════════════════════════════════════════════════════════════════════

def ast_to_string(node: ASTNode, indent: int = 0) -> str:
    """Representación en texto del AST como árbol indentado."""
    pad = "    " * indent

    if isinstance(node, LiteralNode):
        ch = chr(node.value)
        display = repr(ch) if not ch.isprintable() or ch == " " else f"'{ch}'"
        return f"{pad}LITERAL {display}"

    if isinstance(node, CharClassNode):
        neg = "^" if node.negated else ""
        display = _format_char_set(node.chars)
        return f"{pad}CHAR_CLASS [{neg}{display}]"

    if isinstance(node, WildcardNode):
        return f"{pad}WILDCARD _"

    if isinstance(node, EofNode):
        return f"{pad}EOF"

    if isinstance(node, RefNode):
        return f"{pad}REF '{node.name}'"

    if isinstance(node, ConcatNode):
        return (f"{pad}CONCAT\n"
                f"{ast_to_string(node.left, indent + 1)}\n"
                f"{ast_to_string(node.right, indent + 1)}")

    if isinstance(node, UnionNode):
        return (f"{pad}UNION\n"
                f"{ast_to_string(node.left, indent + 1)}\n"
                f"{ast_to_string(node.right, indent + 1)}")

    if isinstance(node, StarNode):
        return (f"{pad}STAR\n"
                f"{ast_to_string(node.child, indent + 1)}")

    if isinstance(node, PlusNode):
        return (f"{pad}PLUS\n"
                f"{ast_to_string(node.child, indent + 1)}")

    if isinstance(node, QuestionNode):
        return (f"{pad}QUESTION\n"
                f"{ast_to_string(node.child, indent + 1)}")

    if isinstance(node, DiffNode):
        return (f"{pad}DIFF\n"
                f"{ast_to_string(node.left, indent + 1)}\n"
                f"{ast_to_string(node.right, indent + 1)}")

    return f"{pad}UNKNOWN({type(node).__name__})"


def ast_to_postfix(node: ASTNode) -> list[tuple]:
    """
    Convierte el AST a una lista de tuplas en notación postfix.
    Útil para que el siguiente módulo (Thompson) lo consuma directamente.

    Formato de tuplas:
      ('CHAR', ord)
      ('CHAR_CLASS', frozenset, negated)
      ('REF', name)
      ('WILDCARD',)
      ('EOF',)
      ('CONCAT',)
      ('UNION',)
      ('STAR',)
      ('PLUS',)
      ('QUESTION',)
      ('DIFF',)
    """
    if isinstance(node, LiteralNode):
        return [("CHAR", node.value)]
    if isinstance(node, CharClassNode):
        return [("CHAR_CLASS", node.chars, node.negated)]
    if isinstance(node, RefNode):
        return [("REF", node.name)]
    if isinstance(node, WildcardNode):
        return [("WILDCARD",)]
    if isinstance(node, EofNode):
        return [("EOF",)]
    if isinstance(node, ConcatNode):
        return ast_to_postfix(node.left) + ast_to_postfix(node.right) + [("CONCAT",)]
    if isinstance(node, UnionNode):
        return ast_to_postfix(node.left) + ast_to_postfix(node.right) + [("UNION",)]
    if isinstance(node, StarNode):
        return ast_to_postfix(node.child) + [("STAR",)]
    if isinstance(node, PlusNode):
        return ast_to_postfix(node.child) + [("PLUS",)]
    if isinstance(node, QuestionNode):
        return ast_to_postfix(node.child) + [("QUESTION",)]
    if isinstance(node, DiffNode):
        return ast_to_postfix(node.left) + ast_to_postfix(node.right) + [("DIFF",)]
    return []


# ── Formato legible de un conjunto de caracteres ─────────────────────────────

def _format_char_set(chars: frozenset) -> str:
    """Muestra un frozenset de ords como rangos legibles (ej. 'a'-'z')."""
    if not chars:
        return "∅"

    sorted_chars = sorted(chars)
    ranges: list[str] = []
    i = 0

    while i < len(sorted_chars):
        start = sorted_chars[i]
        end = start
        while i + 1 < len(sorted_chars) and sorted_chars[i + 1] == end + 1:
            end = sorted_chars[i + 1]
            i += 1

        if start == end:
            ranges.append(_display_char(start))
        elif end == start + 1:
            ranges.append(f"{_display_char(start)}{_display_char(end)}")
        else:
            ranges.append(f"{_display_char(start)}-{_display_char(end)}")
        i += 1

    return "".join(ranges)


def _display_char(code: int) -> str:
    """Representación legible de un carácter por su código."""
    ch = chr(code)
    if ch == " ":
        return "' '"
    if ch == "\t":
        return "\\t"
    if ch == "\n":
        return "\\n"
    if ch == "\r":
        return "\\r"
    if ch.isprintable():
        return ch
    return f"\\x{code:02x}"
