/*
 * Brilliant Earth → marquise gallery extractor
 * -------------------------------------------------
 * The build environment that generated this gallery cannot reach
 * brilliantearth.com (network policy + bot protection), but YOUR browser can.
 * Run this in your own Chrome (or via Claude for Chrome) to pull the real
 * product data + angle photo URLs, then paste the JSON back to Claude and it
 * will swap the illustrations for the real photography.
 *
 * HOW TO USE
 * 1. Open a Brilliant Earth marquise page in Chrome, e.g.
 *      https://www.brilliantearth.com/engagement-rings/marquise/
 *    or an individual product page (best image coverage), e.g.
 *      https://www.brilliantearth.com/Odessa-Halo-Diamond-Ring-(1/5-ct.-tw.)-White-Gold-BE1D32H-1153217/
 * 2. Open DevTools (F12 or Cmd+Opt+I) → Console tab.
 * 3. Paste this whole file, press Enter.
 * 4. It copies a JSON blob to your clipboard (and prints it). Paste that back
 *    to Claude in this session.
 *
 * On a product page it grabs every gallery/angle image. On the listing page it
 * grabs one representative image + name + price per ring. Run it on a few
 * product pages to get all three angles for each ring.
 */
(() => {
  const abs = (u) => { try { return new URL(u, location.href).href; } catch { return u; } };
  const isRingImg = (u) =>
    /brilliantearth|cloudfront|imgix|scene7|cdn/i.test(u || '') &&
    /\.(jpe?g|png|webp|avif)(\?|$)/i.test(u || '');

  // Pull the biggest candidate from a srcset string.
  const fromSrcset = (ss) => {
    if (!ss) return null;
    const parts = ss.split(',').map((s) => s.trim().split(/\s+/)[0]).filter(Boolean);
    return parts.length ? parts[parts.length - 1] : null;
  };

  // 1) Structured data (most reliable): JSON-LD Product blocks.
  const products = [];
  document.querySelectorAll('script[type="application/ld+json"]').forEach((s) => {
    let data; try { data = JSON.parse(s.textContent); } catch { return; }
    const arr = Array.isArray(data) ? data : (data['@graph'] || [data]);
    arr.forEach((node) => {
      if (!node || !/product/i.test(node['@type'] || '')) return;
      const imgs = []
        .concat(node.image || [])
        .map((i) => (typeof i === 'string' ? i : i && i.url))
        .filter(Boolean)
        .map(abs);
      products.push({
        name: node.name || null,
        sku: node.sku || node.mpn || null,
        brand: (node.brand && (node.brand.name || node.brand)) || null,
        price: (node.offers && ([].concat(node.offers)[0] || {}).price) || null,
        priceCurrency: (node.offers && ([].concat(node.offers)[0] || {}).priceCurrency) || null,
        url: node.url ? abs(node.url) : location.href,
        images: [...new Set(imgs)],
      });
    });
  });

  // 2) Every ring image on the page (gallery thumbs, main image, zoom, og:image).
  const imgSet = new Set();
  document.querySelectorAll('img').forEach((img) => {
    [img.currentSrc, img.src, fromSrcset(img.srcset), img.dataset.src, img.dataset.zoomImage]
      .filter(Boolean).map(abs).forEach((u) => { if (isRingImg(u)) imgSet.add(u); });
  });
  document.querySelectorAll('source[srcset]').forEach((s) => {
    const u = fromSrcset(s.srcset); if (u && isRingImg(abs(u))) imgSet.add(abs(u));
  });
  const og = document.querySelector('meta[property="og:image"]');
  if (og && isRingImg(og.content)) imgSet.add(abs(og.content));

  const payload = {
    source: 'brilliantearth.com',
    pageUrl: location.href,
    pageTitle: document.title,
    extractedProducts: products,
    allRingImageUrls: [...imgSet],
  };

  const json = JSON.stringify(payload, null, 2);
  console.log('%cMarquise extractor — copy the JSON below (also copied to clipboard):',
    'color:#b08d3f;font-weight:bold');
  console.log(json);
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(json).then(
      () => console.log('%c✓ Copied to clipboard. Paste it back to Claude.', 'color:green'),
      () => console.log('Clipboard blocked — select the JSON above and copy manually.')
    );
  }
  return payload;
})();
