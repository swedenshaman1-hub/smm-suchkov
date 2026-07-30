"""Run the bounded NotebookLM editorial pipeline locally without Telegram."""

from __future__ import annotations

import os
import sys
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from agents import notebook_live, team_registry, telegram_team


DEFAULT_TOPIC = (
    "Самое болезненное в отношениях начинается не с расставания. "
    "А с момента, когда ты уже чувствуешь, что тебя не выбирают, "
    "но всё ещё пытаешься стать удобнее, чтобы это изменить"
)


def show(title: str, text: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}\n{text}")


def main() -> int:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("GEMINI_API_KEY не найден в .env")
        return 1

    topic = " ".join(sys.argv[1:]).strip() or DEFAULT_TOPIC
    route = team_registry.route_for(topic)
    print(f"ТЕМА: {topic}")
    print(f"РЕЖИМ: {route.mode}")

    context_cache = os.environ.get("EDITORIAL_EVAL_CONTEXT_FILE", "").strip()
    cache_path = Path(context_cache) if context_cache else None
    if cache_path and cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        contexts = notebook_live.TopicContexts(
            mode=payload["mode"],
            answers=payload["answers"],
            selected_notebooks=tuple(payload["selected_notebooks"]),
            skipped_optional=tuple(payload.get("skipped_optional", ())),
        )
    else:
        contexts = notebook_live.build_topic_context(topic, route.mode)
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps(
                    {
                        "mode": contexts.mode,
                        "answers": contexts.answers,
                        "selected_notebooks": contexts.selected_notebooks,
                        "skipped_optional": contexts.skipped_optional,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
    print("NOTEBOOKS:", ", ".join(contexts.selected_notebooks))

    expert_context = contexts.without_roles("voice", "ethics")
    blueprint = telegram_team.build_editorial_blueprint(
        topic,
        expert_context,
        api_key,
        route.mode,
    )
    show("BLUEPRINT", blueprint)
    blueprint_issues = telegram_team.blueprint_contract_issues(topic, blueprint)
    if blueprint_issues:
        show("BLUEPRINT ISSUES", "\n".join(blueprint_issues))
        blueprint = telegram_team.repair_editorial_blueprint(
            topic,
            blueprint,
            blueprint_issues,
            api_key,
            route.mode,
        )
        show("BLUEPRINT AFTER ONE REPAIR", blueprint)
        blueprint_issues = telegram_team.blueprint_contract_issues(topic, blueprint)
        if blueprint_issues:
            show("STOP", "\n".join(blueprint_issues))
            return 1

    voice_brief = telegram_team.build_voice_brief(
        topic,
        contexts.voice,
        api_key,
    )
    show("VOICE BRIEF", voice_brief)

    draft = telegram_team.write_editorial_post(
        topic,
        blueprint,
        voice_brief,
        api_key,
    )
    draft = telegram_team.clean_human_surface(topic, draft)
    show("DRAFT", draft)

    issues = telegram_team.editorial_contract_issues(topic, draft)
    audit = telegram_team.audit_editorial_post(
        topic,
        blueprint,
        draft,
        contexts.ethics,
        api_key,
        issues,
    )
    show("AUDIT", audit["review"])

    final_text = draft
    final_audit = audit
    if not audit["accepted"]:
        final_text = telegram_team.repair_editorial_post(
            topic,
            blueprint,
            draft,
            audit["review"],
            voice_brief,
            api_key,
            issues,
        )
        final_text = telegram_team.clean_human_surface(topic, final_text)
        show("ONE REPAIR", final_text)
        final_issues = telegram_team.editorial_contract_issues(topic, final_text)
        final_audit = telegram_team.audit_editorial_post(
            topic,
            blueprint,
            final_text,
            contexts.ethics,
            api_key,
            final_issues,
        )
        show("FINAL AUDIT", final_audit["review"])
    else:
        final_issues = issues
    show(
        "RESULT",
        final_text
        + "\n\nContract issues: "
        + ("; ".join(final_issues) if final_issues else "нет"),
    )
    return 0 if final_audit["accepted"] and not final_issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
