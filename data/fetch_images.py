# Downloads the attraction photos from Wikimedia through the Wikipedia API and
# writes down where each one came from, which we need for the acknowledgements
# in the report.
#
# The titles are looked up 50 at a time (the API limit) because doing one
# request per attraction got us rate limited almost immediately. Downloads are
# spaced out and retried when we get a 429.
#
# Run:  python data/fetch_images.py

import io
import json
import time
from pathlib import Path

import requests
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGE_DIR = PROJECT_ROOT / "data" / "images"

WIKI_API = "https://en.wikipedia.org/w/api.php"
# wikimedia asks bots to identify themselves, they throttle you harder if you
# don't
HEADERS = {
    "User-Agent": "SLTourismRAG/0.1 (SCS 4203 coursework; contact via repository)"
}

MAX_EDGE_PX = 1024
REQUEST_DELAY_S = 2.5
MAX_RETRIES = 5

TITLE_BATCH_SIZE = 50

# Wikimedia sends back Retry-After: 600 when it throttles the image CDN.
# Actually waiting 10 minutes each time would take hours, and in practice
# requests start working again well before that, so cap the wait.
MAX_BACKOFF_S = 75

# keeps track of which url each file came from so the attribution table
# survives between runs
SOURCES_CACHE = "_sources.json"

# attraction id -> (folder, wikipedia article title)
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


def request_with_backoff(url, params=None):
    # kept as a function rather than copied at its two call sites below (the
    # title lookup and the image download) - it's retry/backoff logic against a
    # live, rate-limited API, and two hand-written copies could end up handling
    # a 429 differently and get the whole team rate-limited
    delay = 2.0
    last_error = None

    attempt = 0
    while attempt < MAX_RETRIES:
        try:
            response = requests.get(url, params=params, headers=HEADERS, timeout=60)
            if response.status_code == 429:
                wait = float(response.headers.get("Retry-After", delay))
                if wait > MAX_BACKOFF_S:
                    wait = MAX_BACKOFF_S
                print("    rate limited, waiting " + str(int(wait)) + "s")
                time.sleep(wait)
                delay = min(delay * 2, MAX_BACKOFF_S)
                attempt += 1
                continue
            response.raise_for_status()
            return response
        except requests.RequestException as error:
            last_error = error
            time.sleep(delay)
            delay = delay * 2
            attempt += 1

    raise RuntimeError("gave up after " + str(MAX_RETRIES) + " attempts: " +
                       str(last_error))


def lead_image_urls(titles):
    # returns {article title: image url}. the API renames and redirects some
    # titles so we map them back to what we asked for. kept as a function since
    # it's called both for the pending list and for orphan recovery below, and
    # it's the batching/alias logic around the same rate-limited API
    resolved = {}

    start = 0
    while start < len(titles):
        batch = titles[start:start + TITLE_BATCH_SIZE]
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

        start += TITLE_BATCH_SIZE
        time.sleep(REQUEST_DELAY_S)

    return resolved


def reconcile_cache(cache):
    # fills in the source for files that are already on disk but not in the
    # cache (downloaded before the cache existed, or added by hand). kept as a
    # function since it wraps the same rate-limited lookup above and is called
    # from both branches below
    orphans = {}
    for attraction_id in SOURCES:
        folder, title = SOURCES[attraction_id]
        if (IMAGE_DIR / folder / (attraction_id + ".jpg")).exists() \
                and attraction_id not in cache:
            orphans[attraction_id] = title

    if not orphans:
        return cache

    print("Recovering attribution for " + str(len(orphans)) + " existing files...")
    try:
        urls = lead_image_urls(list(orphans.values()))
    except Exception as error:
        print("  attribution lookup failed: " + str(error))
        return cache

    for attraction_id in orphans:
        title = orphans[attraction_id]
        if title in urls:
            cache[attraction_id] = {"title": title, "url": urls[title]}

    cache_path = IMAGE_DIR / SOURCES_CACHE
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")

    return cache


pending = {}
for attraction_id in SOURCES:
    folder, title = SOURCES[attraction_id]
    if not (IMAGE_DIR / folder / (attraction_id + ".jpg")).exists():
        pending[attraction_id] = (folder, title)

already = len(SOURCES) - len(pending)
if already:
    print(str(already) + " images already downloaded, skipping those.")

cache_path = IMAGE_DIR / SOURCES_CACHE
if cache_path.exists():
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        cache = {}
else:
    cache = {}

if not pending:
    print("Nothing to fetch.")
    cache = reconcile_cache(cache)
else:
    print("Looking up " + str(len(pending)) + " article images...")
    urls = lead_image_urls([title for folder, title in pending.values()])

    cache = reconcile_cache(cache)
    downloaded = 0
    failures = []

    for attraction_id in pending:
        folder, title = pending[attraction_id]
        url = urls.get(title)
        if not url:
            print(attraction_id + ": no lead image on '" + title + "'")
            failures.append(attraction_id)
            continue

        print(attraction_id + ": downloading")
        destination = IMAGE_DIR / folder / (attraction_id + ".jpg")

        # shrink to 1024px, CLIP resizes to 224x224 anyway so keeping the full
        # resolution just makes the repo bigger
        try:
            response = request_with_backoff(url)
            image = Image.open(io.BytesIO(response.content)).convert("RGB")
            image.thumbnail((MAX_EDGE_PX, MAX_EDGE_PX))
            destination.parent.mkdir(parents=True, exist_ok=True)
            image.save(destination, "JPEG", quality=88)
            download_ok = True
        except Exception as error:
            print("    download failed: " + str(error))
            download_ok = False

        if download_ok:
            cache[attraction_id] = {"title": title, "url": url}
            # save after each one so an interrupted run keeps what it got
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
            downloaded += 1
        else:
            failures.append(attraction_id)

        time.sleep(REQUEST_DELAY_S)

    print("")
    print("Downloaded " + str(downloaded) + " images this run, " + str(len(cache)) +
          " in total.")
    if failures:
        print("Still missing: " + ", ".join(failures))
        print("Re-run to retry, or add files as data/images/<category>/<id>.jpg")

# write the attribution table - built from the whole cache, not just this run,
# so stopping and restarting doesn't chop the table in half
if cache:
    attributions = []
    for attraction_id in cache:
        entry = cache[attraction_id]
        attributions.append((attraction_id, entry["title"], entry["url"]))

    lines = [
        "# Image sources",
        "",
        "All images were retrieved from Wikimedia Commons through the Wikipedia API.",
        "Each file carries its own licence, shown on the linked file page.",
        "Regenerate this list with `python data/fetch_images.py`.",
        "",
        "| Attraction | Wikipedia article | File |",
        "|---|---|---|",
    ]
    for attraction_id, title, url in sorted(attributions):
        article = "https://en.wikipedia.org/wiki/" + title.replace(" ", "_")
        lines.append("| `" + attraction_id + "` | [" + title + "](" + article +
                     ") | [file](" + url + ") |")

    output = IMAGE_DIR / "IMAGE_SOURCES.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote " + str(output.relative_to(PROJECT_ROOT)))
