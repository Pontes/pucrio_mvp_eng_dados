"""Cria o schema vitacare_mvp e tabelas de controle de carga bruta."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.db import connect, project_root  # noqa: E402

STATEMENT_SPLIT = re.compile(r";\s*\n")
TARGET_DB = "vitacare_mvp"
CONTAINER = "mysql_db"


def load_sql(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        lines.append(line)
    cleaned = "\n".join(lines)
    parts = [p.strip() for p in STATEMENT_SPLIT.split(cleaned)]
    return [p for p in parts if p]


def _provision_via_docker() -> bool:
    """Cria DB + GRANT usando root do env do container (não lê .env no host)."""
    script = f"""
set -euo pipefail
mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "CREATE DATABASE IF NOT EXISTS \\`{TARGET_DB}\\` DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_unicode_ci;"
mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "GRANT ALL PRIVILEGES ON \\`{TARGET_DB}\\`.* TO '$MYSQL_USER'@'%'; FLUSH PRIVILEGES;"
"""
    try:
        proc = subprocess.run(
            ["docker", "exec", CONTAINER, "bash", "-lc", script],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False
    return proc.returncode == 0


def _run_statements(statements: list[str], *, database: str | None) -> list[str]:
    conn = connect(database=database)
    try:
        with conn.cursor() as cur:
            for stmt in statements:
                cur.execute(stmt)
            cur.execute(f"USE `{TARGET_DB}`")
            cur.execute("SHOW TABLES")
            tables = sorted(row[next(iter(row))] for row in cur.fetchall())
        conn.commit()
        return tables
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def apply_schema(sql_file: Path, *, bootstrap_database: str | None = None) -> int:
    statements = load_sql(sql_file)
    try:
        tables = _run_statements(statements, database=bootstrap_database)
    except Exception as first_exc:
        errno = getattr(first_exc, "args", [None])[0]
        if errno not in (1044, 1045):
            raise
        print(
            f"Sem permissão para criar `{TARGET_DB}` com o usuário do .env. "
            f"Tentando provisionar via docker exec `{CONTAINER}`…",
            file=sys.stderr,
        )
        if not _provision_via_docker():
            print(
                "Falha no provisionamento Docker. Crie o schema manualmente "
                f"(container `{CONTAINER}`, GRANT em `{TARGET_DB}`.*).",
                file=sys.stderr,
            )
            raise
        tables = _run_statements(statements, database=bootstrap_database)

    print(f"OK: aplicados statements de {sql_file.name}")
    print(f"Schema: {TARGET_DB}")
    print("Tabelas:", ", ".join(tables) if tables else "(nenhuma)")
    conn = connect(database=TARGET_DB)
    conn.close()
    print(f"Conexão OK → {TARGET_DB}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cria schema vitacare_mvp (carga bruta)"
    )
    parser.add_argument(
        "--sql",
        type=Path,
        default=project_root() / "sql" / "10_schema_vitacare_mvp.sql",
        help="Caminho do arquivo SQL",
    )
    parser.add_argument(
        "--bootstrap-database",
        default=None,
        help="Schema inicial da conexão (padrão: MYSQL_DATABASE do .env)",
    )
    args = parser.parse_args()
    if not args.sql.is_file():
        print(f"Arquivo SQL não encontrado: {args.sql}", file=sys.stderr)
        return 1
    try:
        return apply_schema(args.sql, bootstrap_database=args.bootstrap_database)
    except Exception as exc:
        print(
            f"Falha ao criar {TARGET_DB}: {type(exc).__name__}. "
            "Confirme GRANT CREATE no MySQL (sem expor senha).",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
