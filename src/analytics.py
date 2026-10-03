"""Admin analytics engine for the Lentor Modern Concierge.

Pure functions (no I/O) so they can be unit-tested: metric computation, content-gap
ranking, text-first dashboard formatting, and an admin-only conversational Q&A helper.
"""

import logging
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

TOTAL_UNITS = 605
# Singapore has no DST, so a fixed UTC+8 offset is exact (and avoids a tzdata dependency).
SGT = timezone(timedelta(hours=8))
MENU_PREFIX = "[Menu] "

TOOL_TOPICS = {
    "search_bylaws_and_handbook": "Estate rules & handbook",
    "search_mall_directory": "Mall & shops",
    "get_verified_community_tips": "Community tips",
    "generate_mcst_email_draft": "MA email drafts",
    "submit_tip_to_moderation": "Tip submissions",
    "submit_developer_feedback": "Feedback to admin",
    "search_estate_profile": "Estate profile & transit",
    "analyze_resident_image": "Photo queries",
}

MENU_LABELS = {
    "menu_contacts": "Estate Contacts",
    "menu_facilities": "Facilities & Gym",
    "menu_transit": "Transit & Buses",
    "menu_mall": "Mall & Deals",
    "menu_reno": "Moving & Reno",
    "menu_iplus": "iPlus Living Guide",
}

# Phrases in a final reply that indicate the bot could not actually answer.
_UNANSWERED_PATTERNS = [
    r"i don'?t know",
    r"i do not know",
    r"i don'?t have (?:that|this|any|the|specific|verified)",
    r"i do not have (?:that|this|any|the|specific|verified)",
    r"(?:do not|don'?t) have (?:that )?information",
    r"no official by-?laws found",
    r"no shops found",
    r"no verified community tips",
    r"couldn'?t find",
    r"could not find",
    r"unable to find",
    r"not sure",
    r"no information",
    r"encountered an unexpected issue",
]
_UNANSWERED_RE = re.compile("|".join(_UNANSWERED_PATTERNS), re.IGNORECASE)

