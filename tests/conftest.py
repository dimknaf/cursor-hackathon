import sys
from pathlib import Path

# Repo root on path for `sec_agent` imports when running pytest from repo root
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
