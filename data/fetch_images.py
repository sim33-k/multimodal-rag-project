"""Download attraction images from Wikimedia Commons via the Wikipedia API.

Images are not committed to the repo, so this script rebuilds the image set from
scratch on a fresh clone. It also writes data/images/IMAGE_SOURCES.md recording
where every file came from, which is what the report's acknowledgements section
is built from.

Article titles are looked up in batches of 50, which is the API's limit, because
issuing one request per attraction gets the client rate-limited very quickly.
Downloads are then spaced out and retried with backoff on HTTP 429.

Run with:  python -m data.fetch_images
"""

import io
import json
import sys
import time
from pathlib import Path

import requests
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGE_DIR = PROJECT_ROOT / "data" / "images"

WIKI_API = "https://en.wikipedia.org/w/api.php"
# Wikimedia's user-agent policy asks automated clients to identify themselves and
# give a contact address; requests without one are throttled aggressively.
HEADERS = {
    "User-Agent": "SLTourismRAG/0.1 (SCS 4203 coursework; contact via repository)"
}

MAX_EDGE_PX = 1024
REQUEST_DELAY_S = 2.5
MAX_RETRIES = 5
TITLE_BATCH_SIZE = 50

# Wikimedia's image CDN answers a burst of downloads with 429 and a Retry-After
# of ten minutes. Honouring that literally would take hours for a full run, and
# in practice requests start succeeding again well before it elapses, so the wait
# is capped and the attempt simply retried.
MAX_BACKOFF_S = 75

# Records which URL each downloaded file came from. Kept on disk so the
# attribution table survives across partial runs - without it, a resumed run
# would only know about the files it fetched that time.
SOURCES_CACHE = "_sources.json"

# attraction id -> (category folder, Wikipedia article title)
SOURCES = {
    # Beaches
    "mirissa_beach": ("beaches", "Mirissa"),
    "unawatuna_beach": ("beaches", "Unawatuna"),
    "arugam_bay": ("beaches", "Arugam Bay"),
    "hikkaduwa_beach": ("beaches", "Hikkaduwa"),
    "bentota_beach": ("beaches", "Bentota"),
    "nilaveli_beach": ("beaches", "Nilaveli"),
    "pasikuda_beach": ("beaches", "Pasikuda"),
    "tangalle_beach": ("beaches", "Tangalle"),
    "weligama_beach": ("beaches", "Weligama"),
    "negombo_beach": ("beaches", "Negombo"),
    # Mountains
    "adams_peak": ("mountains", "Adam's Peak"),
    "pidurutalagala": ("mountains", "Pidurutalagala"),
    "kirigalpotta": ("mountains", "Kirigalpotta"),
    "thotupola_kanda": ("mountains", "Thotupola Kanda"),
    "gombaniya_knuckles": ("mountains", "Knuckles Mountain Range"),
    "ella_rock": ("mountains", "Ella, Sri Lanka"),
    "little_adams_peak": ("mountains", "Little Adam's Peak"),
    "namunukula": ("mountains", "Namunukula"),
    "hakgala_rock": ("mountains", "Hakgala Botanical Garden"),
    "bathalegala": ("mountains", "Bathalegala"),
    # National parks
    "yala_national_park": ("national_parks", "Yala National Park"),
    "udawalawe_national_park": ("national_parks", "Udawalawe National Park"),
    "wilpattu_national_park": ("national_parks", "Wilpattu National Park"),
    "minneriya_national_park": ("national_parks", "Minneriya National Park"),
    "horton_plains_national_park": ("national_parks", "Horton Plains National Park"),
    "kumana_national_park": ("national_parks", "Kumana National Park"),
    "bundala_national_park": ("national_parks", "Bundala National Park"),
    "wasgamuwa_national_park": ("national_parks", "Wasgamuwa National Park"),
    "kaudulla_national_park": ("national_parks", "Kaudulla National Park"),
    "sinharaja_forest_reserve": ("national_parks", "Sinharaja Forest Reserve"),
    # Historical sites
    "sigiriya": ("historical_sites", "Sigiriya"),
    "dambulla_cave_temple": ("historical_sites", "Dambulla cave temple"),
    "polonnaruwa": ("historical_sites", "Polonnaruwa"),
    "anuradhapura": ("historical_sites", "Anuradhapura"),
    "galle_fort": ("historical_sites", "Galle Fort"),
    "temple_of_the_tooth": ("historical_sites", "Temple of the Tooth"),
    "yapahuwa": ("historical_sites", "Yapahuwa"),
    "mihintale": ("historical_sites", "Mihintale"),
    "ritigala": ("historical_sites", "Ritigala"),
    "nalanda_gedige": ("historical_sites", "Nalanda Gedige"),
}


def request_with_backoff(url: str, params: dict | None = None) -> requests.Response:
    """GET with exponential backoff, since Wikimedia returns 429 under bursty load."""
    delay = 2.0
    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, params=params, headers=HEADERS, timeout=60)
            if response.status_code == 429:
                wait = min(float(response.headers.get("Retry-After", delay)), MAX_BACKOFF_S)
                print(f"    rate limited, waiting {wait:.0f}s")
                time.sleep(wait)
                delay = min(delay * 2, MAX_BACKOFF_S)
                continue
            response.raise_for_status()
            return response
        except requests.RequestException as error:
            last_error = error
            time.sleep(delay)
            delay *= 2

    raise RuntimeError(f"gave up after {MAX_RETRIES} attempts: {last_error}")


