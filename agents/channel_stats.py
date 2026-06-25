"""
Сбор и чтение реальной статистики Telegram-канала (просмотры, реакции, подписчики).
Хранится в Supabase, таблицы channel_posts и channel_subscriber_snapshots.
"""

from datetime import datetime, timezone
from agents.memory_utils import _get_client


def save_post(chat_id: int, message_id: int, date: datetime, text: str,
              views: int = None, forwards: int = None, reactions: dict = None):
    client = _get_client()
    if not client:
        return
    row = {
        "chat_id": chat_id,
        "message_id": message_id,
        "date": date.isoformat(),
        "text": (text or "")[:500],
        "views": views,
        "forwards": forwards,
        "reactions": reactions or {},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        client.table("channel_posts").upsert(row, on_conflict="chat_id,message_id").execute()
    except Exception:
        pass


def update_post_views(chat_id: int, message_id: int, views: int):
    client = _get_client()
    if not client:
        return
    try:
        client.table("channel_posts").update({
            "views": views,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("chat_id", chat_id).eq("message_id", message_id).execute()
    except Exception:
        pass


def update_post_reactions(chat_id: int, message_id: int, reactions: dict):
    client = _get_client()
    if not client:
        return
    try:
        client.table("channel_posts").update({
            "reactions": reactions,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("chat_id", chat_id).eq("message_id", message_id).execute()
    except Exception:
        pass


def snapshot_subscribers(chat_id: int, count: int):
    client = _get_client()
    if not client:
        return
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        client.table("channel_subscriber_snapshots").upsert({
            "chat_id": chat_id,
            "date": today,
            "count": count,
        }, on_conflict="chat_id,date").execute()
    except Exception:
        pass


def get_recent_posts(chat_id: int, n: int = 20) -> list:
    client = _get_client()
    if not client:
        return []
    try:
        res = client.table("channel_posts").select("*") \
            .eq("chat_id", chat_id).order("date", desc=True).limit(n).execute()
        return res.data or []
    except Exception:
        return []


def get_subscriber_history(chat_id: int, n: int = 30) -> list:
    client = _get_client()
    if not client:
        return []
    try:
        res = client.table("channel_subscriber_snapshots").select("*") \
            .eq("chat_id", chat_id).order("date", desc=True).limit(n).execute()
        return res.data or []
    except Exception:
        return []
