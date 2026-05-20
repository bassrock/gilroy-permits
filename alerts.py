import html
import logging
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage

from checker import get_db

log = logging.getLogger(__name__)

_FIELDS = ("host", "port", "username", "password", "use_tls", "use_ssl",
           "from_addr", "to_addr", "base_url", "enabled")
MASKED = "***"


def get_smtp_settings() -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM smtp_settings WHERE id=1").fetchone()
    return dict(row) if row else None


def get_smtp_settings_safe() -> dict:
    """Same as get_smtp_settings but with password masked. Always returns a dict."""
    s = get_smtp_settings() or {}
    out = {k: s.get(k) for k in _FIELDS}
    out["port"] = out["port"] or 587
    out["use_tls"] = 1 if s.get("use_tls", 1) else 0
    out["use_ssl"] = 1 if s.get("use_ssl", 0) else 0
    out["enabled"] = 1 if s.get("enabled", 0) else 0
    out["password"] = MASKED if s.get("password") else ""
    return out


def save_smtp_settings(**fields) -> None:
    current = get_smtp_settings() or {}
    # Preserve password if caller sent the mask sentinel
    if fields.get("password") == MASKED:
        fields["password"] = current.get("password")
    merged = {k: fields.get(k, current.get(k)) for k in _FIELDS}
    # Normalize booleans
    for b in ("use_tls", "use_ssl", "enabled"):
        merged[b] = 1 if merged.get(b) else 0
    merged["port"] = int(merged.get("port") or 587)
    merged["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    cols = list(merged.keys())
    placeholders = ",".join("?" for _ in cols)
    assignments = ",".join(f"{c}=excluded.{c}" for c in cols)
    sql = (
        f"INSERT INTO smtp_settings (id,{','.join(cols)}) VALUES (1,{placeholders}) "
        f"ON CONFLICT(id) DO UPDATE SET {assignments}"
    )
    with get_db() as conn:
        conn.execute(sql, [merged[c] for c in cols])
    log.info("Saved SMTP settings (enabled=%s, host=%s)", merged["enabled"], merged["host"])


def _send(subject: str, body_html: str) -> None:
    s = get_smtp_settings()
    if not s or not s.get("enabled"):
        log.info("SMTP disabled or unconfigured — skipping send")
        return
    if not (s.get("host") and s.get("from_addr") and s.get("to_addr")):
        raise ValueError("SMTP host / from_addr / to_addr must be set")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = s["from_addr"]
    msg["To"] = s["to_addr"]
    msg.set_content("This message has an HTML body. View it in an HTML-capable client.")
    msg.add_alternative(body_html, subtype="html")

    smtp_cls = smtplib.SMTP_SSL if s.get("use_ssl") else smtplib.SMTP
    with smtp_cls(s["host"], int(s["port"] or 587), timeout=30) as srv:
        if s.get("use_tls") and not s.get("use_ssl"):
            srv.starttls()
        if s.get("username"):
            srv.login(s["username"], s.get("password") or "")
        srv.send_message(msg)
    log.info("Sent email %r to %s", subject, s["to_addr"])


def send_test() -> None:
    body = (
        "<p>This is a test email from the Gilroy permits checker.</p>"
        "<p style='color:#6b7280;font-size:.85rem'>If you got this, alerts are configured correctly.</p>"
    )
    _send("Gilroy permits — test email", body)


def _render_diff_html(changes: list[dict], base_url: str) -> str:
    rows = []
    for c in changes:
        link = f"{base_url.rstrip('/')}/permit/{c['case_id']}" if base_url else None
        title_html = (
            f'<a href="{html.escape(link)}" style="color:#2563eb;text-decoration:none">'
            f'{html.escape(c["case_number"] or c["case_id"])}</a>'
            if link else html.escape(c["case_number"] or c["case_id"])
        )
        diff_rows = "".join(
            f'<tr><td style="padding:.15rem .6rem;color:#6b7280;font-size:.8rem">{html.escape(f)}</td>'
            f'<td style="padding:.15rem .6rem;font-size:.85rem">'
            f'<span style="color:#9ca3af;text-decoration:line-through">{html.escape(old) or "—"}</span>'
            f' &rarr; <strong>{html.escape(new) or "—"}</strong></td></tr>'
            for f, (old, new) in c["diffs"].items()
        )
        rows.append(
            '<div style="border:1px solid #e5e7eb;border-radius:.5rem;padding:.75rem 1rem;margin-bottom:.75rem;background:#fff">'
            f'<div style="font-weight:600;margin-bottom:.4rem">{title_html} '
            f'<span style="color:#6b7280;font-weight:400;font-size:.8rem">· keyword: {html.escape(c.get("keyword") or "")}</span></div>'
            f'<table style="border-collapse:collapse">{diff_rows}</table>'
            '</div>'
        )
    return (
        '<div style="font-family:system-ui,-apple-system,sans-serif;background:#f3f4f6;padding:1.5rem;color:#1f2937">'
        f'<h2 style="font-size:1.1rem;margin:0 0 1rem">{len(changes)} favorited permit(s) updated</h2>'
        + "".join(rows)
        + '</div>'
    )


def send_change_digest(changes: list[dict]) -> None:
    if not changes:
        return
    s = get_smtp_settings()
    if not s or not s.get("enabled"):
        log.info("SMTP disabled — %d favorite change(s) not sent", len(changes))
        return
    base_url = s.get("base_url") or ""
    subject = f"Gilroy permits: {len(changes)} favorite(s) updated"
    _send(subject, _render_diff_html(changes, base_url))
