"""Hands: things JARVIS can do on the Windows PC it runs on.

Every function returns a short plain-text result for the brain to read.
Non-Windows systems get sensible fallbacks where possible.
"""
import base64
import difflib
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path

import psutil

import config

IS_WIN = config.IS_WINDOWS
NO_WINDOW = 0x08000000 if IS_WIN else 0  # CREATE_NO_WINDOW


class PCError(Exception):
    pass


def _need_windows(what):
    if not IS_WIN:
        raise PCError(f"{what} only works when I'm running on Windows.")


def _powershell(script, timeout=30):
    """Run a Windows PowerShell 5.1 script safely (no quoting problems)."""
    script = ("[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
              "$ProgressPreference = 'SilentlyContinue'; " + script)
    encoded = base64.b64encode(script.encode("utf-16-le")).decode()
    exe = "powershell.exe" if IS_WIN else (shutil.which("pwsh") or "pwsh")
    proc = subprocess.run([exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                           "-EncodedCommand", encoded],
                          capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW,
                          encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def _ps_quote(text):
    return "'" + str(text).replace("'", "''") + "'"


def _trim(text, limit=6000):
    text = text or ""
    return text if len(text) <= limit else text[:limit] + f"\n...[{len(text) - limit} more characters cut]"


def resolve_path(path):
    raw = os.path.expandvars(str(path).strip().strip('"'))
    if raw == "~" or raw.startswith(("~/", "~\\")):
        raw = str(config.HOME_DIR) + raw[1:]
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = config.HOME_DIR / p
    return p.resolve()


# ---------------------------------------------------------------- apps
_apps_cache = {"t": 0, "apps": []}

ALIASES = {
    "calculator": "calc", "notepad": "notepad", "paint": "mspaint", "file explorer": "explorer",
    "explorer": "explorer", "files": "explorer", "task manager": "taskmgr", "command prompt": "cmd",
    "cmd": "cmd", "powershell": "powershell", "terminal": "wt", "settings": "ms-settings:",
    "control panel": "control", "snipping tool": "snippingtool", "camera": "microsoft.windows.camera:",
    "store": "ms-windows-store:", "microsoft store": "ms-windows-store:", "clock": "ms-clock:",
    "edge": "msedge", "chrome": "chrome", "google chrome": "chrome", "firefox": "firefox",
}


def _start_apps():
    """All Start-menu apps (desktop + Store apps) with their launch IDs. Cached 10 min."""
    if time.time() - _apps_cache["t"] < 600 and _apps_cache["apps"]:
        return _apps_cache["apps"]
    apps = []
    try:
        code, out, _ = _powershell("Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress", 40)
        if code == 0 and out:
            data = json.loads(out)
            apps = [{"name": a["Name"], "id": a["AppID"]} for a in (data if isinstance(data, list) else [data])]
    except Exception:
        apps = []
    _apps_cache.update(t=time.time(), apps=apps)
    return apps


def _best_app(query):
    q = query.lower().strip()
    best, best_score = None, 0.0
    for app in _start_apps():
        n = app["name"].lower()
        if n == q:
            score = 1.0
        elif n.startswith(q) or q.startswith(n):
            score = 0.9
        elif q in n:
            score = 0.8
        else:
            score = difflib.SequenceMatcher(None, q, n).ratio()
        if score > best_score:
            best, best_score = app, score
    return best, best_score


def open_app(name):
    q = name.strip()
    if not q:
        raise PCError("Which app?")
    if not IS_WIN:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([opener, q] if sys.platform != "darwin" else ["open", "-a", q])
        return f"Tried to open {q}."
    alias = ALIASES.get(q.lower())
    app, score = _best_app(q)
    if app and score >= 0.75 and not alias:
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app['id']}"], creationflags=NO_WINDOW)
        return f"Opened {app['name']}."
    target = alias or q
    try:
        os.startfile(target)  # type: ignore[attr-defined]  (Windows only)
        return f"Opened {q}."
    except OSError:
        pass
    if app and score >= 0.5:
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app['id']}"], creationflags=NO_WINDOW)
        return f"Opened {app['name']} (closest match to '{q}')."
    close = [a["name"] for a in _start_apps() if q.lower()[:3] in a["name"].lower()][:8]
    raise PCError(f"Couldn't find an app called '{q}'." + (f" Similar: {', '.join(close)}" if close else ""))


def list_apps(filter_text=""):
    apps = _start_apps()
    names = sorted({a["name"] for a in apps if filter_text.lower() in a["name"].lower()})
    if not names:
        return "No matching apps found." if IS_WIN else "App listing only works on Windows."
    return _trim(", ".join(names), 4000)


