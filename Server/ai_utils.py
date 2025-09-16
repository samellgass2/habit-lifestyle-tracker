import os
from datetime import datetime
from sqlalchemy import select, and_
from zoneinfo import ZoneInfo

from .models import AiProcessedReflectionsTable
from openai import OpenAI

OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
PROMPT_VERSION = "v1"

_client = None
def get_client():
    global _client
    if _client is None:
        _client = OpenAI()
    return _client

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

    # “7 daily + 4 weekly if available; otherwise just fill with more dailies”
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
        summaries = ["They’re starting a new habit journey and care about growth, consistency, and self-kindness."]
    msgs = build_motivation_prompt(summaries)
    cli = get_client()
    resp = cli.chat.completions.create(model=OPENAI_MODEL, messages=msgs, temperature=0.7)
    return resp.choices[0].message.content.strip()
