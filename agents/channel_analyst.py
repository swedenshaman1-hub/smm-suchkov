"""
Агент: Аналитик канала — анализирует реальную статистику Telegram-канала
(просмотры, реакции, динамику подписчиков), а не предполагаемые данные.
"""

from agents.gemini_utils import gemini_call
from agents import channel_stats
from agents import memory_utils

TEAM_AGENTS = ["strategist", "analyst", "copywriter", "instagram_writer", "editor", "instagram_editor"]

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

    result_text = gemini_call(api_key, MODEL, SYSTEM_PROMPT, user_msg, max_tokens=8000, temperature=0.4,
                               disable_thinking=True)

    return {
        "agent": "Аналитик канала",
        "posts_count": len(posts),
        "subscriber_points": len(history),
        "analysis": result_text,
    }


def sync_to_team_memory(chat_id: int, api_key: str, n_posts: int = 400) -> dict:
    """Извлекает рабочие/неработающие паттерны из реальных данных канала
    и кладёт их в память команды (стратег, аналитик, копирайтеры), чтобы
    они учитывались при создании новых постов."""
    posts = channel_stats.get_recent_posts(chat_id, n_posts)
    if len(posts) < 5:
        return {"status": "not_enough_data", "posts_count": len(posts)}

    lessons_prompt = f"""ПОСЛЕДНИЕ ПОСТЫ КАНАЛА ({len(posts)} шт.):
{_format_posts(posts)}

На основе этих реальных данных выдели короткие практические уроки для команды копирайтеров.
Формат строго такой, без пояснений:
РАБОТАЕТ: <короткий конкретный паттерн, который реально дал высокую вовлечённость>
НЕ РАБОТАЕТ: <короткий конкретный паттерн, который провалился>
По 2-4 строки каждого типа. Только на основе видимых данных, без выдумывания."""

    raw = gemini_call(api_key, MODEL, SYSTEM_PROMPT, lessons_prompt, max_tokens=1500, temperature=0.3,
                       disable_thinking=True)

    successful, failed = [], []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if line.upper().startswith("РАБОТАЕТ:"):
            successful.append(line.split(":", 1)[1].strip())
        elif line.upper().startswith("НЕ РАБОТАЕТ:"):
            failed.append(line.split(":", 1)[1].strip())

    feedback_text = (
        f"Обновлённый анализ {len(posts)} постов канала (реальные данные, без выдумывания): "
        f"работает — {'; '.join(successful) or 'нет явных паттернов'}; "
        f"не работает — {'; '.join(failed) or 'нет явных паттернов'}."
    )

    for agent_id in TEAM_AGENTS:
        memory = memory_utils.load(agent_id)
        for s in successful:
            memory_utils.add_technique(memory, s, topic="реальная статистика канала", successful=True)
        for f in failed:
            memory_utils.add_technique(memory, f, topic="реальная статистика канала", successful=False)
        memory_utils.add_feedback(memory, from_agent="Аналитик канала (реальные данные)",
                                   feedback=feedback_text, topic="аудит канала")
        memory_utils.save(agent_id, memory)

    audience_profile = infer_audience_profile(posts, api_key)
    if audience_profile:
        analyst_memory = memory_utils.load("analyst")
        memory_utils.set_audience_profile(analyst_memory, audience_profile)
        memory_utils.save("analyst", analyst_memory)

    return {
        "status": "ok", "posts_count": len(posts), "successful": successful, "failed": failed,
        "audience_profile": audience_profile,
    }


def infer_audience_profile(posts: list, api_key: str) -> str:
    """Выводит реальный профиль аудитории из текстов и реакций постов канала —
    без предположений о возрасте/поле/роде занятий, только то, что подтверждается данными."""
    if len(posts) < 5:
        return ""

    prompt = f"""ПОСЛЕДНИЕ ПОСТЫ КАНАЛА ({len(posts)} шт.) — текст и реакции:
{_format_posts(posts)}

На основе РЕАЛЬНОГО текста и формулировок этих постов (не предположений) опиши аудиторию канала:
- Какие темы и боли реально поднимаются в постах, которые получают отклик
- Какой язык и обращение использует автор (от этого можно судить о близости/дистанции с аудиторией)
- Какие потребности/желания аудитории видны из тех постов, которые набирают больше реакций

Не утверждай возраст, пол, профессию или социальный статус — у тебя нет данных для этого.
Формулируй только то, что прямо подтверждается текстами и реакциями.
Коротко, 4-6 предложений, без заголовков."""

    return gemini_call(api_key, MODEL, SYSTEM_PROMPT, prompt, max_tokens=800, temperature=0.3,
                        disable_thinking=True)
