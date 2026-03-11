"""
main.py — Punto de entrada del Generador de Analizadores Léxicos.

Uso:
    python src/main.py <archivo.yal>
"""

import os
import sys

# Agregar el directorio raíz del proyecto al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.lexer.regex_parser import ParserError, YALexParser
from src.lexer.resolver import DefinitionResolver, ResolverError
from src.lexer.scanner import Scanner, ScannerError
from src.utils.visualizer import render_resolved_spec


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python src/main.py <archivo.yal>")
        sys.exit(1)

    filepath = sys.argv[1]
    print(f"\n>>> Procesando archivo: {filepath}\n")

    try:
        # ── Módulo 1: Procesador (Scanner) ──
        scanner = Scanner(filepath)
        result = scanner.process()
        print(result.pretty_print())

        # ── Módulo 2: Parser de Especificación ──
        parser = YALexParser(result)
        lexer_spec = parser.parse()
        print(lexer_spec.pretty_print())

        # ── Módulo 3: Resolvedor de Definiciones y Validador Semántico ──
        resolver = DefinitionResolver(lexer_spec)
        resolved_spec = resolver.resolve()
        print(resolved_spec.pretty_print())

        # ── Visualización: imagen única del AST ──
        print("\n>>> Generando imagen del AST...")
        path = render_resolved_spec(resolved_spec, output_dir="output")
        print(f">>> Imagen guardada en: {path}\n")

    except ScannerError as e:
        print(f"\n[ERROR del Procesador] {e}", file=sys.stderr)
        sys.exit(1)
    except ParserError as e:
        print(f"\n[ERROR del Parser] {e}", file=sys.stderr)
        sys.exit(1)
    except ResolverError as e:
        print(f"\n[ERROR del Resolvedor] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
