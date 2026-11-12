"""A polite HTTP client for the knowledge crawler.

Being a good guest on someone else's site:
  * robots.txt is read once per host and obeyed (also for every redirect hop)
  * one request at a time per host, at most one per `delay` seconds (default 1s), slower if the
    site's Crawl-delay asks for it; 429/503 answers are retried later, honouring Retry-After
  * every response is cached on disk (gzip), and pages are re-asked with If-None-Match /
    If-Modified-Since, so an unchanged page costs a tiny 304 instead of the whole page
  * a generic User-Agent that says what this is, with no names or emails in it

The transport, clock and sleep are injectable so tests run without the network.
"""
import gzip
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from .robots import Robots

USER_AGENT = ("KindredSpiritKnowledge/0.1 (local knowledge base for a single-player Minecraft companion; "
              "slow, cached, obeys robots.txt)")
ROBOTS_TOKEN = "KindredSpiritKnowledge"


class Response:
    def __init__(self, status, headers=None, body=b"", url="", from_cache=False, not_modified=False):
        self.status = status
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.body = body
        self.url = url
        self.from_cache = from_cache
        self.not_modified = not_modified
        self.fetched = 0  # for a cached copy: when it was last fetched or confirmed (304)

    @property
    def text(self):
        ctype = self.headers.get("content-type", "")
        charset = "utf-8"
        if "charset=" in ctype:
            charset = ctype.split("charset=", 1)[1].split(";")[0].strip() or "utf-8"
        try:
            return self.body.decode(charset, "replace")
        except LookupError:
            return self.body.decode("utf-8", "replace")

    def json(self):
        return json.loads(self.body.decode("utf-8"))


class Blocked(Exception):
    """robots.txt says no: the crawler skips the URL and says so."""


class FetchError(Exception):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # we follow redirects ourselves (robots per hop)
        return None


def urllib_transport(method, url, headers, timeout):
    req = urllib.request.Request(url, method=method, headers=headers)
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, dict(r.headers.items()), r.read()
    except urllib.error.HTTPError as e:  # 3xx/4xx/5xx come here: they are answers too
        return e.code, dict(e.headers.items()) if e.headers else {}, e.read() or b""


