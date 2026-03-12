"""
codegen.py — Módulo 8: Generador de Código

Responsabilidades:
  - Serializa la tabla de transiciones del DFA minimizado como dict de Python.
  - Genera el motor next_token() con política de maximal munch.
  - Integra las acciones semánticas de la especificación original.
  - Produce un archivo .py listo para ejecutar como analizador léxico.

Entrada:  DFA minimizado  +  ResolvedSpec
Salida:   archivo .py del analizador léxico generado
"""

from __future__ import annotations

import os
import textwrap
from datetime import datetime

from src.lexer.dfa import DFA
from src.lexer.resolver import ResolvedSpec


# ══════════════════════════════════════════════════════════════════════════════
#  Excepción
# ══════════════════════════════════════════════════════════════════════════════


class CodeGenError(Exception):
    """Error durante la generación de código."""


# ══════════════════════════════════════════════════════════════════════════════
#  Generador
# ══════════════════════════════════════════════════════════════════════════════


class LexerCodeGenerator:
    """
    Genera el código fuente del analizador léxico a partir del DFA minimizado.

    Uso:
        gen = LexerCodeGenerator(min_dfa, resolved_spec)
        code = gen.generate()
        gen.write("output/lexer.py")
    """

    def __init__(self, dfa: DFA, spec: ResolvedSpec) -> None:
        self._dfa = dfa
        self._spec = spec

    # ── API pública ───────────────────────────────────────────────────────────

    def generate(self) -> str:
        """Devuelve el código fuente del lexer como string."""
        parts: list[str] = []
        parts.append(self._section_banner())
        parts.append(self._section_header())
        parts.append(self._section_transition_table())
        parts.append(self._section_accept_states())
        parts.append(self._section_skip_tokens())
        parts.append(self._section_start_state())
        parts.append(self._section_token_class())
        parts.append(self._section_lexer_class())
        parts.append(self._section_trailer())
        parts.append(self._section_main())
        return "\n\n".join(parts)

    def write(self, output_path: str) -> str:
        """Genera el código y lo escribe en output_path. Devuelve la ruta."""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        code = self.generate()
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(code)
        return output_path

    # ── Secciones del archivo generado ───────────────────────────────────────

    def _section_banner(self) -> str:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        spec_name = getattr(self._spec, "source_file", "<spec>")
        return textwrap.dedent(f"""\
            # =============================================================
            #  LEXER GENERADO AUTOMÁTICAMENTE
            #  Generado por: Generador de Analizadores Léxicos
            #  Fecha       : {ts}
            #  Especificación: {spec_name}
            #
            #  NO EDITAR MANUALMENTE — regenerar desde la especificación .yal
            # =============================================================
        """)

    def _section_header(self) -> str:
        header = (self._spec.header or "").strip()
        if not header:
            return "# (sin header)"
        indented = textwrap.indent(header, "    ")
        return (
            "# --- Header ---\n"
            "try:\n"
            f"{indented}\n"
            "except (ImportError, ModuleNotFoundError):\n"
            "    pass  # modulo del header no disponible en este entorno"
        )

    def _section_transition_table(self) -> str:
        """
        Genera la tabla de transiciones del DFA como dict anidado:
            _TRANS: dict[int, dict[int, int]]
            _TRANS[estado][ord(char)] = estado_destino
        """
        lines: list[str] = []
        lines.append("# --- Tabla de transiciones del DFA minimizado ---")
        lines.append("# _TRANS[estado][ord(char)] = siguiente_estado")
        lines.append("_TRANS: dict[int, dict[int, int]] = {")

        for state in sorted(self._dfa.states, key=lambda s: s.state_id):
            if not state.transitions:
                lines.append(f"    {state.state_id}: {{}},")
                continue
            # Ordenar por símbolo para reproducibilidad
            items = sorted(state.transitions.items(), key=lambda x: x[0])
            inner = ", ".join(
                f"{sym}: {tgt.state_id}" for sym, tgt in items
            )
            lines.append(f"    {state.state_id}: {{{inner}}},")

        lines.append("}")
        return "\n".join(lines)

    def _section_accept_states(self) -> str:
        """
        Genera el dict de estados de aceptación:
            _ACCEPT[estado] = "nombre_del_token"
        """
        lines: list[str] = []
        lines.append("# --- Estados de aceptación: estado → token ---")
        lines.append("_ACCEPT: dict[int, str] = {")

        for state in sorted(self._dfa.accept_states, key=lambda s: s.state_id):
            token = _extract_token_name(state.token or "UNKNOWN")
            lines.append(f"    {state.state_id}: {token!r},")

        lines.append("}")
        return "\n".join(lines)

    def _section_skip_tokens(self) -> str:
        """
        Genera el set de tokens que deben silenciarse (skip).
        Un token se silencia si su acción no contiene 'return'.
        """
        skip: list[str] = []
        for state in self._dfa.accept_states:
            action = (state.token or "").strip()
            if action and "return" not in action.lower():
                skip.append(_extract_token_name(action))

        lines: list[str] = []
        lines.append("# --- Tokens silenciados (sin return en su acción) ---")
        if skip:
            items = ", ".join(repr(t) for t in sorted(set(skip)))
            lines.append(f"_SKIP: set[str] = {{{items}}}")
        else:
            lines.append("_SKIP: set[str] = set()")
        return "\n".join(lines)

    def _section_start_state(self) -> str:
        return f"# --- Estado inicial ---\n_START: int = {self._dfa.start.state_id}"

    def _section_token_class(self) -> str:
        return textwrap.dedent("""\
            # --- Clase Token ---

            class Token:
                \"\"\"Representa un token reconocido por el lexer.\"\"\"

                __slots__ = ("type", "value", "line", "column")

                def __init__(self, type_: str, value: str,
                             line: int = 0, column: int = 0) -> None:
                    self.type   = type_
                    self.value  = value
                    self.line   = line
                    self.column = column

                def __repr__(self) -> str:
                    return f"Token({self.type!r}, {self.value!r}, line={self.line})"
        """)

    def _section_lexer_class(self) -> str:
        return textwrap.dedent("""\
            # --- Motor del Lexer (maximal munch sobre DFA) ---

            class Lexer:
                \"\"\"
                Analizador léxico generado.

                Uso:
                    lexer = Lexer("x = 42 + y")
                    for tok in lexer.tokenize():
                        print(tok)
                \"\"\"

                def __init__(self, text: str) -> None:
                    self._text   = text
                    self._pos    = 0       # posición actual en el texto
                    self._line   = 1
                    self._col    = 1
                    self._errors: list[str] = []

                # ── Interfaz pública ──────────────────────────────────────────

                def tokenize(self) -> list[Token]:
                    \"\"\"Tokeniza todo el texto y devuelve la lista de tokens.\"\"\"
                    tokens: list[Token] = []
                    while self._pos < len(self._text):
                        tok = self._next_token()
                        if tok is not None:
                            tokens.append(tok)
                    if self._errors:
                        print("\\n[ERRORES LÉXICOS]")
                        for err in self._errors:
                            print(" ", err)
                    return tokens

                @property
                def errors(self) -> list[str]:
                    return list(self._errors)

                # ── Motor interno ─────────────────────────────────────────────

                def _next_token(self) -> Token | None:
                    \"\"\"
                    Reconoce el siguiente token usando maximal munch.

                    Algoritmo:
                      1. Partimos del estado inicial del DFA.
                      2. Consumimos caracteres mientras haya transición válida.
                      3. Cada vez que llegamos a un estado de aceptación,
                         guardamos (estado, posición) como 'último aceptante'.
                      4. Al quedarnos sin transición usamos el último aceptante.
                      5. Si nunca hubo aceptación → error léxico, avanzar 1 char.
                    \"\"\"
                    start_pos   = self._pos
                    start_line  = self._line
                    start_col   = self._col

                    state       = _START
                    last_accept_state: int | None = None
                    last_accept_pos  : int        = start_pos
                    last_accept_line : int        = start_line
                    last_accept_col  : int        = start_col

                    # Verificar si el estado inicial ya es aceptante
                    if state in _ACCEPT:
                        last_accept_state = state
                        last_accept_pos   = self._pos
                        last_accept_line  = self._line
                        last_accept_col   = self._col

                    while self._pos < len(self._text):
                        ch  = self._text[self._pos]
                        sym = ord(ch)

                        next_state = _TRANS.get(state, {}).get(sym)
                        if next_state is None:
                            break   # sin transición → usar último aceptante

                        state = next_state
                        self._pos += 1
                        if ch == "\\n":
                            self._line += 1
                            self._col = 1
                        else:
                            self._col += 1

                        if state in _ACCEPT:
                            last_accept_state = state
                            last_accept_pos   = self._pos
                            last_accept_line  = self._line
                            last_accept_col   = self._col

                    if last_accept_state is None:
                        # Error léxico: carácter no reconocido
                        bad_char = self._text[start_pos]
                        self._errors.append(
                            f"Linea {start_line}, col {start_col}: "
                            f"caracter no reconocido {bad_char!r}"
                        )
                        self._pos  = start_pos + 1
                        self._line = start_line
                        self._col  = start_col + 1
                        return None

                    # Retroceder al último punto de aceptación (maximal munch)
                    self._pos  = last_accept_pos
                    self._line = last_accept_line
                    self._col  = last_accept_col

                    lexeme     = self._text[start_pos:last_accept_pos]
                    token_name = _ACCEPT[last_accept_state]

                    # Silenciar tokens marcados como skip
                    if token_name in _SKIP:
                        return None

                    return Token(token_name, lexeme, start_line, start_col)
        """)

    def _section_trailer(self) -> str:
        trailer = (self._spec.trailer or "").strip()
        if not trailer:
            return "# (sin trailer)"
        return f"# --- Trailer ---\n{trailer}"

    def _section_main(self) -> str:
        return textwrap.dedent("""\
            # --- Punto de entrada ---

            if __name__ == "__main__":
                import sys as _sys

                if len(_sys.argv) < 2:
                    print("Uso: python lexer.py <archivo.txt>")
                    _sys.exit(1)

                _input_file = _sys.argv[1]
                try:
                    with open(_input_file, encoding="utf-8") as _f:
                        _source = _f.read()
                except FileNotFoundError:
                    print(f"[ERROR] Archivo no encontrado: {_input_file!r}")
                    _sys.exit(1)

                print(f">>> Analizando: {_input_file}\\n")
                _lexer  = Lexer(_source)
                _tokens = _lexer.tokenize()

                print(f"{'TOKEN':<20} {'LEXEMA':<20} {'LINEA':>5}  {'COL':>4}")
                print("-" * 55)
                for _tok in _tokens:
                    print(f"{_tok.type:<20} {_tok.value!r:<20} {_tok.line:>5}  {_tok.column:>4}")

                print(f"\\n>>> Total tokens: {len(_tokens)}")
                if _lexer.errors:
                    print(f">>> Errores lexicos: {len(_lexer.errors)}")
                    _sys.exit(1)
        """)


