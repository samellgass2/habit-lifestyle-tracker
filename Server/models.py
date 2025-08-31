# DB Setup & Reinitialization 
from sqlalchemy import (
    MetaData, Table, Column, Integer, String, BigInteger, Index,
    DateTime, ForeignKey, Text, Date, JSON, UniqueConstraint
)
from datetime import datetime, timedelta
# Place all schema in one collection
metadata = MetaData()

UsersTable = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(64), nullable=False, unique=True),
    Column("password_hash", String(300), nullable=False),
    Column("points_earned", BigInteger, nullable=False, server_default="0"),
    Column("points_spent", BigInteger, nullable=False, server_default="0"),
    Column("timezone", String(64), nullable=False, default="UTC", server_default="UTC")

)

SessionsTable = Table(
    "sessions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False, index=True),
    # store only a HASH of the token (so a DB leak can’t be used to impersonate)
    Column("token_hash", String(64), nullable=False, unique=True),  # hex sha256 = 64 chars
    Column("created_at", DateTime, nullable=False),
    Column("expires_at", DateTime, nullable=False),
    Column("user_agent", String(256), nullable=True),
    Column("ip", String(64), nullable=True),
)

ReflectionsTable = Table(
    "reflections",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False, index=True),
    Column("day", Date, nullable=False, index=True),            # calendar day (UTC)
    Column("summary", Text, nullable=True),
    Column("highs", Text, nullable=True),
    Column("lows", Text, nullable=True),
    Column("buffalos", Text, nullable=True),
    Column("mood", Integer, nullable=True),                     # 1..10
    Column("gratitude", JSON, nullable=True),                  
    Column("created_at_utc", DateTime, nullable=False),
    Column("updated_at_utc", DateTime, nullable=False),
    Column("day_local", Date, nullable=False, index=True),
    UniqueConstraint("user_id", "day_local", name="ux_reflections_user_day_local"),

)

Index("ix_users_username", UsersTable.c.username, unique=True)

def create_all_tables(engine):
    metadata.create_all(engine)