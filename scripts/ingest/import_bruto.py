"""Importação bruta: todos os CSVs de vitacare_fontes → schema vitacare_mvp.

Sem limpeza, sem filtro LGPD, sem mapeamento restrito de colunas.
Todas as colunas da fonte como TEXT + metadados de proveniência.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.db import connect, project_root  # noqa: E402

BATCH_SIZE = 2000
TARGET_DB = "vitacare_mvp"
COMPETENCIA_RE = re.compile(r"(20\d{2}-\d{2})")
NOME_ARQUIVO_RE = re.compile(
    r"^Marica_(.+)_(20\d{2}-\d{2})\.csv$",
    re.IGNORECASE,
)

# tipo no nome do arquivo → tabela destino
TIPO_TABELA: dict[str, str] = {
    "ATENDIMENTO_COM_CID_PARAM_BIO": "csv_atendimento_cid_param_bio",
    "LISTAGEM_CADASTRO_DO_USUARIO_CAP": "csv_cadastro_usuario_cap",
    "LISTAGEM_CONSOLIDADA": "csv_consolidada",
    "LISTAGEM_CONSULTAS_CAP": "csv_consultas_cap",
    "SUBPAV_MENSAL_EXAMES": "csv_exames",
    "SUBPAV_PLAN_ACOMP_MENSAL_DIAB": "csv_acompanhamento_diab",
    "SUBPAV_PLAN_ACOMP_MENSAL_HIPER": "csv_acompanhamento_hiper",
    "SUB_PAV_FICHA_A_V2": "csv_ficha_a_v2",  # override por n. de cols
}

FICHA_A_COLS_BASE = 61
FICHA_A_COLS_EXT = 161
META_RESERVED = {
    "id",
    "row_id",
    "carga_id",
    "linha_origem",
    "arquivo_origem",
    "data_importacao",
    "competencia_extracao",
}


@dataclass(frozen=True)
class ArquivoFonte:
    path: Path
    tipo: str
    competencia: str
    tabela: str
    fonte_key: str  # chave estável p/ idempotência (inclui variante ficha)


@dataclass
class LoadResult:
    carga_id: int
    fonte: str
    tabela: str
    arquivo: str
    sha256: str
    qtd_lidas: int
    qtd_aceitas: int
    qtd_rejeitadas: int
    skipped: bool = False
    dry_run: bool = False


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def competencia_from_name(filename: str) -> str:
    match = COMPETENCIA_RE.search(filename)
    if not match:
        raise ValueError(f"Competência YYYY-MM não encontrada no nome: {filename}")
    return match.group(1)


def normalize_sql_column(raw: str) -> str:
    name = raw.replace("\ufeff", "").strip()
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"[^0-9A-Za-z_]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    if not name:
        name = "col"
    if name[0].isdigit():
        name = f"c_{name}"
    name = name.lower()
    if name in META_RESERVED:
        name = f"src_{name}"
    return name


def unique_columns(headers: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result: list[str] = []
    for h in headers:
        base = normalize_sql_column(h)
        count = seen.get(base, 0) + 1
        seen[base] = count
        result.append(base if count == 1 else f"{base}_{count}")
    return result


def resolve_tabela(tipo: str, n_cols: int) -> tuple[str, str]:
    """Retorna (tabela, fonte_key). Ficha A: 61 → csv_ficha_a_v2; 161 → _ext."""
    if tipo == "SUB_PAV_FICHA_A_V2":
        if n_cols == FICHA_A_COLS_EXT:
            return "csv_ficha_a_v2_ext", "ficha_a_v2_ext"
        if n_cols == FICHA_A_COLS_BASE:
            return "csv_ficha_a_v2", "ficha_a_v2"
        # layout inesperado: tabela própria por largura
        return f"csv_ficha_a_v2_c{n_cols}", f"ficha_a_v2_c{n_cols}"
    if tipo not in TIPO_TABELA:
        raise ValueError(f"Tipo de arquivo não mapeado: {tipo}")
    table = TIPO_TABELA[tipo]
    fonte = table.removeprefix("csv_")
    return table, fonte


def parse_arquivo(path: Path) -> tuple[str, str]:
    match = NOME_ARQUIVO_RE.match(path.name)
    if not match:
        raise ValueError(f"Nome de arquivo fora do padrão Marica_<TIPO>_YYYY-MM.csv: {path.name}")
    return match.group(1).upper(), match.group(2)


def discover_csvs(base: Path) -> list[Path]:
    return sorted(p for p in base.glob("*.csv") if p.is_file())


def read_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh, delimiter=";")
        try:
            return next(reader)
        except StopIteration as exc:
            raise ValueError(f"CSV vazio: {path.name}") from exc


def build_fonte(path: Path) -> ArquivoFonte:
    tipo, competencia = parse_arquivo(path)
    header = read_header(path)
    tabela, fonte_key = resolve_tabela(tipo, len(header))
    return ArquivoFonte(
        path=path.resolve(),
        tipo=tipo,
        competencia=competencia,
        tabela=tabela,
        fonte_key=fonte_key,
    )


def _short_ident(prefix: str, tabela: str) -> str:
    """Identificador MySQL ≤ 64 chars."""
    digest = hashlib.sha1(tabela.encode()).hexdigest()[:8]
    base = f"{prefix}_{digest}"
    return base[:64]


def ensure_table(cur, tabela: str, data_columns: list[str]) -> None:
    cols_sql = ",\n    ".join(f"`{c}` TEXT NULL" for c in data_columns)
    uk = _short_ident("uk", tabela)
    idx = _short_ident("idx", tabela)
    fk = _short_ident("fk", tabela)
    ddl = f"""
