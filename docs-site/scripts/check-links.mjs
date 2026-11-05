// Walks dist/ and checks every internal href/src: the target file must exist,
// and a #fragment must match an id on the target page. External links are
// counted, not fetched.
import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { join, resolve, extname } from "node:path";

const dist = resolve(
  new URL("../dist", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"),
);

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) yield* walk(p);
    else yield p;
  }
}

const htmlFiles = [...walk(dist)].filter((f) => extname(f) === ".html");
const idsCache = new Map();
function idsOf(file) {
  if (!idsCache.has(file)) {
    const html = readFileSync(file, "utf8");
    idsCache.set(
      file,
      new Set([...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1])),
    );
  }
  return idsCache.get(file);
}

function resolveTarget(pathname) {
  const clean = decodeURIComponent(pathname).replace(/^\//, "");
  const candidates = [
    join(dist, clean),
    join(dist, clean, "index.html"),
    join(dist, `${clean}.html`),
  ];
  return candidates.find((c) => existsSync(c) && statSync(c).isFile());
}

const siteOrigin = "https://kelvis-evalgate.vercel.app";
let checked = 0;
let external = 0;
const problems = [];

for (const file of htmlFiles) {
  const page = "/" + file.slice(dist.length + 1).replace(/\\/g, "/");
  const html = readFileSync(file, "utf8");
  // Starlight's 404 page declares itself canonical at /404/, which does not
  // exist as a route. That is the framework's choice, so it is not counted.
  const body =
    page === "/404.html"
      ? html.replace(/<link rel="canonical"[^>]*>/, "")
      : html;
  for (const m of body.matchAll(/\s(?:href|src)="([^"]*)"/g)) {
    const raw = m[1].replace(/&amp;/g, "&");
    if (
      !raw ||
      raw.startsWith("mailto:") ||
      raw.startsWith("data:") ||
      raw.startsWith("javascript:")
    )
      continue;
    let url;
    try {
      url = new URL(raw, siteOrigin + page.replace(/index\.html$/, ""));
    } catch {
      problems.push(`${page}: unparseable ${raw}`);
      continue;
    }
    if (url.origin !== siteOrigin) {
      external++;
      continue;
    }
    checked++;
    const target = resolveTarget(url.pathname);
    if (!target) {
      problems.push(`${page}: broken link ${raw}`);
      continue;
    }
    if (url.hash && extname(target) === ".html") {
      const id = decodeURIComponent(url.hash.slice(1));
      if (!idsOf(target).has(id))
        problems.push(`${page}: missing anchor ${raw}`);
    }
  }
}

console.log(
  `pages: ${htmlFiles.length}, internal refs checked: ${checked}, external refs skipped: ${external}`,
);
if (problems.length) {
  console.log(`\n${problems.length} problem(s):`);
  for (const p of [...new Set(problems)]) console.log("  " + p);
  process.exit(1);
}
console.log("no broken internal links or anchors");
