"""Swappable brains.

Jarvis's agent loop speaks the Claude Messages format. For other providers, OpenAICompatBrain
translates that format to OpenAI-style chat completions (which Gemini, Groq, OpenRouter and Ollama all
accept) and translates the answer back, so the rest of Jarvis doesn't need to know which brain it has.
"""
import json
import urllib.error
import urllib.request
import uuid
from types import SimpleNamespace as NS

import config

PRESETS = {
    "gemini": {"url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
               "key": lambda: config.GEMINI_API_KEY, "images": True, "label": "Gemini", "echo_raw": True},
    "groq": {"url": "https://api.groq.com/openai/v1/chat/completions",
             "key": lambda: config.GROQ_API_KEY, "images": False, "label": "Groq"},
    "openrouter": {"url": "https://openrouter.ai/api/v1/chat/completions",
                   "key": lambda: config.OPENROUTER_API_KEY, "images": False, "label": "OpenRouter"},
}


# Error types named so agent._friendly_error recognises them.
class BrainError(Exception):
    pass


class RateLimitError(BrainError):
    pass


class AuthenticationError(BrainError):
    pass


class APIConnectionError(BrainError):
    pass


class OpenAICompatBrain:
    """Looks like `anthropic.Anthropic()` to the agent: brain.messages.create(...)."""

    def __init__(self, name, model, url=None, api_key=None, opener=None):
        preset = PRESETS.get(name, {})
        self.name = name
        self.model = model
        self.url = url or preset.get("url")
        self.api_key = api_key if api_key is not None else preset.get("key", lambda: "")()
        self.images = preset.get("images", False)
        self.label = preset.get("label", name)
        self.echo_raw = preset.get("echo_raw", False)
        self._open = opener or urllib.request.urlopen
        self.messages = self  # so callers can use brain.messages.create(...)

    # ---------------------------------------------------------------- Claude format -> OpenAI format
    @staticmethod
    def _tools(tools):
        out = []
        for t in tools:
            if "input_schema" not in t:  # Claude-only server tools (e.g. its built-in web search)
                continue
            out.append({"type": "function", "function": {
                "name": t["name"], "description": t.get("description", ""), "parameters": t["input_schema"]}})
        return out

    def _messages(self, system, messages):
        sys_text = "\n\n".join(b["text"] for b in system) if isinstance(system, list) else (system or "")
        out = [{"role": "system", "content": sys_text}]
        for m in messages:
            content = m["content"]
            if isinstance(content, str):
                out.append({"role": m["role"], "content": content})
                continue
            if m["role"] == "assistant":
                out.append(self._assistant(content))
                continue
            # user turn holding tool results
            extra_images = []
            for part in content:
                if part.get("type") != "tool_result":
                    continue
                result = part.get("content")
                if isinstance(result, list):
                    text = " ".join(p.get("text", "") for p in result if p.get("type") == "text")
                    for p in result:
                        if p.get("type") == "image" and self.images:
                            src = p["source"]
                            extra_images.append({"type": "image_url", "image_url": {
                                "url": f"data:{src['media_type']};base64,{src['data']}"}})
                    if any(p.get("type") == "image" for p in result) and not self.images:
                        text += " (This brain can't view images.)"
                    result = text or "Done."
                out.append({"role": "tool", "tool_call_id": part["tool_use_id"], "content": str(result)})
            if extra_images:
                out.append({"role": "user", "content": [{"type": "text", "text": "Here is the screenshot."}]
                            + extra_images})
        return out

    def _assistant(self, blocks):
        # Echo our own provider's raw reply back unchanged: some models (e.g. Gemini 3) attach hidden
        # reasoning signatures to tool calls that must be returned exactly.
        raw = next((getattr(b, "_raw", None) for b in blocks if getattr(b, "_provider", None) == self.name), None)
        if raw is not None and self.echo_raw:
            return raw
        text = "".join(getattr(b, "text", "") for b in blocks if getattr(b, "type", None) == "text")
        calls = [{"id": b.id, "type": "function",
                  "function": {"name": b.name, "arguments": json.dumps(b.input or {})}}
                 for b in blocks if getattr(b, "type", None) == "tool_use"]
        msg = {"role": "assistant", "content": text or None}
        if calls:
            msg["tool_calls"] = calls
        return msg

    # ---------------------------------------------------------------- HTTP
    def _post(self, payload):
        req = urllib.request.Request(self.url, data=json.dumps(payload).encode(), method="POST", headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/jarvis-assistant",  # OpenRouter likes these; others ignore
            "X-Title": "Jarvis",
        })
        try:
            with self._open(req, timeout=120) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            detail = e.read()[:400].decode("utf-8", "replace")
            if e.code == 429:
                raise RateLimitError(f"{self.label} free limit reached (429): {detail}")
            if e.code in (401, 403) or (e.code == 400 and "API_KEY_INVALID" in detail):
                raise AuthenticationError(f"{self.label} rejected the API key ({e.code}): {detail}")
            raise BrainError(f"{self.label} error {e.code}: {detail}")
        except (urllib.error.URLError, TimeoutError) as e:
            raise APIConnectionError(f"Can't reach {self.label}: {e}")

    # ---------------------------------------------------------------- the call the agent makes
    def create(self, model=None, max_tokens=4096, system=None, tools=(), messages=(), **_):
        payload = {"model": self.model, "messages": self._messages(system, messages), "max_tokens": max_tokens}
        fn_tools = self._tools(tools)
        if fn_tools:
            payload["tools"] = fn_tools
            payload["tool_choice"] = "auto"
        data = self._post(payload)
        try:
            msg = data["choices"][0]["message"]
            finish = data["choices"][0].get("finish_reason")
        except (KeyError, IndexError, TypeError):
            raise BrainError(f"{self.label} sent an unexpected reply: {str(data)[:300]}")

        blocks = []
        text = msg.get("content")
        if isinstance(text, list):  # some providers return content parts
            text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
        if text:
            blocks.append(NS(type="text", text=text, citations=None))
        for call in msg.get("tool_calls") or []:
            fn = call.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            if not call.get("id"):
                call["id"] = "call_" + uuid.uuid4().hex[:12]
            blocks.append(NS(type="tool_use", id=call["id"], name=fn.get("name", ""),
                             input=args if isinstance(args, dict) else {}))
        raw = {k: v for k, v in msg.items() if v is not None or k == "content"}
        raw["role"] = "assistant"
        for b in blocks:
            b._raw, b._provider = raw, self.name
        if not blocks:
            blocks.append(NS(type="text", text="", citations=None, _raw=raw, _provider=self.name))
        has_calls = any(b.type == "tool_use" for b in blocks)
        stop = "tool_use" if has_calls else ("max_tokens" if finish == "length" else "end_turn")
        return NS(stop_reason=stop, content=blocks)


