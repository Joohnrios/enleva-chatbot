# Generated manually — extensão pgvector + tabelas de chunks/âncoras (só Postgres)

from django.db import migrations


CREATE_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS kb_chunk (
    id TEXT PRIMARY KEY,
    body TEXT NOT NULL,
    source VARCHAR(255) NOT NULL DEFAULT '',
    title VARCHAR(255) NOT NULL DEFAULT '',
    domain VARCHAR(120) NOT NULL DEFAULT '',
    classification VARCHAR(32) NOT NULL DEFAULT '',
    file_hash VARCHAR(64) NOT NULL DEFAULT '',
    embedding vector(384) NOT NULL
);

CREATE INDEX IF NOT EXISTS kb_chunk_source_idx ON kb_chunk (source);
CREATE INDEX IF NOT EXISTS kb_chunk_embedding_hnsw
    ON kb_chunk USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS kb_anchor (
    id TEXT PRIMARY KEY,
    body TEXT NOT NULL,
    domain VARCHAR(120) NOT NULL DEFAULT '',
    kind VARCHAR(32) NOT NULL DEFAULT '',
    title VARCHAR(255) NOT NULL DEFAULT '',
    source VARCHAR(255) NOT NULL DEFAULT '',
    embedding vector(384) NOT NULL
);

CREATE INDEX IF NOT EXISTS kb_anchor_source_idx ON kb_anchor (source);
CREATE INDEX IF NOT EXISTS kb_anchor_embedding_hnsw
    ON kb_anchor USING hnsw (embedding vector_cosine_ops);
"""

DROP_SQL = """
DROP TABLE IF EXISTS kb_anchor;
DROP TABLE IF EXISTS kb_chunk;
"""


def apply_pgvector(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(CREATE_SQL)


def reverse_pgvector(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(DROP_SQL)


class Migration(migrations.Migration):
    dependencies = [
        ("kb", "0002_kb_supereditor_group"),
    ]

    operations = [
        migrations.RunPython(apply_pgvector, reverse_pgvector),
    ]
