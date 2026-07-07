import os
import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import select, and_, insert, update
from .models import (
    ReflectionsTable, AiProcessedReflectionsTable, UsersTable,
    CategoriesTable, CompletedHabitsTable, HabitsTable
)
from .utils import week_bounds, month_bounds # helper you already have

# ── adamOS L3 compute (Seam 5) ──────────────────────────────────────────────
# The habit tracker is an L3 resource consumer of adamOS compute. AI no longer
# calls OpenAI directly — it POSTs to adamOS's /api/adam/call through the GATEWAY
# (which resolves the project bearer, enforces the daily compute quota, records
# cost/latency, and routes to local Qwen). Business logic (prompts, DB writes,
# JSON repair) is unchanged — only the transport moved.
#
#   ADAM_API_BASE      the gateway, host-reachable (default http://localhost:5001)
#   ADAM_PROJECT_TOKEN the `habits-ai-prod` project token (Bearer)
#   ADAM_MODEL_HINT    preferred local model id
#
# Read lazily at call time — app.py's load_dotenv() runs after this module is
# imported (app.py:34 imports ai_utils, load_dotenv is called later), so freezing
# these at module scope would capture pre-.env-load values (empty token → 500).
_ADAM_MODEL_HINT_DEFAULT = "mlx-community/Qwen3.6-35B-A3B-8bit"


def _adam_api_base() -> str:
    return os.getenv("ADAM_API_BASE", "http://localhost:5001").rstrip("/")


def _adam_project_token() -> str:
    return os.environ.get("ADAM_PROJECT_TOKEN", "")


def _adam_model_hint() -> str:
    return os.getenv("ADAM_MODEL_HINT", _ADAM_MODEL_HINT_DEFAULT)


# Kept name: app.py imports OPENAI_MODEL and writes it into the AI bookkeeping
# `model` column. It now names the model we ASK adamOS for (the served model is
# echoed back in metrics.model — see _adam_text's second return value).
# Lazy attribute access via module __getattr__ so late .env loads still land.
def __getattr__(name):
    if name == "OPENAI_MODEL":
        return _adam_model_hint()
    raise AttributeError(name)


PROMPT_VERSION = "v1"

_client = None
def get_client():
    # Retained as a no-op so app.py call signatures (recompute_week_month(...,
    # cli, model)) are untouched. adamOS compute needs no client handle.
    return None


def _adam_text(messages, temperature=0.7, response_format=None, source="habits:ai"):
    """Transport-only: POST messages to adamOS /api/adam/call and return
    (content, served_model). No business logic — prompts + parsing stay in this
    module (I-COMPUTE-3/-4)."""
    token = _adam_project_token()
    if not token:
        raise RuntimeError("ADAM_PROJECT_TOKEN is not set — cannot reach adamOS compute")
    model_hint = _adam_model_hint()
    body = {
        "capability": "text-generation",
        "input": {"messages": messages, "temperature": temperature},
        "project": "habits",
        "source": source,
        "routing": "local-preferred",
        "quality_floor": "good",
        "model_hint": model_hint,
    }
    if response_format:
        body["input"]["response_format"] = response_format
    resp = requests.post(
        f"{_adam_api_base()}/api/adam/call?sync=true",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"adam/call failed: {data.get('error')}")
    output = data.get("output") or {}
    content = output.get("content") if isinstance(output, dict) else output
    served_model = (data.get("metrics") or {}).get("model") or model_hint
    return (content or "").strip(), served_model


SYSTEM_PROMPT = (
    "You will motivate users and focus on positive outcomes..."
    # (reuse your existing prompt text)
)

AI_HABIT_JSON_INSTRUCTIONS = (
    "Return only a valid JSON object, nothing else. "
    "Do not include markdown, code fences, or commentary. "
    "If unsure, make a reasonable assumption."
)

