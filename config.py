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


def _key(name):
    """Read a key, forgiving stray spaces or quotes pasted around it."""
    return os.getenv(name, "").strip().strip('"').strip("'").strip()


def _bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


IS_WINDOWS = sys.platform.startswith("win")

# Where Jarvis runs. Cloud mode switches on automatically on Railway.
CLOUD = _bool("JARVIS_CLOUD", bool(os.getenv("RAILWAY_PROJECT_ID") or os.getenv("RAILWAY_ENVIRONMENT_NAME")))

# Data lives on a persistent volume in the cloud, or next to the code on a PC.
DATA_DIR = Path(os.getenv("JARVIS_DATA_DIR") or os.getenv("RAILWAY_VOLUME_MOUNT_PATH") or (BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Brain. Pick one with JARVIS_BRAIN, or just add a key and Jarvis picks for you.
#   claude  - paid, the strongest (ANTHROPIC_API_KEY)
#   gemini  - free tier from Google (GEMINI_API_KEY)
#   groq    - free tier, very fast open models (GROQ_API_KEY)
#   openrouter - many models, some free (OPENROUTER_API_KEY, set JARVIS_MODEL)
API_KEY = _key("ANTHROPIC_API_KEY")
GEMINI_API_KEY = _key("GEMINI_API_KEY")
GROQ_API_KEY = _key("GROQ_API_KEY")
OPENROUTER_API_KEY = _key("OPENROUTER_API_KEY")
TAVILY_API_KEY = _key("TAVILY_API_KEY")   # optional, better web search for free brains

_KEYS = {"claude": API_KEY, "gemini": GEMINI_API_KEY, "groq": GROQ_API_KEY, "openrouter": OPENROUTER_API_KEY}
BRAIN = os.getenv("JARVIS_BRAIN", "").strip().lower() or next((b for b, k in _KEYS.items() if k), "claude")
BACKUP_BRAIN = os.getenv("JARVIS_BACKUP_BRAIN", "").strip().lower() or next(
    (b for b in ("gemini", "groq") if b != BRAIN and _KEYS[b] and BRAIN != "claude"), "")
DEFAULT_MODELS = {"claude": "claude-sonnet-5-5", "gemini": "gemini-3.8-flash", "groq": "openai/gpt-oss-120b",
                  "openrouter": ""}
MODEL = os.getenv("JARVIS_MODEL", "").strip() or DEFAULT_MODELS.get(BRAIN, "")
BACKUP_MODEL = os.getenv("JARVIS_BACKUP_MODEL", "").strip() or DEFAULT_MODELS.get(BACKUP_BRAIN, "")
BRAIN_URL = os.getenv("JARVIS_BRAIN_URL", "").strip()          # advanced: any OpenAI-compatible endpoint
BACKUP_BRAIN_URL = os.getenv("JARVIS_BACKUP_BRAIN_URL", "").strip()
MAX_TOKENS = int(os.getenv("JARVIS_MAX_TOKENS", "1500" if BRAIN == "claude" else "4096"))
MAX_TOOL_STEPS = int(os.getenv("JARVIS_MAX_TOOL_STEPS", "12"))
# Groq's free tier allows few tokens per minute, so it gets a shorter memory of the chat.
MAX_HISTORY_MESSAGES = int(os.getenv("JARVIS_HISTORY", "12" if BRAIN == "groq" else "30"))
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
