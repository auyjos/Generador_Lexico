"""
main.py — Punto de entrada del Generador de Analizadores Léxicos.

Uso:
    python src/main.py <archivo.yal>
"""

import os
import sys

# Agregar el directorio raíz del proyecto al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.lexer.codegen import CodeGenError, generate_lexer
from src.lexer.dfa import DFAError, build_dfa, minimize_dfa
from src.lexer.nfa import NFAError, build_nfa
from src.lexer.regex_parser import ParserError, YALexParser
from src.lexer.resolver import DefinitionResolver, ResolverError
from src.lexer.scanner import Scanner, ScannerError
from src.utils.visualizer import render_resolved_spec, render_automata


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

        # ── Módulo 4: Constructor de NFA (Thompson) ──
        print("\n>>> Construyendo NFA (Thompson's construction)...")
        nfa = build_nfa(resolved_spec)
        print(nfa.pretty_print())

        # ── Módulo 5: Constructor de DFA (construcción de subconjuntos) ──
        print("\n>>> Construyendo DFA (subset construction)...")
        dfa = build_dfa(nfa)
        print(dfa.pretty_print(title="DFA (sin minimizar)"))

        # ── Módulo 6: Minimización de Hopcroft ──
        print("\n>>> Minimizando DFA (algoritmo de Hopcroft)...")
        min_dfa = minimize_dfa(dfa)
        print(min_dfa.pretty_print(title="DFA Minimizado (Hopcroft)"))

        print(f"\n>>> Pipeline completo:")
        print(f"    NFA : {len(nfa.states)} estados")
        print(f"    DFA : {len(dfa.states)} estados")
        print(f"    DFA minimizado: {len(min_dfa.states)} estados\n")
        # ── Visualización: imágenes de autómatas ──
        print("\n>>> Generando imágenes de autómatas...")
        auto_paths = render_automata(nfa, dfa, min_dfa, output_dir="output")
        print(f">>> NFA guardado en:          {auto_paths['nfa']}")
        print(f">>> DFA guardado en:          {auto_paths['dfa']}")
        print(f">>> DFA minimizado guardado en: {auto_paths['min_dfa']}")

        # ── Módulo 8: Generador de Código ──
        lexer_out = os.path.join("output", "Lexer.java")
        print(f"\n>>> Generando lexer en: {lexer_out}")
        generate_lexer(min_dfa, resolved_spec, output_path=lexer_out)
        print(f">>> Lexer generado exitosamente.\n")

    except ScannerError as e:
        print(f"\n[ERROR del Procesador] {e}", file=sys.stderr)
        sys.exit(1)
    except ParserError as e:
        print(f"\n[ERROR del Parser] {e}", file=sys.stderr)
        sys.exit(1)
    except ResolverError as e:
        print(f"\n[ERROR del Resolvedor] {e}", file=sys.stderr)
        sys.exit(1)
    except NFAError as e:
        print(f"\n[ERROR del NFA] {e}", file=sys.stderr)
        sys.exit(1)
    except DFAError as e:
        print(f"\n[ERROR del DFA] {e}", file=sys.stderr)
        sys.exit(1)
    except CodeGenError as e:
        print(f"\n[ERROR del Generador] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
