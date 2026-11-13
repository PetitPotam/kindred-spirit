// Builds the website into web/dist with Node's standard library only (no dependencies to install or update).
//
// Each page in src/pages is a fragment of HTML with a small header:
//
//   ---
//   title: Install and set up
//   description: One sentence for search engines and link previews.
//   section: guides            (which top menu item is highlighted)
//   layout: guide              (default | guide | legal)
//   scripts: video             (extra scripts from src/assets, comma separated)
//   ---
//   <h1>...</h1> ...
//
// {{name}} in a page or the layout is replaced from site.config.json and the values below; an unknown name stops
// the build, so a typo can't reach the site. src/pages/guides/install.html becomes dist/guides/install.html, served
// as /guides/install (Firebase's cleanUrls); an index.html is served as its folder (/guides/).
import { createHash } from "node:crypto";
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = dirname(fileURLToPath(import.meta.url));
const SRC = join(ROOT, "src");
const OUT = join(ROOT, "dist");
const config = JSON.parse(readFileSync(join(ROOT, "site.config.json"), "utf8"));

const walk = (dir) =>
  readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });

export function parsePage(text, file) {
  const match = /^---\n([\s\S]*?)\n---\n/.exec(text);
  if (!match) throw new Error(`${file}: the page must start with a --- header ---`);
  const meta = {};
  for (const line of match[1].split("\n")) {
    const m = /^(\w+):\s*(.*)$/.exec(line.trim());
    if (m) meta[m[1]] = m[2];
  }
  for (const key of ["title", "description"]) {
    if (!meta[key]) throw new Error(`${file}: missing "${key}" in the header`);
  }
  return { meta, body: text.slice(match[0].length) };
}

export function fill(template, values, file) {
  return template.replace(/\{\{([\w.]+)\}\}/g, (_, name) => {
    const value = name.split(".").reduce((v, k) => (v == null ? undefined : v[k]), values);
    if (value == null) throw new Error(`${file}: unknown {{${name}}}`);
    return String(value);
  });
}

export function urlFor(relPath) {
  const path = "/" + relPath.replace(/\\/g, "/").replace(/\.html$/, "");
  return path.endsWith("/index") ? path.slice(0, -"index".length) : path;
}

const escapeHtml = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

function guideNav(current) {
  const items = config.guides
    .map(([slug, title]) => {
      const here = slug === current ? ' aria-current="page"' : "";
      return `<li><a href="/guides/${slug}"${here}>${title}</a></li>`;
    })
    .join("");
  return `<nav class="guide-nav" aria-label="Guides"><p class="guide-nav-title"><a href="/guides/">All guides</a></p><ol>${items}</ol></nav>`;
}

function guidePager(current) {
  const i = config.guides.findIndex(([slug]) => slug === current);
  if (i < 0) return "";
  const prev = config.guides[i - 1];
  const next = config.guides[i + 1];
  const link = (g, rel, label) =>
    g ? `<a class="pager-${rel}" rel="${rel}" href="/guides/${g[0]}"><span>${label}</span>${g[1]}</a>` : "<span></span>";
  return `<nav class="pager" aria-label="Previous and next guide">${link(prev, "prev", "Previous")}${link(next, "next", "Next")}</nav>`;
}

function wrap(meta, body, relPath) {
  if (meta.layout === "guide") {
    const slug = relPath.replace(/^guides\//, "").replace(/\.html$/, "");
    return `<div class="guide-layout wrap">${guideNav(slug)}<article class="prose guide">${body}${guidePager(slug)}</article></div>`;
  }
  if (meta.layout === "legal") {
    return `<div class="wrap"><article class="prose legal">${body}</article></div>`;
  }
  return body;
}

export function build() {
  rmSync(OUT, { recursive: true, force: true });
  mkdirSync(OUT, { recursive: true });
  for (const dir of ["img", "media"]) {
    if (existsSync(join(SRC, dir))) cpSync(join(SRC, dir), join(OUT, dir), { recursive: true });
  }
  cpSync(join(SRC, "static"), OUT, { recursive: true });

  // Stylesheets and scripts get their content's hash in their name, so they can be cached for a year.
  const assets = {};
  mkdirSync(join(OUT, "assets"), { recursive: true });
  for (const file of readdirSync(join(SRC, "assets"))) {
    const text = readFileSync(join(SRC, "assets", file));
    const hash = createHash("sha256").update(text).digest("hex").slice(0, 10);
    const name = file.replace(/\.(\w+)$/, `.${hash}.$1`);
    writeFileSync(join(OUT, "assets", name), text);
    assets[file.replace(/\.(\w+)$/, "_$1")] = `/assets/${name}`;
  }

  const layout = readFileSync(join(SRC, "layout.html"), "utf8");
  const pagesDir = join(SRC, "pages");
  const urls = [];
  for (const file of walk(pagesDir).filter((f) => f.endsWith(".html"))) {
    const rel = relative(pagesDir, file);
    const { meta, body } = parsePage(readFileSync(file, "utf8"), rel);
    const url = urlFor(rel);
    const scripts = (meta.scripts || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean)
      .map((s) => {
        const src = assets[`${s}_js`];
        if (!src) throw new Error(`${rel}: no script src/assets/${s}.js`);
        return `<script src="${src}" defer></script>`;
      })
      .join("");
    const values = {
      ...config,
      assets,
      page: { ...meta, url, scripts, fullTitle: meta.title === config.siteName ? meta.title : `${meta.title} · ${config.siteName}` },
      year: "2026",
      analyticsCookie: `_ga_${config.measurementId.replace(/^G-/, "")}`,
      blob: `${config.repo}/blob/main`,
      tree: `${config.repo}/tree/main`,
      issues: `${config.repo}/issues`,
      milestones: `${config.repo}/milestones`,
    };
    const content = fill(wrap(meta, body, rel), values, rel);
    const nav = (section) => (meta.section === section ? ' aria-current="page"' : "");
    values.page.fullTitle = escapeHtml(values.page.fullTitle);
    values.page.description = escapeHtml(meta.description);
    const navState = Object.fromEntries(["guides", "roadmap", "contributing", "credits"].map((s) => [s, nav(s)]));
    const html = fill(layout, { ...values, content, nav: navState }, "layout.html");
    const outFile = join(OUT, rel);
    mkdirSync(dirname(outFile), { recursive: true });
    writeFileSync(outFile, html);
    if (rel !== "404.html") urls.push(url);
  }

  urls.sort();
  writeFileSync(
    join(OUT, "sitemap.xml"),
    `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls
      .map((u) => `  <url><loc>${config.siteUrl}${u}</loc></url>`)
      .join("\n")}\n</urlset>\n`,
  );
  writeFileSync(join(OUT, "robots.txt"), `User-agent: *\nAllow: /\n\nSitemap: ${config.siteUrl}/sitemap.xml\n`);
  return urls;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const urls = build();
  console.log(`Built ${urls.length} pages into ${relative(process.cwd(), OUT) || "."}`);
}
