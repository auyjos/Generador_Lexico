# Proyecto 1 — Generador de Analizadores Léxicos

**Curso:** Diseño de Compiladores 1  
**Universidad:** Universidad del Valle de Guatemala  
**Lenguaje:** Python 3.x

---

## Descripción

Implementación de un generador de analizadores léxicos que parte de una especificación de tokens (archivo `.yal`) y produce un analizador capaz de reconocer cadenas de entrada. El proceso sigue la cadena clásica de construcción de autómatas:

```
Expresión Regular  →  NFA  →  DFA  →  DFA Mínimo  →  Simulación
```

### Algoritmos implementados

| Etapa | Algoritmo |
|-------|-----------|
| RE → NFA | Construcción de Thompson |
| NFA → DFA | Construcción de subconjuntos |
| DFA → DFA mínimo | Algoritmo de Hopcroft |
| Simulación | Recorrido del DFA sobre cadena de entrada |

---

## Estructura del proyecto

```
Proyecto1/
├── src/
│   ├── main.py              # Punto de entrada
│   ├── lexer/
│   │   ├── scanner.py       # Lectura y parseo del archivo .yal
│   │   ├── regex_parser.py  # Parser de expresiones regulares (infix → postfix)
│   │   ├── thompson.py      # Construcción de Thompson (RE → NFA)
│   │   ├── subset.py        # Construcción de subconjuntos (NFA → DFA)
│   │   ├── hopcroft.py      # Minimización de DFA (Hopcroft)
│   │   └── simulator.py     # Simulación del DFA sobre entradas
│   └── utils/
│       └── visualizer.py    # Generación de grafos con Graphviz
├── tests/
│   ├── inputs/              # Archivos .yal de prueba
│   └── expected/            # Salidas esperadas para validación
├── output/                  # Imágenes generadas de los autómatas
├── requirements.txt
└── README.md
```

---

## Requisitos

- Python 3.10 o superior
- [Graphviz](https://graphviz.org/download/) instalado en el sistema y en el PATH

Instalar dependencias de Python:

```bash
pip install -r requirements.txt
```

---

## Uso

```bash
python src/main.py <archivo.yal> <cadena_de_entrada>
```

**Ejemplo:**

```bash
python src/main.py tests/inputs/ejemplo.yal "abc123"
```

### Salida esperada

- Resultado de la simulación (`ACCEPTED` / `REJECTED`)
- Imágenes de los autómatas generados en `output/`:
  - `nfa.png` — NFA resultante de Thompson
  - `dfa.png` — DFA resultante de la construcción de subconjuntos
  - `dfa_min.png` — DFA minimizado con Hopcroft

---

## Formato del archivo `.yal`

El archivo de especificación sigue la sintaxis de YALex:

```
(* Comentario *)
let digit = ['0'-'9']
let letter = ['a'-'z''A'-'Z']
let id = letter (letter | digit)*

rule tokens =
  | digit+       { INT }
  | id           { ID }
  | ' '          { skip }
  | '\n'         { newline }
```

---

## Ejemplos de expresiones regulares soportadas

| Notación | Significado |
|----------|-------------|
| `a\|b`   | Unión |
| `ab`     | Concatenación |
| `a*`     | Kleene star (0 o más) |
| `a+`     | Una o más repeticiones |
| `a?`     | Cero o una repetición |
| `[a-z]`  | Clase de caracteres |
| `(ab)`   | Agrupación |

---

## Autor

| Nombre | Carné |
|--------|-------|
|        |       |
