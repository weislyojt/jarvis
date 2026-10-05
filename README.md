# Jarvis — your personal AI assistant

Jarvis runs in the cloud or on your Windows PC, and you talk to it from your phone (installed as an app), any browser, or the PC. It hears you, talks back, remembers what you teach it, sets reminders, searches the web, and controls your PC.

## What it can do

| Area | Examples |
|---|---|
| Voice | Tap the mic, or turn on "Always listen" and say "Jarvis, open Spotify" |
| Learns about you | "Remember my sister is Ana." It also saves useful facts on its own. See and delete everything it knows in Settings → Memory |
| Routines | "When I say gaming mode, open Discord and Steam and set volume to 40" |
| Reminders | "Remind me to drink water every day at 10am" — pops up and speaks on the PC, and on your phone when the app is open |
| Web search | News, prices, weather, scores, anything current, with sources |
| PC control (PC mode) | Open/close apps, open websites, play/pause, volume, type text, clipboard, lock, sleep, shutdown |
| Files | Find, read, write, and move files to trash |
| Eyes | "What's on my screen?" — it takes a screenshot and looks |
| Anything else | "Run a command that…" — it writes PowerShell and asks you first |

**Safety:** running commands, deleting/overwriting files and shutting down always show an **Approve / Deny** card first (or just say "approve"). Deleted files go to `data\trash`, not gone forever.

## Run it in the cloud — set up entirely from your phone

No PC needed. Jarvis lives on Railway and becomes an app on your phone. You get voice, memory, routines, reminders (with notifications even when the app is closed) and web search. PC control comes back later by linking your PC.

1. **API key:** on your phone, open https://console.anthropic.com → Settings → API keys → Create key. Copy it. Add a few dollars of credit and set a monthly spend limit.
2. **Railway:** open https://railway.com/new → *Deploy from GitHub repo* → pick this repo (`jarvis`).
3. **Storage (keeps its memory):** in the service, open the menu (⋮ or right-click on the service) → *Attach volume* → mount path `/data`.
4. **Variables:** service → *Variables* → add:
   - `ANTHROPIC_API_KEY` = your key
   - `JARVIS_PIN` = a PIN with **at least 6** digits/characters
   - `PORT` = `8000`
   - optional: `JARVIS_USER_NAME`, `JARVIS_CALL_ME`, `JARVIS_MODEL` (`claude-opus-5-5` for the smartest brain), `JARVIS_CITY` = `Manila`, `JARVIS_COUNTRY` = `PH`
5. **Address:** service → *Settings* → *Networking* → *Generate Domain* (port `8000`). You get `https://something.up.railway.app`.
6. **Install on your phone:** open that address, enter your PIN.
   - Android (Chrome): ⋮ → *Add to Home screen / Install app*.
   - iPhone (Safari): Share → *Add to Home Screen*, then open Jarvis from the Home Screen.
7. **Notifications:** in Jarvis, ⚙ → Device → *Get reminders on this device*. Tap *Send a test notification* to check.

Railway's trial gives $5 of credit; after that the Hobby plan is $5/month including $5 of usage, which a personal Jarvis normally fits in. Claude API usage is billed separately by Anthropic.

Jarvis follows your phone's time zone automatically, so reminders stay right when you travel.

## Setup on your PC (about 10 minutes)

1. Install **Python 3.11+** from https://www.python.org/downloads/ — tick **"Add python.exe to PATH"**.
2. Get a Claude API key at https://console.anthropic.com → Settings → API keys. Add a few dollars of credit and **set a monthly spend limit**.
3. Unzip this folder somewhere permanent, e.g. `C:\Jarvis`.
4. Double-click **install.bat**. It installs everything and asks for your key, a PIN, and your name.
5. Double-click **start_jarvis.bat**. Your browser opens to `http://localhost:8000`. Enter your PIN.
6. Optional: **add_to_startup.bat** makes Jarvis start silently whenever you log in. (Undo with remove_from_startup.bat.)

Windows may ask to allow Python through the firewall the first time — allow it on **Private networks**.

## Use it on your phone (and anywhere)

Voice and app install need a secure **https** link. The easiest free way is Tailscale:

1. Install **Tailscale** on the PC and on your phone (https://tailscale.com/download), sign in with the same account on both.
2. On the PC, open Command Prompt and run:
   ```
   tailscale serve --bg --https=443 localhost:8000
   ```
   If it asks you to enable HTTPS for your network, open the link it shows and click enable, then run it again.
3. It prints your address, like `https://your-pc.tail1234.ts.net`. Open that on your phone, enter your PIN.
4. Install it: **Android Chrome** → ⋮ → *Add to Home screen / Install app*. **iPhone Safari** → Share → *Add to Home Screen*.

This works on mobile data too, and only your own devices can reach it. Your PC must be on with Jarvis running.

Quick test without Tailscale: on the same Wi-Fi, open `http://<your-PC-IP>:8000` on the phone (find the IP with `ipconfig`). Typing works; voice needs the https link.

## Settings (`.env` file)

| Setting | What it does |
|---|---|
| `JARVIS_MODEL` | `claude-sonnet-5-5` (fast, cheaper) or `claude-opus-5-5` (smartest) |
| `JARVIS_PIN` | Unlock PIN for your devices |
| `JARVIS_NAME` / `JARVIS_CALL_ME` | Its name, and what it calls you |
| `JARVIS_AUTO_APPROVE` | `true` lets risky actions run without asking. Only if you fully trust it |
| `JARVIS_PC_VOICE` | PC speaks reminders out loud |
| `JARVIS_HOST` | `0.0.0.0` (reachable on Wi-Fi) or `127.0.0.1` (Tailscale only, most private) |

Restart Jarvis after editing.

## How the "learning" works

Jarvis doesn't retrain the AI model. It learns the way a good assistant does: it writes down facts, preferences and routines about you in its memory (a database in `data\jarvis.db`) and reads them before every reply. The more you tell it, the more it adapts. You stay in control in Settings → Memory.

## Privacy and costs

- Everything is stored on your PC in the `data` folder. Messages go to Claude's API to be answered.
- Keep `.env` private: it holds your API key and PIN. Don't upload this folder to GitHub with `.env` in it.
- You pay per use on your API account. Web searches cost extra per search. A spend limit in the Console keeps surprises away.

## Troubleshooting

- **"Can't reach Jarvis"** — is `start_jarvis.bat` running on the PC? Is the PC awake?
- **Mic doesn't work on phone** — use the `https://…ts.net` address, not the `http://` IP one, and allow microphone access.
- **"API key was rejected"** — fix `ANTHROPIC_API_KEY` in `.env`, restart.
- **Forgot PIN** — change `JARVIS_PIN` in `.env`, restart.
- Logs when started hidden: `data\jarvis.log`.

## Coming in Phase 2

Link your PC to cloud Jarvis for remote control · Gmail, Google Calendar and Drive access · always-on wake word on the PC without a browser tab · mouse control · smart home devices · morning briefings.