def close_app(name):
    """Politely close an app (like clicking X), so it can still ask to save work."""
    q = name.lower().replace(".exe", "").strip()
    matches = {p.info["name"] for p in psutil.process_iter(["name"])
               if p.info["name"] and q in p.info["name"].lower().replace(".exe", "")}
    if not matches:
        raise PCError(f"No running app matches '{name}'.")
    for proc_name in matches:
        if IS_WIN:
            subprocess.run(["taskkill", "/IM", proc_name], capture_output=True, creationflags=NO_WINDOW)
        else:
            for p in psutil.process_iter(["name"]):
                if p.info["name"] == proc_name:
                    p.terminate()
    return f"Asked {', '.join(sorted(matches))} to close."


def open_website(url):
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opened {url} on the PC."


# ---------------------------------------------------------------- media and volume
VK = {"volume_up": 0xAF, "volume_down": 0xAE, "mute": 0xAD, "play_pause": 0xB3,
      "next": 0xB0, "previous": 0xB1, "stop": 0xB2}


def _press_vk(vk, times=1):
    import ctypes
    for _ in range(times):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
        time.sleep(0.02)


def media(action, amount=None):
    _need_windows("Media and volume control")
    if action == "set_volume":
        level = max(0, min(100, int(amount if amount is not None else 50)))
        _press_vk(VK["volume_down"], 50)
        _press_vk(VK["volume_up"], round(level / 2))
        return f"Volume set to about {level}%."
    if action not in VK:
        raise PCError(f"Unknown media action {action}.")
    times = 1
    if action in ("volume_up", "volume_down"):
        times = max(1, min(50, round((amount or 10) / 2)))
    _press_vk(VK[action], times)
    return {"volume_up": f"Volume up {times * 2}%.", "volume_down": f"Volume down {times * 2}%.",
            "mute": "Toggled mute.", "play_pause": "Toggled play/pause.", "next": "Next track.",
            "previous": "Previous track.", "stop": "Stopped media."}[action]


# ---------------------------------------------------------------- keyboard and clipboard
def _sendkeys_escape(text):
    out = []
    for ch in text:
        if ch in "+^%~(){}[]":
            out.append("{" + ch + "}")
        elif ch == "\n":
            out.append("{ENTER}")
        else:
            out.append(ch)
    return "".join(out)


def keyboard(text=None, keys=None):
    """Type text, or press a key combo in SendKeys notation (e.g. ^c, %{TAB}, {ENTER})."""
    _need_windows("Keyboard control")
    seq = _sendkeys_escape(text) if text else (keys or "")
    if not seq:
        raise PCError("Nothing to type.")
    code, _, err = _powershell(
        "Start-Sleep -Milliseconds 300; $w = New-Object -ComObject WScript.Shell; "
        f"$w.SendKeys({_ps_quote(seq)})")
    if code != 0:
        raise PCError(err or "Typing failed.")
    return "Typed it." if text else f"Pressed {keys}."


def clipboard(action, text=None):
    _need_windows("Clipboard access")
    if action == "get":
        _, out, _ = _powershell("Get-Clipboard -Raw")
        return "Clipboard: " + (_trim(out, 4000) if out else "(empty)")
    _powershell(f"Set-Clipboard -Value {_ps_quote(text or '')}")
    return "Copied to the clipboard."


# ---------------------------------------------------------------- system
def system_status():
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage(str(Path(config.HOME_DIR.anchor or "/")))
    lines = [
        f"PC: {platform.node()} ({platform.system()} {platform.release()})",
        f"CPU: {psutil.cpu_percent(interval=0.5)}%  RAM: {vm.percent}% of {vm.total // 2**30} GB",
        f"Disk: {disk.percent}% used, {disk.free // 2**30} GB free",
        f"Up since: {datetime.fromtimestamp(psutil.boot_time()).strftime('%b %d %I:%M %p')}",
    ]
    try:
        bat = psutil.sensors_battery()
        if bat:
            lines.append(f"Battery: {bat.percent:.0f}% ({'charging' if bat.power_plugged else 'on battery'})")
    except Exception:
        pass
    procs = []
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            procs.append((p.info["memory_info"].rss, p.info["name"]))
        except Exception:
            continue
    top = sorted(procs, reverse=True)[:6]
    lines.append("Top memory: " + ", ".join(f"{n} {m // 2**20}MB" for m, n in top))
    return "\n".join(lines)


