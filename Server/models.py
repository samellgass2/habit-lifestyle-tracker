# DB Setup & Reinitialization 
from sqlalchemy import (
    MetaData, Table, Column, Integer, String, BigInteger, Index,
    DateTime, ForeignKey, Text, Date, JSON, UniqueConstraint, 
    Enum, Boolean, Numeric, func, text
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
    Column("points_earned", Numeric(10,2), nullable=False, server_default="0.00"),
    Column("points_spent",  Numeric(10,2), nullable=False, server_default="0.00"),
    Column("timezone", String(64), nullable=False, default="UTC", server_default="UTC"),
    Column("emoji", String(8), nullable=True),
    Column("accent_color", String(16), nullable=True),
    Column("ai_title", String(128), nullable=True),
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

AiProcessedReflectionsTable = Table(
    "ai_processed_reflections",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False, index=True),
    Column("scope", Enum("day","week","month", name="ai_scope"), nullable=False),
    Column("kind", Enum("summary","gratitude","accomplishments","motivation","insight", name="ai_kind"), nullable=False),
    Column("target_date", Date, nullable=True),
    Column("period_start", Date, nullable=True),
    Column("period_end", Date, nullable=True),
    Column("summary", Text, nullable=False),
    Column("model", String(64), nullable=False),
    Column("prompt_version", String(32), nullable=False),
    Column("generated_at_utc", DateTime, nullable=False),
    UniqueConstraint("user_id","scope","kind","target_date", name="ux_air_user_scope_day_kind"),
    UniqueConstraint("user_id","scope","kind","period_start","period_end", name="ux_air_user_scope_range_kind"),
)

PointsMode = Enum("tasks", "time", "percent", name="points_mode", native_enum=False)

CategoriesTable = Table(
    "categories", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("category_name", String(64), nullable=False),
    Column("emoji", String(8), nullable=True),
    Column("color", String(16), nullable=True),
    Column("points_mode", PointsMode, nullable=False, server_default="tasks"),
    Column("is_default", Boolean, nullable=False, server_default="0"),
    Column("is_focused", Boolean, nullable=False, server_default="0"),
    Column("ai_summary", Text, nullable=True),
    Column("created_at_utc", DateTime, nullable=False, default=datetime.utcnow),
    Column("updated_at_utc", DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow),
    UniqueConstraint("user_id", "category_name", name="ux_user_catname"),
)

Challenge = Enum("automatic", "easy", "difficult", "hard", "daunting",
                 name="challenge_level", native_enum=False)

HabitType = Enum("one-off", "recurring", name="habit_type", native_enum=False)

FeedItemKind = Enum(
    "habit",        # CompletedHabitsTable row
    "reward",       # RewardsPurchasedTable row
    "reflection",   # ReflectionsTable row
    name="feed_item_kind",
    native_enum=False,
)

HabitsTable = Table(
    "habits", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("creator_user_id", Integer, ForeignKey("users.id"), nullable=True),
    Column("category_id", Integer, ForeignKey("categories.id"), nullable=False),

    Column("name", String(128), nullable=False),
    Column("type", HabitType, nullable=False),
    Column("date_local", Date, nullable=True),  # only meaningful for one-off

    Column("challenge", Challenge, nullable=False, server_default="easy"),
    Column("importance", Integer, nullable=False, server_default="1"),  # 1..3
    Column("base_value", Numeric(6, 2), nullable=False, server_default="1.00"),

    Column("time_minutes", Integer, nullable=True),         # when points_mode='time'
    Column("percent_target", Numeric(5, 2), nullable=True), # when points_mode='percent' (0..100)

    Column("schedule", JSON, nullable=True), # For recurring habits to set a schedule like [0,1,2] (sun-tues)

    Column("notes", Text, nullable=True),
    Column("active", Boolean, nullable=False, server_default="1"),
    Column("ai_created", Boolean, nullable=False, server_default="0"),
    Column("instances", Integer, nullable=False, server_default="1"),

    Column("created_at_utc", DateTime, nullable=False, default=datetime.utcnow),
    Column("updated_at_utc", DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow),
)