class FallbackBrain:
    """Use the main brain; if its free limit runs out, switch to the backup for a while."""

    def __init__(self, primary, backup, cooldown=600):
        import time
        self._time = time.time
        self.primary, self.backup, self.cooldown = primary, backup, cooldown
        self._primary_blocked_until = 0
        self.messages = self

    def create(self, **kw):
        if self._time() >= self._primary_blocked_until:
            try:
                return self.primary.messages.create(**kw)
            except (RateLimitError, AuthenticationError) as e:
                print(f"Main brain unavailable, using backup: {e}", flush=True)
                self._primary_blocked_until = self._time() + self.cooldown
        return self.backup.messages.create(**kw)


def make_brain():
    """Build the configured brain (plus backup, when one is set up)."""
    def build(name, model, url=""):
        if name == "claude":
            import anthropic
            return anthropic.Anthropic(api_key=config.API_KEY, max_retries=3)
        if name not in PRESETS:
            raise ValueError(f"Unknown brain '{name}'. Use claude, gemini, groq or openrouter.")
        return OpenAICompatBrain(name, model, url=url or None)

    primary = build(config.BRAIN, config.MODEL, config.BRAIN_URL)
    if config.BACKUP_BRAIN and config.BACKUP_BRAIN != config.BRAIN and config.BACKUP_BRAIN in PRESETS:
        return FallbackBrain(primary, build(config.BACKUP_BRAIN, config.BACKUP_MODEL, config.BACKUP_BRAIN_URL))
    return primary


def brain_key_missing():
    """Returns the variable name that's missing for the chosen brain, or ''."""
    needed = {"claude": ("ANTHROPIC_API_KEY", config.API_KEY), "gemini": ("GEMINI_API_KEY", config.GEMINI_API_KEY),
              "groq": ("GROQ_API_KEY", config.GROQ_API_KEY),
              "openrouter": ("OPENROUTER_API_KEY", config.OPENROUTER_API_KEY)}.get(config.BRAIN)
    if not needed:
        return f"JARVIS_BRAIN (unknown value '{config.BRAIN}')"
    if config.BRAIN == "openrouter" and not config.MODEL:
        return "JARVIS_MODEL (pick an OpenRouter model, e.g. one ending in :free)"
    return "" if needed[1] else needed[0]
