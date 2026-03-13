"""
Procesador (Scanner) — Módulo 1 del Generador de Analizadores Léxicos.

Responsabilidades:
  - Lectura del archivo .yal / .yalex
  - Manejo de encoding (UTF-8)
  - Eliminación de comentarios (* … *)
  - Separación del contenido en secciones: header, definitions, rules, trailer
  - Reporte de errores de lectura y estructura

Entrada:  ruta a un archivo .yal
Salida:   diccionario con las secciones limpias del archivo
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

# ──────────────────────────────────────────────────────────────────────────────
# Excepciones propias del Procesador
# ──────────────────────────────────────────────────────────────────────────────

class ScannerError(Exception):
    """Error genérico del Procesador."""

    def __init__(self, message: str, line: int | None = None):
        self.line = line
        prefix = f"[línea {line}] " if line is not None else ""
        super().__init__(f"{prefix}{message}")


# ──────────────────────────────────────────────────────────────────────────────
# Estructuras de datos de salida
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class RuleEntry:
    """Una regla individual dentro de la sección rule."""
    pattern: str          # Expresión regular (texto crudo)
    action: str           # Código de la acción semántica
    line_number: int      # Línea de origen en el archivo .yal
    order: int            # Orden de aparición (para precedencia)


@dataclass
class ScannerResult:
    """Resultado completo del Procesador."""
    header: str | None = None
    definitions: list[tuple[str, str]] = field(default_factory=list)   # [(nombre, regexp), ...]
    rule_name: str | None = None                                       # nombre del entrypoint
    rules: list[RuleEntry] = field(default_factory=list)
    trailer: str | None = None

    def pretty_print(self) -> str:
        """Devuelve una representación legible del resultado."""
        lines: list[str] = []
        lines.append("=" * 60)
        lines.append("  RESULTADO DEL PROCESADOR (Scanner)")
        lines.append("=" * 60)

        # Header
        lines.append("\n-- Header --")
        if self.header:
            for h_line in self.header.strip().splitlines():
                lines.append(f"  {h_line}")
        else:
            lines.append("  (vacío)")

        # Definitions
        lines.append("\n-- Definitions --")
        if self.definitions:
            for name, regex in self.definitions:
                lines.append(f"  let {name} = {regex}")
        else:
            lines.append("  (ninguna)")

        # Rules
        lines.append(f"\n-- Rules  (entrypoint: {self.rule_name or '?'}) --")
        if self.rules:
            for r in self.rules:
                lines.append(f"  [{r.order}] línea {r.line_number}:  {r.pattern}  {{ {r.action} }}")
        else:
            lines.append("  (ninguna)")

        # Trailer
        lines.append("\n-- Trailer --")
        if self.trailer:
            for t_line in self.trailer.strip().splitlines():
                lines.append(f"  {t_line}")
        else:
            lines.append("  (vacío)")

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Procesador principal
# ──────────────────────────────────────────────────────────────────────────────

class Scanner:
    """
    Lee un archivo .yal / .yalex, elimina comentarios, y separa su
    contenido en secciones listas para el parser de especificación.
    """

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.raw_text: str = ""
        self.clean_text: str = ""
        self.result = ScannerResult()

    # ── API pública ──────────────────────────────────────────────────────

    def process(self) -> ScannerResult:
        """Ejecuta todas las etapas del procesador y devuelve el resultado."""
        self._read_file()
        self._strip_comments()
        self._extract_sections()
        return self.result

    # ── Etapa 1: Lectura del archivo ─────────────────────────────────────

    def _read_file(self) -> None:
        if not os.path.isfile(self.filepath):
            raise ScannerError(f"El archivo no existe: {self.filepath}")

        ext = os.path.splitext(self.filepath)[1].lower()
        if ext not in (".yal", ".yalex"):
            raise ScannerError(
                f"Extensión no soportada '{ext}'. Se espera .yal o .yalex"
            )

        try:
            with open(self.filepath, encoding="utf-8") as f:
                self.raw_text = f.read()
        except UnicodeDecodeError as exc:
            raise ScannerError(
                f"Error de encoding al leer el archivo: {exc}"
            ) from exc

        if not self.raw_text.strip():
            raise ScannerError("El archivo está vacío.")

    # ── Etapa 2: Eliminación de comentarios (* … *) ─────────────────────

    def _strip_comments(self) -> None:
        """
        Elimina comentarios delimitados por (* y *).
        Soporta comentarios anidados contando profundidad.
        Preserva los saltos de línea para mantener números de línea correctos.
        Respeta:
          - cadenas entre comillas simples y dobles
          - bloques { … } (header, acciones, trailer): su contenido se
            preserva íntegro, igual que Flex preserva código C en acciones.
        """
        result: list[str] = []
        i = 0
        depth = 0          # profundidad de comentarios (* … *)
        text = self.raw_text
        length = len(text)

        while i < length:
            # ── Fuera de comentario: respetar bloques { … } ──
            # Todo lo que está dentro de llaves es código del usuario
            # (header, acciones semánticas, trailer) y se copia tal cual.
            if depth == 0 and text[i] == "{":
                brace_depth = 1
                result.append(text[i])
                i += 1
                while i < length and brace_depth > 0:
                    if text[i] == "{":
                        brace_depth += 1
                    elif text[i] == "}":
                        brace_depth -= 1
                    result.append(text[i])
                    i += 1
                continue

            # ── Fuera de comentario: respetar comillas ──
            if depth == 0 and text[i] in ("'", '"'):
                quote = text[i]
                result.append(text[i])
                i += 1
                while i < length and text[i] != quote:
                    if text[i] == "\\" and i + 1 < length:
                        result.append(text[i])
                        i += 1
                    result.append(text[i])
                    i += 1
                if i < length:
                    result.append(text[i])  # comilla de cierre
                    i += 1
                continue

            # ¿Inicio de comentario?
            if i + 1 < length and text[i] == "(" and text[i + 1] == "*":
                depth += 1
                i += 2
                continue

            # ¿Fin de comentario?
            if i + 1 < length and text[i] == "*" and text[i + 1] == ")":
                if depth == 0:
                    raise ScannerError(
                        "Cierre de comentario '*)'  sin apertura correspondiente.",
                        line=text[:i].count("\n") + 1,
                    )
                depth -= 1
                i += 2
                continue

            if depth > 0:
                # Dentro de un comentario: conservar salto de línea
                result.append("\n" if text[i] == "\n" else " ")
            else:
                result.append(text[i])

            i += 1

        if depth > 0:
            raise ScannerError("Comentario '(*' sin cierre correspondiente '*)'.")

        self.clean_text = "".join(result)

    # ── Etapa 3: Separación en secciones ──────────────────────────────────

    def _extract_sections(self) -> None:
        """
        Separa el texto limpio en secciones según la estructura YALex:
          { header }
          let ident = regexp  ...
          rule entrypoint =  regexp { action } | ...
          { trailer }
        """
        text = self.clean_text
        pos = 0
        length = len(text)

        # ── 3a. Header opcional: primer bloque { … } antes de 'let' o 'rule' ─
        pos = self._skip_whitespace(text, pos)
        if pos < length and text[pos] == "{":
            header_end = self._find_matching_brace(text, pos)
            self.result.header = text[pos + 1 : header_end].strip()
            pos = header_end + 1

        # ── 3b. Definitions: líneas "let ident = regexp" ──────────────────
        pos = self._skip_whitespace(text, pos)
        while pos < length:
            match = re.match(r"let\s+", text[pos:])
            if not match:
                break
            pos += match.end()
            pos, name, regex = self._parse_definition(text, pos)
            self.result.definitions.append((name, regex))
            pos = self._skip_whitespace(text, pos)

        # ── 3c. Rule: "rule <name> =" seguido de patrones ────────────────
        pos = self._skip_whitespace(text, pos)
        rule_match = re.match(r"rule\s+(\w+)\s*(\[[^\]]*\]\s*)?=", text[pos:])
        if not rule_match:
            raise ScannerError(
                "No se encontró la sección 'rule'. "
                "Se espera: rule <nombre> =",
                line=text[:pos].count("\n") + 1,
            )
        self.result.rule_name = rule_match.group(1)
        pos += rule_match.end()

        pos = self._skip_whitespace(text, pos)
        order = 0
        while pos < length:
            # Consumir '|' separador opcional (puede estar al inicio)
            if text[pos] == "|":
                pos += 1
                pos = self._skip_whitespace(text, pos)

            # ¿Es inicio de trailer { … } sin patrón previo?
            if pos < length and text[pos] == "{":
                # Si es una referencia a definición {identificador}, no es trailer
                ref_match = re.match(r'\{\w+\}', text[pos:])
                if not ref_match and self._looks_like_trailer(text, pos):
                    break

            if pos >= length:
                break

            # Leer patrón
            line_number = text[:pos].count("\n") + 1
            pos, pattern = self._read_rule_pattern(text, pos)
            pos = self._skip_whitespace(text, pos)

            # Leer acción { … }
            if pos >= length or text[pos] != "{":
                raise ScannerError(
                    f"Se esperaba '{{' para la acción del patrón: {pattern!r}",
                    line=text[:pos].count("\n") + 1,
                )
            action_end = self._find_matching_brace(text, pos)
            action = text[pos + 1 : action_end].strip()
            pos = action_end + 1

            self.result.rules.append(
                RuleEntry(
                    pattern=pattern.strip(),
                    action=action,
                    line_number=line_number,
                    order=order,
                )
            )
            order += 1
            pos = self._skip_whitespace(text, pos)

        # ── 3d. Trailer opcional: bloque { … } restante ──────────────────
        pos = self._skip_whitespace(text, pos)
        if pos < length and text[pos] == "{":
            trailer_end = self._find_matching_brace(text, pos)
            self.result.trailer = text[pos + 1 : trailer_end].strip()
            pos = trailer_end + 1

        # ── Validación mínima ─────────────────────────────────────────────
        if not self.result.rules:
            raise ScannerError("La sección 'rule' no contiene ninguna regla.")

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _skip_whitespace(text: str, pos: int) -> int:
        """Avanza pos saltando espacios, tabs y saltos de línea."""
        while pos < len(text) and text[pos] in " \t\r\n":
            pos += 1
        return pos

    @staticmethod
    def _find_matching_brace(text: str, pos: int) -> int:
        """
        Dado que text[pos] == '{', devuelve el índice del '}' que lo cierra.
        Soporta llaves anidadas y respeta cadenas entre comillas simples/dobles.
        """
        assert text[pos] == "{"
        depth = 0
        i = pos
        length = len(text)
        while i < length:
            ch = text[i]

            # Saltar cadenas entre comillas (simples o dobles)
            if ch in ("'", '"'):
                quote = ch
                i += 1
                while i < length and text[i] != quote:
                    if text[i] == "\\":
                        i += 1  # saltar carácter escapado
                    i += 1
                # avanzar pasando la comilla de cierre
                i += 1
                continue

            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
            i += 1

        raise ScannerError(
            "Llave '{' sin cierre correspondiente '}'.",
            line=text[:pos].count("\n") + 1,
        )

    @staticmethod
    def _parse_definition(text: str, pos: int) -> tuple[int, str, str]:
        """
        Parsea 'ident = regexp' a partir de pos.
        Retorna (new_pos, nombre, regexp).
        """
        # Leer nombre del identificador
        m = re.match(r"(\w+)\s*=\s*", text[pos:])
        if not m:
            raise ScannerError(
                "Definición mal formada. Se espera: let <nombre> = <regexp>",
                line=text[:pos].count("\n") + 1,
            )
        name = m.group(1)
        pos += m.end()

        # Leer la regexp hasta fin de línea lógico (nueva línea que NO esté
        # dentro de corchetes o paréntesis)
        regex_parts: list[str] = []
        depth_paren = 0
        depth_bracket = 0
        length = len(text)
        while pos < length:
            ch = text[pos]

            if ch == "(":
                depth_paren += 1
            elif ch == ")":
                depth_paren -= 1
            elif ch == "[":
                depth_bracket += 1
            elif ch == "]":
                depth_bracket -= 1

            # Cadenas con comillas: consumir completo
            if ch in ("'", '"'):
                quote = ch
                regex_parts.append(ch)
                pos += 1
                while pos < length and text[pos] != quote:
                    if text[pos] == "\\":
                        regex_parts.append(text[pos])
                        pos += 1
                    regex_parts.append(text[pos])
                    pos += 1
                if pos < length:
                    regex_parts.append(text[pos])  # comilla de cierre
                    pos += 1
                continue

            # Fin de línea fuera de agrupadores → fin de la definición
            if ch == "\n" and depth_paren <= 0 and depth_bracket <= 0:
                break

            regex_parts.append(ch)
            pos += 1

        regex = "".join(regex_parts).strip()
        if not regex:
            raise ScannerError(
                f"La definición '{name}' no tiene expresión regular.",
                line=text[:pos].count("\n") + 1,
            )
        return pos, name, regex

    def _read_rule_pattern(self, text: str, pos: int) -> tuple[int, str]:
        """
        Lee un patrón de regla hasta encontrar el inicio de su acción '{'.
        Respeta agrupadores, comillas y corchetes.
        Distingue {identificador} (referencia a definición) de { acción }.
        """
        parts: list[str] = []
        depth_paren = 0
        depth_bracket = 0
        length = len(text)

        while pos < length:
            ch = text[pos]

            # Inicio de acción (fuera de agrupadores)
            if ch == "{" and depth_paren == 0 and depth_bracket == 0:
                # Distinguir {ref} (referencia) de { action } (acción)
                m = re.match(r'\{(\w+)\}', text[pos:])
                if m:
                    # Es una referencia a definición → incluir en patrón
                    ref_text = m.group(0)
                    parts.append(ref_text)
                    pos += len(ref_text)
                    continue
                break

            if ch == "(":
                depth_paren += 1
            elif ch == ")":
                depth_paren -= 1
            elif ch == "[":
                depth_bracket += 1
            elif ch == "]":
                depth_bracket -= 1

            # Cadenas entre comillas
            if ch in ("'", '"'):
                quote = ch
                parts.append(ch)
                pos += 1
                while pos < length and text[pos] != quote:
                    if text[pos] == "\\":
                        parts.append(text[pos])
                        pos += 1
                    if pos < length:
                        parts.append(text[pos])
                        pos += 1
                if pos < length:
                    parts.append(text[pos])  # comilla de cierre
                    pos += 1
                continue

            parts.append(ch)
            pos += 1

        pattern = "".join(parts).strip()
        if not pattern:
            raise ScannerError(
                "Se encontró una acción sin patrón de expresión regular.",
                line=text[:pos].count("\n") + 1,
            )
        return pos, pattern

    def _looks_like_trailer(self, text: str, pos: int) -> bool:
        """
        Heurística: determina si el bloque { … } en pos es un trailer
        (código suelto) y no una acción de regla.
        Un trailer aparece cuando no quedan patrones por leer,
        es decir, el siguiente contenido significativo después de
        cerrar esta llave NO tiene un '|' ni otro patrón.
        """
        try:
            end = self._find_matching_brace(text, pos)
        except ScannerError:
            return False
        rest = text[end + 1 :].strip()
        # Si no queda nada después, es trailer.
        if not rest:
            return True
        # Si lo que sigue es otra llave abierta sin | antes, también trailer.
        if rest[0] == "{":
            return True
        return False
