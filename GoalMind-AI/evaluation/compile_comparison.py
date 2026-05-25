#!/usr/bin/env python3
"""Compila las tablas comparativas entre los tres proveedores.

Lee los tres ficheros JSON de salida del runner y emite tablas en Markdown y en
LaTeX listas para incrustar en la seccion 6.4 de la memoria.

Uso:
    python evaluation/compile_comparison.py <openai.json> <gemini.json> <groq.json>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROVIDER_LABEL = {
    "openai": "OpenAI (gpt-5-nano)",
    "gemini": "Gemini (gemini-3-flash-preview)",
    "groq": "Groq (llama-3.1-8b-instant)",
}

# Orden canonico de las categorias del supervisor.
CATEGORIES = [
    "action",
    "research",
    "deep_research",
    "document",
    "weekly_summary",
    "weekly_plan",
    "progress",
    "recommendations",
    "unknown",
]


def load_run(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value * 100:.2f}\\,\\%".replace(".", ",")


def fmt_pct_md(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value * 100:.2f} %".replace(".", ",")


def fmt_sec(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value:.2f}".replace(".", ",")


def latex_escape(text: str) -> str:
    return text.replace("_", r"\_")


# Etiquetas cortas legibles para los encabezados de la matriz de confusion en LaTeX.
SHORT_LABELS = {
    "action": "act",
    "research": "res",
    "deep_research": "d.res",
    "document": "doc",
    "weekly_summary": "w.sum",
    "weekly_plan": "w.pl",
    "progress": "prog",
    "recommendations": "rec",
    "unknown": "unk",
}


def build_aggregate_table(runs: dict[str, dict]) -> tuple[str, str]:
    """Tabla 6.5 reescrita: metricas agregadas por proveedor.

    Devuelve (md, latex).
    """
    md = ["| Métrica | OpenAI | Gemini | Groq |", "| --- | ---: | ---: | ---: |"]
    rows = [
        ("Precisión global de intención", lambda a: fmt_pct_md(a["intent_accuracy"])),
        ("Tasa de éxito de planes CRUD (n = 20)", lambda a: fmt_pct_md(a["action_match_rate"])),
        ("Aclaraciones solicitadas", lambda a: str(a["asked_clarifications"])),
        ("  de las cuales pertinentes", lambda a: str(a["pertinent_clarifications"])),
        ("  de las cuales fricción innecesaria", lambda a: str(a["unnecessary_clarifications"])),
        ("Silencios sobre ambigüedad", lambda a: str(a["silent_on_ambiguous"])),
        ("Errores de ejecución", lambda a: str(a["n_errors"])),
        ("Latencia media (s)", lambda a: fmt_sec(a["latency_mean"])),
        ("Latencia, mediana (s)", lambda a: fmt_sec(a["latency_p50"])),
        ("Latencia, percentil 95 (s)", lambda a: fmt_sec(a["latency_p95"])),
        ("Latencia, percentil 99 (s)", lambda a: fmt_sec(a["latency_p99"])),
    ]
    for label, fn in rows:
        cells = [fn(runs[p]["aggregates"]) for p in ("openai", "gemini", "groq")]
        md.append(f"| {label} | {cells[0]} | {cells[1]} | {cells[2]} |")

    # LaTeX
    lx = [
        r"\begin{table}[H]",
        r"\centering",
        r"\begin{tabular}{lrrr}",
        r"\toprule",
        r"Métrica & OpenAI & Gemini & Groq \\",
        r"\midrule",
    ]
    for label, fn in rows:
        cells = [fn(runs[p]["aggregates"]) for p in ("openai", "gemini", "groq")]
        # escape % in LaTeX
        cells_lx = [c.replace(" %", r"\,\%") if "%" in c else c for c in cells]
        lx.append(f"{label} & {cells_lx[0]} & {cells_lx[1]} & {cells_lx[2]} \\\\")
    lx += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\caption{Métricas agregadas de la evaluación automatizada sobre las 80 peticiones del conjunto, una columna por proveedor.}",
        r"\label{tab:eval_global}",
        r"\end{table}",
    ]
    return "\n".join(md), "\n".join(lx)


def build_per_category_table(runs: dict[str, dict]) -> tuple[str, str]:
    """Tabla 6.6 reescrita: precision por categoria, una columna por proveedor."""
    md = ["| Categoría | Total | OpenAI | Gemini | Groq |",
          "| --- | ---: | ---: | ---: | ---: |"]
    lx = [
        r"\begin{table}[H]",
        r"\centering",
        r"\begin{tabular}{lrrrr}",
        r"\toprule",
        r"Categoría & Total & OpenAI & Gemini & Groq \\",
        r"\midrule",
    ]

    # Total per category from any provider (they share the dataset)
    any_run = next(iter(runs.values()))
    totals = {}
    for r in any_run["results"]:
        totals[r["expected_intent"]] = totals.get(r["expected_intent"], 0) + 1

    for cat in CATEGORIES:
        total = totals.get(cat, 0)
        if total == 0:
            continue
        row_md = [f"`{cat}`", str(total)]
        row_lx = [f"\\texttt{{{latex_escape(cat)}}}", str(total)]
        for prov in ("openai", "gemini", "groq"):
            acc = runs[prov]["aggregates"]["intent_accuracy_per_category"].get(cat)
            row_md.append(fmt_pct_md(acc))
            row_lx.append(fmt_pct(acc))
        md.append("| " + " | ".join(row_md) + " |")
        lx.append(" & ".join(row_lx) + r" \\")

    lx += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\caption{Precisión de la clasificación de intención por categoría y por proveedor.}",
        r"\label{tab:eval_categoria}",
        r"\end{table}",
    ]
    return "\n".join(md), "\n".join(lx)


def build_confusion_matrix(run: dict, label: str) -> tuple[str, str]:
    """Una matriz de confusion por proveedor."""
    cm = run["aggregates"]["confusion_matrix"]
    cats = CATEGORIES
    header_md = ["Esperada/Predicha"] + [f"`{c}`" for c in cats]
    md = ["| " + " | ".join(header_md) + " |",
          "| --- |" + "|".join([" ---: "] * len(cats)) + " |"]
    for exp in cats:
        if exp not in cm:
            continue
        row = [f"`{exp}`"] + [str(cm.get(exp, {}).get(pred, 0)) for pred in cats]
        md.append("| " + " | ".join(row) + " |")

    lx = [
        r"\begin{table}[H]",
        r"\centering",
        r"\small",
        r"\begin{tabular}{l" + "r" * len(cats) + "}",
        r"\toprule",
        r"Esperada / Predicha & " + " & ".join(SHORT_LABELS.get(c, c) for c in cats) + r" \\",
        r"\midrule",
    ]
    for exp in cats:
        if exp not in cm:
            continue
        cells = [str(cm.get(exp, {}).get(pred, 0)) for pred in cats]
        lx.append(f"\\texttt{{{latex_escape(exp)}}} & " + " & ".join(cells) + r" \\")
    lx += [
        r"\bottomrule",
        r"\end{tabular}",
        f"\\caption{{Matriz de confusión para {label}; las columnas usan abreviaturas: act = action, res = research, d.res = deep\\_research, doc = document, w.sum = weekly\\_summary, w.pl = weekly\\_plan, prog = progress, rec = recommendations, unk = unknown.}}",
        f"\\label{{tab:eval_confusion_{label.lower().replace(' ', '_')}}}",
        r"\end{table}",
    ]
    return "\n".join(md), "\n".join(lx)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("openai_json", type=Path)
    parser.add_argument("gemini_json", type=Path)
    parser.add_argument("groq_json", type=Path)
    parser.add_argument("--out-dir", type=Path, default=Path("evaluation/results"))
    args = parser.parse_args()

    runs = {
        "openai": load_run(args.openai_json),
        "gemini": load_run(args.gemini_json),
        "groq": load_run(args.groq_json),
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)

    agg_md, agg_lx = build_aggregate_table(runs)
    cat_md, cat_lx = build_per_category_table(runs)

    md_out = ["# Comparativa entre proveedores", ""]
    md_out += ["## Tabla 6.5 — Métricas agregadas por proveedor", "", agg_md, ""]
    md_out += ["## Tabla 6.6 — Precisión por categoría", "", cat_md, ""]

    for prov, label in (("openai", "OpenAI"), ("gemini", "Gemini"), ("groq", "Groq")):
        cm_md, cm_lx = build_confusion_matrix(runs[prov], label)
        md_out += [f"## Matriz de confusión — {label}", "", cm_md, ""]

    (args.out_dir / "comparativa.md").write_text("\n".join(md_out), encoding="utf-8")

    lx_out = ["% Tablas LaTeX para la sección 6.4 — comparativa entre proveedores", ""]
    lx_out += [agg_lx, "", cat_lx, ""]
    for prov, label in (("openai", "OpenAI"), ("gemini", "Gemini"), ("groq", "Groq")):
        _, cm_lx = build_confusion_matrix(runs[prov], label)
        lx_out += [cm_lx, ""]

    (args.out_dir / "comparativa.tex").write_text("\n".join(lx_out), encoding="utf-8")

    print("Generados:")
    print(f"  - {args.out_dir / 'comparativa.md'}")
    print(f"  - {args.out_dir / 'comparativa.tex'}")


if __name__ == "__main__":
    main()
