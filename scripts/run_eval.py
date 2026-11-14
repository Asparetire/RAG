"""M5 一键跑批入口（m5-runbook 步 5.6；FR-6.6）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from doclens.eval.ablation import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
