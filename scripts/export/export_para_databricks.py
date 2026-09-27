"""Exporta tabelas limpas do MySQL para arquivos locais (upload manual no Databricks).

Por padrão:
- só tabelas da lista aprovada (sem csv_*/map_*/fila_*);
- remove carga_id e linha_origem;
- grava Parquet em exports/ (CSV opcional);
- falha se houver coluna proibida pelo checklist LGPD.

Uso:
  PYTHONPATH=. python3 -m scripts.export.export_para_databricks
  PYTHONPATH=. python3 -m scripts.export.export_para_databricks --format csv
  PYTHONPATH=. python3 -m scripts.export.export_para_databricks --tabela consultas_ubs
  PYTHONPATH=. python3 -m scripts.export.export_para_databricks --include-meta
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.db import connect, project_root  # noqa: E402
from scripts.export.lgpd_checklist import (  # noqa: E402
    COLS_META_OPCIONAL,
    TABELAS_EXPORT_TODAS,
    colunas_proibidas_encontradas,
)

TARGET_DB = "vitacare_mvp"
BATCH = 5000


def _default_outdir() -> Path:
    return project_root() / "exports" / datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _table_columns(cur: Any, table: str) -> list[str]:
    cur.execute(f"SHOW COLUMNS FROM `{table}`")
    return [r["Field"] for r in cur.fetchall()]


def _select_columns(all_cols: list[str], *, include_meta: bool) -> list[str]:
    cols = list(all_cols)
    if not include_meta:
        cols = [c for c in cols if c.lower() not in COLS_META_OPCIONAL]
    return cols


def _fetch_batches(cur: Any, table: str, columns: list[str]):
    col_sql = ", ".join(f"`{c}`" for c in columns)
    cur.execute(f"SELECT {col_sql} FROM `{table}`")
    while True:
        rows = cur.fetchmany(BATCH)
        if not rows:
            break
        yield rows


def _write_csv(path: Path, columns: list[str], rows_iter) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for batch in rows_iter:
            for row in batch:
                writer.writerow({c: row.get(c) for c in columns})
                n += 1
    return n


def _write_parquet(path: Path, columns: list[str], rows_iter) -> int:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "Parquet exige pyarrow. Instale: pip install pandas pyarrow "
            "ou use --format csv"
        ) from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    # Schema fixo em string evita conflito null vs string entre lotes.
    schema = pa.schema([(c, pa.string()) for c in columns])

    def _cell(value: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    n = 0
    writer: Any = None
    try:
        for batch in rows_iter:
            if not batch:
                continue
            records = [{c: _cell(r.get(c)) for c in columns} for r in batch]
            table = pa.Table.from_pylist(records, schema=schema)
            if writer is None:
                writer = pq.ParquetWriter(str(path), schema)
            writer.write_table(table)
            n += len(batch)
        if writer is None:
            pq.write_table(pa.Table.from_pylist([], schema=schema), str(path))
    finally:
        if writer is not None:
            writer.close()
    return n


def export_table(
    cur: Any,
    table: str,
    outdir: Path,
    *,
    fmt: str,
    include_meta: bool,
) -> dict[str, Any]:
    all_cols = _table_columns(cur, table)
    banned = colunas_proibidas_encontradas(all_cols)
    if banned:
        return {
            "table": table,
            "ok": False,
            "error": f"colunas proibidas: {banned}",
            "rows": 0,
            "path": None,
        }

    columns = _select_columns(all_cols, include_meta=include_meta)
    if not columns:
        return {
            "table": table,
            "ok": False,
            "error": "nenhuma coluna para exportar",
            "rows": 0,
            "path": None,
        }

    ext = "parquet" if fmt == "parquet" else "csv"
    path = outdir / f"{table}.{ext}"

    def iterator():
        yield from _fetch_batches(cur, table, columns)

    if fmt == "parquet":
        n = _write_parquet(path, columns, iterator())
    else:
        n = _write_csv(path, columns, iterator())

    size = path.stat().st_size if path.exists() else 0
    return {
        "table": table,
        "ok": True,
        "error": None,
        "rows": n,
        "cols": len(columns),
        "path": str(path),
        "bytes": size,
        "dropped_meta": sorted(COLS_META_OPCIONAL) if not include_meta else [],
    }


def run(
    *,
    tables: list[str] | None = None,
    outdir: Path | None = None,
    fmt: str = "parquet",
    include_meta: bool = False,
) -> int:
    targets = tables or list(TABELAS_EXPORT_TODAS)
    out = outdir or _default_outdir()
    out.mkdir(parents=True, exist_ok=True)

    manifesto = out / "MANIFESTO.txt"
    print(f"Destino: {out}")
    print(f"Formato: {fmt} | include_meta={include_meta}")
    print(f"Tabelas: {', '.join(targets)}")

    results: list[dict[str, Any]] = []
    conn = connect(database=TARGET_DB)
    try:
        with conn.cursor() as cur:
            existing = set()
            cur.execute("SHOW TABLES")
            for r in cur.fetchall():
                existing.add(list(r.values())[0])

            for table in targets:
                if table not in existing:
                    print(f"PULA {table}: não existe no MySQL")
                    results.append(
                        {
                            "table": table,
                            "ok": False,
                            "error": "tabela ausente",
                            "rows": 0,
                            "path": None,
                        }
                    )
                    continue
                print(f"Exportando {table}…")
                info = export_table(
                    cur, table, out, fmt=fmt, include_meta=include_meta
                )
                results.append(info)
                if info["ok"]:
                    mb = (info.get("bytes") or 0) / (1024 * 1024)
                    print(
                        f"  OK {info['rows']:,} linhas, {info['cols']} cols, "
                        f"{mb:.1f} MiB → {info['path']}"
                    )
                else:
                    print(f"  FALHA: {info['error']}", file=sys.stderr)
        conn.commit()
    finally:
        conn.close()

    lines = [
        f"export_em={datetime.now(timezone.utc).isoformat()}",
        f"formato={fmt}",
        f"include_meta={include_meta}",
        f"database={TARGET_DB}",
        "",
        "# Arquivos gerados (upload manual no Databricks Volume)",
        "",
    ]
    falhas = 0
    for r in results:
        if r["ok"]:
            lines.append(
                f"OK\t{r['table']}\trows={r['rows']}\tcols={r.get('cols')}\t{r['path']}"
            )
        else:
            falhas += 1
            lines.append(f"FAIL\t{r['table']}\t{r.get('error')}")
    lines += [
        "",
        "# Próximos passos no Databricks Free Edition",
        "1. Catalog → Volumes → Upload dos arquivos desta pasta",
        "2. CREATE TABLE a partir dos arquivos (read_files / COPY INTO)",
        "3. Rodar SQL das perguntas do MVP sem exibir PII",
        "",
        "# Não enviar: map_*, fila_*, csv_*, .env, dumps brutos",
    ]
    manifesto.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Manifesto: {manifesto}")

    if falhas:
        print(f"Concluído com {falhas} falha(s).", file=sys.stderr)
        return 1
    print("OK: export local concluído. Faça upload manual no Databricks.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Exporta tabelas limpas para exports/ (Databricks)"
    )
    parser.add_argument(
        "--format",
        choices=["parquet", "csv"],
        default="parquet",
        help="Formato de arquivo (padrão: parquet)",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=None,
        help="Pasta de saída (padrão: exports/YYYYMMDD_HHMMSS)",
    )
    parser.add_argument(
        "--tabela",
        action="append",
        dest="tabelas",
        help="Exporta só esta tabela (repetível). Padrão: todas aprovadas",
    )
    parser.add_argument(
        "--include-meta",
        action="store_true",
        help="Mantém carga_id e linha_origem na exportação",
    )
    parser.add_argument(
        "--listar",
        action="store_true",
        help="Lista tabelas candidatas e sai",
    )
    args = parser.parse_args()
    if args.listar:
        for t in TABELAS_EXPORT_TODAS:
            print(t)
        return 0
    try:
        return run(
            tables=args.tabelas,
            outdir=args.outdir,
            fmt=args.format,
            include_meta=args.include_meta,
        )
    except Exception as exc:
        print(f"Falha: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
