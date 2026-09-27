"""Conexão MySQL a partir de variáveis de ambiente (.env). Sem logar segredos."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pymysql
from dotenv import load_dotenv
from pymysql.connections import Connection


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_env() -> None:
    env_path = project_root() / ".env"
    load_dotenv(env_path, override=False)


def mysql_settings() -> dict[str, str | int]:
    load_env()
    host = os.getenv("MYSQL_HOST", "127.0.0.1")
    port = int(os.getenv("MYSQL_PORT", "3306"))
    user = os.getenv("MYSQL_USER")
    password = os.getenv("MYSQL_PASSWORD")
    database = os.getenv("MYSQL_DATABASE")
    missing = [k for k, v in {
        "MYSQL_USER": user,
        "MYSQL_PASSWORD": password,
        "MYSQL_DATABASE": database,
    }.items() if not v]
    if missing:
        raise RuntimeError(f"Variáveis ausentes no .env: {', '.join(missing)}")
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "database": database,
        "charset": "utf8mb4",
        "autocommit": False,
    }


def connect(*, database: str | None = None) -> Connection:
    """Abre conexão MySQL.

    database=None → usa MYSQL_DATABASE do .env.
    database=""   → conecta sem schema padrão (útil para CREATE DATABASE).
    database="x"  → força o schema x.
    """
    cfg = mysql_settings()
    kwargs: dict[str, str | int] = {
        "host": cfg["host"],
        "port": cfg["port"],
        "user": cfg["user"],
        "password": cfg["password"],
        "charset": cfg["charset"],
        "autocommit": cfg["autocommit"],
        "cursorclass": pymysql.cursors.DictCursor,
    }
    if database is None:
        kwargs["database"] = cfg["database"]
    elif database != "":
        kwargs["database"] = database
    return pymysql.connect(**kwargs)


@contextmanager
def mysql_connection(*, database: str | None = None) -> Iterator[Connection]:
    conn = connect(database=database)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
