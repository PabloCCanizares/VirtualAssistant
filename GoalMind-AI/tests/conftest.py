from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AI_SRC = PROJECT_ROOT / "GoalMind-AI"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if str(AI_SRC) not in sys.path:
    sys.path.insert(0, str(AI_SRC))