def lead_image_urls(titles: list[str]) -> dict[str, str]:
    """Look up the main image for many articles at once.

    Returns {article title: image url}. Titles the API normalises or redirects are
    mapped back to what was asked for so the caller can match on its own keys.
    """
    resolved: dict[str, str] = {}

    for start in range(0, len(titles), TITLE_BATCH_SIZE):
        batch = titles[start : start + TITLE_BATCH_SIZE]
        response = request_with_backoff(
            WIKI_API,
            {
                "action": "query",
                "prop": "pageimages",
                "piprop": "original",
                "titles": "|".join(batch),
                "redirects": "1",
                "format": "json",
                "formatversion": "2",
            },
        )
        payload = response.json().get("query", {})

        # The API rewrites some titles; follow both hops back to the requested name.
        alias = {}
        for entry in payload.get("normalized", []):
            alias[entry["to"]] = entry["from"]
        for entry in payload.get("redirects", []):
            alias[entry["to"]] = alias.get(entry["from"], entry["from"])

        for page in payload.get("pages", []):
            if "original" not in page:
                continue
            title = page["title"]
            resolved[alias.get(title, title)] = page["original"]["source"]

        time.sleep(REQUEST_DELAY_S)

    return resolved


def download_resized(url: str, destination: Path) -> bool:
    """Fetch an image and save it as a JPEG no larger than MAX_EDGE_PX on its long side.

    Downscaling keeps the repo small and speeds up CLIP encoding; the model resizes
    to 224x224 internally, so full resolution buys nothing here.
    """
    try:
        response = request_with_backoff(url)
        image = Image.open(io.BytesIO(response.content)).convert("RGB")
        image.thumbnail((MAX_EDGE_PX, MAX_EDGE_PX))
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination, "JPEG", quality=88)
        return True
    except Exception as error:
        print(f"    download failed: {error}")
        return False


def load_sources_cache() -> dict[str, dict[str, str]]:
    """Attribution recorded by previous runs, keyed by attraction id."""
    path = IMAGE_DIR / SOURCES_CACHE
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_sources_cache(cache: dict[str, dict[str, str]]) -> None:
    path = IMAGE_DIR / SOURCES_CACHE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")


def write_sources_file(cache: dict[str, dict[str, str]]) -> None:
    """Record provenance for the report's acknowledgements section.

    Built from the full cache rather than only this run's downloads, so stopping
    and resuming the script does not truncate the attribution table.
    """
    if not cache:
        return

    attributions = [
        (attraction_id, entry["title"], entry["url"])
        for attraction_id, entry in cache.items()
    ]

    lines = [
        "# Image sources",
        "",
        "All images were retrieved from Wikimedia Commons through the Wikipedia API.",
        "Each file carries its own licence, shown on the linked file page.",
        "Regenerate this list with `python -m data.fetch_images`.",
        "",
        "| Attraction | Wikipedia article | File |",
        "|---|---|---|",
    ]
    for attraction_id, title, url in sorted(attributions):
        article = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
        lines.append(f"| `{attraction_id}` | [{title}]({article}) | [file]({url}) |")

    output = IMAGE_DIR / "IMAGE_SOURCES.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {output.relative_to(PROJECT_ROOT)}")


def reconcile_cache(cache: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    """Fill in attribution for image files that exist but have no cache entry.

    Needed for files downloaded before the cache was introduced, and after any
    manual addition. Only the article API is called, which is not the endpoint
    that throttles, so this is cheap even for a full set.
    """
    orphans = {
        attraction_id: title
        for attraction_id, (folder, title) in SOURCES.items()
        if (IMAGE_DIR / folder / f"{attraction_id}.jpg").exists()
        and attraction_id not in cache
    }
    if not orphans:
        return cache

    print(f"Recovering attribution for {len(orphans)} existing files...")
    try:
        urls = lead_image_urls(list(orphans.values()))
    except Exception as error:
        print(f"  attribution lookup failed: {error}")
        return cache

    for attraction_id, title in orphans.items():
        if title in urls:
            cache[attraction_id] = {"title": title, "url": urls[title]}

    save_sources_cache(cache)
    return cache


def main() -> None:
    pending = {
        attraction_id: (folder, title)
        for attraction_id, (folder, title) in SOURCES.items()
        if not (IMAGE_DIR / folder / f"{attraction_id}.jpg").exists()
    }
    already = len(SOURCES) - len(pending)
    if already:
        print(f"{already} images already downloaded, skipping those.")
    if not pending:
        print("Nothing to fetch.")
        write_sources_file(reconcile_cache(load_sources_cache()))
        return

    print(f"Looking up {len(pending)} article images...")
    urls = lead_image_urls([title for _, title in pending.values()])

    cache = reconcile_cache(load_sources_cache())
    downloaded = 0
    failures: list[str] = []

    for attraction_id, (folder, title) in pending.items():
        url = urls.get(title)
        if not url:
            print(f"{attraction_id}: no lead image on '{title}'")
            failures.append(attraction_id)
            continue

        print(f"{attraction_id}: downloading")
        destination = IMAGE_DIR / folder / f"{attraction_id}.jpg"
        if download_resized(url, destination):
            cache[attraction_id] = {"title": title, "url": url}
            # Saved per file, so a run interrupted halfway keeps what it got.
            save_sources_cache(cache)
            downloaded += 1
        else:
            failures.append(attraction_id)

        time.sleep(REQUEST_DELAY_S)

    write_sources_file(cache)

    print(f"\nDownloaded {downloaded} images this run, {len(cache)} in total.")
    if failures:
        print(f"Still missing: {', '.join(failures)}")
        print("Re-run to retry, or add files as data/images/<category>/<id>.jpg")


if __name__ == "__main__":
    sys.exit(main())
