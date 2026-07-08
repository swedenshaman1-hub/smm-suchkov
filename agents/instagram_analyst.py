"""
Агент: Аналитик Instagram — анализирует реальную статистику Instagram-аккаунта
(лайки, комментарии, охват, сохранения, динамику подписчиков), а не предположения.
"""

from agents.gemini_utils import gemini_call
from agents import instagram_stats
from agents import memory_utils

TEAM_AGENTS = ["strategist", "analyst", "instagram_writer", "instagram_editor"]

AGENT_ID = "instagram_analyst"
MODEL = "gemini-2.5-flash"

SYSTEM_PROMPT = """Ты — аналитик Instagram-аккаунта Дмитрия Сучкова. В отличие от других членов команды, ты работаешь не с предположениями об аудитории, а с реальными цифрами: лайки, комментарии, охват, показы, сохранения постов, динамика числа подписчиков.

## Твоя задача

Получаешь сырые данные — список последних постов (подпись, тип, лайки, комментарии, охват, сохранения, дата) и историю числа подписчиков по дням. На основе этого делаешь конкретные выводы:

1. **Что реально работает** — какие темы/форматы (пост, карусель, Reels) и входы дали вовлечённость выше среднего, и почему (на основе подписи этих постов)
2. **Что не работает** — какие посты провалились, есть ли в них общий паттерн
3. **Динамика подписчиков** — растёт, стоит, падает; есть ли скачки, привязанные к конкретным постам
4. **Вовлечённость** — соотношение (лайки+комментарии) к охвату, сохранения как индикатор ценности контента, меняется ли это во времени
5. **Формат vs результат** — какой формат (пост/карусель/Reels) даёт лучший охват и сохранения именно у этой аудитории
6. **Рекомендации команде** — 2-3 конкретные, основанные на цифрах, а не на общих маркетинговых советах

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
        lines.append(
            f"- [{p.get('timestamp')}] тип: {p.get('media_type')}, "
            f"лайки: {p.get('like_count')}, комментарии: {p.get('comments_count')}, "
            f"охват: {p.get('reach')}, показы: {p.get('impressions')}, сохранения: {p.get('saved')}\n"
            f"  подпись: {(p.get('caption') or '')[:200]}"
        )
    return "\n".join(lines)


def _format_followers(history: list) -> str:
    if not history:
        return "(нет истории подписчиков)"
    return "\n".join(f"- {h.get('date')}: {h.get('count')}" for h in reversed(history))


def run(api_key: str, n_posts: int = 25, n_days: int = 90, sync_first: bool = True) -> dict:
    if not instagram_stats.is_configured():
        return {
            "status": "not_configured",
            "message": "IG_BUSINESS_ACCOUNT_ID / IG_ACCESS_TOKEN не заданы в .env — "
                        "нужен бизнес/creator-аккаунт, привязанный к Facebook-странице, "
                        "и приложение в Meta for Developers с токеном.",
        }

    if sync_first:
        instagram_stats.sync_recent_media(n_posts)
        followers = instagram_stats.fetch_follower_count()
        if followers is not None:
            instagram_stats.snapshot_followers(followers)

    posts = instagram_stats.get_recent_posts(n_posts)
    history = instagram_stats.get_follower_history(n_days)

    user_msg = f"""ПОСЛЕДНИЕ ПОСТЫ INSTAGRAM ({len(posts)} шт.):
{_format_posts(posts)}

ИСТОРИЯ ЧИСЛА ПОДПИСЧИКОВ ({len(history)} точек):
{_format_followers(history)}

Проанализируй эти реальные данные по пунктам из инструкции."""

    result_text = gemini_call(api_key, MODEL, SYSTEM_PROMPT, user_msg, max_tokens=8000, temperature=0.4,
                               disable_thinking=True)

    return {
        "status": "ok",
        "agent": "Аналитик Instagram",
        "posts_count": len(posts),
        "follower_points": len(history),
        "analysis": result_text,
    }


def sync_to_team_memory(api_key: str, n_posts: int = 25) -> dict:
    """Извлекает рабочие/неработающие паттерны из реальных данных Instagram
    и кладёт их в память команды (стратег, аналитик ЦА, Instagram-писатель/редактор)."""
    if not instagram_stats.is_configured():
        return {"status": "not_configured"}

    instagram_stats.sync_recent_media(n_posts)
    posts = instagram_stats.get_recent_posts(n_posts)
    if len(posts) < 5:
        return {"status": "not_enough_data", "posts_count": len(posts)}

    lessons_prompt = f"""ПОСЛЕДНИЕ ПОСТЫ INSTAGRAM ({len(posts)} шт.):
{_format_posts(posts)}

На основе этих реальных данных выдели короткие практические уроки для команды.
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
        f"Обновлённый анализ {len(posts)} постов Instagram (реальные данные, без выдумывания): "
        f"работает — {'; '.join(successful) or 'нет явных паттернов'}; "
        f"не работает — {'; '.join(failed) or 'нет явных паттернов'}."
    )

    for agent_id in TEAM_AGENTS:
        memory = memory_utils.load(agent_id)
        for s in successful:
            memory_utils.add_technique(memory, s, topic="реальная статистика Instagram", successful=True)
        for f in failed:
            memory_utils.add_technique(memory, f, topic="реальная статистика Instagram", successful=False)
        memory_utils.add_feedback(memory, from_agent="Аналитик Instagram (реальные данные)",
                                   feedback=feedback_text, topic="аудит Instagram")
        memory_utils.save(agent_id, memory)

    return {"status": "ok", "posts_count": len(posts), "successful": successful, "failed": failed}