CREATE TABLE IF NOT EXISTS `{tabela}` (
    `row_id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `carga_id` BIGINT UNSIGNED NOT NULL,
    `linha_origem` INT UNSIGNED NOT NULL,
    `arquivo_origem` VARCHAR(255) NOT NULL,
    `data_importacao` DATETIME NOT NULL,
    `competencia_extracao` CHAR(7) NOT NULL,
    {cols_sql},
    PRIMARY KEY (`row_id`),
    UNIQUE KEY `{uk}` (`carga_id`, `linha_origem`),
    KEY `{idx}` (`competencia_extracao`),
    CONSTRAINT `{fk}`
        FOREIGN KEY (`carga_id`) REFERENCES `carga_arquivo` (`carga_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""".strip()
    cur.execute(ddl)


def _find_carga(cur, fonte: str, digest: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT carga_id, status, qtd_lidas, qtd_aceitas, qtd_rejeitadas, tabela_destino
        FROM carga_arquivo
        WHERE fonte = %s AND arquivo_sha256 = %s
        """,
        (fonte, digest),
    )
    return cur.fetchone()


def _purge_carga(cur, carga_id: int, tabela: str) -> None:
    cur.execute("DELETE FROM linha_rejeitada WHERE carga_id = %s", (carga_id,))
    cur.execute(f"DELETE FROM `{tabela}` WHERE carga_id = %s", (carga_id,))
    cur.execute("DELETE FROM carga_arquivo WHERE carga_id = %s", (carga_id,))


def _insert_carga(
    cur,
    *,
    fonte: str,
    tabela: str,
    arquivo_nome: str,
    competencia: str,
    digest: str,
    qtd_colunas: int,
) -> int:
    cur.execute(
        """
        INSERT INTO carga_arquivo (
            fonte, tabela_destino, arquivo_nome, competencia_extracao,
            arquivo_sha256, qtd_colunas, status
        ) VALUES (%s, %s, %s, %s, %s, %s, 'iniciada')
        """,
        (fonte, tabela, arquivo_nome, competencia, digest, qtd_colunas),
    )
    return int(cur.lastrowid)


def _finalize_carga(
    cur,
    carga_id: int,
    *,
    lidas: int,
    aceitas: int,
    rejeitadas: int,
    status: str,
    mensagem: str | None = None,
) -> None:
    cur.execute(
        """
        UPDATE carga_arquivo
        SET qtd_lidas = %s,
            qtd_aceitas = %s,
            qtd_rejeitadas = %s,
            status = %s,
            finalizado_em = %s,
            mensagem = %s
        WHERE carga_id = %s
        """,
        (lidas, aceitas, rejeitadas, status, datetime.now(), mensagem, carga_id),
    )


def _empty_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value if value != "" else None


