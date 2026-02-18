from __future__ import annotations

import os
import re
import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

# ----------------------------
# Optional ChatGPT bridge
# (ChatGPT is the conversational side)
# ----------------------------
try:
    from app.axel_bridge import axel_generate  # type: ignore
except Exception:
    axel_generate = None  # type: ignore

app = FastAPI(title="RAR AI Studio")

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# Local sqlite file (used when DATABASE_URL missing)
DB_PATH = os.path.join(BASE_DIR, "data.sqlite3")

# Works on any host: set DATABASE_URL to Postgres; otherwise SQLite.
DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()

_engine: Optional[Engine] = None


def _db_engine() -> Engine:
    global _engine
    if _engine is not None:
        return _engine

    if DATABASE_URL:
        url = DATABASE_URL
        # Make Postgres URL compatible across hosts + SQLAlchemy
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://") :]
        elif url.startswith("postgresql://") and "psycopg" not in url:
            url = "postgresql+psycopg://" + url[len("postgresql://") :]

        _engine = create_engine(url, pool_pre_ping=True)
    else:
        _engine = create_engine(
            f"sqlite+pysqlite:///{DB_PATH}",
            connect_args={"check_same_thread": False},
        )
    return _engine


def _dialect() -> str:
    return _db_engine().dialect.name  # "postgresql" or "sqlite"


def _exec(sql: str, params: Optional[Dict[str, Any]] = None) -> None:
    eng = _db_engine()
    with eng.begin() as conn:
        conn.execute(text(sql), params or {})


