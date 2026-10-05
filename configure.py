"""One-time setup: asks a few questions and writes the .env file."""
import getpass
from pathlib import Path

ENV = Path(__file__).resolve().parent / ".env"


def ask(prompt, default=""):
    val = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip()
    return val or default


def main():
    print("\n=== JARVIS setup ===\n")
    if ENV.exists() and ask("A .env already exists. Replace it? (y/n)", "n").lower() != "y":
        print("Kept your existing settings.")
        return

    print("1) Choose Jarvis's brain:")
    print("   1 = Gemini (FREE, from Google)   key: https://aistudio.google.com/apikey")
    print("   2 = Groq (FREE, very fast)        key: https://console.groq.com/keys")
    print("   3 = Claude (paid, the smartest)   key: https://console.anthropic.com")
    brain = {"1": "gemini", "2": "groq", "3": "claude"}.get(ask("   Choose 1, 2 or 3", "1"), "gemini")
    key_var = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY", "claude": "ANTHROPIC_API_KEY"}[brain]
    key = ""
    while len(key) < 20:
        key = getpass.getpass(f"   Paste your {brain} API key (hidden): ").strip()
        if len(key) < 20:
            print("   That key looks too short. Copy the whole key and try again.")
    backup_line = ""
    if brain != "claude":
        other = "groq" if brain == "gemini" else "gemini"
        b = getpass.getpass(f"   Optional backup brain ({other}) key for when the free limit runs out (Enter to skip): ").strip()
        if b:
            backup_line = f"{'GROQ_API_KEY' if other == 'groq' else 'GEMINI_API_KEY'}={b}\n"

    print("\n2) A PIN to unlock Jarvis on your devices (at least 4 characters).")
    pin = ""
    while len(pin) < 4:
        pin = getpass.getpass("   Choose PIN (hidden): ").strip()

    print("\n3) A little about you (press Enter to skip).")
    user = ask("   Your name")
    call_me = ask("   What should Jarvis call you", "sir")
    name = ask("   Assistant name", "Jarvis")
    city = ask("   Your city (for local search results)", "Manila")
    country = ask("   Country code", "PH")
    tz = ask("   Time zone", "Asia/Manila")

    model = ""
    if brain == "claude":
        print("\n4) Claude model: 1 = Sonnet (fast, cheaper, recommended)  2 = Opus (smartest, costs more)")
        model = "claude-opus-5-5" if ask("   Choose 1 or 2", "1") == "2" else "claude-sonnet-5-5"

    ENV.write_text(f"""# JARVIS settings. Keep this file private.
JARVIS_BRAIN={brain}
{key_var}={key}
{backup_line}JARVIS_PIN={pin}
JARVIS_MODEL={model}
# Optional: free key from https://tavily.com for more reliable web search with free brains
TAVILY_API_KEY=
JARVIS_NAME={name}
JARVIS_USER_NAME={user}
JARVIS_CALL_ME={call_me}
JARVIS_CITY={city}
JARVIS_COUNTRY={country}
JARVIS_TIMEZONE={tz}

# Network: 0.0.0.0 lets your phone reach Jarvis on home Wi-Fi. Use 127.0.0.1 if you only use Tailscale serve.
JARVIS_HOST=0.0.0.0
JARVIS_PORT=8000

# true = risky actions (commands, deleting, shutdown) run WITHOUT asking you first.
JARVIS_AUTO_APPROVE=false
# true = the PC speaks reminders out loud.
JARVIS_PC_VOICE=true
JARVIS_WEB_SEARCH=true
""", encoding="utf-8")
    print(f"\nSaved settings to {ENV}. Start Jarvis with start_jarvis.bat\n")

    try:
        import os
        os.environ.update({"JARVIS_BRAIN": brain, key_var: key, "JARVIS_MODEL": model})
        import importlib
        import config
        importlib.reload(config)
        import brains
        print("Testing your key...")
        r = brains.make_brain().messages.create(model=config.MODEL, max_tokens=60, system=[{"type": "text", "text": "Be brief."}],
                                               tools=[], messages=[{"role": "user", "content": "Say 'Online and ready.'"}])
        print("   Jarvis says:", "".join(getattr(b, "text", "") for b in r.content if b.type == "text"))
    except Exception as e:
        print(f"   Key test failed: {e}\n   You can fix the key later in the .env file.")


if __name__ == "__main__":
    main()
