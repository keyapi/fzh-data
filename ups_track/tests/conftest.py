"""让 ``import ups_track`` 在从任意目录跑 pytest 时也可用。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
