#!/usr/bin/env python3
from pathlib import Path
from urllib.parse import urlparse, urljoin
from urllib.request import Request, urlopen
from html.parser import HTMLParser
import json
import mimetypes
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
ASSET_DIR = ROOT / "assets" / "logos"
ASSET_DIR.mkdir(parents=True, exist_ok=True)

MAX_BYTES = 5 * 1024 * 1024
TIMEOUT = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/152 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
}


class IconParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.icons = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "link":
            return
        data = {k.lower(): v for k, v in attrs if k and v is not None}
        rel = data.get("rel", "").lower()
        href = data.get("href")
        if href and ("icon" in rel):
            self.icons.append(href)


def request_bytes(url, accept=HEADERS["Accept"]):
    headers = dict(HEADERS)
    headers["Accept"] = accept
    req = Request(url, headers=headers)
    with urlopen(req, timeout=TIMEOUT) as r:
        data = r.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("fichier trop volumineux")
        return data, (r.headers.get_content_type() or "").lower(), r.geturl()


def looks_like_image(data, content_type, url):
    if content_type.startswith("image/"):
        return True

    lower = data[:500].lower().lstrip()
    if lower.startswith(b"<svg") or b"<svg" in lower:
        return True
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if data.startswith(b"\xff\xd8\xff"):
        return True
    if data[:4] in (b"RIFF",):
        return True
    if data[:4] == b"\x00\x00\x01\x00":
        return True

    ext = Path(urlparse(url).path).suffix.lower()
    return ext in {".svg", ".png", ".jpg", ".jpeg", ".webp", ".avif", ".ico", ".gif"}


def extension_for(data, content_type, final_url):
    ext = Path(urlparse(final_url).path).suffix.lower()
    allowed = {".svg", ".png", ".jpg", ".jpeg", ".webp", ".avif", ".ico", ".gif"}
    if ext in allowed:
        return ".jpg" if ext == ".jpeg" else ext

    ct_map = {
        "image/svg+xml": ".svg",
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/avif": ".avif",
        "image/x-icon": ".ico",
        "image/vnd.microsoft.icon": ".ico",
        "image/gif": ".gif",
    }
    if content_type in ct_map:
        return ct_map[content_type]

    lower = data[:500].lower().lstrip()
    if lower.startswith(b"<svg") or b"<svg" in lower:
        return ".svg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data[:4] == b"\x00\x00\x01\x00":
        return ".ico"
    if data[:4] == b"RIFF":
        return ".webp"
    return ".img"


def safe_slug(site):
    try:
        host = urlparse(site.get("url", "")).hostname or ""
    except Exception:
        host = ""
    host = host.lower().removeprefix("www.")
    base = host.split(".")[0] if host else site.get("name", "site")
    slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
    return slug or "site"


def homepage_icon_candidates(site_url):
    candidates = []

    # 1) Icônes déclarées dans le <head>.
    try:
        html, content_type, final_url = request_bytes(
            site_url,
            accept="text/html,application/xhtml+xml,*/*;q=0.8"
        )
        text = html.decode("utf-8", errors="ignore")
        parser = IconParser()
        parser.feed(text)
        for href in parser.icons:
            candidates.append(urljoin(final_url, href))
    except Exception as e:
        print(f"  - impossible de lire la page d'accueil: {e}")

    # 2) Fallbacks classiques.
    for path in (
        "/favicon.svg",
        "/favicon.png",
        "/favicon.ico",
        "/apple-touch-icon.png",
    ):
        candidates.append(urljoin(site_url, path))

    # Déduplique en gardant l'ordre.
    return list(dict.fromkeys(candidates))


def remote_candidates(site):
    logo = (site.get("logo") or "").strip()
    site_url = (site.get("url") or "").strip()
    out = []

    if logo.startswith(("http://", "https://")):
        out.append(logo)

    # Même si une URL de logo précise casse, on essaie le site lui-même ensuite.
    if site_url.startswith(("http://", "https://")):
        out.extend(homepage_icon_candidates(site_url))

    return list(dict.fromkeys(out))


def main():
    source = INDEX.read_text(encoding="utf-8")

    match = re.search(
        r'(<script id="sites-data" type="application/json">\s*)(\[.*?\])(\s*</script>)',
        source,
        flags=re.S,
    )
    if not match:
        print("Bloc sites-data introuvable.", file=sys.stderr)
        return 1

    sites = json.loads(match.group(2))
    changed = False

    for site in sites:
        name = site.get("name", "Site")
        logo = (site.get("logo") or "").strip()

        # Déjà local ou embarqué : surtout ne pas y toucher.
        if logo and not logo.startswith(("http://", "https://")):
            print(f"✓ {name}: déjà local ({logo})")
            continue

        print(f"→ {name}")
        saved = False

        for candidate in remote_candidates(site):
            try:
                data, content_type, final_url = request_bytes(candidate)

                if not looks_like_image(data, content_type, final_url):
                    raise ValueError(f"réponse non-image ({content_type or 'type inconnu'})")

                ext = extension_for(data, content_type, final_url)
                slug = safe_slug(site)
                filename = f"{slug}{ext}"
                path = ASSET_DIR / filename

                # Supprime une ancienne version du même site avec une autre extension.
                for old in ASSET_DIR.glob(f"{slug}.*"):
                    if old != path:
                        old.unlink()

                path.write_bytes(data)
                local = path.relative_to(ROOT).as_posix()
                site["logo"] = local
                changed = True
                saved = True

                print(f"  ✓ sauvegardé: {local} ({len(data)} octets)")
                break

            except Exception as e:
                print(f"  ✗ {candidate}: {e}")

        if not saved:
            if logo:
                print("  ! logo distant conservé car le téléchargement a échoué")
            else:
                print("  ! aucune icône récupérée")

    if changed:
        new_json = json.dumps(sites, ensure_ascii=False, indent=2)
        source = (
            source[:match.start()]
            + match.group(1)
            + new_json
            + match.group(3)
            + source[match.end():]
        )
        INDEX.write_text(source, encoding="utf-8")
        print("\nindex.html mis à jour avec les chemins locaux.")
    else:
        print("\nAucun changement.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
