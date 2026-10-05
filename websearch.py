"""Web search and page reading for brains that don't have Claude's built-in search.

Uses Tavily when TAVILY_API_KEY is set (free plan, more reliable), otherwise DuckDuckGo's
plain HTML results page (no key needed).
"""
import html
import ipaddress
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

import config

UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36"
_open = urllib.request.urlopen  # swapped out in tests


class SearchError(Exception):
    pass


def search(query, max_results=5):
    """Returns a list of {title, url, snippet}."""
    query = (query or "").strip()
    if not query:
        raise SearchError("Empty search.")
    if config.TAVILY_API_KEY:
        try:
            return _tavily(query, max_results)
        except Exception:
            pass  # fall back to DuckDuckGo
    return _duckduckgo(query, max_results)


def _tavily(query, n):
    req = urllib.request.Request("https://api.tavily.com/search", method="POST",
                                 data=json.dumps({"query": query, "max_results": n, "search_depth": "basic"}).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {config.TAVILY_API_KEY}"})
    with _open(req, timeout=20) as resp:
        data = json.loads(resp.read())
    return [{"title": r.get("title", ""), "url": r.get("url", ""), "snippet": (r.get("content") or "")[:400]}
            for r in data.get("results", [])[:n]]


def _duckduckgo(query, n):
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.8"})
    try:
        with _open(req, timeout=20) as resp:
            page = resp.read().decode("utf-8", "replace")
    except Exception as e:
        raise SearchError(f"Search is unavailable right now ({e}).")
    results = []
    for chunk in page.split('result__body')[1:]:
        link = re.search(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', chunk, re.S) or \
            re.search(r'href="([^"]+)"[^>]*class="result__a"[^>]*>(.*?)</a>', chunk, re.S)
        if not link:
            continue
        href, title = html.unescape(link.group(1)), link.group(2)
        snip = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', chunk, re.S)
        if "duckduckgo.com/l/?" in href:
            href = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("uddg", [href])[0]
        if href.startswith("//"):
            href = "https:" + href
        if "duckduckgo.com/y.js" in href or not href.startswith("http"):
            continue  # ads
        results.append({"title": _clean(title), "url": href, "snippet": _clean(snip.group(1) if snip else "")[:400]})
        if len(results) >= n:
            break
    if not results and "anomaly" in page.lower():
        raise SearchError("The search engine is asking for a captcha. Add a free TAVILY_API_KEY for reliable search.")
    return results


def _clean(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", fragment or ""))).strip()


# ---------------------------------------------------------------- reading pages
class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form", "iframe"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr", "section", "article"}

    def __init__(self):
        super().__init__()
        self.parts, self.skip, self.title, self._in_title = [], 0, "", False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        if tag == "title":
            self._in_title = True
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.skip:
            self.parts.append(data)


def _is_public(host):
    """Refuse to fetch addresses inside the server's own network."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


def read_page(url, limit=12000):
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    host = urllib.parse.urlparse(url).hostname or ""
    if not _is_public(host):
        raise SearchError("I can only open public websites.")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with _open(req, timeout=20) as resp:
            kind = resp.headers.get("Content-Type", "")
            body = resp.read(2_000_000)
    except urllib.error.HTTPError as e:
        raise SearchError(f"The page answered with error {e.code}.")
    except Exception as e:
        raise SearchError(f"Couldn't open the page ({e}).")
    if "html" not in kind and "text" not in kind:
        raise SearchError(f"That link is a {kind or 'non-text'} file, not a web page.")
    text = body.decode("utf-8", "replace")
    if "html" in kind:
        p = _Text()
        p.feed(text)
        title = p.title.strip()
        text = re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t]+", " ", "".join(p.parts))).strip()
    else:
        title = ""
    if len(text) > limit:
        text = text[:limit] + "\n...[page cut short]"
    return title, text
