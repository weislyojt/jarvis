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

    print("1) Your Claude API key. Get one at https://console.anthropic.com (Settings > API keys).")
    key = ""
    while not key.startswith("sk-ant-"):
        key = getpass.getpass("   Paste API key (hidden): ").strip()
        if not key.startswith("sk-ant-"):
            print("   That doesn't look like a Claude key (it should start with sk-ant-).")

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

    print("\n4) Brain: 1 = Sonnet (fast, cheaper, recommended)  2 = Opus (smartest, costs more)")
    model = "claude-opus-5-5" if ask("   Choose 1 or 2", "1") == "2" else "claude-sonnet-5-5"

    ENV.write_text(f"""# JARVIS settings. Keep this file private.
ANTHROPIC_API_KEY={key}
JARVIS_PIN={pin}
JARVIS_MODEL={model}
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
        import anthropic
        print("Testing your API key...")
        r = anthropic.Anthropic(api_key=key).messages.create(
            model=model, max_tokens=30, messages=[{"role": "user", "content": "Say 'Online and ready.'"}])
        print("   Claude says:", "".join(b.text for b in r.content if b.type == "text"))
    except Exception as e:
        print(f"   Key test failed: {e}\n   You can fix the key later in the .env file.")


if __name__ == "__main__":
    main()
