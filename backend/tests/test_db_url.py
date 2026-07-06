"""Normalização da DATABASE_URL para o driver psycopg (deploy gerenciado)."""
from app.core.db import normalize_database_url


def test_postgres_scheme_de_provedor_gerenciado_vira_psycopg():
    # Fly/Heroku/Render injetam este formato.
    url = "postgres://user:pass@host:5432/db"
    assert normalize_database_url(url) == "postgresql+psycopg://user:pass@host:5432/db"


def test_postgresql_sem_driver_vira_psycopg():
    url = "postgresql://user:pass@host:5432/db"
    assert normalize_database_url(url) == "postgresql+psycopg://user:pass@host:5432/db"


def test_url_que_ja_tem_driver_fica_intacta():
    url = "postgresql+psycopg://user:pass@host:5432/db"
    assert normalize_database_url(url) == url


def test_sqlite_fica_intacta():
    url = "sqlite:///./dev.db"
    assert normalize_database_url(url) == url


def test_preserva_query_e_credenciais_com_caracteres():
    url = "postgres://u:p%40ss@h:5432/db?sslmode=require"
    assert normalize_database_url(url) == (
        "postgresql+psycopg://u:p%40ss@h:5432/db?sslmode=require"
    )