class Fetcher:
    def __init__(self, cache_dir=None, delay=1.0, transport=None, clock=time.monotonic, sleep=time.sleep,
                 user_agent=USER_AGENT, timeout=30, retries=3, log=None):
        self.cache_dir = cache_dir
        self.delay = float(delay)
        self.transport = transport or urllib_transport
        self.clock = clock
        self.sleep = sleep
        self.user_agent = user_agent
        self.timeout = timeout
        self.retries = retries
        self.log = log or (lambda msg: None)
        self._robots = {}      # host -> Robots
        self._last = {}        # host -> time of the last request
        self.requests = 0      # network requests made (for stats)
        self.bytes = 0         # bytes downloaded
        self.not_modified = 0  # 304 answers

    # ---------------------------------------------------------------- politeness

    def _host(self, url):
        p = urllib.parse.urlsplit(url)
        return "%s://%s" % (p.scheme, p.netloc)

    def robots(self, url):
        host = self._host(url)
        if host not in self._robots:
            r = self._raw("GET", host + "/robots.txt", {})
            for _ in range(5):  # RFC 9309: follow a few redirects
                if r.status not in (301, 302, 303, 307, 308) or not r.headers.get("location"):
                    break
                r = self._raw("GET", urllib.parse.urljoin(host + "/robots.txt", r.headers["location"]), {})
            # no robots.txt (4xx) = everything allowed; a server error = be careful, allow nothing
            if r.status == 200:
                self._robots[host] = Robots(r.body.decode("utf-8", "replace"))
            elif 400 <= r.status < 500:
                self._robots[host] = Robots("")
            else:
                self._robots[host] = Robots("User-agent: *\nDisallow: /")
        return self._robots[host]

    def allowed(self, url):
        if not url.startswith(("http://", "https://")):
            return True
        return self.robots(url).allowed(url, ROBOTS_TOKEN)

    def _wait_turn(self, host):
        delay = self.delay
        rb = self._robots.get(host)
        cd = rb.crawl_delay(ROBOTS_TOKEN) if rb else None
        if cd:
            delay = max(delay, min(cd, 60.0))
        last = self._last.get(host)
        if last is not None:
            wait = last + delay - self.clock()
            if wait > 0:
                self.sleep(wait)
        self._last[host] = self.clock()

    def _raw(self, method, url, headers):
        host = self._host(url)
        hdrs = {"User-Agent": self.user_agent, "Accept-Encoding": "gzip"}
        hdrs.update(headers)
        for attempt in range(self.retries + 1):
            self._wait_turn(host)
            try:
                status, rh, body = self.transport(method, url, hdrs, self.timeout)
            except (OSError, urllib.error.URLError) as exc:
                if attempt >= self.retries:
                    raise FetchError("%s: %s" % (url, exc))
                self.sleep(min(60, 2 ** attempt * 2))
                continue
            self.requests += 1
            self.bytes += len(body or b"")
            rh = {k.lower(): v for k, v in (rh or {}).items()}
            if body and rh.get("content-encoding", "").lower() == "gzip":
                body = gzip.decompress(body)
                rh.pop("content-encoding", None)
            if status in (429, 503) and attempt < self.retries:
                wait = rh.get("retry-after", "")
                wait = float(wait) if wait.replace(".", "", 1).isdigit() else 2 ** attempt * 5
                self.log("  %s says slow down (HTTP %s): waiting %.0fs" % (host, status, wait))
                self.sleep(min(wait, 300))
                continue
            return Response(status, rh, body, url)
        raise FetchError("%s: gave up after %d tries" % (url, self.retries + 1))

    # ---------------------------------------------------------------- cache

    def _cache_paths(self, url):
        if not self.cache_dir:
            return None, None
        host = urllib.parse.urlsplit(url).netloc or "local"
        h = hashlib.sha1(url.encode("utf-8")).hexdigest()
        d = os.path.join(self.cache_dir, host.replace(":", "_"), h[:2])
        return os.path.join(d, h + ".json"), os.path.join(d, h + ".body.gz")

    def cached(self, url):
        meta_p, body_p = self._cache_paths(url)
        if not meta_p or not os.path.exists(meta_p) or not os.path.exists(body_p):
            return None
        with open(meta_p, encoding="utf-8") as f:
            meta = json.load(f)
        with gzip.open(body_p, "rb") as f:
            body = f.read()
        r = Response(meta.get("status", 200), meta.get("headers"), body, url, from_cache=True)
        r.fetched = meta.get("fetched") or 0
        return r

    def _store(self, url, r):
        meta_p, body_p = self._cache_paths(url)
        if not meta_p:
            return
        os.makedirs(os.path.dirname(meta_p), exist_ok=True)
        keep = {k: r.headers[k] for k in ("etag", "last-modified", "content-type") if k in r.headers}
        with gzip.open(body_p + ".tmp", "wb", compresslevel=6) as f:
            f.write(r.body)
        os.replace(body_p + ".tmp", body_p)
        with open(meta_p + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"url": url, "status": r.status, "headers": keep, "fetched": time.time()}, f)
        os.replace(meta_p + ".tmp", meta_p)

    def _touch(self, url):
        """A 304 says the cached copy is still right: remember when that was checked."""
        meta_p, _ = self._cache_paths(url)
        if meta_p and os.path.exists(meta_p):
            with open(meta_p, encoding="utf-8") as f:
                meta = json.load(f)
            meta["fetched"] = time.time()
            with open(meta_p + ".tmp", "w", encoding="utf-8") as f:
                json.dump(meta, f)
            os.replace(meta_p + ".tmp", meta_p)

    def drop(self, url):
        for p in self._cache_paths(url):
            if p and os.path.exists(p):
                os.remove(p)

    # ---------------------------------------------------------------- the one call sources use

    def get(self, url, revalidate=True, offline=False, max_redirects=5, max_age=None):
        """GET url politely. revalidate=False (or offline) answers from the cache when it can, and so
        does a cached copy younger than max_age seconds. A 304 comes back as the cached response
        with .not_modified = True."""
        cached = self.cached(url)
        if cached and (offline or not revalidate or (max_age and time.time() - cached.fetched < max_age)):
            return cached
        if offline:
            raise FetchError("%s: not in the cache (offline)" % url)
        hops = 0
        cur = url
        while True:
            if not self.allowed(cur):
                raise Blocked("robots.txt of %s disallows %s" % (self._host(cur), cur))
            headers = {}
            if cached and cur == url:
                if cached.headers.get("etag"):
                    headers["If-None-Match"] = cached.headers["etag"]
                if cached.headers.get("last-modified"):
                    headers["If-Modified-Since"] = cached.headers["last-modified"]
            r = self._raw("GET", cur, headers)
            if r.status == 304 and cached:
                self.not_modified += 1
                self._touch(url)
                cached.not_modified = True
                cached.from_cache = False
                return cached
            if r.status in (301, 302, 303, 307, 308) and r.headers.get("location") and hops < max_redirects:
                cur = urllib.parse.urljoin(cur, r.headers["location"])
                hops += 1
                continue
            r.url = cur
            if r.status == 200:
                self._store(url, r)
            return r
