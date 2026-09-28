/* ============================================================
   SEO snapshot — what a search engine and a customer see on every
   page, written down so a rebuild can be held to it.

     node scripts/seo-snapshot.mjs baseline <dir>   write seo/baseline.json
     node scripts/seo-snapshot.mjs check <dir>      compare, exit 1 on any difference

   <dir> is a folder of built HTML (normally out/). The baseline was
   first taken from the hand-built static site this Next.js app
   replaced, so a passing check means the migration changed nothing
   Google reads. After an intended change (a new price, new copy),
   rebuild and re-run `baseline`, and review the diff in git.

   Deliberately ignored, because they are not content:
     - the build date ("Last updated", sitemap lastmod)
     - scripts and stylesheets that belong to the framework, and the empty
       <div hidden> Next.js puts at the top of <body>
     - rel=preload hints: they change how fast a page loads, not what it
       says (React adds its own for the font stylesheet and for any image
       marked fetchPriority="high")
     - links written as /index.html, which now point at / (the
       canonical URL the page already declared)
   ============================================================ */

import { readFileSync, writeFileSync, existsSync, readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import * as cheerio from "cheerio";

const SITE = "https://kfoods.lk";
const here = dirname(fileURLToPath(import.meta.url));
const BASELINE = join(here, "..", "seo", "baseline.json");

const BLOCK = new Set([
  "address", "article", "aside", "blockquote", "br", "caption", "dd", "details", "div",
  "dl", "dt", "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3",
  "h4", "h5", "h6", "header", "hr", "legend", "li", "main", "nav", "ol", "option", "p",
  "section", "select", "summary", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul"
]);
const SKIP = new Set(["script", "style", "noscript", "template"]);

function pages(dir) {
  const list = ["index.html", "cart.html", "korean-ramen-price-sri-lanka.html"];
  for (const f of readdirSync(join(dir, "products")).sort()) {
    if (f.endsWith(".html")) list.push(`products/${f}`);
  }
  return list;
}

/* Resolve an href/src the way the browser would, then normalise the
   differences that are not differences: ?v=N cache busters and the
   /index.html spelling of the home page. */
function resolve(ref, page) {
  if (ref === undefined || ref === null) return null;
  const base = `${SITE}/${page}`;
  let u;
  try { u = new URL(ref, base); } catch { return ref; }
  if (u.origin === SITE) {
    u.searchParams.delete("v");
    if (u.pathname === "/index.html") u.pathname = "/";
  }
  const s = u.toString();
  /* a same-page fragment stays a fragment, whichever way it was written */
  if (u.origin === SITE && u.hash && `${u.origin}${u.pathname}` === pageUrl(page)) return u.hash;
  return s;
}

function pageUrl(page) {
  return page === "index.html" ? `${SITE}/` : `${SITE}/${page}`;
}

function canonicalJson(v) {
  if (Array.isArray(v)) return v.map(canonicalJson);
  if (v && typeof v === "object") {
    return Object.fromEntries(Object.keys(v).sort().map((k) => [k, canonicalJson(v[k])]));
  }
  return v;
}

function visibleText($, root) {
  let out = "";
  const walk = (node) => {
    /* a newline in the source is just whitespace; only blocks break lines */
    if (node.type === "text") { out += node.data.replace(/\s+/g, " "); return; }
    if (node.type !== "tag") return;
    const tag = node.name;
    if (SKIP.has(tag)) return;
    if (BLOCK.has(tag)) out += "\n";
    for (const c of node.children || []) walk(c);
    if (BLOCK.has(tag)) out += "\n";
  };
  walk(root);
  return out
    .split("\n")
    .map((l) => l.replace(/\s+/g, " ").trim())
    .filter(Boolean)
    /* the price page states its build date */
    .map((l) => l.replace(/Last updated [A-Z][a-z]+ \d{1,2}, \d{4}\./, "Last updated <date>."))
    .join("\n");
}

/* The element tree as tag.class, so a missing wrapper or a renamed class
   — the things that change how the page looks — shows up. */
function skeleton($, root) {
  const out = [];
  const walk = (node, depth) => {
    if (node.type !== "tag" || SKIP.has(node.name)) return;
    if (depth === 0 && node.name === "div" && $(node).attr("hidden") !== undefined && !$(node).children().length) return;
    const cls = ($(node).attr("class") || "").split(/\s+/).filter(Boolean).sort().join(".");
    const id = $(node).attr("id");
    out.push(`${"  ".repeat(depth)}${node.name}${cls ? "." + cls : ""}${id ? "#" + id : ""}`);
    for (const c of node.children || []) walk(c, depth + 1);
  };
  for (const c of root.children || []) walk(c, 0);
  return out;
}

function snapshot(html, page) {
  const $ = cheerio.load(html);
  const attr = (el, name) => $(el).attr(name) ?? null;

  const meta = [];
  $("head meta").each((_, el) => {
    const key = attr(el, "name") || attr(el, "property");
    if (!key) return;                        /* charset */
    let content = attr(el, "content");
    if (key === "viewport") content = content.replace(/initial-scale=1\.0\b/, "initial-scale=1");
    if (key === "next-size-adjust") return;
    meta.push(`${key}=${content}`);
  });
  meta.sort();

  const headLinks = [];
  $("head link").each((_, el) => {
    const rel = attr(el, "rel");
    if (rel === "preload") return;
    const href = resolve(attr(el, "href"), page);
    /* the site's own stylesheet and script preloads are the framework's
       business; the font stylesheet and every hint we wrote are content */
    if (href && href.startsWith(`${SITE}/_next/`)) return;
    if (href === `${SITE}/styles.css`) return;
    const extra = ["as", "type", "crossorigin", "fetchpriority"]
      .map((a) => (attr(el, a) !== null ? `${a}=${attr(el, a)}` : null))
      .filter(Boolean).join(" ");
    headLinks.push(`${rel} ${href}${extra ? " " + extra : ""}`);
  });
  headLinks.sort();

  const jsonld = [];
  $('script[type="application/ld+json"]').each((_, el) => {
    jsonld.push(JSON.stringify(canonicalJson(JSON.parse($(el).text()))));
  });
  jsonld.sort();

  const body = $("body").get(0);
  const headings = [];
  $("body h1, body h2, body h3").each((_, el) => {
    headings.push(`${el.name}: ${$(el).text().replace(/\s+/g, " ").trim()}`);
  });

  const links = [];
  $("body a").each((_, el) => {
    const parts = [resolve(attr(el, "href"), page), $(el).text().replace(/\s+/g, " ").trim()];
    for (const a of ["rel", "target", "aria-label", "aria-hidden", "tabindex", "aria-current"]) {
      if (attr(el, a) !== null) parts.push(`${a}=${attr(el, a)}`);
    }
    links.push(parts.join(" | "));
  });

  const images = [];
  $("body img").each((_, el) => {
    if ($(el).closest("noscript").length) return;
    const parts = [resolve(attr(el, "src"), page), `alt=${attr(el, "alt")}`];
    for (const a of ["width", "height", "loading", "decoding", "fetchpriority", "aria-hidden"]) {
      if (attr(el, a) !== null) parts.push(`${a}=${attr(el, a)}`);
    }
    images.push(parts.join(" | "));
  });

  const controls = [];
  $("body input, body select, body textarea, body button").each((_, el) => {
    const parts = [el.name];
    for (const a of ["id", "name", "type", "value", "required", "checked", "disabled", "pattern",
      "placeholder", "autocomplete", "inputmode", "min", "rows", "aria-label", "aria-disabled",
      "data-add-sku", "data-filter", "data-qty-step", "data-step", "data-use-qty", "data-cart-href"]) {
      if (attr(el, a) === null) continue;
      parts.push(`${a}=${a === "data-cart-href" ? resolve(attr(el, a), page) : attr(el, a)}`);
    }
    if (el.name === "button") parts.push(`"${$(el).text().replace(/\s+/g, " ").trim()}"`);
    controls.push(parts.join(" "));
  });

  const noscript = [];
  $("noscript").each((_, el) => {
    const inner = cheerio.load($(el).html() || "");
    inner("img").each((__, img) => noscript.push(`img ${inner(img).attr("src")}`));
  });

  return {
    lang: $("html").attr("lang") ?? null,
    title: $("head title").text(),
    meta,
    headLinks,
    jsonld,
    headings,
    text: visibleText($, body),
    links,
    images,
    controls,
    noscript,
    skeleton: skeleton($, body)
  };
}

function build(dir) {
  const out = {};
  for (const page of pages(dir)) {
    out[page] = snapshot(readFileSync(join(dir, page), "utf8"), page);
  }
  return out;
}

function diffList(a, b) {
  /* a small LCS diff, enough to point at the line that moved */
  const n = a.length, m = b.length;
  const dp = Array.from({ length: n + 1 }, () => new Int32Array(m + 1));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const lines = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) { i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) lines.push(`  - ${a[i++]}`);
    else lines.push(`  + ${b[j++]}`);
  }
  while (i < n) lines.push(`  - ${a[i++]}`);
  while (j < m) lines.push(`  + ${b[j++]}`);
  return lines;
}

