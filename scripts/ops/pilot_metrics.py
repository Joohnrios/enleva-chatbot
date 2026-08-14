"""Contagem simples de métricas a partir dos logs JSONL."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import get_settings  # noqa: E402


def main() -> None:
    settings = get_settings()
    log_dir = settings.log_path
    total = 0
    refused = 0
    with_sources = 0
    days: Counter[str] = Counter()

    if not log_dir.exists():
        print(f"Sem logs em {log_dir}")
        return

    for path in sorted(log_dir.glob("chat-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            total += 1
            if row.get("refused"):
                refused += 1
            if row.get("sources"):
                with_sources += 1
            days[path.stem.replace("chat-", "")] += 1

    print(f"Total de interações: {total}")
    print(f"Recusas: {refused} ({(refused / total * 100) if total else 0:.1f}%)")
    print(f"Com fontes: {with_sources} ({(with_sources / total * 100) if total else 0:.1f}%)")
    print("Por dia:")
    for day, count in days.most_common():
        print(f"  {day}: {count}")


if __name__ == "__main__":
    main()
