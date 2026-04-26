import logging
import os
import sqlite3
import time

import requests

log = logging.getLogger(__name__)

DB_PATH = os.environ.get("DB_PATH", "/data/permits.db")
_NOMINATIM = "https://nominatim.openstreetmap.org/search"
_UA = {"User-Agent": "GilroyPermitsChecker/1.0 (permit monitoring tool)"}


def _geocode(address: str):
    try:
        r = requests.get(
            _NOMINATIM,
            params={"q": address, "format": "json", "limit": 1, "countrycodes": "us"},
            headers=_UA,
            timeout=10,
        )
        r.raise_for_status()
        hits = r.json()
        if hits:
            return float(hits[0]["lat"]), float(hits[0]["lon"])
    except Exception as exc:
        log.debug("Geocode failed for %r: %s", address, exc)
    return None


def run_geocoder():
    log.info("Geocoder started — will process ~1 address/sec")
    while True:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        row = conn.execute(
            "SELECT case_id, address FROM permits "
            "WHERE lat IS NULL AND address IS NOT NULL AND address != '' LIMIT 1"
        ).fetchone()
        remaining = conn.execute(
            "SELECT count(*) FROM permits WHERE lat IS NULL AND address IS NOT NULL AND address != ''"
        ).fetchone()[0]
        conn.close()

        if not row:
            time.sleep(60)
            continue

        case_id, address = row
        result = _geocode(address)

        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        if result:
            lat, lng = result
            conn.execute("UPDATE permits SET lat=?, lng=? WHERE case_id=?", (lat, lng, case_id))
            if remaining % 200 == 0:
                log.info("Geocoding: ~%d permits remaining", remaining)
        else:
            # 0,0 = tried and failed — filtered out in map queries
            conn.execute("UPDATE permits SET lat=0, lng=0 WHERE case_id=?", (case_id,))
        conn.commit()
        conn.close()

        time.sleep(1.2)  # Nominatim: max 1 req/sec
