"""Settings for JARVIS. Edit the .env file (made by configure.py) or your cloud host's variables, not this file."""
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # optional
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent
if load_dotenv:
    load_dotenv(BASE_DIR / ".env")


def _bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


IS_WINDOWS = sys.platform.startswith("win")

# Where Jarvis runs. Cloud mode switches on automatically on Railway.
CLOUD = _bool("JARVIS_CLOUD", bool(os.getenv("RAILWAY_PROJECT_ID") or os.getenv("RAILWAY_ENVIRONMENT_NAME")))

# Data lives on a persistent volume in the cloud, or next to the code on a PC.
DATA_DIR = Path(os.getenv("JARVIS_DATA_DIR") or os.getenv("RAILWAY_VOLUME_MOUNT_PATH") or (BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Brain
API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
MODEL = os.getenv("JARVIS_MODEL", "claude-sonnet-5-5").strip()
MAX_TOKENS = int(os.getenv("JARVIS_MAX_TOKENS", "1500"))
MAX_TOOL_STEPS = int(os.getenv("JARVIS_MAX_TOOL_STEPS", "12"))
MAX_HISTORY_MESSAGES = int(os.getenv("JARVIS_HISTORY", "30"))
WEB_SEARCH = _bool("JARVIS_WEB_SEARCH", True)
WEB_SEARCH_MAX_USES = int(os.getenv("JARVIS_WEB_SEARCH_MAX_USES", "5"))

# Identity
ASSISTANT_NAME = os.getenv("JARVIS_NAME", "Jarvis").strip() or "Jarvis"
USER_NAME = os.getenv("JARVIS_USER_NAME", "").strip()
CALL_ME = os.getenv("JARVIS_CALL_ME", "sir").strip()
CITY = os.getenv("JARVIS_CITY", "").strip()
COUNTRY = os.getenv("JARVIS_COUNTRY", "").strip()      # 2-letter code, e.g. PH
TIMEZONE = os.getenv("JARVIS_TIMEZONE", "").strip()    # IANA name, e.g. Asia/Manila. Empty = follow your phone

# Server and security
HOST = os.getenv("JARVIS_HOST", "0.0.0.0").strip()
PORT = int(os.getenv("PORT") or os.getenv("JARVIS_PORT") or "8000")
PIN = os.getenv("JARVIS_PIN", "").strip()
MIN_PIN = 6 if CLOUD else 4                             # a public URL needs a longer PIN
AUTO_APPROVE = _bool("JARVIS_AUTO_APPROVE", False)     # True = risky actions run without asking
PC_VOICE = _bool("JARVIS_PC_VOICE", True)              # PC speaks reminders out loud
HOME_DIR = Path(os.getenv("JARVIS_HOME_DIR", str(Path.home()))).expanduser()
PUSH_CONTACT = os.getenv("JARVIS_PUSH_CONTACT", "mailto:jarvis@example.com").strip()

DB_PATH = DATA_DIR / "jarvis.db"
TRASH_DIR = DATA_DIR / "trash"