PendingHabitsTable = Table(
    "pending_habits", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("creator_user_id", Integer, ForeignKey("users.id"), nullable=True),
    Column("category_id", Integer, ForeignKey("categories.id"), nullable=False),

    Column("name", String(128), nullable=False),
    Column("type", HabitType, nullable=False),
    Column("date_local", Date, nullable=True),

    Column("challenge", Challenge, nullable=False, server_default="easy"),
    Column("importance", Integer, nullable=False, server_default="1"),
    Column("base_value", Numeric(6, 2), nullable=False, server_default="1.00"),

    Column("time_minutes", Integer, nullable=True),
    Column("percent_target", Numeric(5, 2), nullable=True),

    Column("schedule", JSON, nullable=True),

    Column("notes", Text, nullable=True),
    Column("active", Boolean, nullable=False, server_default="1"),
    Column("ai_created", Boolean, nullable=False, server_default="0"),
    Column("instances", Integer, nullable=False, server_default="1"),

    Column("created_at_utc", DateTime, nullable=False, default=datetime.utcnow),
    Column("updated_at_utc", DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow),
)

CompletedHabitsTable = Table(
    "completed_habits", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),

    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("habit_id", Integer, ForeignKey("habits.id"), nullable=True),
    Column("category_id", Integer, ForeignKey("categories.id"), nullable=False),

    Column("name_snapshot", String(128), nullable=False),
    Column("points_mode", PointsMode, nullable=False),

    Column("challenge", Challenge, nullable=False),
    Column("importance", Integer, nullable=False),
    Column("base_value", Numeric(6, 2), nullable=False),

    Column("time_minutes", Integer, nullable=True),
    Column("percent_value", Numeric(5, 2), nullable=True),  # 0..100 actual

    Column("points_awarded", Numeric(8, 2), nullable=False),
    Column("ai_created", Boolean, nullable=False, server_default="0"),

    Column("completed_at_local", DateTime, nullable=False),
    Column("day_local", Date, nullable=False),

    Column("created_at_utc", DateTime, nullable=False, default=datetime.utcnow),
)

PointsSpendLedger = Table(
    "points_spend_ledger", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("amount", Numeric(10,2), nullable=False),
    Column("note", String(255), nullable=True),
    Column("created_at_utc", DateTime, nullable=False, default=datetime.utcnow),
    Index("ix_psl_user", "user_id", "created_at_utc"),
)

RewardsTable = Table(
    "rewards", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False, index=True),
    Column("creator_user_id", Integer, ForeignKey("users.id"), nullable=True),
    Column("name", String(120), nullable=False),
    Column("emoji", String(16), nullable=True),
    Column("color", String(16), nullable=True),             # pastel hex like "#F6E58D"
    Column("cost_points", Numeric(10,2), nullable=False),   # price in points
    Column("is_recurring", Integer, nullable=False, server_default="0"),  # 0/1
    Column("active", Integer, nullable=False, server_default="1"),
    Column("created_at_utc", DateTime, nullable=False, default=datetime.utcnow),
    Index("ix_rewards_user_active", "user_id", "active"),
)

PendingRewardsTable = Table(
    "pending_rewards", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False, index=True),
    Column("creator_user_id", Integer, ForeignKey("users.id"), nullable=True),
    Column("name", String(120), nullable=False),
    Column("emoji", String(16), nullable=True),
    Column("color", String(16), nullable=True),
    Column("cost_points", Numeric(10,2), nullable=False),
    Column("note", Text, nullable=True),
    Column("is_recurring", Integer, nullable=False, server_default="0"),
    Column("active", Integer, nullable=False, server_default="1"),
    Column("created_at_utc", DateTime, nullable=False, default=datetime.utcnow),
    Index("ix_pending_rewards_user_active", "user_id", "active"),
)

RewardsPurchasedTable = Table(
    "rewards_purchased", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False, index=True),
    Column("reward_id", Integer, ForeignKey("rewards.id"), nullable=True),  # allow manual purchases too
    Column("points_spent", Numeric(10,2), nullable=False),
    Column("note", String(255), nullable=True),
    Column("purchased_at_utc", DateTime, nullable=False, default=datetime.utcnow),
    Index("ix_rewards_purchased_user_time", "user_id", "purchased_at_utc"),
)