def _build_input_text(row):
    parts = []
    if row.get("summary"): parts.append(f"Summary: {row['summary']}")
    if row.get("highs"):    parts.append(f"Highs: {row['highs']}")
    if row.get("lows"):    parts.append(f"Lows: {row['lows']}")
    if row.get("buffalos"):parts.append(f"Buffalos: {row['buffalos']}")
    if row.get("mood") is not None: parts.append(f"Mood: {row['mood']}/5")
    return "\n".join(parts).strip()

def _call_openai(cli, model, text):
    # Name kept for call-site compatibility; body now routes through adamOS.
    content, _served = _adam_text(
        [{"role": "system", "content": SYSTEM_PROMPT},
         {"role": "user", "content": text}],
        temperature=0.7,
        source="habits:summary",
    )
    return content

def upsert_ai_day(conn, user_id, day_local, text, model, prompt_version="v1"):
    now_utc = datetime.utcnow()
    existing_id = conn.execute(
        select(AiProcessedReflectionsTable.c.id).where(and_(
            AiProcessedReflectionsTable.c.user_id == user_id,
            AiProcessedReflectionsTable.c.scope == "day",
            AiProcessedReflectionsTable.c.kind == "summary",
            AiProcessedReflectionsTable.c.target_date == day_local,
        ))
    ).scalar()
    payload = dict(
        summary=text, model=model, prompt_version=prompt_version,
        generated_at_utc=now_utc
    )
    if existing_id:
        conn.execute(update(AiProcessedReflectionsTable)
            .where(AiProcessedReflectionsTable.c.id == existing_id)
            .values(**payload))
    else:
        conn.execute(insert(AiProcessedReflectionsTable).values(
            user_id=user_id, scope="day", kind="summary",
            target_date=day_local, **payload))

def recompute_week_month(conn, user_id, day_local, cli, model):
    # If week containing day is fully in the past (end < today_local), compute/update
    tz = conn.execute(select(UsersTable.c.timezone)
                    .where(UsersTable.c.id == user_id)).scalar() or "UTC"
    today_local = datetime.now(ZoneInfo(tz)).date()

    w_start, w_end = week_bounds(day_local)        # inclusive
    m_start, m_end = month_bounds(day_local)    # inclusive

    # Only roll weekly summary if the week is complete
    if w_end < today_local:
        rows = conn.execute(
            select(ReflectionsTable.c.summary, ReflectionsTable.c.highs, ReflectionsTable.c.lows,
                ReflectionsTable.c.buffalos, ReflectionsTable.c.mood)
            .where(and_(ReflectionsTable.c.user_id==user_id,
                        ReflectionsTable.c.day_local>=w_start,
                        ReflectionsTable.c.day_local<=w_end))
            .order_by(ReflectionsTable.c.day_local.asc())
        ).mappings().all()
        text = "\n\n".join(_build_input_text(r) for r in rows if _build_input_text(r))
        if text:
            ai = _call_openai(cli, model, text)
            _upsert_period(conn, user_id, "week", w_start, w_end, ai, model)

    # Only roll monthly summary if month complete
    if m_end < today_local:
        rows = conn.execute(
            select(ReflectionsTable.c.summary, ReflectionsTable.c.highs, ReflectionsTable.c.lows,
                ReflectionsTable.c.buffalos, ReflectionsTable.c.mood)
            .where(and_(ReflectionsTable.c.user_id==user_id,
                        ReflectionsTable.c.day_local>=m_start,
                        ReflectionsTable.c.day_local<=m_end))
            .order_by(ReflectionsTable.c.day_local.asc())
        ).mappings().all()
        text = "\n\n".join(_build_input_text(r) for r in rows if _build_input_text(r))
        if text:
            ai = _call_openai(cli, model, text)
            _upsert_period(conn, user_id, "month", m_start, m_end, ai, model)