_ANALYTICS_QUESTION_RE = re.compile(
    r"(what (?:did|are|do) (?:the )?residents?|residents? (?:ask|asked|asking)|most asked|top questions?|"
    r"popular topics?|content gaps?|unanswered|how many (?:users|residents|people)|usage stats?|"
    r"analytics|admin stats|bot stats|how is the bot (?:doing|performing))",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------
def is_answered(response_text: str, tools_called: List[str]) -> bool:
    """Heuristic: did the bot actually answer? Looks at reply wording, not just two phrases."""
    if not response_text or not response_text.strip():
        return False
    return not _UNANSWERED_RE.search(response_text)


def topic_for_tools(tools_called: List[str]) -> str:
    for t in tools_called or []:
        if t in TOOL_TOPICS:
            return TOOL_TOPICS[t]
    return "General (no tool)"


def normalize_query(q: str) -> str:
    q = re.sub(r"[^\w\s]", " ", (q or "").lower())
    return re.sub(r"\s+", " ", q).strip()


def is_analytics_question(text: str) -> bool:
    return bool(_ANALYTICS_QUESTION_RE.search(text or ""))


def _parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------
def compute_analytics(
    users: List[Dict[str, Any]],
    logs: List[Dict[str, Any]],
    feedback: List[Dict[str, Any]],
    days: Optional[int] = 7,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Builds the analytics summary for the last `days` days (None = all time)."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days) if days else None

    def in_window(ts: Any) -> bool:
        dt = _parse_ts(ts)
        if dt is None:
            return cutoff is None
        return cutoff is None or dt >= cutoff

    # --- Users (Telegram accounts, NOT households) ---
    registered = len(users)
    new_users = sum(1 for u in users if in_window(u.get("first_seen")))
    active_7d = sum(1 for u in users if (_parse_ts(u.get("last_active")) or datetime.min.replace(tzinfo=timezone.utc)) >= now - timedelta(days=7))
    active_30d = sum(1 for u in users if (_parse_ts(u.get("last_active")) or datetime.min.replace(tzinfo=timezone.utc)) >= now - timedelta(days=30))

    # --- Queries ---
    window_logs = [l for l in logs if in_window(l.get("timestamp"))]
    menu_logs = [l for l in window_logs if str(l.get("user_query", "")).startswith(MENU_PREFIX)]
    query_logs = [l for l in window_logs if not str(l.get("user_query", "")).startswith(MENU_PREFIX)]

    unanswered_logs = [l for l in query_logs if not l.get("answered_successfully", True)]
    gap_counter: Counter = Counter()
    gap_display: Dict[str, str] = {}
    for l in unanswered_logs:
        raw = str(l.get("user_query", "")).strip()
        key = normalize_query(raw)
        if not key:
            continue
        gap_counter[key] += 1
        gap_display.setdefault(key, raw)
    unanswered_ranked: List[Tuple[str, int]] = [(gap_display[k], c) for k, c in gap_counter.most_common(20)]

    topic_counts = Counter(topic_for_tools(l.get("tools_called", [])) for l in query_logs)
    menu_counts = Counter(MENU_LABELS.get(str(l.get("user_query", ""))[len(MENU_PREFIX):], str(l.get("user_query", ""))[len(MENU_PREFIX):]) for l in menu_logs)

    # Last-7-days daily counts (Singapore days, oldest -> newest)
    today = now.astimezone(SGT).date()
    day_keys = [today - timedelta(days=i) for i in range(6, -1, -1)]
    daily = Counter()
    for l in logs:
        if str(l.get("user_query", "")).startswith(MENU_PREFIX):
            continue
        dt = _parse_ts(l.get("timestamp"))
        if dt:
            daily[dt.astimezone(SGT).date()] += 1
    queries_by_day = [(d, daily.get(d, 0)) for d in day_keys]

    total_queries = len(query_logs)
    answer_rate = (1 - len(unanswered_logs) / total_queries) if total_queries else None

    # --- Feedback ---
    fb_by_category = Counter(f.get("category", "general") for f in feedback)
    fb_by_status = Counter(f.get("status", "new") for f in feedback)
    unresolved = [f for f in feedback if f.get("status", "new") == "new"]
    oldest_days = None
    ages = [(now - dt).days for dt in (_parse_ts(f.get("created_at")) for f in unresolved) if dt]
    if ages:
        oldest_days = max(ages)

    return {
        "days": days,
        "registered_users": registered,
        "new_users": new_users,
        "active_7d": active_7d,
        "active_30d": active_30d,
        "adoption_pct": registered / TOTAL_UNITS,
        "total_units": TOTAL_UNITS,
        "total_queries": total_queries,
        "answer_rate": answer_rate,
        "queries_by_day": queries_by_day,
        "topic_counts": topic_counts.most_common(),
        "menu_counts": menu_counts.most_common(),
        "unanswered_ranked": unanswered_ranked,
        "unanswered_count": len(unanswered_logs),
        "feedback_total": len(feedback),
        "feedback_new": len(unresolved),
        "feedback_by_category": dict(fb_by_category),
        "feedback_by_status": dict(fb_by_status),
        "feedback_oldest_unresolved_days": oldest_days,
        # Legacy keys kept for backwards compatibility
        "total_users": registered,
        "unanswered_examples": [q for q, _ in unanswered_ranked[:5]],
        "total_feedback": len(feedback),
        "unresolved_feedback": len(unresolved),
    }


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------
def progress_bar(fraction: float, width: int = 10) -> str:
    fraction = max(0.0, min(1.0, fraction))
    filled = round(fraction * width)
    return "█" * filled + "░" * (width - filled)


def sparkline(values: List[int]) -> str:
    blocks = "▁▂▃▄▅▆▇█"
    if not values or max(values) == 0:
        return "▁" * len(values)
    peak = max(values)
    return "".join(blocks[min(len(blocks) - 1, round(v / peak * (len(blocks) - 1)))] for v in values)


def _md(text: str) -> str:
    """Strips Telegram-Markdown control characters from user-generated text."""
    return re.sub(r"[*_`\[\]]", "", text or "")


def window_label(days: Optional[int]) -> str:
    return "All time" if not days else f"Last {days} days"


def format_dashboard(s: Dict[str, Any]) -> str:
    days = s.get("days")
    lines = [f"📊 *Lentor Modern Concierge Analytics* — {window_label(days)}", ""]

    lines += [
        "👥 *Residents (Telegram users)*",
        f"Registered: *{s['registered_users']}* · New in window: *{s['new_users']}*",
        f"Active 7d: *{s['active_7d']}* · Active 30d: *{s['active_30d']}*",
        f"Adoption ≈ {progress_bar(s['adoption_pct'])} {s['adoption_pct']:.0%} of {s['total_units']} units",
        "_Counts Telegram accounts, not households: one home may have several users._",
        "",
    ]

    rate = s.get("answer_rate")
    rate_text = "n/a" if rate is None else f"{rate:.0%} {progress_bar(rate)}"
    daily = s["queries_by_day"]
    lines += [
        "💬 *Questions*",
        f"Asked: *{s['total_queries']}* · Answer rate: {rate_text}",
        f"Last 7 days: {sparkline([c for _, c in daily])} ({daily[0][0].strftime('%d %b')}→{daily[-1][0].strftime('%d %b')}, peak {max(c for _, c in daily)}/day)",
        "",
    ]

    if s["topic_counts"]:
        total = sum(c for _, c in s["topic_counts"]) or 1
        lines.append("🧭 *Top topics*")
        for name, c in s["topic_counts"][:5]:
            lines.append(f"• {name}: {c} ({c / total:.0%})")
        lines.append("")

    if s["menu_counts"]:
        lines.append("🔘 *Quick-menu taps*")
        lines.append(" · ".join(f"{n} {c}" for n, c in s["menu_counts"]))
        lines.append("")

    cat = s["feedback_by_category"]
    cat_text = ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in sorted(cat.items())) or "none"
    oldest = s.get("feedback_oldest_unresolved_days")
    oldest_text = f" · oldest unresolved: {oldest}d" if oldest is not None else ""
    lines += [
        "💡 *Feedback (all time)*",
        f"{s['feedback_total']} total · {s['feedback_new']} new{oldest_text}",
        f"By type: {cat_text}",
        "",
    ]

    gaps = s["unanswered_ranked"]
    lines.append(f"❓ *Top content gaps* ({s['unanswered_count']} unanswered)")
    if gaps:
        for i, (q, c) in enumerate(gaps[:3], 1):
            lines.append(f"{i}. \"{_md(q)[:80]}\" ×{c}")
        if len(gaps) > 3:
            lines.append("_Tap Full gap list for the rest._")
    else:
        lines.append("(none in this window 🎉)")
    return "\n".join(lines)


def format_gaps(s: Dict[str, Any]) -> str:
    gaps = s["unanswered_ranked"]
    lines = [f"❓ *Content gaps* — {window_label(s.get('days'))}", ""]
    if not gaps:
        lines.append("No unanswered questions in this window 🎉")
    for i, (q, c) in enumerate(gaps, 1):
        lines.append(f"{i}. \"{_md(q)[:120]}\" ×{c}")
    lines += ["", "_Fix a gap by adding the answer to the handbook/mall data, or approve a resident tip._"]
    return "\n".join(lines)


def stats_keyboard(days: Optional[int]) -> InlineKeyboardMarkup:
    def label(text: str, d: Optional[int]) -> str:
        return f"• {text}" if d == days else text

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(label("7d", 7), callback_data="stats_7"),
                InlineKeyboardButton(label("30d", 30), callback_data="stats_30"),
                InlineKeyboardButton(label("All", None), callback_data="stats_all"),
            ],
            [
                InlineKeyboardButton("📋 Full gap list", callback_data=f"stats_gaps_{days or 'all'}"),
                InlineKeyboardButton("🔄 Refresh", callback_data=f"stats_{days or 'all'}"),
            ],
        ]
    )