AiProcessedGratitudesTable = Table(
    "ai_processed_gratitudes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False, index=True),
    # rolling window we summarized over (local)
    Column("period_start", Date, nullable=False),
    Column("period_end",   Date, nullable=False),
    # array of { "word": str, "count": int }
    Column("cloud", JSON, nullable=False),
    # book-keeping
    Column("model", String(64), nullable=False),
    Column("prompt_version", String(16), nullable=False),
    Column("generated_at_utc", DateTime, nullable=False),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)

AiGeneratedMotivationsTable = Table(
    "ai_generated_motivations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False, index=True),
    Column("text", Text, nullable=False),
    Column("source", String(16), nullable=False),  # 'daily' | 'on_demand'
    Column("model", String(64), nullable=True),
    Column("prompt_version", String(16), nullable=True),
    Column("generated_at_utc", DateTime, nullable=False),
    Index("ai_motivations_user_time_desc", "user_id", "generated_at_utc"),
)

FriendsTable = Table(
    "friends",
    metadata,
    Column("friendship_id", Integer, primary_key=True, autoincrement=True),

    # requester
    Column(
        "friending_user_id",
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    ),

    # recipient
    Column(
        "friended_user_id",
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    ),

    Column(
        "status",
        Enum("pending", "accepted", "rejected", name="friend_status"),
        nullable=False,
        server_default="pending",
    ),

    Column("message", String(500), nullable=True),

    Column(
        "created_at_utc",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    Column(
        "updated_at_utc",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    ),

    # prevent duplicate rows per unordered pair
    UniqueConstraint(
        "friending_user_id",
        "friended_user_id",
        name="uq_friend_pair",
    ),

    # 🔥 Performance-critical indexes
    Index("idx_friend_friending", "friending_user_id"),
    Index("idx_friend_friended", "friended_user_id"),

    # Optional but recommended if you do heavy filtering on status
    Index("idx_friend_status", "status"),
)

FeedReactionsTable = Table(
    "feed_reactions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("feed_kind", Enum("habit", "reward", "reflection", name="feed_kind_enum"), nullable=False, index=True),
    Column("feed_item_id", Integer, nullable=False),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False, index=True),
    Column("recipient_id", Integer, ForeignKey("users.id"), nullable=False, index=True),
    Column("reaction", String(16), nullable=False),
    Column("seen", Boolean, nullable=False, server_default=text("0")),
    Column("created_at_utc", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")),
    Index("idx_feed_reactions_recipient_seen", "recipient_id", "seen"),
)


FeedCommentsTable = Table(
    "feed_comments",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("feed_kind", Enum("habit", "reward", "reflection", name="feed_comments_kind_enum"), nullable=False, index=True),
    Column("feed_item_id", Integer, nullable=False),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False, index=True),
    Column("recipient_id", Integer, ForeignKey("users.id"), nullable=False, index=True),
    Column("comment_text", Text, nullable=False),
    Column("seen", Boolean, nullable=False, server_default=text("0")),
    Column("created_at_utc", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")),
    Index("idx_feed_comments_recipient_seen", "recipient_id", "seen"),
)



Index("ix_completed_user_day", CompletedHabitsTable.c.user_id, CompletedHabitsTable.c.day_local)
Index("ix_categories_user", CategoriesTable.c.user_id)
Index("ix_users_username", UsersTable.c.username, unique=True)
Index("ix_habits_user_active", HabitsTable.c.user_id, HabitsTable.c.active)
Index("ix_habits_user_date", HabitsTable.c.user_id, HabitsTable.c.date_local)
Index("ix_pending_habits_user_active", PendingHabitsTable.c.user_id, PendingHabitsTable.c.active)
Index("ix_pending_habits_user_date", PendingHabitsTable.c.user_id, PendingHabitsTable.c.date_local)



def create_all_tables(engine):
    metadata.create_all(engine)
