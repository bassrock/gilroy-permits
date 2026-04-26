import os
import sqlite3
import logging
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

API_URL = "https://gilroyca-energovweb.tylerhost.net/apps/selfservice/api/energov/search/search"
_HEADERS = {
    "Content-Type": "application/json;charset=UTF-8",
    "Accept": "application/json, text/plain, */*",
    "tenantid": "1",
    "tenantname": "GilroyCA",
    "tyler-tenant-culture": "en-US",
    "tyler-tenanturl": "GilroyCA",
    "Referer": "https://gilroyca-energovweb.tylerhost.net/apps/SelfService",
}

DB_PATH = os.environ.get("DB_PATH", "/data/permits.db")
SEARCH_TERMS = [t.strip() for t in os.environ.get("SEARCH_TERMS", "solar").split(",") if t.strip()]
EXACT_MATCH = os.environ.get("EXACT_MATCH", "false").lower() == "true"
PAGE_SIZE = int(os.environ.get("PAGE_SIZE", "100"))


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS permits (
                case_id     TEXT PRIMARY KEY,
                case_number TEXT,
                case_type   TEXT,
                status      TEXT,
                address     TEXT,
                apply_date  TEXT,
                issue_date  TEXT,
                description TEXT,
                keyword     TEXT,
                first_seen  TEXT,
                lat         REAL,
                lng         REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ran_at    TEXT NOT NULL,
                new_found INTEGER NOT NULL DEFAULT 0
            )
        """)
        # Migrate existing DBs that are missing the newer columns
        _add_column_if_missing(conn, "permits", "issue_date", "TEXT")
        _add_column_if_missing(conn, "permits", "lat", "REAL")
        _add_column_if_missing(conn, "permits", "lng", "REAL")


def _add_column_if_missing(conn, table, col, col_type):
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if col not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
        log.info("Migrated: added column %s.%s", table, col)


def _build_body(keyword: str, page: int) -> dict:
    empty = {"PageNumber": 0, "PageSize": 0, "SortBy": None, "SortAscending": False}
    return {
        "Keyword": keyword,
        "ExactMatch": EXACT_MATCH,
        "SearchModule": 1,
        "FilterModule": 2,
        "SearchMainAddress": False,
        "PermitCriteria": {
            "PermitNumber": None, "PermitTypeId": None, "PermitWorkclassId": None,
            "PermitStatusId": None, "ProjectName": None, "IssueDateFrom": None,
            "IssueDateTo": None, "Address": None, "Description": None,
            "ExpireDateFrom": None, "ExpireDateTo": None, "FinalDateFrom": None,
            "FinalDateTo": None, "ApplyDateFrom": None, "ApplyDateTo": None,
            "SearchMainAddress": False, "ContactId": None, "TypeId": None,
            "WorkClassIds": None, "ParcelNumber": None, "ExcludeCases": None,
            "EnableDescriptionSearch": False, **empty,
        },
        "PlanCriteria": empty.copy(),
        "InspectionCriteria": {
            "TypeId": [], "WorkClassIds": [], "ExcludeCases": [],
            "ExcludeFilterModules": [], "HiddenInspectionTypeIDs": None, **empty,
        },
        "CodeCaseCriteria": empty.copy(),
        "RequestCriteria": empty.copy(),
        "BusinessLicenseCriteria": empty.copy(),
        "ProfessionalLicenseCriteria": empty.copy(),
        "LicenseCriteria": {
            "EnableDescriptionSearchForBLicense": False,
            "EnableDescriptionSearchForPLicense": False,
            "EnableDescriptionSearchForOperationalPermit": False,
            "IsOperationalPermit": False,
            **empty,
        },
        "ProjectCriteria": empty.copy(),
        "ExcludeCases": None,
        "HiddenInspectionTypeIDs": None,
        "PageNumber": page,
        "PageSize": PAGE_SIZE,
        "SortBy": "relevance",
        "SortAscending": False,
    }


def _fetch_page(keyword: str, page: int) -> dict:
    resp = requests.post(API_URL, json=_build_body(keyword, page), headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()["Result"]


def run_check() -> int:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    total_new = 0

    with get_db() as conn:
        for keyword in SEARCH_TERMS:
            log.info("Checking %r", keyword)
            new_permits = []
            page = 1

            while True:
                try:
                    result = _fetch_page(keyword, page)
                except Exception as exc:
                    log.error("API error on page %d for %r: %s", page, keyword, exc)
                    break

                entities = result.get("EntityResults") or []
                total_pages = result.get("TotalPages") or 1
                page_new = 0

                for e in entities:
                    cid = e.get("CaseId")
                    if not cid:
                        continue
                    try:
                        conn.execute(
                            """INSERT INTO permits
                               (case_id, case_number, case_type, status, address,
                                apply_date, issue_date, description, keyword, first_seen)
                               VALUES (?,?,?,?,?,?,?,?,?,?)""",
                            (
                                cid,
                                e.get("CaseNumber"),
                                e.get("CaseType"),
                                e.get("CaseStatus"),
                                e.get("AddressDisplay"),
                                (e.get("ApplyDate") or "")[:10],
                                (e.get("IssueDate") or "")[:10],
                                e.get("Description") or "",
                                keyword,
                                now,
                            ),
                        )
                        new_permits.append(e)
                        page_new += 1
                    except sqlite3.IntegrityError:
                        pass  # already known

                log.info("  page %d/%d — %d new", page, total_pages, page_new)

                if page_new == 0 or page >= total_pages:
                    break
                page += 1

            total_new += len(new_permits)
            if new_permits:
                log.info("%d new permit(s) for %r:", len(new_permits), keyword)
                for e in new_permits:
                    log.info(
                        "  %s | %s | %s | %s",
                        e.get("CaseNumber"),
                        e.get("CaseType"),
                        e.get("AddressDisplay"),
                        (e.get("ApplyDate") or "")[:10],
                    )
            else:
                log.info("No new permits for %r", keyword)

        conn.execute("INSERT INTO runs (ran_at, new_found) VALUES (?,?)", (now, total_new))

    log.info("Check complete — %d new total.", total_new)
    return total_new