def _upsert_period(conn, user_id, scope, p_start, p_end, text, model, prompt_version="v1"):
    now_utc = datetime.utcnow()
    existing_id = conn.execute(
        select(AiProcessedReflectionsTable.c.id).where(and_(
            AiProcessedReflectionsTable.c.user_id == user_id,
            AiProcessedReflectionsTable.c.scope == scope,
            AiProcessedReflectionsTable.c.kind == "summary",
            AiProcessedReflectionsTable.c.period_start == p_start,
            AiProcessedReflectionsTable.c.period_end == p_end,
        ))
    ).scalar()
    payload = dict(
        summary=text, model=model, prompt_version=prompt_version,
        generated_at_utc=now_utc, period_start=p_start, period_end=p_end
    )
    if existing_id:
        conn.execute(update(AiProcessedReflectionsTable)
            .where(AiProcessedReflectionsTable.c.id == existing_id)
            .values(**payload))
    else:
        conn.execute(insert(AiProcessedReflectionsTable).values(
            user_id=user_id, scope=scope, kind="summary", **payload))

def fetch_recent_summaries(conn, user_id: int, limit_day=7, limit_week=4):
    # Get most recent day & week summaries (prefer days first)
    day_rows = conn.execute(
        select(AiProcessedReflectionsTable.c.summary)
        .where(and_(AiProcessedReflectionsTable.c.user_id == user_id,
                    AiProcessedReflectionsTable.c.scope == "day",
                    AiProcessedReflectionsTable.c.kind == "summary"))
        .order_by(AiProcessedReflectionsTable.c.generated_at_utc.desc())
        .limit(limit_day)
    ).scalars().all()

    week_rows = conn.execute(
        select(AiProcessedReflectionsTable.c.summary)
        .where(and_(AiProcessedReflectionsTable.c.user_id == user_id,
                    AiProcessedReflectionsTable.c.scope == "week",
                    AiProcessedReflectionsTable.c.kind == "summary"))
        .order_by(AiProcessedReflectionsTable.c.generated_at_utc.desc())
        .limit(limit_week)
    ).scalars().all()

    # "7 daily + 4 weekly if available; otherwise just fill with more dailies"
    texts = day_rows + week_rows
    return texts[:11]

def build_motivation_prompt(summaries: list[str]) -> list[dict]:
    joined = "\n\n".join(f"- {s}" for s in summaries if s and s.strip())
    sys = (
        "You are a warm, concise coach. You will motivate users and remind them of their strengths. "
        "Write a short, uplifting note (max ~60 words). Make it personal but not overly specific; "
        "sound like a wise friend who knows their patterns."
    )
    usr = (
        "Here are the user's recent summarized reflections (daily & weekly):\n\n"
        f"{joined}\n\n"
        "Based on these, write one encouraging message they need to hear today."
    )
    return [{"role": "system", "content": sys}, {"role": "user", "content": usr}]

def generate_motivation(conn, user_id: int) -> str:
    summaries = fetch_recent_summaries(conn, user_id)
    # Graceful fallback if they have no summaries yet
    if not summaries:
        summaries = ["They're starting a new habit journey and care about growth, consistency, and self-kindness."]
    msgs = build_motivation_prompt(summaries)
    content, _served = _adam_text(msgs, temperature=0.7, source="habits:motivation")
    return content

def _fetch_category_info(conn, user_id: int, category_id: int):
    return conn.execute(
        select(
            CategoriesTable.c.category_name,
            CategoriesTable.c.points_mode
        ).where(and_(
            CategoriesTable.c.id == category_id,
            CategoriesTable.c.user_id == user_id
        ))
    ).mappings().first()


def _fetch_recent_completed_habits(conn, user_id: int, category_id: int):
    rows = conn.execute(
        select(
            CompletedHabitsTable.c.name_snapshot,
            CompletedHabitsTable.c.points_awarded,
            CompletedHabitsTable.c.completed_at_local,
        ).where(and_(
            CompletedHabitsTable.c.user_id == user_id,
            CompletedHabitsTable.c.category_id == category_id
        ))
        .order_by(CompletedHabitsTable.c.completed_at_local.desc())
        .limit(10)
    ).mappings().all()
    return [
        {
            "name": r["name_snapshot"],
            "points": float(r["points_awarded"]),
            "when": r["completed_at_local"].isoformat()
        }
        for r in rows
    ]