def power(action):
    if action == "lock":
        _need_windows("Locking")
        import ctypes
        ctypes.windll.user32.LockWorkStation()
        return "PC locked."
    _need_windows("Power control")
    cmds = {"shutdown": ["shutdown", "/s", "/t", "30"], "restart": ["shutdown", "/r", "/t", "30"],
            "cancel": ["shutdown", "/a"],
            "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]}
    if action not in cmds:
        raise PCError(f"Unknown power action {action}.")
    subprocess.Popen(cmds[action], creationflags=NO_WINDOW)
    return {"shutdown": "Shutting down in 30 seconds (say 'cancel shutdown' to stop it).",
            "restart": "Restarting in 30 seconds (say 'cancel shutdown' to stop it).",
            "cancel": "Cancelled the shutdown.", "sleep": "Going to sleep."}[action]


def run_command(command, timeout=60):
    if IS_WIN:
        code, out, err = _powershell(command, timeout)
    else:
        p = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
        code, out, err = p.returncode, p.stdout.strip(), p.stderr.strip()
    result = f"Exit code {code}."
    if out:
        result += "\nOutput:\n" + _trim(out)
    if err:
        result += "\nErrors:\n" + _trim(err, 2000)
    return result


# ---------------------------------------------------------------- files
def list_files(path="~"):
    p = resolve_path(path)
    if not p.exists():
        raise PCError(f"{p} doesn't exist.")
    if p.is_file():
        return f"{p} is a file ({p.stat().st_size} bytes)."
    items = []
    for child in sorted(p.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower()))[:200]:
        try:
            items.append(child.name + ("/" if child.is_dir() else f"  ({child.stat().st_size // 1024} KB)"))
        except OSError:
            continue
    return f"{p}:\n" + ("\n".join(items) if items else "(empty)")


def find_files(query, folder="~", limit=30):
    root = resolve_path(folder)
    q = query.lower()
    skip = {"node_modules", ".git", "appdata", "$recycle.bin", ".venv", "__pycache__", "windows"}
    found, scanned = [], 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d.lower() not in skip and not d.startswith(".")]
        for name in filenames + dirnames:
            if q in name.lower():
                found.append(os.path.join(dirpath, name))
                if len(found) >= limit:
                    return "\n".join(found)
        scanned += 1
        if scanned > 20000:
            break
    return "\n".join(found) if found else f"Nothing matching '{query}' under {root}."


TEXT_EXT = {".txt", ".md", ".py", ".js", ".ts", ".json", ".csv", ".html", ".css", ".xml", ".yml", ".yaml",
            ".ini", ".log", ".bat", ".ps1", ".sql", ".java", ".c", ".cpp", ".cs", ".php", ".env", ".toml"}


def read_file(path):
    p = resolve_path(path)
    if not p.is_file():
        raise PCError(f"{p} isn't a file.")
    if p.stat().st_size > 2_000_000 and p.suffix.lower() not in TEXT_EXT:
        raise PCError("That file is too big or not a text file.")
    data = p.read_bytes()[:400_000]
    if b"\x00" in data[:2000]:
        raise PCError(f"{p.name} is a binary file; I can only read text files for now.")
    return f"{p}:\n" + _trim(data.decode("utf-8", errors="replace"), 20000)


def write_file(path, content, mode="overwrite"):
    p = resolve_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a" if mode == "append" else "w", encoding="utf-8") as f:
        f.write(content)
    return f"{'Appended to' if mode == 'append' else 'Saved'} {p}."


def delete_file(path):
    """Moves to JARVIS's own trash folder (data/trash) instead of deleting forever."""
    p = resolve_path(path)
    if not p.exists():
        raise PCError(f"{p} doesn't exist.")
    config.TRASH_DIR.mkdir(exist_ok=True)
    dest = config.TRASH_DIR / f"{datetime.now():%Y%m%d-%H%M%S}_{p.name}"
    shutil.move(str(p), str(dest))
    return f"Moved {p.name} to Jarvis trash ({dest})."


# ---------------------------------------------------------------- screen
def screenshot():
    """Returns (base64 jpeg, width, height)."""
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab(all_screens=False)
    except Exception as e:
        raise PCError(f"Couldn't capture the screen: {e}")
    img = img.convert("RGB")
    img.thumbnail((1568, 1568))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=70)
    return base64.b64encode(buf.getvalue()).decode(), img.width, img.height


# ---------------------------------------------------------------- PC alerts (used by reminders)
def alert(title, message):
    """Windows toast + spoken message on the PC. Silent no-op elsewhere."""
    if not IS_WIN:
        return

    def _run():
        toast = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$x = $t.GetElementsByTagName('text')
$x.Item(0).AppendChild($t.CreateTextNode({_ps_quote(title)})) > $null
$x.Item(1).AppendChild($t.CreateTextNode({_ps_quote(message)})) > $null
$app = '{{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}}\\WindowsPowerShell\\v1.0\\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($t))
"""
        try:
            _powershell(toast, 20)
        except Exception:
            pass
        if config.PC_VOICE:
            try:
                _powershell("Add-Type -AssemblyName System.Speech; "
                            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                            f"$s.Speak({_ps_quote(message)})", 60)
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True).start()