def parse_stats_callback(data: str) -> Tuple[str, Optional[int]]:
    """'stats_7' -> ('dash', 7); 'stats_gaps_30' -> ('gaps', 30); 'stats_all' -> ('dash', None)."""
    parts = data.split("_")
    if len(parts) >= 3 and parts[1] == "gaps":
        return "gaps", (None if parts[2] == "all" else int(parts[2]))
    return "dash", (None if len(parts) < 2 or parts[1] == "all" else int(parts[1]))


# ---------------------------------------------------------------------------
# Conversational admin Q&A
# ---------------------------------------------------------------------------
def summary_for_llm(s: Dict[str, Any]) -> str:
    return (
        f"Window: {window_label(s.get('days'))}\n"
        f"Registered Telegram users: {s['registered_users']} (approx {s['adoption_pct']:.0%} of {s['total_units']} units; users, not households)\n"
        f"New users: {s['new_users']}; active 7d: {s['active_7d']}; active 30d: {s['active_30d']}\n"
        f"Questions asked: {s['total_queries']}; answer rate: {'n/a' if s['answer_rate'] is None else format(s['answer_rate'], '.0%')}\n"
        f"Questions per day (last 7): {[(d.isoformat(), c) for d, c in s['queries_by_day']]}\n"
        f"Topics: {s['topic_counts']}\n"
        f"Quick-menu taps: {s['menu_counts']}\n"
        f"Unanswered (question, times asked): {s['unanswered_ranked'][:10]}\n"
        f"Feedback: total {s['feedback_total']}, new {s['feedback_new']}, by type {s['feedback_by_category']}"
    )


def answer_admin_question(question: str, summary: Dict[str, Any], agent: Any) -> str:
    """Answers an admin analytics question from verified aggregates. Falls back to the dashboard."""
    client = getattr(agent, "client", None)
    if not client:
        return format_dashboard(summary)

    prompt = (
        "You are the data analyst for the Lentor Modern resident concierge bot. Answer the admin's question "
        "using ONLY the verified aggregates below. Give exact numbers, be concise (max ~8 lines), "
        "and end with one actionable suggestion. Never invent numbers; if the data cannot answer, say so. "
        "Note that 'users' are Telegram accounts, not households.\n\n"
        f"DATA:\n{summary_for_llm(summary)}\n\nQUESTION: {question}"
    )
    models = [getattr(agent, "model", "gemini-3.8-flash"), "gemini-3.5-flash", "gemini-3.1-flash-lite"]
    seen = set()
    for m in models:
        if m in seen:
            continue
        seen.add(m)
        try:
            resp = client.models.generate_content(model=m, contents=prompt)
            if resp.text:
                return resp.text.strip()
        except Exception as e:  # cascade on quota/availability errors
            logger.warning(f"Admin analytics Q&A model {m} failed: {e}")
    return format_dashboard(summary)
