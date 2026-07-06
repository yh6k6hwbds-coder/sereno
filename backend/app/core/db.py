"""
core/db.py — Infraestrutura de banco (SQLAlchemy 2.0), com engine PREGUIÇOSA.

A engine só é criada no primeiro uso, para que importar a app não exija o driver
do banco (útil em testes SQLite e no CI). Produção: PostgreSQL via DATABASE_URL;
dev/testes: SQLite. Modelo físico em core/models.py.
"""
from __future__ import annotations
import os
from collections.abc import Iterator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from app.core.models import Base

DEFAULT_URL = "postgresql+psycopg://sereno:sereno@localhost:5432/sereno"

_engine = None
_SessionLocal: sessionmaker | None = None


def normalize_database_url(url: str) -> str:
    """Normaliza o esquema da URL para o driver psycopg v3 (SQLAlchemy 2.0).

    Provedores gerenciados (Fly, Heroku, Render) injetam ``DATABASE_URL`` como
    ``postgres://...`` — esquema que o SQLAlchemy 2.0 recusa e que não seleciona
    o driver psycopg usado aqui (ver requirements). Reescreve ``postgres://`` e
    ``postgresql://`` (sem driver) para ``postgresql+psycopg://``. sqlite e URLs
    que já trazem ``+driver`` ficam intactas.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _init() -> None:
    global _engine, _SessionLocal
    if _engine is None:
        url = normalize_database_url(os.getenv("DATABASE_URL", DEFAULT_URL))
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, connect_args=connect_args, future=True)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False, class_=Session)


def get_engine():
    _init()
    return _engine


def get_db() -> Iterator[Session]:
    """Uma sessão por requisição, com commit no sucesso e rollback em erro."""
    _init()
    db = _SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_all() -> None:
    """Cria o schema a partir dos modelos (dev/testes; produção usa Alembic)."""
    Base.metadata.create_all(bind=get_engine())
