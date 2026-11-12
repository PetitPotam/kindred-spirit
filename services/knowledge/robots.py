"""robots.txt, read the way big crawlers read it (RFC 9309 + the * and $ wildcards).

Python's urllib.robotparser only does prefix matching, so a rule like "Disallow: /*api.php"
(which minecraft.wiki uses) would silently allow everything. This one supports:
  * groups per User-agent (several agents may share a group), falling back to "*"
  * Allow / Disallow with * (any characters) and $ (end of URL)
  * longest matching rule wins; on a tie, Allow wins
  * Crawl-delay (seconds), honoured by the fetcher when it is slower than our own delay
"""
import re
import urllib.parse


def _pattern(path):
    """A robots path pattern -> compiled regex anchored at the start."""
    out, end = [], path.endswith("$")
    if end:
        path = path[:-1]
    for part in re.split(r"(\*)", path):
        out.append(".*" if part == "*" else re.escape(part))
    return re.compile("".join(out) + ("$" if end else ""))


class Robots:
    def __init__(self, text=""):
        self.groups = []  # [(agents, [(allow, raw, regex)], crawl_delay)]
        self._parse(text or "")

    def _parse(self, text):
        agents, rules, delay, in_rules = [], [], None, False
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            field, value = (s.strip() for s in line.split(":", 1))
            field = field.lower()
            if field == "user-agent":
                if in_rules:  # a new group starts
                    self.groups.append((agents, rules, delay))
                    agents, rules, delay, in_rules = [], [], None, False
                agents.append(value.lower())
            elif field in ("allow", "disallow"):
                in_rules = True
                if value:  # "Disallow:" (empty) allows everything
                    rules.append((field == "allow", value, _pattern(value)))
            elif field == "crawl-delay":
                in_rules = True
                try:
                    delay = float(value)
                except ValueError:
                    pass
        if agents:
            self.groups.append((agents, rules, delay))

    def _group(self, agent):
        """The most specific group for this agent (its product token), else '*'."""
        token = agent.split("/")[0].strip().lower()
        best, star = None, None
        for agents, rules, delay in self.groups:
            for a in agents:
                if a == "*":
                    star = (rules, delay) if star is None else (star[0] + rules, star[1] or delay)
                elif a and token.startswith(a):
                    best = (rules, delay) if best is None else (best[0] + rules, best[1] or delay)
        return best or star or ([], None)

    def allowed(self, url, agent="*"):
        parts = urllib.parse.urlsplit(url)
        path = (parts.path or "/") + ("?" + parts.query if parts.query else "")
        if path == "/robots.txt":
            return True
        rules, _ = self._group(agent)
        verdict, length = True, -1
        for allow, raw, rx in rules:
            if rx.match(path) or rx.match(urllib.parse.unquote(path)):
                n = len(raw)
                if n > length or (n == length and allow):
                    verdict, length = allow, n
        return verdict

    def crawl_delay(self, agent="*"):
        return self._group(agent)[1]
