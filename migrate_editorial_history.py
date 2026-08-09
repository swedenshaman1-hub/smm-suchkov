"""One-time, idempotent migration of accepted /post history into editorial_drafts.

Run manually after applying the SQL migration and before deploying table-backed code.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agents import editorial_history, memory_utils


def _date(record: dict, index: int, total: int) -> str:
    value = record.get("decided_at") or record.get("created_at") or record.get("date")
    if value:
        return value
    # Preserve source order when legacy rows have no timestamp.
    return (datetime.now(timezone.utc) - timedelta(seconds=total - index)).isoformat()


def migrate(chat_id: int | None = None) -> tuple[int, int]:
    client = memory_utils._get_client()
    if not client:
        raise RuntimeError("SUPABASE_URL/SUPABASE_KEY are unavailable")
    records = editorial_history.legacy_accepted()
    if chat_id is None:
        chat_ids = {int(r["chat_id"]) for r in records if r.get("chat_id") is not None}
        if len(chat_ids) != 1:
            raise RuntimeError("Cannot infer one chat_id; pass --chat-id explicitly")
        chat_id = chat_ids.pop()
    accepted_ids = {r.get("id") or r.get("draft_id") for r in records}
    inserted = 0
    for index, record in enumerate(records):
        draft_id = record.get("id") or record.get("draft_id")
        if not draft_id:
            continue
        # Old accepted history often did not retain the original draft link. Do not
        # invent one: normalize such rows as independent accepted records.
        candidate_revision_of = record.get("revision_of") or None
        revision_of = candidate_revision_of if candidate_revision_of in accepted_ids else None
        revision_count = 1 if revision_of else 0
        row = {
            "draft_id": draft_id,
            "chat_id": chat_id,
            "status": "accepted",
            "topic": record.get("topic") or "Без темы",
            "text": record.get("text") or "[legacy accepted post: text unavailable]",
            "planned_profile": record.get("planned_profile") or record.get("planned") or {},
            "actual_fingerprint": record.get("actual_fingerprint") or record.get("actual") or {},
            "warnings": record.get("warnings") or [],
            "revision_context": None,
            "revision_of": revision_of,
            "revision_count": revision_count,
            "created_at": record.get("created_at") or _date(record, index, len(records)),
            "decided_at": _date(record, index, len(records)),
        }
        existing = client.table(editorial_history.TABLE).select("draft_id").eq("draft_id", draft_id).limit(1).execute()
        if existing.data:
            continue
        client.table(editorial_history.TABLE).insert(row).execute()
        inserted += 1
    return inserted, len(records)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--chat-id", type=int)
    args = parser.parse_args()
    done, expected = migrate(args.chat_id)
    print(f"Inserted {done}; legacy accepted total {expected}")
