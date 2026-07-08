#!/usr/bin/env python3
"""
Brilliant Earth — Marquise ring photo downloader
================================================
Downloads the real product photos (all angles) for 8 marquise ring designs
from brilliantearth.com and saves them to your DESKTOP, one folder per
product:

    Desktop/
      Brilliant Earth Marquise Rings/
        01 - Aire Solitaire/
          01.jpg  02.jpg  03.jpg ...   <- real angle photos
          product.txt                  <- name + link
          open-product.url             <- double-click to open the page
        02 - Odessa Halo/
        ...

HOW TO RUN
----------
Mac:      open Terminal, type:   python3 ~/Desktop/get_be_photos.py
Windows:  open PowerShell, type: py Desktop\\get_be_photos.py
          (if 'py' is not found, install Python from python.org first)

Needs nothing besides Python itself (standard library only).
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

PRODUCTS = [
    ("Aire Solitaire",
     "https://www.brilliantearth.com/Aire-Solitaire-Ring-Gold-BE15547-43100876/"),
    ("Odessa Halo",
     "https://www.brilliantearth.com/Odessa-Halo-Diamond-Ring-(1/5-ct.-tw.)-White-Gold-BE1D32H-1153217/"),
    ("Simply Tacori Three Stone",
     "https://www.brilliantearth.com/Simply-Tacori-Three-Stone-Marquise-Diamond-Ring-Gold-BE1DT2685-12921126/"),
    ("Sasha Three Stone",
     "https://www.brilliantearth.com/Sasha-Three-Stone-Marquise-Diamond-Ring-(1/3-ct.-tw.)-White-Gold-BE1D384-52875428/"),
    ("Secret Garden",
     "https://www.brilliantearth.com/Secret-Garden-Diamond-Ring-(1/2-ct.-tw.)-Gold-BE1D6351-8721404/"),
    ("East-West Marquise (collection)",
     "https://www.brilliantearth.com/engagement-rings/east-west/"),
    ("Petite Elodie",
     "https://www.brilliantearth.com/Petite-Elodie-1.5mm-Ring-White-Gold-BE18959-9027465/"),
    ("Custom Marquise Halo (Blue Diamond)",
     "https://www.brilliantearth.com/custom-rings/Marquise-Halo-Blue-Diamond-Ring-8833670/"),
]

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "en-US,en;q=0.9",
}

MAX_IMAGES_PER_PRODUCT = 12

IMG_URL_RE = re.compile(
    r'https?://[^\s"\'<>\\]+?\.(?:jpe?g|png|webp)(?:\?[^\s"\'<>\\]*)?', re.I)
SKIP_RE = re.compile(r'logo|sprite|icon|favicon|placeholder|swatch|flag|badge', re.I)
KEEP_RE = re.compile(r'brilliantearth|/media/|product|ring|top|side|angle|perspective', re.I)


def fetch(url, referer=None, binary=False, timeout=40):
    headers = dict(HEADERS)
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    return data if binary else data.decode("utf-8", "replace")


def parse_images(html):
    """Collect product image URLs: JSON-LD first (canonical angles), then
    og:image, then any product-looking image URL in the page."""
    urls = []

    # 1) JSON-LD Product blocks — Brilliant Earth lists the angle shots here.
    for m in re.finditer(
            r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>',
            html, re.S | re.I):
        try:
            data = json.loads(m.group(1).strip())
        except ValueError:
            continue
        if isinstance(data, list):
            nodes = data
        elif isinstance(data, dict):
            nodes = data.get("@graph", [data])
        else:
            continue
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if "product" not in str(node.get("@type", "")).lower():
                continue
            imgs = node.get("image") or []
            if isinstance(imgs, (str, dict)):
                imgs = [imgs]
            for img in imgs:
                u = img.get("url") if isinstance(img, dict) else img
                if u:
                    urls.append(u)

    # 2) og:image
    m = (re.search(r'property=["\']og:image["\'][^>]*content=["\']([^"\']+)', html)
         or re.search(r'content=["\']([^"\']+)["\'][^>]*property=["\']og:image', html))
    if m:
        urls.append(m.group(1))

    # 3) Everything else that looks like a product photo.
    for u in IMG_URL_RE.findall(html):
        if KEEP_RE.search(u):
            urls.append(u)

    # Dedupe preserving order, drop obvious non-product assets.
    seen, out = set(), []
    for u in urls:
        u = u.replace("&amp;", "&")
        if u in seen or SKIP_RE.search(u):
            continue
        seen.add(u)
        out.append(u)
    return out[:MAX_IMAGES_PER_PRODUCT]


def desktop_dir():
    home = Path.home()
    for cand in (home / "Desktop",
                 home / "OneDrive" / "Desktop",
                 home / "OneDrive - Personal" / "Desktop"):
        if cand.is_dir():
            return cand
    d = home / "Desktop"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ext_of(url):
    path = url.split("?")[0].lower()
    for e in (".jpeg", ".jpg", ".png", ".webp"):
        if path.endswith(e):
            return ".jpg" if e == ".jpeg" else e
    return ".jpg"


def main():
    products = PRODUCTS
    # Hidden test hook: --products file.json overrides the product list.
    if len(sys.argv) == 3 and sys.argv[1] == "--products":
        products = [tuple(p) for p in json.load(open(sys.argv[2]))]

    base = desktop_dir() / "Brilliant Earth Marquise Rings"
    base.mkdir(parents=True, exist_ok=True)
    print(f"Saving to: {base}\n")

    total_ok, total_fail = 0, 0
    for idx, (name, url) in enumerate(products, 1):
        folder = base / f"{idx:02d} - {name}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "product.txt").write_text(f"{name}\n{url}\n", encoding="utf-8")
        (folder / "open-product.url").write_text(
            f"[InternetShortcut]\nURL={url}\n", encoding="utf-8")

        print(f"[{idx}/{len(products)}] {name}")
        try:
            html = fetch(url)
        except Exception as e:  # noqa: BLE001 — report and continue
            print(f"    ! Could not load the page ({e}).")
            print(f"      Open it in your browser instead: {url}")
            total_fail += 1
            continue

        images = parse_images(html)
        if not images:
            print("    ! No images found on the page — open it in your "
                  "browser and right-click > Save Image.")
            total_fail += 1
            continue

        got = 0
        for n, img_url in enumerate(images, 1):
            target = folder / f"{n:02d}{ext_of(img_url)}"
            try:
                data = fetch(img_url, referer=url, binary=True)
                if len(data) < 2048:   # skip trackers / broken responses
                    continue
                target.write_bytes(data)
                got += 1
            except Exception:
                continue
        print(f"    ✓ saved {got} photo(s)")
        total_ok += got

    print(f"\nDone. {total_ok} photos saved into '{base.name}' on your Desktop.")
    if total_fail:
        print(f"{total_fail} product(s) need a manual look — their links are "
              "in each folder's product.txt.")


if __name__ == "__main__":
    main()