def _flush_accepts(
    cur,
    tabela: str,
    data_columns: list[str],
    rows: list[tuple[Any, ...]],
) -> None:
    if not rows:
        return
    meta = [
        "carga_id",
        "linha_origem",
        "arquivo_origem",
        "data_importacao",
        "competencia_extracao",
    ]
    all_cols = meta + data_columns
    col_sql = ", ".join(f"`{c}`" for c in all_cols)
    placeholders = ", ".join(["%s"] * len(all_cols))
    sql = f"INSERT INTO `{tabela}` ({col_sql}) VALUES ({placeholders})"
    cur.executemany(sql, rows)


def _flush_rejects(cur, rows: list[tuple[Any, ...]]) -> None:
    if not rows:
        return
    cur.executemany(
        """
        INSERT INTO linha_rejeitada (
            carga_id, fonte, linha_origem, motivo_codigo, linha_bruta
        ) VALUES (%s, %s, %s, %s, %s)
        """,
        rows,
    )


def count_data_lines(path: Path) -> int:
    """Conta linhas de dados (exclui cabeçalho; ignora linha final vazia)."""
    n = 0
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh, delimiter=";")
        next(reader, None)
        for fields in reader:
            if len(fields) == 1 and fields[0].strip() == "":
                continue
            n += 1
    return n


def import_csv(
    path: Path,
    *,
    database: str = TARGET_DB,
    batch_size: int = BATCH_SIZE,
    dry_run: bool = False,
) -> LoadResult:
    fonte_info = build_fonte(path)
    path = fonte_info.path
    digest = sha256_file(path)
    arquivo_nome = path.name
    header = read_header(path)
    data_columns = unique_columns(header)
    expected_cols = len(data_columns)
    agora = datetime.now()

    if dry_run:
        lidas = count_data_lines(path)
        print(
            f"DRY-RUN arquivo={arquivo_nome} tipo={fonte_info.tipo} "
            f"tabela={fonte_info.tabela} cols={expected_cols} linhas≈{lidas}"
        )
        return LoadResult(
            carga_id=0,
            fonte=fonte_info.fonte_key,
            tabela=fonte_info.tabela,
            arquivo=arquivo_nome,
            sha256=digest,
            qtd_lidas=lidas,
            qtd_aceitas=0,
            qtd_rejeitadas=0,
            dry_run=True,
        )

    conn = connect(database=database)
    try:
        with conn.cursor() as cur:
            existing = _find_carga(cur, fonte_info.fonte_key, digest)
            if existing and existing["status"] == "concluida":
                conn.commit()
                return LoadResult(
                    carga_id=int(existing["carga_id"]),
                    fonte=fonte_info.fonte_key,
                    tabela=str(existing["tabela_destino"]),
                    arquivo=arquivo_nome,
                    sha256=digest,
                    qtd_lidas=int(existing["qtd_lidas"] or 0),
                    qtd_aceitas=int(existing["qtd_aceitas"] or 0),
                    qtd_rejeitadas=int(existing["qtd_rejeitadas"] or 0),
                    skipped=True,
                )
            if existing:
                _purge_carga(
                    cur,
                    int(existing["carga_id"]),
                    str(existing["tabela_destino"]),
                )
                conn.commit()

            ensure_table(cur, fonte_info.tabela, data_columns)
            carga_id = _insert_carga(
                cur,
                fonte=fonte_info.fonte_key,
                tabela=fonte_info.tabela,
                arquivo_nome=arquivo_nome,
                competencia=fonte_info.competencia,
                digest=digest,
                qtd_colunas=expected_cols,
            )
            conn.commit()

        lidas = aceitas = rejeitadas = 0
        accept_buf: list[tuple[Any, ...]] = []
        reject_buf: list[tuple[Any, ...]] = []

        try:
            with path.open("r", encoding="utf-8-sig", newline="") as fh:
                reader = csv.reader(fh, delimiter=";")
                next(reader)  # cabeçalho já validado
                for line_no, fields in enumerate(reader, start=2):
                    if len(fields) == 1 and fields[0].strip() == "":
                        continue
                    lidas += 1
                    raw_line = ";".join(fields)
                    if len(fields) != expected_cols:
                        rejeitadas += 1
                        reject_buf.append(
                            (
                                carga_id,
                                fonte_info.fonte_key,
                                line_no,
                                "Q_LINHA_MALFORMADA",
                                raw_line,
                            )
                        )
                    else:
                        values = tuple(_empty_to_none(v) for v in fields)
                        accept_buf.append(
                            (
                                carga_id,
                                line_no,
                                arquivo_nome,
                                agora,
                                fonte_info.competencia,
                            )
                            + values
                        )
                        aceitas += 1

                    if len(accept_buf) >= batch_size:
                        with conn.cursor() as cur:
                            _flush_accepts(
                                cur, fonte_info.tabela, data_columns, accept_buf
                            )
                        conn.commit()
                        accept_buf.clear()
                    if len(reject_buf) >= batch_size:
                        with conn.cursor() as cur:
                            _flush_rejects(cur, reject_buf)
                        conn.commit()
                        reject_buf.clear()

            with conn.cursor() as cur:
                _flush_accepts(cur, fonte_info.tabela, data_columns, accept_buf)
                _flush_rejects(cur, reject_buf)
                _finalize_carga(
                    cur,
                    carga_id,
                    lidas=lidas,
                    aceitas=aceitas,
                    rejeitadas=rejeitadas,
                    status="concluida",
                )
            conn.commit()
        except Exception as exc:
            with conn.cursor() as cur:
                _finalize_carga(
                    cur,
                    carga_id,
                    lidas=lidas,
                    aceitas=aceitas,
                    rejeitadas=rejeitadas,
                    status="falha",
                    mensagem=type(exc).__name__,
                )
            conn.commit()
            raise

        return LoadResult(
            carga_id=carga_id,
            fonte=fonte_info.fonte_key,
            tabela=fonte_info.tabela,
            arquivo=arquivo_nome,
            sha256=digest,
            qtd_lidas=lidas,
            qtd_aceitas=aceitas,
            qtd_rejeitadas=rejeitadas,
        )
    finally:
        conn.close()


