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

## Choose a brain (free or paid)

| Brain | Cost | Get a key | Notes |
|---|---|---|---|
| **Gemini** (default free) | Free tier | https://aistudio.google.com/apikey | Smart and fast. Google sets the free limits per account (see them in AI Studio) and may use free-tier chats to improve its products |
| **Groq** (free backup) | Free tier | https://console.groq.com/keys | Very fast open models; about 1,000 requests a day but a small per-minute budget |
| **Claude** | Pay per use | https://console.anthropic.com | The strongest at following instructions and using tools safely |

Add the key as a variable (`GEMINI_API_KEY`, `GROQ_API_KEY` or `ANTHROPIC_API_KEY`) and Jarvis picks that brain. Add **both** a Gemini and a Groq key and Jarvis switches to Groq automatically whenever Gemini's free limit runs out. To force one, set `JARVIS_BRAIN` to `gemini`, `groq`, `claude` or `openrouter`.

Free brains search the web through DuckDuckGo. For steadier search, add a free `TAVILY_API_KEY` from https://tavily.com (1,000 free searches a month).

## Run it in the cloud — set up entirely from your phone

No PC needed. Jarvis lives on Railway and becomes an app on your phone. You get voice, memory, routines, reminders (with notifications even when the app is closed) and web search. PC control comes back later by linking your PC.

1. **Brain key (free):** on your phone, open https://aistudio.google.com/apikey → *Create API key* → copy it. Optional backup: https://console.groq.com/keys → *Create API key*.
2. **Railway:** open https://railway.com/new → *Deploy from GitHub repo* → pick this repo (`jarvis`).
3. **Storage (keeps its memory):** in the service, open the menu (⋮ or right-click on the service) → *Attach volume* → mount path `/data`.
4. **Variables:** service → *Variables* → add:
   - `GEMINI_API_KEY` = your Gemini key (or `ANTHROPIC_API_KEY` for Claude)
   - optional backup: `GROQ_API_KEY` = your Groq key
   - `JARVIS_PIN` = a PIN with **at least 6** digits/characters
   - `PORT` = `8000`
   - optional: `JARVIS_USER_NAME`, `JARVIS_CALL_ME`, `TAVILY_API_KEY`, `JARVIS_CITY` = `Manila`, `JARVIS_COUNTRY` = `PH`
5. **Address:** service → *Settings* → *Networking* → *Generate Domain* (port `8000`). You get `https://something.up.railway.app`.
6. **Install on your phone:** open that address, enter your PIN.
   - Android (Chrome): ⋮ → *Add to Home screen / Install app*.
   - iPhone (Safari): Share → *Add to Home Screen*, then open Jarvis from the Home Screen.
7. **Notifications:** in Jarvis, ⚙ → Device → *Get reminders on this device*. Tap *Send a test notification* to check.

Railway's trial gives $5 of credit; after that the Hobby plan is $5/month including $5 of usage, which a personal Jarvis normally fits in. With the Gemini or Groq free tier, the brain itself costs nothing.

Jarvis follows your phone's time zone automatically, so reminders stay right when you travel.

## Setup on your PC (about 10 minutes)

1. Install **Python 3.11+** from https://www.python.org/downloads/ — tick **"Add python.exe to PATH"**.
2. Get a brain key: free Gemini at https://aistudio.google.com/apikey, or Claude at https://console.anthropic.com (set a monthly spend limit).
3. Unzip this folder somewhere permanent, e.g. `C:\Jarvis`.
4. Double-click **install.bat**. It installs everything and asks which brain, your key, a PIN, and your name.
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
| `JARVIS_BRAIN` | `gemini`, `groq`, `claude` or `openrouter` |
| `JARVIS_MODEL` | Override the model, e.g. `claude-opus-5-5` for the smartest Claude |
| `JARVIS_PIN` | Unlock PIN for your devices |
| `JARVIS_NAME` / `JARVIS_CALL_ME` | Its name, and what it calls you |
| `JARVIS_AUTO_APPROVE` | `true` lets risky actions run without asking. Only if you fully trust it |
| `JARVIS_PC_VOICE` | PC speaks reminders out loud |
| `JARVIS_HOST` | `0.0.0.0` (reachable on Wi-Fi) or `127.0.0.1` (Tailscale only, most private) |

Restart Jarvis after editing.

## How the "learning" works

Jarvis doesn't retrain the AI model. It learns the way a good assistant does: it writes down facts, preferences and routines about you in its memory (a database in `data\jarvis.db`) and reads them before every reply. The more you tell it, the more it adapts. You stay in control in Settings → Memory.

## Privacy and costs

- Memory, reminders and chats are stored in the `data` folder (or the Railway volume). Messages go to the brain you chose to be answered. Google's free tier may use them to improve its products, so pick Claude for very private matters.
- Keep `.env` private: it holds your API key and PIN. Don't upload this folder to GitHub with `.env` in it.
- You pay per use on your API account. Web searches cost extra per search. A spend limit in the Console keeps surprises away.

## Troubleshooting

- **"Can't reach Jarvis"** — is `start_jarvis.bat` running on the PC? Is the PC awake?
- **Mic doesn't work on phone** — use the `https://…ts.net` address, not the `http://` IP one, and allow microphone access.
- **"API key was rejected"** — fix the brain key in Railway Variables or `.env`, restart.
- **"Hit my free brain's limit"** — wait a bit, or add a `GROQ_API_KEY` backup.
- **Forgot PIN** — change `JARVIS_PIN` in `.env`, restart.
- Logs when started hidden: `data\jarvis.log`.

## Coming in Phase 2

Link your PC to cloud Jarvis for remote control · Gmail, Google Calendar and Drive access · always-on wake word on the PC without a browser tab · mouse control · smart home devices · morning briefings.
