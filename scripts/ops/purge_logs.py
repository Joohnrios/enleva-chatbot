"""CLI: purgar logs expirados conforme LOG_RETENTION_DAYS.

Uso:
  python -m scripts.purge_logs
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import get_settings  # noqa: E402
from backend.app.security.retention import purge_expired_logs  # noqa: E402


def main() -> None:
    settings = get_settings()
    removed = purge_expired_logs(settings.log_path, settings.log_retention_days)
    print(
        f"Removidos {removed} arquivo(s) de log com mais de "
        f"{settings.log_retention_days} dias em {settings.log_path}"
    )


if __name__ == "__main__":
    main()
