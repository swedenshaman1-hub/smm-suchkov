"""
Сбор и чтение реальной статистики Instagram (Graph API): посты, инсайты, подписчики.
Хранится в Supabase, таблицы instagram_posts и instagram_subscriber_snapshots.

Требует IG_BUSINESS_ACCOUNT_ID и IG_ACCESS_TOKEN в .env (бизнес/creator-аккаунт,
привязанный к Facebook-странице, приложение в Meta for Developers с токеном
с правами instagram_basic, instagram_manage_insights, pages_show_list).
"""

import os
from datetime import datetime, timezone

import requests

from agents.memory_utils import _get_client

def _graph_api_base() -> str:
    host = os.getenv("IG_API_HOST", "https://graph.instagram.com").strip()
    version = os.getenv("IG_GRAPH_API_VERSION", "v23.0").strip()
    return f"{host.rstrip('/')}/{version.strip('/')}"


def _config() -> tuple[str, str] | tuple[None, None]:
    account_id = os.getenv("IG_BUSINESS_ACCOUNT_ID", "").strip()
    token = os.getenv("IG_ACCESS_TOKEN", "").strip()
    if not account_id or not token:
        return None, None
    return account_id, token


def is_configured() -> bool:
    account_id, token = _config()
    return bool(account_id and token)


def fetch_recent_media(limit: int = 25) -> list:
    """Тянет последние медиа аккаунта с базовыми метриками вовлечённости."""
    account_id, token = _config()
    if not account_id:
        return []

    fields = "id,caption,media_type,media_url,permalink,timestamp,like_count,comments_count"
    resp = requests.get(
        f"{_graph_api_base()}/{account_id}/media",
        params={"fields": fields, "limit": limit, "access_token": token},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


def fetch_media_insights(media_id: str, media_type: str) -> dict:
    """Доп. метрики (охват, показы, сохранения) — для Reels/Carousel набор полей шире."""
    account_id, token = _config()
    if not account_id:
        return {}

    if media_type == "VIDEO" or media_type == "REELS":
        metrics = "reach,impressions,saved,video_views"
    else:
        metrics = "reach,impressions,saved"

    resp = requests.get(
        f"{_graph_api_base()}/{media_id}/insights",
        params={"metric": metrics, "access_token": token},
        timeout=30,
    )
    if resp.status_code != 200:
        return {}
    data = resp.json().get("data", [])
    return {d["name"]: d["values"][0]["value"] for d in data if d.get("values")}


def fetch_follower_count() -> int | None:
    account_id, token = _config()
    if not account_id:
        return None

    resp = requests.get(
        f"{_graph_api_base()}/{account_id}",
        params={"fields": "followers_count", "access_token": token},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("followers_count")


def save_post(media_id: str, caption: str, media_type: str, timestamp: str,
              like_count: int = None, comments_count: int = None, insights: dict = None):
    client = _get_client()
    if not client:
        return
    row = {
        "media_id": media_id,
        "caption": (caption or "")[:500],
        "media_type": media_type,
        "timestamp": timestamp,
        "like_count": like_count,
        "comments_count": comments_count,
        "reach": (insights or {}).get("reach"),
        "impressions": (insights or {}).get("impressions"),
        "saved": (insights or {}).get("saved"),
        "video_views": (insights or {}).get("video_views"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        client.table("instagram_posts").upsert(row, on_conflict="media_id").execute()
    except Exception:
        pass


def snapshot_followers(count: int):
    client = _get_client()
    if not client:
        return
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        client.table("instagram_subscriber_snapshots").upsert({
            "date": today,
            "count": count,
        }, on_conflict="date").execute()
    except Exception:
        pass


def sync_recent_media(limit: int = 25) -> int:
    """Тянет последние медиа из Graph API, докладывает инсайты и сохраняет в Supabase.
    Возвращает количество синхронизированных постов."""
    media = fetch_recent_media(limit)
    for item in media:
        insights = fetch_media_insights(item["id"], item.get("media_type", ""))
        save_post(
            media_id=item["id"],
            caption=item.get("caption", ""),
            media_type=item.get("media_type", ""),
            timestamp=item.get("timestamp", ""),
            like_count=item.get("like_count"),
            comments_count=item.get("comments_count"),
            insights=insights,
        )
    return len(media)


def get_recent_posts(n: int = 25) -> list:
    client = _get_client()
    if not client:
        return []
    try:
        res = client.table("instagram_posts").select("*") \
            .order("timestamp", desc=True).limit(n).execute()
        return res.data or []
    except Exception:
        return []


def get_follower_history(n: int = 30) -> list:
    client = _get_client()
    if not client:
        return []
    try:
        res = client.table("instagram_subscriber_snapshots").select("*") \
            .order("date", desc=True).limit(n).execute()
        return res.data or []
    except Exception:
        return []
