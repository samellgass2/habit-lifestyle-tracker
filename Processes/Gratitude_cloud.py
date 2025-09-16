import os, sys, argparse, logging, pathlib, json
from dotenv import load_dotenv
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from sqlalchemy import create_engine, select, insert, and_, func
from sqlalchemy.exc import SQLAlchemyError


ROOT = pathlib.Path(__file__).resolve().parents[1]
load_dotenv(ROOT / "Server" / ".env")

from Server.models import (
    UsersTable, ReflectionsTable, AiProcessedGratitudesTable, metadata
)

# --- OpenAI
from openai import OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
PROMPT_VERSION = "v1"
client = OpenAI(api_key=OPENAI_API_KEY)

LOG = logging.getLogger("gratitude_cloud")

def setup_logging(v):
    level = logging.INFO if v == 1 else logging.DEBUG if v >= 2 else logging.WARNING
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")

def parse_args():
    p = argparse.ArgumentParser("Build daily gratitude clouds")
    p.add_argument("--days", type=int, default=30, help="lookback window (default 30)")
    p.add_argument("--min-answers", type=int, default=100, help="ensure at least this many answers if available (default 100)")
    p.add_argument("--user-id", type=int)
    p.add_argument("--user", type=str)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("-v", "--verbose", action="count", default=0)
    return p.parse_args()

def connect_engine():
    cnf = os.getenv("MYSQL_CNF")
    if not cnf:
        raise RuntimeError("MYSQL_CNF not set")
    return create_engine(
        "mysql+pymysql://",
        connect_args={"read_default_file": cnf, "read_default_group": "client"},
        pool_pre_ping=True, pool_recycle=1800, future=True
    )

SYSTEM_PROMPT = (
    "You are an NLP normalizer. You will deduplicate and canonicalize gratitude entries "
    "into SINGLE WORD tokens representing people/things/categories (e.g., 'Kasey', "
    "'family', 'health', 'music', 'sunshine').\n"
    "- Merge near-duplicates and references (e.g., 'my girlfriend', 'my lovely girlfriend Kasey' -> 'Kasey').\n"
    "- Strip punctuation and emojis.\n"
    "- Lowercase general categories (family, health), but KEEP proper names capitalized.\n"
    "- Return JSON array of objects: [{\"word\": str, \"count\": int}], sorted by count desc. "
    "Return at least 5 and at most 20 items."
)

def call_openai(items):
    # items: list[str] of raw gratitude texts
    content = "Gratitude answers:\n" + "\n".join(f"- {s}" for s in items if s)
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0.2,
        messages=[
            {"role":"system", "content": SYSTEM_PROMPT},
            {"role":"user", "content": content},
        ],
    )
    text = resp.choices[0].message.content.strip()
    # Try to load JSON; if it's fenced, strip code fence
    if text.startswith("```"):
        text = text.strip("`")
        # remove potential language hint like ```json
        text = "\n".join(line for line in text.splitlines() if not line.strip().startswith("json"))
    try:
        arr = json.loads(text)
        # minimal validation
        out = []
        for x in arr:
            w = (x.get("word") or "").strip()
            c = int(x.get("count") or 0)
            if w and c > 0:
                out.append({"word": w, "count": c})
        return out[:20]
    except Exception as e:
        LOG.warning("JSON parse failed; returning empty. raw=%s", text[:400])
        return []

def clamp_window(conn, uid, tzname, look_days, min_answers):
    tz = tzname or "UTC"
    today = datetime.now(ZoneInfo(tz)).date()
    start = today - timedelta(days=look_days-1)  # inclusive
    # Find earliest date going back until we accumulate >= min_answers (if possible)
    # Pull counts per day first
    rows = conn.execute(
        select(ReflectionsTable.c.day_local, ReflectionsTable.c.gratitude)
        .where(and_(ReflectionsTable.c.user_id == uid,
                    ReflectionsTable.c.day_local <= today,
                    ReflectionsTable.c.day_local >= today - timedelta(days=365)))  # guardrail
        .order_by(ReflectionsTable.c.day_local.desc())
    ).mappings().all()

    answers = []
    earliest = today
    for r in rows:
        d = r["day_local"]
        g = r["gratitude"] or []
        if isinstance(g, list):
            answers.extend([s for s in g if isinstance(s, str)])
        earliest = d
        if len(answers) >= min_answers and d <= start:
            break

    # Final window: max(last N days, window that accumulated 100 items)
    period_start = min(start, earliest)
    period_end   = today
    return period_start, period_end, answers

def upsert_cloud(conn, uid, start, end, cloud, dry):
    vals = dict(
        cloud=cloud, model=OPENAI_MODEL, prompt_version=PROMPT_VERSION,
        generated_at_utc=datetime.utcnow()
    )
    if dry:
        LOG.info("[DRY] Would insert ai_processed_gratitudes for user=%s %s..%s", uid, start, end)
        return

    conn.execute(
        insert(AiProcessedGratitudesTable).values(
            user_id=uid, period_start=start, period_end=end, **vals
        )
    )

def main():
    args = parse_args()
    setup_logging(args.verbose)
    eng = connect_engine()

    with eng.begin() as conn:
        sel = select(UsersTable.c.id, UsersTable.c.username, UsersTable.c.timezone)
        if args.user_id:
            sel = sel.where(UsersTable.c.id == args.user_id)
        if args.user:
            sel = sel.where(UsersTable.c.username == args.user)
        users = conn.execute(sel).all()
        if not users:
            LOG.warning("No users matched.")
            return 0

        for uid, uname, tz in users:
            start, end, answers = clamp_window(conn, uid, tz, args.days, args.min_answers)
            if not answers:
                LOG.info("%s: no gratitude answers in window %s..%s", uname, start, end); continue

            cloud = call_openai(answers)
            if not cloud:
                LOG.info("%s: AI returned empty cloud", uname); continue

            upsert_cloud(conn, uid, start, end, cloud, args.dry_run)
            LOG.info("%s: saved cloud (%d items) for %s..%s", uname, len(cloud), start, end)
    return 0

if __name__ == "__main__":
    sys.exit(main())
