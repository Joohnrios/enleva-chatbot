"""CLI: reindexar a base de conhecimento.

Uso (na raiz do projeto):
  python -m scripts.ingest
  python -m scripts.ops.ingest --full
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.rag.ingest import ingest_knowledge  # noqa: E402

logging.basicConfig(level=logging.INFO)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reindexa a base de conhecimento")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Reset completo do índice (ignora file_hash)",
    )
    args = parser.parse_args()
    result = ingest_knowledge(full=args.full)
    print(result.message)
    if result.skipped_files:
        print("Ignorados:")
        for item in result.skipped_files:
            print(f"  - {item}")
    print(
        f"Arquivos: {result.indexed_files} atualizados | "
        f"{result.unchanged_files} inalterados | "
        f"{result.removed_files} removidos | "
        f"Chunks: {result.indexed_chunks}"
    )


if __name__ == "__main__":
    main()
