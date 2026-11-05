# evalgate docs

The documentation site for evalgate, built with [Astro Starlight](https://starlight.astro.build). It lives in its own folder with its own `package.json` so the Python package stays free of Node.

## Develop

```
cd docs-site
npm ci
npm run dev        # http://localhost:4321
npm run build      # static site in dist/, search index included (Pagefind)
npm run check-links     # every internal link and #anchor in dist/ must resolve
npm run check-contrast  # WCAG ratios for the theme tokens in both themes
```

Run `npm run build` before `check-links`; it reads `dist/`.

Versions are pinned exactly. `.npmrc` sets `ignore-scripts=true`, so install scripts of dependencies never run, and `min-release-age=7`. Note that npm 11.8 prints "Unknown project config min-release-age" and ignores that key, so the age rule is only enforced by hand: new versions were picked at least two weeks old.

## What is placeholder

`site` in `astro.config.mjs` is `https://docs.evalgate.example`. It feeds the sitemap, canonical links and `og:image`, and `public/robots.txt` repeats it. Replace both before publishing.

## Deploying

Nothing is deployed and there is no deploy config on purpose: the repository is private and where to host the docs is a later decision. The output is plain static files in `dist/`, so any static host works. `.github/workflows/docs.yml` only builds and checks the site on changes under `docs-site/`.

## Content rules

Command output on these pages is copied from real runs of the code, not written by hand. If the CLI, a metric or the baseline format changes, rerun the commands and update the pages in the same change.

Fonts are self-hosted through fontsource (Fraunces for headings, IBM Plex Sans and Mono for text and code). `public/og.png` is a 1200x630 render of the wordmark.
