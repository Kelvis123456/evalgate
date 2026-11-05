// WCAG 2.x contrast for the text/background pairs the theme actually uses.
// Reads the tokens straight from src/styles/evalgate.css so it cannot drift.
// Exits 1 if any text pair is under 4.5:1.
import { readFileSync } from "node:fs";

const css = readFileSync(
  new URL("../src/styles/evalgate.css", import.meta.url),
  "utf8",
);

function tokens(block) {
  return Object.fromEntries(
    [...block.matchAll(/(--[\w-]+):\s*(#[0-9a-fA-F]{6}|var\(--[\w-]+\))/g)].map(
      (m) => [m[1], m[2]],
    ),
  );
}

const darkBlock = css.match(/:root\s*\{([^}]*)\}/)?.[1] ?? "";
const lightBlock =
  css.match(/:root\[data-theme=['"]light['"]\]\s*\{([^}]*)\}/)?.[1] ?? "";

// Values may be var(--other); resolve them within the theme.
function resolve(map) {
  const out = {};
  for (const [k, v] of Object.entries(map)) {
    let val = v;
    while (val.startsWith("var(")) val = map[val.slice(4, -1)];
    out[k] = val;
  }
  return out;
}
const base = tokens(darkBlock);
const dark = resolve(base);
const light = resolve({
  ...base,
  ...tokens(lightBlock),
});

const lin = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((i) =>
    lin(parseInt(hex.slice(i, i + 2), 16) / 255),
  );
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function ratio(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// [label, foreground token, background token]
const pairs = [
  ["body text on page", "--sl-color-gray-2", "--sl-color-black"],
  ["headings / strong on page", "--sl-color-white", "--sl-color-black"],
  ["muted text on page", "--sl-color-gray-3", "--sl-color-black"],
  ["muted text on sidebar", "--sl-color-gray-3", "--sl-color-bg-sidebar"],
  ["body text on sidebar", "--sl-color-gray-2", "--sl-color-bg-sidebar"],
  ["link / accent text on page", "--sl-color-accent-high", "--sl-color-black"],
  [
    "link / accent text on sidebar",
    "--sl-color-accent-high",
    "--sl-color-bg-sidebar",
  ],
  ["current sidebar item", "--sl-color-accent-high", "--sl-color-accent-low"],
  ["button label on accent", "--sl-color-black", "--sl-color-accent"],
  ["inline code on its chip", "--sl-color-gray-2", "--sl-color-gray-6"],
  ["PASS chip", "--eg-pass", "--eg-pass-bg"],
  ["FAIL chip", "--eg-fail", "--eg-fail-bg"],
];

// Starlight puts inline code on gray-5 in dark and gray-6 in light.
const codeBg = { dark: "--sl-color-gray-5", light: "--sl-color-gray-6" };

let failed = false;
for (const [name, theme] of [
  ["dark", dark],
  ["light", light],
]) {
  console.log(`\n${name} theme`);
  for (const [label, fg, bg0] of pairs) {
    const bg = label === "inline code on its chip" ? codeBg[name] : bg0;
    const r = ratio(theme[fg], theme[bg]);
    const ok = r >= 4.5;
    if (!ok) failed = true;
    console.log(
      `  ${ok ? "ok  " : "FAIL"} ${r.toFixed(2).padStart(5)}:1  ${label}  (${theme[fg]} on ${theme[bg]})`,
    );
  }
}
process.exit(failed ? 1 : 0);
