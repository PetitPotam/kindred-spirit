// A local preview of web/dist that behaves like Firebase Hosting: clean URLs (/guides/install serves
// guides/install.html, and the .html address redirects to the clean one), 404.html for missing pages, and the
// headers from firebase.json, including the Content-Security-Policy, so what works here works once deployed.
// Usage: node serve.mjs [port]   (default 5050, on 127.0.0.1 only)
import { createReadStream, existsSync, readFileSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = dirname(fileURLToPath(import.meta.url));
const DIST = join(ROOT, "dist");
const PORT = Number(process.argv[2] || 5050);
const hosting = JSON.parse(readFileSync(join(ROOT, "firebase.json"), "utf8")).hosting;

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".mp4": "video/mp4",
  ".vtt": "text/vtt; charset=utf-8",
  ".xml": "application/xml",
  ".txt": "text/plain; charset=utf-8",
};

// Firebase's header "source" globs: ** (any path), * (within a segment), @(a|b) (one of).
function globToRegExp(glob) {
  let re = "";
  for (let i = 0; i < glob.length; i++) {
    const c = glob[i];
    if (c === "*" && glob[i + 1] === "*") {
      re += ".*";
      i++;
      if (glob[i + 1] === "/") i++;
    } else if (c === "*") re += "[^/]*";
    else if (c === "@" && glob[i + 1] === "(") {
      const end = glob.indexOf(")", i);
      re += `(?:${glob.slice(i + 2, end)})`;
      i = end;
    } else re += c.replace(/[.+^${}()|[\]\\?]/g, "\\$&");
  }
  return new RegExp(`^/?${re}$`);
}
// A rule has a "source" glob or a "regex"; like Firebase, both are matched against the address asked for.
const headerRules = (hosting.headers || []).map((rule) => ({
  re: rule.regex ? new RegExp(rule.regex) : globToRegExp(rule.source),
  headers: rule.headers,
}));

function headersFor(requestPath) {
  const out = {};
  for (const rule of headerRules) {
    if (rule.re.test(requestPath)) for (const { key, value } of rule.headers) out[key] = value;
  }
  delete out["Strict-Transport-Security"]; // not on plain http://127.0.0.1
  return out;
}

function find(urlPath) {
  const clean = normalize(decodeURIComponent(urlPath)).replace(/^(\.\.[/\\])+/, "");
  const candidates = clean.endsWith("/") ? [join(clean, "index.html")] : [clean, `${clean}.html`, join(clean, "index.html")];
  for (const rel of candidates) {
    const abs = join(DIST, rel);
    if (abs.startsWith(DIST) && existsSync(abs) && statSync(abs).isFile()) return { abs, rel: rel.replace(/\\/g, "/") };
  }
  return null;
}

createServer((req, res) => {
  const url = new URL(req.url, "http://localhost");
  let path = url.pathname;
  if (path.endsWith(".html")) {
    const to = path.replace(/(index)?\.html$/, "");
    res.writeHead(301, { Location: to + url.search });
    return res.end();
  }
  const dirIndex = !path.endsWith("/") && existsSync(join(DIST, path, "index.html"));
  if (dirIndex) {
    res.writeHead(301, { Location: `${path}/${url.search}` });
    return res.end();
  }
  let found = find(path);
  let status = 200;
  if (!found) {
    found = { abs: join(DIST, "404.html"), rel: "/404.html" };
    status = 404;
  }
  const size = statSync(found.abs).size;
  const headers = { "Content-Type": TYPES[extname(found.abs)] || "application/octet-stream", ...headersFor(decodeURIComponent(path)) };
  const range = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range || "");
  if (range && status === 200) {
    const start = range[1] ? Number(range[1]) : 0;
    const end = range[2] ? Math.min(Number(range[2]), size - 1) : size - 1;
    res.writeHead(206, { ...headers, "Content-Range": `bytes ${start}-${end}/${size}`, "Content-Length": end - start + 1, "Accept-Ranges": "bytes" });
    return createReadStream(found.abs, { start, end }).pipe(res);
  }
  res.writeHead(status, { ...headers, "Content-Length": size, "Accept-Ranges": "bytes" });
  if (req.method === "HEAD") return res.end();
  createReadStream(found.abs).pipe(res);
}).listen(PORT, "127.0.0.1", () => console.log(`Preview: http://127.0.0.1:${PORT}/`));
