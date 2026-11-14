// Checks the built site in web/dist (run `node build.mjs` first). No dependencies: it reads the HTML with a few
// regular expressions, which is enough for pages this project writes itself. It fails on:
// - a link, image, script, stylesheet, video or caption file inside the site that doesn't exist, or a #fragment that
//   doesn't match an id on the target page;
// - a page without lang, a title, a description, exactly one <h1>, or with duplicate ids;
// - an <img> without alt, width and height; a heading level skipped (h2 to h4);
// - inline scripts, inline event handlers or style attributes (the Content-Security-Policy in firebase.json blocks
//   them, so they would break silently once deployed);
// - a script, stylesheet or font from another site in the page itself (only the cookie code may add Google Analytics,
//   after consent), and leftover {{placeholders}};
// - personal data patterns: e-mail addresses and home-folder paths.
// External links are not fetched (CI shouldn't fail because another site is down); they're listed with --external.
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = dirname(fileURLToPath(import.meta.url));
const DIST = join(ROOT, "dist");
const config = JSON.parse(readFileSync(join(ROOT, "site.config.json"), "utf8"));
const problems = [];
const external = new Set();

const walk = (dir) =>
  readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });

if (!existsSync(DIST)) {
  console.error("web/dist is missing: run `node build.mjs` first.");
  process.exit(1);
}

const files = walk(DIST);
const pages = new Map(); // URL path -> { file, ids }
for (const file of files.filter((f) => f.endsWith(".html"))) {
  const rel = relative(DIST, file).replace(/\\/g, "/");
  const html = readFileSync(file, "utf8");
  const ids = new Set([...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]));
  const url = "/" + rel.replace(/\.html$/, "").replace(/(^|\/)index$/, "$1");
  pages.set(url, { file: rel, html, ids });
}

// Resolves a site path the way Firebase Hosting does with cleanUrls: /a -> a.html, /a/ -> a/index.html, files as is.
function resolve(path) {
  if (pages.has(path)) return pages.get(path);
  if (path.endsWith("/") && pages.has(path)) return pages.get(path);
  const file = join(DIST, decodeURIComponent(path));
  if (existsSync(file) && statSync(file).isFile()) return { file: path, ids: null };
  return null;
}

for (const [url, page] of pages) {
  const { html, file } = page;
  const fail = (msg) => problems.push(`${file}: ${msg}`);

  if (!/<html lang="[a-z-]+"/.test(html)) fail("no <html lang>");
  if (!/<title>[^<]+<\/title>/.test(html)) fail("no <title>");
  if (!/<meta name="description" content="[^"]{30,}"/.test(html)) fail("no meta description (30+ characters)");
  const h1 = (html.match(/<h1[\s>]/g) || []).length;
  if (h1 !== 1) fail(`${h1} <h1> elements (one expected)`);

  const allIds = [...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]);
  const dupes = allIds.filter((id, i) => allIds.indexOf(id) !== i);
  if (dupes.length) fail(`duplicate ids: ${[...new Set(dupes)].join(", ")}`);

  let last = 1;
  for (const m of html.matchAll(/<h([1-6])[\s>]/g)) {
    const level = Number(m[1]);
    if (level > last + 1) fail(`heading skips from h${last} to h${level}`);
    last = level;
  }

  for (const m of html.matchAll(/<img\b[^>]*>/g)) {
    const tag = m[0];
    if (!/\balt="/.test(tag)) fail(`<img> without alt: ${tag.slice(0, 80)}`);
    if (!/\bwidth="\d+"/.test(tag) || !/\bheight="\d+"/.test(tag)) fail(`<img> without width and height: ${tag.slice(0, 80)}`);
  }

  for (const m of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script\b[^>]*>/gi)) {
    if (!/\bsrc="/.test(m[1])) fail("inline <script> (blocked by the Content-Security-Policy)");
    else if (/\bsrc="(https?:)?\/\//.test(m[1])) fail(`script from another site: ${m[1].trim()}`);
  }
  if (/\son[a-z]+="/i.test(html)) fail("inline event handler (on...=) is blocked by the Content-Security-Policy");
  if (/\sstyle="/.test(html)) fail("style attribute is blocked by the Content-Security-Policy");
  if (/<style\b/.test(html)) fail("<style> element is blocked by the Content-Security-Policy");
  for (const m of html.matchAll(/<link\b[^>]*rel="stylesheet"[^>]*>/g)) {
    if (/href="(https?:)?\/\//.test(m[0])) fail(`stylesheet from another site: ${m[0]}`);
  }
  if (/\{\{[\w.]+\}\}/.test(html)) fail("leftover {{placeholder}}");
  for (const m of html.matchAll(/[\w.+-]+@[\w-]+\.[a-z]{2,}/gi)) fail(`looks like an e-mail address: ${m[0]}`);
  if (/\/Users\/[\w.-]+|\/home\/[\w.-]+|C:\\Users\\/i.test(html)) fail("home-folder path");

  // Links and references
  for (const m of html.matchAll(/\s(href|src|poster|data-src|data-captions)="([^"]*)"/g)) {
    const [, attr, value] = m;
    if (!value) {
      if (attr !== "data-src") fail(`empty ${attr}`);
      continue;
    }
    if (/^\s*(javascript|vbscript):/i.test(value)) {
      fail(`script link (${value.slice(0, 20)})`);
      continue;
    }
    if (/^data:/i.test(value) && attr === "href") {
      fail(`data: link`);
      continue;
    }
    if (/^(mailto:|tel:|data:)/i.test(value)) continue;
    if (/^https?:\/\//.test(value)) {
      if (value.startsWith(config.siteUrl)) continue; // canonical and social tags point at the live site
      external.add(value);
      continue;
    }
    const [pathPart, fragment] = value.split("#");
    let path = pathPart;
    if (!path) path = url; // "#id" on the same page
    else if (!path.startsWith("/")) {
      fail(`relative link "${value}": use a path from the site root`);
      continue;
    }
    const target = resolve(path);
    if (!target) {
      fail(`${attr}="${value}": no such page or file`);
      continue;
    }
    if (fragment && target.ids && !target.ids.has(fragment)) fail(`${attr}="${value}": no id "${fragment}" on ${target.file}`);
  }
}

for (const required of ["404.html", "sitemap.xml", "robots.txt"]) {
  if (!existsSync(join(DIST, required))) problems.push(`missing ${required}`);
}

if (process.argv.includes("--external")) {
  console.log([...external].sort().join("\n"));
}

if (problems.length) {
  console.error(`${problems.length} problem(s):\n- ${problems.join("\n- ")}`);
  process.exit(1);
}
console.log(`Checked ${pages.size} pages and their links: all good (${external.size} external links not fetched).`);
