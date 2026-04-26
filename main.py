import logging
import os
import threading
import time

import schedule

from checker import init_db, run_check
from geocoder import run_geocoder
from web import app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

CHECK_TIME = os.environ.get("CHECK_TIME", "08:00")


def _scheduler():
    log.info("Running initial permit check…")
    run_check()
    schedule.every().day.at(CHECK_TIME).do(run_check)
    log.info("Next daily check scheduled at %s", CHECK_TIME)
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    init_db()
    threading.Thread(target=_scheduler, daemon=True, name="scheduler").start()
    threading.Thread(target=run_geocoder, daemon=True, name="geocoder").start()
    log.info("Web UI at http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, threaded=True)