function compare(base, now) {
  let problems = 0;
  const pagesAll = new Set([...Object.keys(base), ...Object.keys(now)]);
  for (const page of [...pagesAll].sort()) {
    if (!base[page]) { console.log(`\n${page}: new page, not in the baseline`); problems++; continue; }
    if (!now[page]) { console.log(`\n${page}: MISSING from the build`); problems++; continue; }
    for (const key of Object.keys(base[page])) {
      const a = base[page][key], b = now[page][key];
      if (JSON.stringify(a) === JSON.stringify(b)) continue;
      problems++;
      console.log(`\n${page} — ${key}`);
      const la = Array.isArray(a) ? a : String(a).split("\n");
      const lb = Array.isArray(b) ? b : String(b).split("\n");
      for (const l of diffList(la, lb).slice(0, 40)) console.log(l);
    }
  }
  return problems;
}

const [mode, dir] = process.argv.slice(2);
if (!["baseline", "check"].includes(mode) || !dir) {
  console.error("usage: node scripts/seo-snapshot.mjs baseline|check <dir>");
  process.exit(2);
}
if (!existsSync(join(dir, "index.html"))) {
  console.error(`${dir}/index.html not found — build the site first (npm run build)`);
  process.exit(2);
}

const now = build(dir);
if (mode === "baseline") {
  writeFileSync(BASELINE, JSON.stringify(now, null, 2) + "\n");
  console.log(`seo/baseline.json written (${Object.keys(now).length} pages)`);
} else {
  const base = JSON.parse(readFileSync(BASELINE, "utf8"));
  const problems = compare(base, now);
  if (problems) {
    console.log(`\n${problems} difference(s) from seo/baseline.json`);
    process.exit(1);
  }
  console.log(`SEO snapshot matches the baseline (${Object.keys(now).length} pages)`);
}
