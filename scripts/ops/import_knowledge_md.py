"""Import knowledge/*.md → Django CMS. Uso: python -m scripts.import_knowledge_md"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cms.config.settings")

    from django.core.management import execute_from_command_line

    execute_from_command_line(
        ["manage.py", "import_knowledge_md", *sys.argv[1:]]
    )


if __name__ == "__main__":
    main()