# ══════════════════════════════════════════════════════════════════════════════
#  Utilidades internas
# ══════════════════════════════════════════════════════════════════════════════


def _extract_token_name(action: str) -> str:
    """
    Extrae el nombre del token de una cadena de acción.

    Ejemplos:
        "return WHITESPACE"  →  "WHITESPACE"
        "return ID"          →  "ID"
        "return NUM"         →  "NUM"
        "skip"               →  "skip"
    """
    action = action.strip()
    lower = action.lower()
    if lower.startswith("return"):
        rest = action[6:].strip()
        # Tomar solo la primera palabra (por si hay expresión compleja)
        token = rest.split()[0] if rest.split() else action
        # Quitar punto y coma si lo hay
        return token.rstrip(";")
    return action


# ══════════════════════════════════════════════════════════════════════════════
#  Función de conveniencia
# ══════════════════════════════════════════════════════════════════════════════


def generate_lexer(
    dfa: DFA,
    spec: ResolvedSpec,
    output_path: str = "output/lexer.py",
) -> str:
    """
    Genera el analizador léxico y lo escribe en output_path.

    Parámetros:
        dfa         — DFA minimizado (salida de HopcroftMinimizer)
        spec        — especificación resuelta (salida de DefinitionResolver)
        output_path — ruta del archivo .py a generar

    Retorna:
        Ruta del archivo generado.
    """
    gen = LexerCodeGenerator(dfa, spec)
    return gen.write(output_path)
