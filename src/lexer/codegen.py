"""
codegen.py — Módulo 8: Generador de Código

Responsabilidades:
  - Serializa la tabla de transiciones del DFA minimizado como Map de Java.
  - Genera el motor nextToken() con política de maximal munch.
  - Integra las acciones semánticas de la especificación original.
  - Produce un archivo .java listo para compilar como analizador léxico.

Entrada:  DFA minimizado  +  ResolvedSpec
Salida:   archivo .java del analizador léxico generado
"""

from __future__ import annotations

import os
import re
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
    Genera el código fuente Java del analizador léxico a partir del DFA minimizado.

    Uso:
        gen = LexerCodeGenerator(min_dfa, resolved_spec)
        code = gen.generate()
        gen.write("output/Lexer.java")
    """

    def __init__(self, dfa: DFA, spec: ResolvedSpec) -> None:
        self._dfa  = dfa
        self._spec = spec

    # ── API pública ───────────────────────────────────────────────────────────

    def generate(self) -> str:
        """Devuelve el código fuente Java del lexer como string."""
        parts: list[str] = [
            self._section_banner(),
            self._section_imports(),
            "public final class Lexer {",
            "",
            self._indent(self._section_token_enum()),
            "",
            self._indent(self._section_token_class()),
            "",
            self._indent(self._section_transition_table()),
            "",
            self._indent(self._section_accept_states()),
            "",
            self._indent(self._section_skip_tokens()),
            "",
            self._indent(self._section_start_state()),
            "",
            self._indent(self._section_lexer_fields()),
            "",
            self._indent(self._section_constructor()),
            "",
            self._indent(self._section_tokenize()),
            "",
            self._indent(self._section_next_token()),
            "",
            self._indent(self._section_helpers()),
            "",
            self._indent(self._section_main()),
            "}",
        ]
        return "\n".join(parts)

    def write(self, output_path: str) -> str:
        """Genera el código y lo escribe en output_path. Devuelve la ruta."""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        code = self.generate()
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(code)
        return output_path

    # ── Helpers internos ─────────────────────────────────────────────────────

    @staticmethod
    def _indent(text: str, level: int = 1) -> str:
        prefix = "    " * level
        return textwrap.indent(text, prefix)

    # ── Secciones del archivo generado ───────────────────────────────────────

    def _section_banner(self) -> str:
        ts        = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        spec_name = getattr(self._spec, "source_file", "<spec>")
        return textwrap.dedent(f"""\
            // =============================================================
            //  LEXER GENERADO AUTOMÁTICAMENTE
            //  Generado por: Generador de Analizadores Léxicos
            //  Fecha       : {ts}
            //  Especificación: {spec_name}
            //
            //  NO EDITAR MANUALMENTE — regenerar desde la especificación .yal
            // =============================================================
        """)

    def _section_imports(self) -> str:
        header = (self._spec.header or "").strip()
        lines: list[str] = [
            "import java.io.IOException;",
            "import java.nio.file.Files;",
            "import java.nio.file.Paths;",
            "import java.util.ArrayList;",
            "import java.util.HashMap;",
            "import java.util.HashSet;",
            "import java.util.List;",
            "import java.util.Map;",
            "import java.util.Set;",
        ]
        if header:
            lines.append("")
            lines.append(f"// --- Header ---")
            for h in header.splitlines():
                lines.append(f"// {h}")
        lines.append("")
        return "\n".join(lines)

    def _section_token_enum(self) -> str:
        tokens: list[str] = []
        seen: set[str] = set()
        for state in self._dfa.accept_states:
            name = _extract_token_name(state.token or "UNKNOWN")
            if name not in seen:
                seen.add(name)
                tokens.append(name)
        tokens_str = ",\n        ".join(tokens + ["EOF", "ERROR"])
        return textwrap.dedent(f"""\
            /** Tipos de tokens reconocidos por el lexer. */
            public enum TokenType {{
                {tokens_str}
            }}
        """)

    def _section_token_class(self) -> str:
        return textwrap.dedent("""\
            /** Representa un token reconocido por el lexer. */
            public static final class Token {

                public final TokenType type;
                public final String    value;
                public final int       line;
                public final int       column;

                public Token(
                        final TokenType type,
                        final String    value,
                        final int       line,
                        final int       column) {
                    this.type   = type;
                    this.value  = value;
                    this.line   = line;
                    this.column = column;
                }

                @Override
                public String toString() {
                    return String.format("Token(%-15s %-20s line=%d col=%d)",
                            type, "\\\"" + value + "\\\"", line, column);
                }
            }
        """)

    def _section_transition_table(self) -> str:
        """
        Genera la tabla de transiciones como:
            Map<Integer, Map<Integer, Integer>> TRANS
            TRANS.get(estado).get(ord_char) = siguiente_estado
        """
        lines: list[str] = [
            "// --- Tabla de transiciones del DFA minimizado ---",
            "// TRANS.get(estado).get(ord(char)) = siguiente_estado",
            "private static final Map<Integer, Map<Integer, Integer>> TRANS;",
            "static {",
            "    TRANS = new HashMap<>();",
            "    Map<Integer, Integer> row;",
        ]

        for state in sorted(self._dfa.states, key=lambda s: s.state_id):
            if not state.transitions:
                lines.append(f"    TRANS.put({state.state_id}, new HashMap<>());")
                continue
            lines.append(f"    row = new HashMap<>();")
            for sym, tgt in sorted(state.transitions.items()):
                lines.append(f"    row.put({sym}, {tgt.state_id});")
            lines.append(f"    TRANS.put({state.state_id}, row);")

        lines.append("}")
        return "\n".join(lines)

    def _section_accept_states(self) -> str:
        """
        Genera el mapa de estados de aceptación:
            Map<Integer, TokenType> ACCEPT
        """
        lines: list[str] = [
            "// --- Estados de aceptación: estado → TokenType ---",
            "private static final Map<Integer, TokenType> ACCEPT;",
            "static {",
            "    ACCEPT = new HashMap<>();",
        ]
        for state in sorted(self._dfa.accept_states, key=lambda s: s.state_id):
            token = _extract_token_name(state.token or "UNKNOWN")
            lines.append(f"    ACCEPT.put({state.state_id}, TokenType.{token});")
        lines.append("}")
        return "\n".join(lines)

    def _section_skip_tokens(self) -> str:
        """
        Genera el set de tokens silenciados (sin 'return' en su acción).
        """
        skip: list[str] = []
        for state in self._dfa.accept_states:
            action = (state.token or "").strip()
            if action and "return" not in action.lower():
                skip.append(_extract_token_name(action))

        lines: list[str] = [
            "// --- Tokens silenciados (sin return en su acción) ---",
            "private static final Set<TokenType> SKIP;",
            "static {",
            "    SKIP = new HashSet<>();",
        ]
        for t in sorted(set(skip)):
            lines.append(f"    SKIP.add(TokenType.{t});")
        lines.append("}")
        return "\n".join(lines)

    def _section_start_state(self) -> str:
        sid = self._dfa.start.state_id
        return f"// --- Estado inicial ---\nprivate static final int START = {sid};"

    def _section_lexer_fields(self) -> str:
        return textwrap.dedent("""\
            // --- Campos del lexer ---
            private final String       source;
            private       int          pos    = 0;
            private       int          line   = 1;
            private       int          col    = 1;
            private final List<String> errors = new ArrayList<>();
        """)

    def _section_constructor(self) -> str:
        return textwrap.dedent("""\
            public Lexer(final String source) {
                this.source = source;
            }
        """)

    def _section_tokenize(self) -> str:
        return textwrap.dedent("""\
            /** Tokeniza todo el texto y devuelve la lista de tokens. */
            public List<Token> tokenize() {
                final List<Token> tokens = new ArrayList<>();
                while (pos < source.length()) {
                    final Token tok = nextToken();
                    if (tok != null) {
                        tokens.add(tok);
                    }
                }
                if (!errors.isEmpty()) {
                    System.err.println("\\n[ERRORES LÉXICOS]");
                    for (final String err : errors) {
                        System.err.println("  " + err);
                    }
                }
                return tokens;
            }

            /** Devuelve una lista inmutable de errores léxicos encontrados. */
            public List<String> getErrors() {
                return List.copyOf(errors);
            }
        """)

    def _section_next_token(self) -> str:
        return textwrap.dedent("""\
            /**
             * Reconoce el siguiente token usando maximal munch sobre el DFA.
             *
             * Algoritmo:
             *   1. Partir del estado inicial del DFA.
             *   2. Consumir caracteres mientras haya transición válida.
             *   3. Cada vez que se llega a un estado de aceptación,
             *      guardar (estado, posición) como último aceptante.
             *   4. Al quedarse sin transición, usar el último aceptante.
             *   5. Si nunca hubo aceptación → error léxico, avanzar 1 char.
             */
            private Token nextToken() {
                final int startPos  = pos;
                final int startLine = line;
                final int startCol  = col;

                int  state            = START;
                int  lastAcceptState  = -1;
                int  lastAcceptPos    = startPos;
                int  lastAcceptLine   = startLine;
                int  lastAcceptCol    = startCol;

                // Verificar si el estado inicial ya es aceptante
                if (ACCEPT.containsKey(state)) {
                    lastAcceptState = state;
                    lastAcceptPos   = pos;
                    lastAcceptLine  = line;
                    lastAcceptCol   = col;
                }

                while (pos < source.length()) {
                    final char ch  = source.charAt(pos);
                    final int  sym = (int) ch;

                    final Map<Integer, Integer> row = TRANS.get(state);
                    if (row == null || !row.containsKey(sym)) {
                        break; // sin transición → usar último aceptante
                    }

                    state = row.get(sym);
                    pos++;
                    if (ch == '\\n') {
                        line++;
                        col = 1;
                    } else {
                        col++;
                    }

                    if (ACCEPT.containsKey(state)) {
                        lastAcceptState = state;
                        lastAcceptPos   = pos;
                        lastAcceptLine  = line;
                        lastAcceptCol   = col;
                    }
                }

                if (lastAcceptState == -1) {
                    // Error léxico: carácter no reconocido
                    final char bad = source.charAt(startPos);
                    errors.add(String.format(
                            "Linea %d, col %d: caracter no reconocido '%c'",
                            startLine, startCol, bad));
                    pos  = startPos + 1;
                    line = startLine;
                    col  = startCol + 1;
                    return null;
                }

                // Retroceder al último punto de aceptación (maximal munch)
                pos  = lastAcceptPos;
                line = lastAcceptLine;
                col  = lastAcceptCol;

                final String    lexeme    = source.substring(startPos, lastAcceptPos);
                final TokenType tokenType = ACCEPT.get(lastAcceptState);

                // Silenciar tokens marcados como skip
                if (SKIP.contains(tokenType)) {
                    return null;
                }

                return new Token(tokenType, lexeme, startLine, startCol);
            }
        """)

    def _section_helpers(self) -> str:
        trailer = (self._spec.trailer or "").strip()
        comment = ""
        if trailer:
            comment = f"// --- Trailer ---\n// {trailer}\n"
        return comment

    def _section_main(self) -> str:
        return textwrap.dedent("""\
            // --- Punto de entrada ---
            public static void main(final String[] args) throws IOException {
                if (args.length < 1) {
                    System.err.println("Uso: java Lexer <archivo.txt>");
                    System.exit(1);
                }

                final String source = Files.readString(Paths.get(args[0]));
                System.out.printf(">>> Analizando: %s%n%n", args[0]);

                final Lexer       lexer  = new Lexer(source);
                final List<Token> tokens = lexer.tokenize();

                System.out.printf("%-20s %-25s %5s  %4s%n",
                        "TOKEN", "LEXEMA", "LINEA", "COL");
                System.out.println("-".repeat(60));
                for (final Token tok : tokens) {
                    System.out.printf("%-20s %-25s %5d  %4d%n",
                            tok.type, "\\"" + tok.value + "\\"",
                            tok.line, tok.column);
                }

                System.out.printf("%n>>> Total tokens: %d%n", tokens.size());
                if (!lexer.getErrors().isEmpty()) {
                    System.out.printf(">>> Errores lexicos: %d%n",
                            lexer.getErrors().size());
                    System.exit(1);
                }
            }
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
        "(* skip whitespace *)"  →  "__SKIP__"
    """
    # Eliminar comentarios OCaml (* ... *)
    action = re.sub(r'\(\*.*?\*\)', '', action).strip()

    if not action:
        return "__SKIP__"

    lower = action.lower()
    if lower.startswith("return"):
        rest  = action[6:].strip()
        token = rest.split()[0] if rest.split() else action
        return token.rstrip(";")

    # Acción sin 'return' → sanitizar a identificador Java válido
    sanitized = re.sub(r'[^A-Za-z0-9_]', '_', action)
    sanitized = re.sub(r'_+', '_', sanitized).strip('_')
    return sanitized if sanitized else "__SKIP__"


# ══════════════════════════════════════════════════════════════════════════════
#  Función de conveniencia
# ══════════════════════════════════════════════════════════════════════════════


def generate_lexer(
    dfa: DFA,
    spec: ResolvedSpec,
    output_path: str = "output/Lexer.java",
) -> str:
    """
    Genera el analizador léxico Java y lo escribe en output_path.

    Parámetros:
        dfa         — DFA minimizado (salida de HopcroftMinimizer)
        spec        — especificación resuelta (salida de DefinitionResolver)
        output_path — ruta del archivo .java a generar

    Retorna:
        Ruta del archivo generado.
    """
    gen = LexerCodeGenerator(dfa, spec)
    return gen.write(output_path)
