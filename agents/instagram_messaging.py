"""Direct Instagram Messaging API integration.

The module exposes a tiny HTTP webhook server so the existing Railway process can
receive Meta events without another paid service.  It supports this flow:

1. A person writes a configured keyword under an Instagram post or reel.
2. Instagram receives one private reply asking the person to answer in Direct.
3. After that answer, the bot checks whether the person follows the business.
4. Followers receive the configured free resource link.

Meta's messaging window and one-private-reply restriction are deliberately
respected.  The module does not initiate unsolicited Direct conversations.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

logger = logging.getLogger(__name__)

DEFAULT_KEYWORDS = (
    "медитация",
    "медитацию",
    "получить",
    "хочу",
)
DEFAULT_CONFIRM_WORDS = (
    "получить",
    "медитация",
    "медитацию",
    "готово",
    "подписался",
    "подписалась",
)

_seen_events: dict[str, float] = {}
_seen_lock = threading.Lock()
_server: ThreadingHTTPServer | None = None
_server_thread: threading.Thread | None = None


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _api_base() -> str:
    host = _env("IG_API_HOST") or "https://graph.instagram.com"
    version = _env("IG_GRAPH_API_VERSION") or "v23.0"
    return f"{host.rstrip('/')}/{version.strip('/')}"


def missing_config() -> list[str]:
    required = (
        "IG_BUSINESS_ACCOUNT_ID",
        "IG_ACCESS_TOKEN",
        "IG_APP_SECRET",
        "IG_WEBHOOK_VERIFY_TOKEN",
        "IG_FREEBIE_URL",
    )
    return [name for name in required if not _env(name)]


def is_configured() -> bool:
    return not missing_config()


def status_line() -> str:
    missing = missing_config()
    if not missing:
        return "готов к комментариям и Direct"
    return "ожидает Meta: " + ", ".join(missing)


def _split_words(value: str, defaults: tuple[str, ...]) -> tuple[str, ...]:
    if not value.strip():
        return defaults
    return tuple(item.strip().lower() for item in value.split(",") if item.strip())


def _keywords() -> tuple[str, ...]:
    return _split_words(_env("IG_FREEBIE_KEYWORDS"), DEFAULT_KEYWORDS)


def _confirm_words() -> tuple[str, ...]:
    return _split_words(_env("IG_FREEBIE_CONFIRM_WORDS"), DEFAULT_CONFIRM_WORDS)


def _normalized(text: str) -> str:
    return " ".join((text or "").lower().replace("ё", "е").split())


def is_keyword_comment(text: str) -> bool:
    normalized = _normalized(text)
    return bool(normalized) and any(_normalized(word) in normalized for word in _keywords())


def is_freebie_request(text: str) -> bool:
    normalized = _normalized(text)
    if not normalized:
        return False
    return any(
        normalized == _normalized(word) or _normalized(word) in normalized
        for word in _confirm_words()
    )


def _event_once(event_id: str, ttl_seconds: int = 24 * 60 * 60) -> bool:
    """Return True once per event ID and expire old IDs in memory."""
    if not event_id:
        return True
    now = time.time()
    with _seen_lock:
        expired = [key for key, stamp in _seen_events.items() if now - stamp > ttl_seconds]
        for key in expired:
            _seen_events.pop(key, None)
        if event_id in _seen_events:
            return False
        _seen_events[event_id] = now
        return True


def verify_signature(raw_body: bytes, signature_header: str) -> bool:
    secret = _env("IG_APP_SECRET")
    if not secret or not signature_header.startswith("sha256="):
        return False
    supplied = signature_header.split("=", 1)[1]
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, supplied)


def _graph_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    token = _env("IG_ACCESS_TOKEN")
    response = requests.post(
        f"{_api_base()}/{path.lstrip('/')}",
        params={"access_token": token},
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _graph_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    all_params = dict(params)
    all_params["access_token"] = _env("IG_ACCESS_TOKEN")
    response = requests.get(
        f"{_api_base()}/{path.lstrip('/')}",
        params=all_params,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def send_direct_message(recipient_id: str, text: str) -> dict[str, Any]:
    return _graph_post(
        f"{_env('IG_BUSINESS_ACCOUNT_ID')}/messages",
        {
            "recipient": {"id": recipient_id},
            "message": {"text": text},
        },
    )


def send_private_comment_reply(comment_id: str, text: str) -> dict[str, Any]:
    return _graph_post(
        f"{_env('IG_BUSINESS_ACCOUNT_ID')}/messages",
        {
            "recipient": {"comment_id": comment_id},
            "message": {"text": text},
        },
    )


def get_user_profile(scoped_user_id: str) -> dict[str, Any]:
    return _graph_get(
        scoped_user_id,
        {"fields": "name,username,is_user_follow_business"},
    )


def _comment_reply_text() -> str:
    return _env("IG_COMMENT_PRIVATE_REPLY") or (
        "Спасибо! Ответьте на это сообщение словом «ПОЛУЧИТЬ». "
        "После ответа я проверю подписку и пришлю медитацию."
    )


def _follow_first_text() -> str:
    return _env("IG_FOLLOW_FIRST_REPLY") or (
        "Сначала подпишитесь на @sda_cosmikshaman, затем напишите здесь "
        "«ПОЛУЧИТЬ» ещё раз — и я пришлю медитацию."
    )


def _delivery_text() -> str:
    custom = _env("IG_FREEBIE_DELIVERY_REPLY")
    if custom:
        return custom.replace("{url}", _env("IG_FREEBIE_URL"))
    return f"Готово. Вот ваша медитация: {_env('IG_FREEBIE_URL')}"


def _handle_comment(value: dict[str, Any]) -> None:
    comment_id = str(value.get("id") or value.get("comment_id") or "")
    text = str(value.get("text") or "")
    author = value.get("from") or {}
    author_id = str(author.get("id") or value.get("from_id") or "")

    if not comment_id or not is_keyword_comment(text):
        return
    if author_id and author_id == _env("IG_BUSINESS_ACCOUNT_ID"):
        return
    if not _event_once(f"comment:{comment_id}"):
        return

    send_private_comment_reply(comment_id, _comment_reply_text())
    logger.info("Instagram private reply sent for comment %s", comment_id)


def _message_text(event: dict[str, Any]) -> str:
    message = event.get("message") or {}
    return str(message.get("text") or "")


def _message_id(event: dict[str, Any]) -> str:
    message = event.get("message") or {}
    return str(message.get("mid") or event.get("timestamp") or "")


def _sender_id(event: dict[str, Any]) -> str:
    sender = event.get("sender") or {}
    return str(sender.get("id") or "")


def _handle_message(event: dict[str, Any]) -> None:
    sender_id = _sender_id(event)
    text = _message_text(event)
    message_id = _message_id(event)

    if not sender_id or not is_freebie_request(text):
        return
    if sender_id == _env("IG_BUSINESS_ACCOUNT_ID"):
        return
    if not _event_once(f"message:{message_id}"):
        return

    profile = get_user_profile(sender_id)
    if profile.get("is_user_follow_business") is True:
        send_direct_message(sender_id, _delivery_text())
        logger.info("Instagram freebie delivered to scoped user %s", sender_id)
    else:
        send_direct_message(sender_id, _follow_first_text())
        logger.info("Instagram follow request sent to scoped user %s", sender_id)


def process_webhook(payload: dict[str, Any]) -> None:
    """Process supported Instagram webhook payloads.

    Meta sends comments as changes and Direct messages as messaging events.
    Unknown fields are intentionally ignored so newly added subscriptions do not
    break the endpoint.
    """
    if payload.get("object") != "instagram":
        return

    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            if change.get("field") in {"comments", "live_comments"}:
                _handle_comment(change.get("value") or {})
        for event in entry.get("messaging") or []:
            if event.get("message") and not (event.get("message") or {}).get("is_echo"):
                _handle_message(event)


class InstagramWebhookHandler(BaseHTTPRequestHandler):
    server_version = "SDAInstagramWebhook/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        logger.info("Instagram webhook: " + fmt, *args)

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            self._json(
                200,
                {
                    "ok": True,
                    "service": "sda-smm",
                    "instagram_configured": is_configured(),
                    "instagram_missing": missing_config(),
                },
            )
            return

        if parsed.path != "/instagram/webhook":
            self._json(404, {"ok": False})
            return

        query = parse_qs(parsed.query)
        mode = (query.get("hub.mode") or [""])[0]
        token = (query.get("hub.verify_token") or [""])[0]
        challenge = (query.get("hub.challenge") or [""])[0]
        expected = _env("IG_WEBHOOK_VERIFY_TOKEN")
        if mode == "subscribe" and expected and hmac.compare_digest(token, expected):
            body = challenge.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._json(403, {"ok": False, "error": "verification_failed"})

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        if urlparse(self.path).path != "/instagram/webhook":
            self._json(404, {"ok": False})
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length)
        if not verify_signature(raw_body, self.headers.get("X-Hub-Signature-256", "")):
            self._json(401, {"ok": False, "error": "invalid_signature"})
            return

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(400, {"ok": False, "error": "invalid_json"})
            return

        self._json(200, {"ok": True})
        threading.Thread(
            target=_safe_process,
            args=(payload,),
            daemon=True,
            name="instagram-webhook-event",
        ).start()


def _safe_process(payload: dict[str, Any]) -> None:
    try:
        process_webhook(payload)
    except Exception:
        logger.exception("Instagram webhook event failed")


def start_webhook_server() -> ThreadingHTTPServer:
    global _server, _server_thread
    if _server is not None:
        return _server

    port = int(_env("PORT") or "8080")
    _server = ThreadingHTTPServer(("0.0.0.0", port), InstagramWebhookHandler)
    _server_thread = threading.Thread(
        target=_server.serve_forever,
        daemon=True,
        name="instagram-webhook-server",
    )
    _server_thread.start()
    logger.info("Instagram webhook server listening on port %s", port)
    return _server


def stop_webhook_server() -> None:
    global _server, _server_thread
    if _server is not None:
        _server.shutdown()
        _server.server_close()
    _server = None
    _server_thread = None

