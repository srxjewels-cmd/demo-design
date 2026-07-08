# Marquise Cut Ring Designs — Brilliant Earth

A self-contained gallery of six marquise-cut engagement ring designs curated from
[Brilliant Earth](https://www.brilliantearth.com/engagement-rings/marquise/), each shown
from **three angles**: top, profile, and 3/4 perspective.

- **`index.html`** — the gallery. Open it directly in a browser (no build step, no
  dependencies). Ring illustrations are generated in-page as SVG.
- **`data.json`** — the structured dataset: name, setting, metal, specs, SKU, and the
  live product URL for each ring.

## A note on the photos

The task was to fetch each ring with three angle photos. Brilliant Earth's website and its
image CDN are **unreachable from this build environment** — the session's network policy
denies the host at the proxy, and the site's bot protection returns `403` to direct fetches.
So the real photography could not be downloaded here.

What is real: every ring's **name, setting, metal, specs, SKU, and product link** were
gathered from Brilliant Earth product/category pages via web search. The three angle views
are **hand-built SVG illustrations** standing in for the blocked photography — nothing is
broken or hotlinked. Each card links to its live product page, where the actual photos can
be viewed.

To swap in the real photos, replace the `topView` / `sideView` / `perspView` SVG output in
`index.html` with `<img>` tags pointing at the downloaded images (or enable network access
to `brilliantearth.com` in the environment and re-fetch).