def filter_jobs(
    paths: list[Path],
    *,
    tipo: str | None = None,
    arquivo: Path | None = None,
) -> list[Path]:
    if arquivo is not None:
        return [arquivo.resolve()]
    if tipo is None:
        return paths
    tipo_u = tipo.upper()
    out: list[Path] = []
    for p in paths:
        try:
            t, _ = parse_arquivo(p)
        except ValueError:
            continue
        if t == tipo_u or t.replace("_", "") == tipo_u.replace("_", ""):
            out.append(p)
        elif tipo_u in t:
            out.append(p)
    return out


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Importa CSVs brutos para schema vitacare_mvp"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        default=True,
        help="Importar todos os CSVs em vitacare_fontes (padrão)",
    )
    parser.add_argument(
        "--tipo",
        help="Filtrar por tipo (ex.: LISTAGEM_CONSULTAS_CAP ou consultas)",
    )
    parser.add_argument("--arquivo", type=Path, help="Caminho de um CSV específico")
    parser.add_argument(
        "--database",
        default=TARGET_DB,
        help=f"Schema destino (padrão: {TARGET_DB})",
    )
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Só valida cabeçalho/contagem; não grava no MySQL",
    )
    parser.add_argument(
        "--fontes-dir",
        type=Path,
        default=None,
        help="Pasta dos CSVs (padrão: vitacare_fontes/)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    base = args.fontes_dir or (project_root() / "vitacare_fontes")
    if not base.is_dir():
        print(f"Pasta de fontes não encontrada: {base}", file=sys.stderr)
        return 1

    paths = discover_csvs(base)
    jobs = filter_jobs(paths, tipo=args.tipo, arquivo=args.arquivo)
    if not jobs:
        print("Nenhum CSV selecionado.", file=sys.stderr)
        return 2

    exit_code = 0
    for path in jobs:
        try:
            print(f"==> {path.name}")
            result = import_csv(
                path,
                database=args.database,
                batch_size=args.batch_size,
                dry_run=args.dry_run,
            )
            if result.dry_run:
                continue
            estado = "SKIP (já carregado)" if result.skipped else "OK"
            check = result.qtd_lidas == result.qtd_aceitas + result.qtd_rejeitadas
            print(
                f"{estado} carga_id={result.carga_id} tabela={result.tabela} "
                f"lidas={result.qtd_lidas} aceitas={result.qtd_aceitas} "
                f"rejeitadas={result.qtd_rejeitadas} check={check}"
            )
        except Exception as exc:
            exit_code = 1
            print(
                f"FALHA arquivo={path.name} erro={type(exc).__name__}",
                file=sys.stderr,
            )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
