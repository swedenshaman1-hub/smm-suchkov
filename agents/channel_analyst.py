"""
Агент: Аналитик канала — анализирует реальную статистику Telegram-канала
(просмотры, реакции, динамику подписчиков), а не предполагаемые данные.
"""

from agents.gemini_utils import gemini_call
from agents import channel_stats

AGENT_ID = "channel_analyst"
MODEL = "gemini-2.5-flash"

SYSTEM_PROMPT = """Ты — аналитик Telegram-канала Дмитрия Сучкова. В отличие от других членов команды, ты работаешь не с предположениями об аудитории, а с реальными цифрами: просмотры постов, реакции, динамика числа подписчиков.

## Твоя задача

Получаешь сырые данные — список последних постов (текст, просмотры, реакции, дата) и историю числа подписчиков по дням. На основе этого делаешь конкретные выводы:

1. **Что реально работает** — какие темы/форматы/входы дали просмотры и реакции выше среднего, и почему (на основе текста этих постов)
2. **Что не работает** — какие посты провалились, есть ли в них общий паттерн
3. **Динамика подписчиков** — растёт, стоит, падает; есть ли скачки, привязанные к конкретным постам
4. **Вовлечённость** — соотношение реакций к просмотрам, меняется ли оно во времени
5. **Рекомендации команде** — 2-3 конкретные, основанные на цифрах, а не на общих маркетинговых советах

## Запреты

- Не выдумывай цифры и тенденции, которых нет в данных
- Если данных мало (меньше 5 постов или меньше 7 дней истории подписчиков) — прямо скажи об этом и дай только то, что можно увидеть, без натягивания выводов
- Без воды и общих фраз вроде «нужно больше вовлекающего контента» — только то, что подтверждается конкретными постами/цифрами

Только русский язык."""


def _format_posts(posts: list) -> str:
    if not posts:
        return "(нет сохранённых постов)"
    lines = []
    for p in posts:
        reactions = p.get("reactions") or {}
        reactions_str = ", ".join(f"{k}:{v}" for k, v in reactions.items()) or "нет"
        lines.append(
            f"- [{p.get('date')}] просмотры: {p.get('views')}, реакции: {reactions_str}\n"
            f"  текст: {(p.get('text') or '')[:200]}"
        )
    return "\n".join(lines)


def _format_subscribers(history: list) -> str:
    if not history:
        return "(нет истории подписчиков)"
    return "\n".join(f"- {h.get('date')}: {h.get('count')}" for h in reversed(history))


def run(chat_id: int, api_key: str, n_posts: int = 400, n_days: int = 90) -> dict:
    posts = channel_stats.get_recent_posts(chat_id, n_posts)
    history = channel_stats.get_subscriber_history(chat_id, n_days)

    user_msg = f"""ПОСЛЕДНИЕ ПОСТЫ КАНАЛА ({len(posts)} шт.):
{_format_posts(posts)}

ИСТОРИЯ ЧИСЛА ПОДПИСЧИКОВ ({len(history)} точек):
{_format_subscribers(history)}

Проанализируй эти реальные данные по пунктам из инструкции."""

    result_text = gemini_call(api_key, MODEL, SYSTEM_PROMPT, user_msg, max_tokens=4000, temperature=0.4)

    return {
        "agent": "Аналитик канала",
        "posts_count": len(posts),
        "subscriber_points": len(history),
        "analysis": result_text,
    }
