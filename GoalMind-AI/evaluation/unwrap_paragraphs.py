#!/usr/bin/env python3
"""Junta cada parrafo (y cada item de lista) en una sola linea.

Respeta tablas Markdown, cabeceras, bloques de codigo y entornos LaTeX
(table, tabular, figure, itemize, enumerate). Pensado para los ficheros
docs/tfg/capitulo5/5_4_assistant_evaluation.md y
docs/tfg/capitulo5/6_4_evaluacion_completa.tex.

Uso: python unwrap_paragraphs.py <fichero1> <fichero2> ...
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

LIST_RE = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")
TABLE_LINE = re.compile(r"^\s*\|")
HEADER = re.compile(r"^#+\s")
CODE_FENCE = re.compile(r"^```")
LATEX_BEGIN = re.compile(r"\\begin\{(\w+)\*?\}")
LATEX_END = re.compile(r"\\end\{(\w+)\*?\}")
LATEX_NONPROSE_CMDS = (
    "\\section", "\\subsection", "\\subsubsection", "\\paragraph",
    "\\chapter", "\\title", "\\author", "\\date",
    "\\caption", "\\label", "\\centering",
    "\\toprule", "\\midrule", "\\bottomrule", "\\cmidrule",
    "\\hline",
    "\\maketitle", "\\tableofcontents", "\\bibliography", "\\bibliographystyle",
    "\\newpage", "\\clearpage", "\\pagebreak", "\\noindent",
    "\\usepackage", "\\documentclass", "\\input", "\\include",
)
# Nota: \\item se gestiona aparte por el handler de items, no se trata
# como no-prosa generica.
LATEX_INPROSE_CMDS = (
    "\\emph", "\\textbf", "\\textit", "\\texttt", "\\textsl",
    "\\ref", "\\cite", "\\footnote", "\\url",
)

# Entornos en los que NO se debe juntar lineas (los reflows romperian la
# estructura visual de la tabla o del listado en el render LaTeX).
PROTECTED_ENVS = {"table", "tabular", "figure", "verbatim", "lstlisting",
                  "equation", "align", "minipage", "tikzpicture"}
ITEM_ENVS = {"itemize", "enumerate", "description"}


def is_latex_nonprose_line(stripped: str) -> bool:
    # Linea de comentario LaTeX: siempre se mantiene tal cual.
    if stripped.startswith("%"):
        return True
    if not stripped.startswith("\\"):
        return False
    if any(stripped.startswith(c) for c in LATEX_INPROSE_CMDS):
        # Comando que aparece dentro de la prosa: no rompe parrafo.
        return False
    return any(stripped.startswith(c) for c in LATEX_NONPROSE_CMDS)


def reflow(text: str, is_latex: bool) -> str:
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    in_code = False
    env_stack: list[str] = []

    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()

        # Markdown: bloque de codigo cercado por ```
        if not is_latex and CODE_FENCE.match(stripped):
            out.append(raw)
            i += 1
            in_code = not in_code
            continue
        if in_code:
            out.append(raw)
            i += 1
            continue

        # LaTeX: actualizar pila de entornos antes de decidir.
        if is_latex:
            for m in LATEX_BEGIN.finditer(raw):
                env_stack.append(m.group(1))
            for m in LATEX_END.finditer(raw):
                if env_stack and env_stack[-1] == m.group(1):
                    env_stack.pop()
            if any(e in PROTECTED_ENVS for e in env_stack):
                out.append(raw)
                i += 1
                continue
            # Si la linea es exactamente \begin{...} o \end{...} de un entorno
            # protegido la dejamos tal cual (ya está en out por el paso previo
            # cuando aún no estaba en pila o cuando acaba de salir).
            if stripped.startswith("\\begin{") or stripped.startswith("\\end{"):
                out.append(raw)
                i += 1
                continue

        if stripped == "":
            out.append("")
            i += 1
            continue

        # Cabecera markdown o comando LaTeX que no es prosa: linea suelta.
        if not is_latex and HEADER.match(stripped):
            out.append(raw)
            i += 1
            continue
        if is_latex and is_latex_nonprose_line(stripped):
            out.append(raw)
            i += 1
            continue

        # Fila de tabla markdown.
        if not is_latex and TABLE_LINE.match(stripped):
            out.append(raw)
            i += 1
            continue

        # Item de lista LaTeX (\item ...): junta con sus lineas de
        # continuacion hasta el siguiente \item o el \end{...} del entorno.
        if is_latex and stripped.startswith("\\item"):
            indent = raw[: len(raw) - len(raw.lstrip())]
            # Quitar el comando \item (que puede llevar [opcion]) del inicio.
            head = stripped  # comienza con "\item"
            parts = [head]
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                nxt_strip = nxt.strip()
                if nxt_strip == "":
                    break
                if nxt_strip.startswith("\\item"):
                    break
                if nxt_strip.startswith("\\end{"):
                    break
                parts.append(nxt_strip)
                j += 1
            out.append(f"{indent}{' '.join(parts)}")
            i = j
            continue

        # Item de lista markdown: junta el item con sus lineas de
        # continuacion (indentadas con al menos un espacio respecto al
        # marcador) en una sola linea.
        list_match = LIST_RE.match(raw) if not is_latex else None
        if list_match:
            indent, marker, content = list_match.groups()
            parts = [content.strip()]
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                nxt_strip = nxt.strip()
                if nxt_strip == "":
                    break
                if LIST_RE.match(nxt) and not nxt.startswith(indent + " "):
                    # Otro item de la lista al mismo nivel.
                    break
                if HEADER.match(nxt_strip) or TABLE_LINE.match(nxt_strip):
                    break
                # Continuacion: lineas indentadas o sin marcador propio.
                parts.append(nxt_strip)
                j += 1
            out.append(f"{indent}{marker} {' '.join(parts)}")
            i = j
            continue

        # Parrafo de prosa: junta hasta encontrar una linea en blanco u otro
        # bloque especial.
        parts = [stripped]
        j = i + 1
        while j < len(lines):
            nxt = lines[j]
            nxt_strip = nxt.strip()
            if nxt_strip == "":
                break
            if not is_latex and (HEADER.match(nxt_strip) or TABLE_LINE.match(nxt_strip)
                                  or LIST_RE.match(nxt) or CODE_FENCE.match(nxt_strip)):
                break
            if is_latex and (is_latex_nonprose_line(nxt_strip)
                              or nxt_strip.startswith("\\begin{")
                              or nxt_strip.startswith("\\end{")):
                break
            parts.append(nxt_strip)
            j += 1
        out.append(" ".join(parts))
        i = j

    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def main(argv):
    if len(argv) < 2:
        print("Uso: python unwrap_paragraphs.py <fichero1> <fichero2> ...", file=sys.stderr)
        return 2
    for path_s in argv[1:]:
        path = Path(path_s)
        text = path.read_text(encoding="utf-8")
        is_latex = path.suffix == ".tex"
        new_text = reflow(text, is_latex=is_latex)
        path.write_text(new_text, encoding="utf-8")
        print(f"  reflowed {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