def _fetch_active_habits(conn, user_id: int, category_id: int):
    rows = conn.execute(
        select(
            HabitsTable.c.name,
            HabitsTable.c.base_value,
            HabitsTable.c.challenge,
        ).where(and_(
            HabitsTable.c.user_id == user_id,
            HabitsTable.c.category_id == category_id,
            HabitsTable.c.active == 1
        ))
        .order_by(HabitsTable.c.created_at_utc.desc())
        .limit(10)
    ).mappings().all()
    return [
        {
            "name": r["name"],
            "challenge": r["challenge"],
            "base_value": float(r["base_value"]),
        }
        for r in rows
    ]

def build_habit_prompt(conn, user_id: int, category_id: int, user_input: str):
    cat = _fetch_category_info(conn, user_id, category_id)
    if not cat:
        raise ValueError("Category not found / not owner")

    category_name = cat["category_name"]
    mode = cat["points_mode"]  # tasks | time | percent

    completed = _fetch_recent_completed_habits(conn, user_id, category_id)
    if completed:
        habits = completed
        context_kind = "completed"
    else:
        habits = _fetch_active_habits(conn, user_id, category_id)
        context_kind = "active"

    # Nicely formatted bullet list
    if habits:
        bullets = "\n".join(f"- {h['name']}" for h in habits)
    else:
        bullets = "None yet — new category"

    sys = (
        f"You are an expert habit coach specializing in '{category_name}'. "
        "Analyze what habits exist, their difficulty, and what might help the user grow.\n\n"
        "Generate a brand new habit proposal.\n\n"
        f"{AI_HABIT_JSON_INSTRUCTIONS}\n\n"
        "Your JSON format MUST include:\n"
        "  name: string\n"
        "  type: 'one-off' | 'recurring'\n"
        "  challenge: 'easy' | 'difficult' | 'hard' | 'daunting'\n"
        "  importance: 1 | 2 | 3\n"
        "  base_value: float >= 0.5\n"
        "  reason: 10-30 word explanation of why this habit is recommended. "
        "Explain in terms of existing habits or the category.\n"
        "If this category uses a metric:\n"
        "  - For 'time': include time_minutes (int > 0)\n"
        "  - For 'percent': include percent_target (1–100 integer)\n"
        "  - For 'tasks': do not include metric fields\n"
        "Output ONLY the JSON object."
    )

    usr = (
        f"The user's {context_kind} habits in this category:\n"
        f"{bullets}\n\n"
        f"Category points mode: {mode}\n"
    )
    if user_input:
        usr += f"User request: \"{user_input.strip()}\"\n\n"

    usr += "Now propose one new habit they should add."

    return [
        {"role": "system", "content": sys},
        {"role": "user", "content": usr},
    ]

def generate_habit(conn, user_id: int, category_id: int, user_input, today_date):
    msgs = build_habit_prompt(conn, user_id, category_id, user_input)

    # Route through adamOS; request JSON mode now that the transport supports it.
    txt, _served = _adam_text(
        msgs, temperature=0.4,
        response_format={"type": "json_object"},
        source="habits:habit-gen",
    )

    # Attempt to extract JSON robustly (unchanged repair logic)
    try:
        data = json.loads(txt)  # ideal case
    except json.JSONDecodeError:
        # Try stripping code fences or trailing text
        try:
            start = txt.find("{")
            end = txt.rfind("}") + 1
            cleaned = txt[start:end]
            data = json.loads(cleaned)
        except Exception as e:
            raise RuntimeError(f"AI returned malformed JSON: {txt}") from e

    # Sanitize + optional fill defaults based on DB rules:
    data.setdefault("type", "recurring")
    data.setdefault("importance", 1)
    data.setdefault("challenge", "easy")
    data["ai_created"] = True
    if data["type"] == "one-off":
        data["date_local"] = today_date.isoformat()
    print(f"Outcome from AI payload: {data}")

    return data