def _fetchone(sql: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    eng = _db_engine()
    with eng.begin() as conn:
        row = conn.execute(text(sql), params or {}).mappings().first()
        return dict(row) if row else None


def _fetchall(sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    eng = _db_engine()
    with eng.begin() as conn:
        rows = conn.execute(text(sql), params or {}).mappings().all()
        return [dict(r) for r in rows]


# ----------------------------
# Integrations env flags (read-only)
# ----------------------------
TWILIO_ACCOUNT_SID = (os.getenv("TWILIO_ACCOUNT_SID") or "").strip()
TWILIO_AUTH_TOKEN = (os.getenv("TWILIO_AUTH_TOKEN") or "").strip()
TWILIO_FROM_NUMBER = (os.getenv("TWILIO_FROM_NUMBER") or "").strip()

SENDGRID_API_KEY = (os.getenv("SENDGRID_API_KEY") or "").strip()
SENDGRID_FROM_EMAIL = (os.getenv("SENDGRID_FROM_EMAIL") or "").strip()


# ----------------------------
# Helpers
# ----------------------------
def _now() -> str:
    return datetime.utcnow().isoformat()


def _month_key() -> str:
    return datetime.utcnow().strftime("%Y-%m")  # YYYY-MM (UTC)


def _slug(n_bytes: int = 8) -> str:
    return secrets.token_urlsafe(n_bytes).replace("-", "").replace("_", "")


def _stringify_output(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    try:
        import json

        return json.dumps(x, indent=2, ensure_ascii=False)
    except Exception:
        return str(x)


def _clean_one_line(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


# ----------------------------
# DB init + migrations
# ----------------------------
def _column_exists(table: str, column: str) -> bool:
    d = _dialect()
    try:
        if d == "sqlite":
            rows = _fetchall(f"PRAGMA table_info({table})")
            cols = {r.get("name") for r in rows}
            return column in cols
        else:
            row = _fetchone(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_name=:t AND column_name=:c
                LIMIT 1
                """,
                {"t": table, "c": column},
            )
            return bool(row)
    except Exception:
        return False


def _init_db() -> None:
    d = _dialect()

    if d == "postgresql":
        msg_id = "BIGSERIAL PRIMARY KEY"
        int_pk_1 = "INTEGER PRIMARY KEY"
    else:
        msg_id = "INTEGER PRIMARY KEY AUTOINCREMENT"
        int_pk_1 = "INTEGER PRIMARY KEY"

    _exec(
        """
        CREATE TABLE IF NOT EXISTS funnels (
            slug TEXT PRIMARY KEY,
            visibility TEXT NOT NULL,
            title TEXT NOT NULL,
            business_name TEXT,
            business_type TEXT,
            offer TEXT,
            location TEXT,
            html TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    _exec(
        f"""
        CREATE TABLE IF NOT EXISTS business_profile (
            id {int_pk_1} CHECK (id = 1),
            biz_name TEXT,
            biz_type TEXT,
            offer TEXT,
            location TEXT,
            tone TEXT,
            contact_method TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )

    _exec(
        """
        CREATE TABLE IF NOT EXISTS leads (
            id TEXT PRIMARY KEY,
            name TEXT,
            contact TEXT,
            source TEXT,
            stage TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    _exec(
        f"""
        CREATE TABLE IF NOT EXISTS messages (
            id {msg_id},
            lead_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    _exec(
        f"""
        CREATE TABLE IF NOT EXISTS tenant_limits (
            id {int_pk_1} CHECK (id = 1),
            plan TEXT NOT NULL,
            lead_cap INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    _exec(
        """
        CREATE TABLE IF NOT EXISTS usage_events (
            month_key TEXT NOT NULL,
            lead_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (month_key, lead_id)
        )
        """
    )

    _exec(
        f"""
        CREATE TABLE IF NOT EXISTS integrations (
            id {int_pk_1} CHECK (id = 1),
            twilio_enabled INTEGER NOT NULL,
            sendgrid_enabled INTEGER NOT NULL,
            autosend_enabled INTEGER NOT NULL,
            autosend_channels TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    _exec(
        """
        CREATE TABLE IF NOT EXISTS outbound_messages (
            id TEXT PRIMARY KEY,
            lead_id TEXT,
            channel TEXT NOT NULL,
            recipient TEXT,
            subject TEXT,
            body TEXT NOT NULL,
            status TEXT NOT NULL,
            provider TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            sent_at TEXT
        )
        """
    )

    # Migration: add monthly_price_usd
    if not _column_exists("tenant_limits", "monthly_price_usd"):
        try:
            _exec("ALTER TABLE tenant_limits ADD COLUMN monthly_price_usd INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass

    # Ensure single rows exist
    if not _fetchone("SELECT id FROM business_profile WHERE id=1"):
        _exec(
            """
            INSERT INTO business_profile (id, biz_name, biz_type, offer, location, tone, contact_method, updated_at)
            VALUES (1, '', '', '', '', 'confident', 'dm', :ts)
            """,
            {"ts": _now()},
        )

    if not _fetchone("SELECT id FROM tenant_limits WHERE id=1"):
        if _column_exists("tenant_limits", "monthly_price_usd"):
            _exec(
                """
                INSERT INTO tenant_limits (id, plan, lead_cap, monthly_price_usd, updated_at)
                VALUES (1, 'pro', 100, 100, :ts)
                """,
                {"ts": _now()},
            )
        else:
            _exec(
                """
                INSERT INTO tenant_limits (id, plan, lead_cap, updated_at)
                VALUES (1, 'pro', 100, :ts)
                """,
                {"ts": _now()},
            )

    if not _fetchone("SELECT id FROM integrations WHERE id=1"):
        _exec(
            """
            INSERT INTO integrations (id, twilio_enabled, sendgrid_enabled, autosend_enabled, autosend_channels, updated_at)
            VALUES (1, 0, 0, 0, 'sms,email', :ts)
            """,
            {"ts": _now()},
        )


try:
    _init_db()
except OperationalError:
    pass


# ----------------------------
# Limits + Usage helpers
# ----------------------------
def _get_limits() -> Dict[str, Any]:
    if _column_exists("tenant_limits", "monthly_price_usd"):
        row = _fetchone("SELECT plan, lead_cap, monthly_price_usd FROM tenant_limits WHERE id=1") or {}
        return {
            "plan": (row.get("plan") or "pro"),
            "lead_cap": int(row.get("lead_cap") or 100),
            "monthly_price_usd": int(row.get("monthly_price_usd") or 0),
        }
    row = _fetchone("SELECT plan, lead_cap FROM tenant_limits WHERE id=1") or {}
    return {"plan": (row.get("plan") or "pro"), "lead_cap": int(row.get("lead_cap") or 100), "monthly_price_usd": 0}


def _count_used_leads_this_month(month_key: str) -> int:
    row = _fetchone("SELECT COUNT(*) AS n FROM usage_events WHERE month_key=:m", {"m": month_key}) or {}
    return int(row.get("n") or 0)


def _is_lead_counted_this_month(month_key: str, lead_id: str) -> bool:
    row = _fetchone("SELECT 1 FROM usage_events WHERE month_key=:m AND lead_id=:id", {"m": month_key, "id": lead_id})
    return bool(row)


def _count_lead_now(month_key: str, lead_id: str) -> None:
    if _dialect() == "sqlite":
        _exec(
            "INSERT OR IGNORE INTO usage_events (month_key, lead_id, created_at) VALUES (:m, :id, :ts)",
            {"m": month_key, "id": lead_id, "ts": _now()},
        )
    else:
        _exec(
            """
            INSERT INTO usage_events (month_key, lead_id, created_at)
            VALUES (:m, :id, :ts)
            ON CONFLICT (month_key, lead_id) DO NOTHING
            """,
            {"m": month_key, "id": lead_id, "ts": _now()},
        )


# ----------------------------
# Integrations helpers
# ----------------------------
def _get_integrations() -> Dict[str, Any]:
    row = _fetchone("SELECT * FROM integrations WHERE id=1") or {}
    row.pop("id", None)
    for k in ("twilio_enabled", "sendgrid_enabled", "autosend_enabled"):
        row[k] = int(row.get(k) or 0)
    row["autosend_channels"] = row.get("autosend_channels") or "sms,email"
    return row


# ----------------------------
# Outbound queue (pipeline safe)
# ----------------------------
def _queue_outbound(lead_id: str, channel: str, recipient: str, body: str, subject: str = "") -> Dict[str, Any]:
    oid = _slug(12)
    ts = _now()
    _exec(
        """
        INSERT INTO outbound_messages (id, lead_id, channel, recipient, subject, body, status, provider, error, created_at, sent_at)
        VALUES (:id, :lid, :ch, :rcpt, :subj, :body, 'queued', '', '', :ts, '')
        """,
        {"id": oid, "lid": lead_id or None, "ch": channel, "rcpt": recipient, "subj": subject, "body": body, "ts": ts},
    )
    return {"id": oid, "status": "queued", "created_at": ts}


def _send_one_outbound(msg: Dict[str, Any], integ: Dict[str, Any]) -> Dict[str, Any]:
    channel = (msg.get("channel") or "").lower()

    env_ready_twilio = bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER)
    env_ready_sendgrid = bool(SENDGRID_API_KEY and SENDGRID_FROM_EMAIL)

    if channel in ("sms", "text"):
        if int(integ.get("twilio_enabled") or 0) != 1:
            return {"ok": False, "provider": "twilio", "error": "Twilio disabled in settings."}
        if not env_ready_twilio:
            return {"ok": False, "provider": "twilio", "error": "Twilio env keys missing."}
        return {"ok": True, "provider": "twilio"}  # simulated

    if channel == "email":
        if int(integ.get("sendgrid_enabled") or 0) != 1:
            return {"ok": False, "provider": "sendgrid", "error": "SendGrid disabled in settings."}
        if not env_ready_sendgrid:
            return {"ok": False, "provider": "sendgrid", "error": "SendGrid env keys missing."}
        return {"ok": True, "provider": "sendgrid"}  # simulated

    return {"ok": True, "provider": "simulated"}


def _run_outbound_queue(limit: int = 25) -> Dict[str, Any]:
    integ = _get_integrations()
    rows = _fetchall(
        """
        SELECT * FROM outbound_messages
        WHERE status='queued'
        ORDER BY created_at ASC
        LIMIT :lim
        """,
        {"lim": int(limit)},
    )

    sent = 0
    failed = 0

    for msg in rows:
        oid = msg.get("id")
        try:
            result = _send_one_outbound(msg, integ)
            if result.get("ok"):
                _exec(
                    "UPDATE outbound_messages SET status='sent', provider=:p, error='', sent_at=:ts WHERE id=:id",
                    {"id": oid, "p": result.get("provider") or "", "ts": _now()},
                )
                sent += 1
            else:
                _exec(
                    "UPDATE outbound_messages SET status='failed', provider=:p, error=:e, sent_at=:ts WHERE id=:id",
                    {"id": oid, "p": result.get("provider") or "", "e": result.get("error") or "failed", "ts": _now()},
                )
                failed += 1
        except Exception as e:
            failed += 1
            try:
                _exec(
                    "UPDATE outbound_messages SET status='failed', provider='internal', error=:e, sent_at=:ts WHERE id=:id",
                    {"id": oid, "e": str(e), "ts": _now()},
                )
            except Exception:
                pass

    return {"ok": True, "queued_found": len(rows), "sent": sent, "failed": failed}


# ----------------------------
# Health
# ----------------------------
@app.get("/health")
def health():
    return JSONResponse({"ok": True, "dialect": _dialect(), "db": bool(DATABASE_URL), "ts": _now()})


# ----------------------------
# Pages
# ----------------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "page_title": "RAR AI Studio",
            "subtitle": "Fast marketing assets for small businesses — in minutes.",
        },
    )


@app.get("/pricing", response_class=HTMLResponse)
def pricing(request: Request):
    return templates.TemplateResponse("pricing.html", {"request": request, "page_title": "Pricing — RAR AI Studio"})


@app.get("/salesperson", response_class=HTMLResponse)
def salesperson_page(request: Request):
    return templates.TemplateResponse("salesperson.html", {"request": request, "page_title": "AI Salesperson — RAR AI Studio"})


@app.get("/autoresponse", response_class=HTMLResponse)
def autoresponse_page(request: Request):
    return templates.TemplateResponse("autoresponse.html", {"request": request, "page_title": "AI Auto-Response — RAR AI Studio"})


@app.get("/funnel", response_class=HTMLResponse)
def funnel_page(request: Request):
    return templates.TemplateResponse("funnel_dashboard.html", {"request": request, "page_title": "Funnel — RAR AI Studio"})


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request, "page_title": "Settings — RAR AI Studio"})


# ----------------------------
# Tool: Marketing Pack
# ----------------------------
@app.post("/generate", response_class=HTMLResponse)
def generate(
    request: Request,
    business_name: str = Form(...),
    business_type: str = Form(...),
    offer: str = Form(""),
    location: str = Form(""),
    vibe: str = Form("confident"),
):
    business_name = _clean_one_line(business_name)
    business_type = _clean_one_line(business_type)
    offer = _clean_one_line(offer)
    location = _clean_one_line(location)
    vibe = _clean_one_line(vibe)

    inputs: Dict[str, Any] = {
        "business_name": business_name,
        "business_type": business_type,
        "offer": offer,
        "location": location,
        "deliverables": ["Hooks (10)", "Captions (6)", "Ad Copy (3)", "DM Closer Script (1)", "Landing Page Outline (1)"],
    }

    if axel_generate:
        out = axel_generate(tool="marketing_pack", inputs=inputs, tone=vibe, audience="small business", brand="RAR AI Studio")
        output_text = _stringify_output(out)
    else:
        output_text = "Set OPENAI_API_KEY (via app/axel_bridge.py) to enable ChatGPT outputs."

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "page_title": "RAR AI Studio",
            "subtitle": "Fast marketing assets for small businesses — in minutes.",
            "result": output_text,
            "prefill": {"business_name": business_name, "business_type": business_type, "offer": offer, "location": location, "vibe": vibe},
        },
    )


# ----------------------------
# Funnel builder
# ----------------------------
@app.post("/funnel", response_class=HTMLResponse)
def funnel_builder(
    request: Request,
    business_name: str = Form(...),
    business_type: str = Form(...),
    offer: str = Form(""),
    location: str = Form(""),
):
    business_name = _clean_one_line(business_name)
    business_type = _clean_one_line(business_type)
    offer = _clean_one_line(offer)
    location = _clean_one_line(location)

    inputs: Dict[str, Any] = {"business_name": business_name, "business_type": business_type, "offer": offer, "location": location}

    if axel_generate:
        html = axel_generate(tool="funnel_html", inputs=inputs, tone="confident", audience="small business", brand="RAR AI Studio")
        html = _stringify_output(html)
    else:
        html = f"<html><body><h1>{business_name}</h1><p>{business_type}</p><p>{offer}</p><p>{location}</p></body></html>"

    slug = _slug()
    title = f"{business_name} — {business_type}"

    _exec(
        """
        INSERT INTO funnels (slug, visibility, title, business_name, business_type, offer, location, html, created_at)
        VALUES (:slug, 'public', :title, :bn, :bt, :of, :loc, :html, :ts)
        """,
        {"slug": slug, "title": title, "bn": business_name, "bt": business_type, "of": offer, "loc": location, "html": html, "ts": _now()},
    )

    return RedirectResponse(url=f"/f/{slug}", status_code=303)


@app.get("/f/{slug}")
def funnel_view(slug: str):
    row = _fetchone("SELECT html FROM funnels WHERE slug=:s", {"s": slug})
    if not row:
        return Response("Not found", status_code=404)
    return HTMLResponse(content=row.get("html") or "")


# ----------------------------
# API: Limits + Usage
# ----------------------------
@app.get("/api/limits")
def api_get_limits():
    return JSONResponse({"ok": True, "limits": _get_limits()})


@app.post("/api/limits")
async def api_set_limits(request: Request):
    payload = await request.json()
    plan = _clean_one_line(payload.get("plan") or "pro").lower()
    lead_cap = int(payload.get("lead_cap") or 100)
    monthly_price_usd = int(payload.get("monthly_price_usd") or 100)

    if lead_cap < 1:
        lead_cap = 1
    if lead_cap > 100000:
        lead_cap = 100000
    if monthly_price_usd < 0:
        monthly_price_usd = 0

    if not _column_exists("tenant_limits", "monthly_price_usd"):
        try:
            _exec("ALTER TABLE tenant_limits ADD COLUMN monthly_price_usd INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass

    if _column_exists("tenant_limits", "monthly_price_usd"):
        _exec(
            "UPDATE tenant_limits SET plan=:p, lead_cap=:c, monthly_price_usd=:m, updated_at=:ts WHERE id=1",
            {"p": plan, "c": lead_cap, "m": monthly_price_usd, "ts": _now()},
        )
    else:
        _exec("UPDATE tenant_limits SET plan=:p, lead_cap=:c, updated_at=:ts WHERE id=1", {"p": plan, "c": lead_cap, "ts": _now()})

    return JSONResponse({"ok": True})


@app.get("/api/usage")
def api_usage():
    mk = _month_key()
    limits = _get_limits()
    used = _count_used_leads_this_month(mk)
    return JSONResponse({"ok": True, "month": mk, "used_leads": used, "lead_cap": limits["lead_cap"], "plan": limits["plan"]})


# ----------------------------
# API: Integrations + Outbound pipeline
# ----------------------------
@app.get("/api/integrations")
def api_get_integrations():
    integ = _get_integrations()
    return JSONResponse(
        {
            "ok": True,
            "integrations": integ,
            "env_ready": {
                "twilio": bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER),
                "sendgrid": bool(SENDGRID_API_KEY and SENDGRID_FROM_EMAIL),
            },
        }
    )


@app.post("/api/integrations")
async def api_set_integrations(request: Request):
    payload = await request.json()
    twilio_enabled = 1 if int(payload.get("twilio_enabled") or 0) else 0
    sendgrid_enabled = 1 if int(payload.get("sendgrid_enabled") or 0) else 0
    autosend_enabled = 1 if int(payload.get("autosend_enabled") or 0) else 0
    autosend_channels = _clean_one_line(payload.get("autosend_channels") or "sms,email")
    _exec(
        """
        UPDATE integrations
        SET twilio_enabled=:t, sendgrid_enabled=:s, autosend_enabled=:a, autosend_channels=:ch, updated_at=:ts
        WHERE id=1
        """,
        {"t": twilio_enabled, "s": sendgrid_enabled, "a": autosend_enabled, "ch": autosend_channels, "ts": _now()},
    )
    return JSONResponse({"ok": True})


@app.post("/api/outbound/queue")
async def api_outbound_queue(request: Request):
    payload = await request.json()
    lead_id = _clean_one_line(payload.get("lead_id") or "")
    channel = _clean_one_line(payload.get("channel") or "sms").lower()
    recipient = _clean_one_line(payload.get("recipient") or "")
    subject = _clean_one_line(payload.get("subject") or "")
    body = (payload.get("body") or "").strip()
    if not body:
        return JSONResponse({"error": "body required"}, status_code=400)

    item = _queue_outbound(lead_id=lead_id, channel=channel, recipient=recipient, body=body, subject=subject)
    return JSONResponse({"ok": True, "queued": item})


@app.post("/api/outbound/run")
def api_outbound_run():
    return JSONResponse(_run_outbound_queue(limit=25))


# ----------------------------
# API: Profile / Leads / Convo / Funnel stage / Salesperson chat
# ----------------------------
@app.get("/api/profile")
def api_get_profile():
    row = _fetchone("SELECT * FROM business_profile WHERE id=1") or {}
    row.pop("id", None)
    return JSONResponse({"ok": True, "profile": row})


@app.post("/api/profile")
async def api_set_profile(request: Request):
    payload = await request.json()
    biz_name = _clean_one_line(payload.get("biz_name") or "")
    biz_type = _clean_one_line(payload.get("biz_type") or "")
    offer = _clean_one_line(payload.get("offer") or "")
    location = _clean_one_line(payload.get("location") or "")
    tone = _clean_one_line(payload.get("tone") or "confident")
    contact_method = _clean_one_line(payload.get("contact_method") or "dm")

    _exec(
        """
        UPDATE business_profile
        SET biz_name=:bn, biz_type=:bt, offer=:of, location=:loc, tone=:tone, contact_method=:cm, updated_at=:ts
        WHERE id=1
        """,
        {"bn": biz_name, "bt": biz_type, "of": offer, "loc": location, "tone": tone, "cm": contact_method, "ts": _now()},
    )
    return JSONResponse({"ok": True})


@app.get("/api/leads")
def api_list_leads():
    rows = _fetchall("SELECT id, name, contact, source, stage, created_at, updated_at FROM leads ORDER BY updated_at DESC")
    return JSONResponse({"ok": True, "leads": rows})


@app.post("/api/leads")
async def api_create_lead(request: Request):
    payload = await request.json()
    lead_id = _slug(10)
    name = _clean_one_line(payload.get("name") or "")
    contact = _clean_one_line(payload.get("contact") or "")
    source = _clean_one_line(payload.get("source") or "")
    stage = "New"
    ts = _now()

    _exec(
        """
        INSERT INTO leads (id, name, contact, source, stage, created_at, updated_at)
        VALUES (:id, :n, :c, :s, :st, :ts, :ts2)
        """,
        {"id": lead_id, "n": name, "c": contact, "s": source, "st": stage, "ts": ts, "ts2": ts},
    )
    return JSONResponse({"ok": True, "lead": {"id": lead_id, "name": name, "contact": contact, "source": source, "stage": stage}})


@app.delete("/api/leads/{lead_id}")
def api_delete_lead(lead_id: str):
    row = _fetchone("SELECT id FROM leads WHERE id=:id", {"id": lead_id})
    if not row:
        return JSONResponse({"error": "Lead not found"}, status_code=404)

    _exec("DELETE FROM messages WHERE lead_id=:id", {"id": lead_id})
    _exec("DELETE FROM usage_events WHERE lead_id=:id", {"id": lead_id})
    _exec("DELETE FROM outbound_messages WHERE lead_id=:id", {"id": lead_id})
    _exec("DELETE FROM leads WHERE id=:id", {"id": lead_id})
    return JSONResponse({"ok": True})


@app.get("/api/convo/{lead_id}")
def api_get_convo(lead_id: str):
    rows = _fetchall("SELECT role, content, created_at FROM messages WHERE lead_id=:id ORDER BY id ASC", {"id": lead_id})
    return JSONResponse({"ok": True, "messages": rows})


@app.post("/api/funnel/move")
async def api_move_stage(request: Request):
    payload = await request.json()
    lead_id = payload.get("lead_id") or ""
    stage = _clean_one_line(payload.get("stage") or "")

    allowed = {"New", "Contacted", "Engaged", "Estimate", "Won", "Lost"}
    if stage not in allowed:
        return JSONResponse({"error": "Invalid stage"}, status_code=400)

    if not _fetchone("SELECT 1 FROM leads WHERE id=:id", {"id": lead_id}):
        return JSONResponse({"error": "Lead not found"}, status_code=404)

    _exec("UPDATE leads SET stage=:st, updated_at=:ts WHERE id=:id", {"st": stage, "ts": _now(), "id": lead_id})
    return JSONResponse({"ok": True})


@app.post("/api/salesperson/chat")
async def api_salesperson_chat(request: Request):
    payload = await request.json()
    lead_id = payload.get("lead_id") or ""
    message = (payload.get("message") or "").strip()
    if not lead_id or not message:
        return JSONResponse({"error": "lead_id and message required"}, status_code=400)

    lead = _fetchone("SELECT * FROM leads WHERE id=:id", {"id": lead_id})
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)

    mk = _month_key()
    limits = _get_limits()
    used = _count_used_leads_this_month(mk)
    already_counted = _is_lead_counted_this_month(mk, lead_id)

    if (not already_counted) and used >= int(limits["lead_cap"]):
        return JSONResponse({"error": f"Monthly lead cap reached ({used}/{limits['lead_cap']}) for {mk}."}, status_code=402)

    if not already_counted:
        _count_lead_now(mk, lead_id)

    # Save user message
    _exec(
        "INSERT INTO messages (lead_id, role, content, created_at) VALUES (:id, 'user', :c, :ts)",
        {"id": lead_id, "c": message, "ts": _now()},
    )

    profile = _fetchone("SELECT * FROM business_profile WHERE id=1") or {}
    hist_rows = _fetchall("SELECT role, content FROM messages WHERE lead_id=:id ORDER BY id DESC LIMIT 12", {"id": lead_id})
    history = list(reversed(hist_rows))

    if not axel_generate:
        reply = "ChatGPT bridge not configured. Add OPENAI_API_KEY + axel_bridge."
    else:
        reply = axel_generate(
            tool="salesperson_chat",
            inputs={"profile": profile, "lead": lead, "history": history, "message": message},
            tone=(profile.get("tone") or "confident"),
            audience="small business",
            brand="RAR AI Studio",
        )
        reply = _stringify_output(reply)

    # Save assistant message
    _exec(
        "INSERT INTO messages (lead_id, role, content, created_at) VALUES (:id, 'assistant', :c, :ts)",
        {"id": lead_id, "c": reply, "ts": _now()},
    )

    _exec("UPDATE leads SET updated_at=:ts WHERE id=:id", {"ts": _now(), "id": lead_id})

    used2 = _count_used_leads_this_month(mk)
    return JSONResponse({"ok": True, "reply": reply, "usage": {"month": mk, "used_leads": used2, "lead_cap": limits["lead_cap"], "plan": limits["plan"]}})


# ----------------------------
# Host-friendly runner
# ----------------------------
if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST") or "0.0.0.0"
    port = int(os.getenv("PORT") or "8000")
    uvicorn.run("app.main:app", host=host, port=port)
