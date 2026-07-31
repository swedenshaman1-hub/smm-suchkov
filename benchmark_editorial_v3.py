"""Multi-topic quality benchmark for the bounded NotebookLM editorial pipeline.

The benchmark is deliberately separate from Telegram. It proves that live
NotebookLM advisers participated, runs the same bounded writer/auditor flow,
and scores the result against one stable rubric. A production prompt should be
changed only when the same weak category appears in at least two cases.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from agents import notebook_live, team_registry, telegram_team


TARGET_SCORE = 9.5

CASES = (
    (
        "not_chosen",
        "Самое болезненное в отношениях начинается не с расставания. "
        "А с момента, когда ты уже чувствуешь, что тебя не выбирают, "
        "но всё ещё пытаешься стать удобнее, чтобы это изменить",
    ),
    (
        "honest_refusal",
        "Почему после честного отказа иногда хочется немедленно всё объяснить "
        "и смягчить, даже если отказ был необходим",
    ),
    (
        "right_choice",
        "Почему после правильного решения может стать тяжелее, а не легче, "
        "и как не перепутать цену выбора с ошибкой",
    ),
    (
        "defending_old_choice",
        "Момент, когда продолжаешь защищать своё решение перед другими и "
        "вдруг замечаешь, что сам уже в него не веришь",
    ),
    (
        "stopped_asking",
        "Момент, когда перестаёшь просить о важном не потому, что оно стало "
        "неважным, а потому что устал не получать ответа",
    ),
    (
        "support_or_control",
        "Где проходит граница между поддержкой близкого человека и попыткой "
        "прожить его жизнь вместо него",
    ),
    (
        "missing_self_after_breakup",
        "Иногда после расставания скучаешь не только по человеку. Скучаешь "
        "по себе рядом с этим человеком: по тому, как легко было смеяться, "
        "строить планы и чувствовать вкус жизни. Как вернуть эту часть себя, "
        "не возвращаясь в отношения?",
    ),
)

QUICK_CASE_IDS = {"not_chosen", "honest_refusal", "support_or_control"}

SCORE_WEIGHTS = {
    "hook": 0.13,
    "idea": 0.17,
    "logic": 0.14,
    "specificity": 0.11,
    "humanity": 0.13,
    "voice": 0.11,
    "expert_synthesis": 0.11,
    "ethics": 0.05,
    "ending": 0.05,
}

CRITICAL_SCORE_FLOORS = {
    "hook": 8.5,
    "idea": 8.5,
    "humanity": 8.5,
    "voice": 8.0,
}

JUDGE_PROMPT = """Ты независимый главред и оцениваешь один Telegram-пост.
Не переписывай текст и не добавляй рекомендации вне рубрики.

Оцени каждый критерий от 0 до 10 с точностью до 0.1:
hook: если скрыть тему и blueprint, первые две фразы всё равно объясняют
человеческую ситуацию, показывают действие и создают напряжение без кликбейта.
idea: есть точное, небанальное и полезное различение, а не пересказ темы.
logic: каждый абзац двигает мысль вперёд, вывод следует из сказанного.
specificity: текст можно узнать и применить, но он не выдумывает жизнь читателя.
humanity: каждую фразу можно естественно сказать близкому человеку вслух;
нет канцелярита, книжных связок и безличной AI-гладкости.
voice: соблюдён переданный голос, без искусственной имитации и чужой стилизации.
expert_synthesis: решения blueprint реально проявлены в тексте, а не остались метками.
ethics: наблюдение отделено от домысла, нет диагноза, стыда и манипуляции.
ending: финал завершает обещание текста и оставляет ясное различение.

Не снижай балл за отсутствие кавычек и декоративных тире: это сознательное
правило автора. Но снижай humanity за орфографические ошибки, в том числе за
пропущенный обязательный дефис. Не награждай текст только за безопасность.
Безопасный, но общий и
обезличенный текст должен получить низкие idea, specificity и humanity.
Если без темы непонятно, о чём первые две фразы, hook не может быть выше 4.
Если в тексте две и более книжные абстракции вместо живых глаголов, humanity
не может быть выше 5.
Если запрет на тире породил фразы с пропущенной связкой вроде «способ это»,
«задача помочь» или «первый стать», humanity не может быть выше 5.
Если один образ растянут больше чем на два предложения или текст перечисляет
четыре и более предмета одной метафоры, humanity не может быть выше 6.
Если исходный смысловой объект заменён соседним советом, например тоска по
прежней версии себя заменена поиском новых поводов радоваться, idea и logic
не могут быть выше 6.
Если текст использует «катализатор», «авторство настоящего», «часть личности»,
«проявить лёгкость», «новый контекст» или смешивает «ты» и «вы», humanity
и voice не могут быть выше 7.

Верни только JSON без Markdown:
{
  "scores": {
    "hook": 0,
    "idea": 0,
    "logic": 0,
    "specificity": 0,
    "humanity": 0,
    "voice": 0,
    "expert_synthesis": 0,
    "ethics": 0,
    "ending": 0
  },
  "blocking": [],
  "strengths": [],
  "weaknesses": []
}

В blocking включай только фактический, этический, брендовый или конструктивный
дефект, из-за которого текст нельзя публиковать. В weaknesses максимум три
коротких замечания."""


@dataclass(frozen=True)
class PipelineResult:
    topic: str
    route_mode: str
    selected_notebooks: tuple[str, ...]
    answer_fingerprints: dict[str, str]
    blueprint: str
    voice_brief: str
    draft: str
    final_text: str
    audit_review: str
    final_audit_review: str
    contract_issues: list[str]
    accepted: bool


def _load_context(path: Path) -> notebook_live.TopicContexts:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return notebook_live.TopicContexts(
        mode=payload["mode"],
        answers=payload["answers"],
        selected_notebooks=tuple(payload["selected_notebooks"]),
        skipped_optional=tuple(payload.get("skipped_optional", ())),
    )


def _save_context(path: Path, contexts: notebook_live.TopicContexts) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
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


def _fingerprints(answers: dict[str, str]) -> dict[str, str]:
    return {
        key: hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
        for key, value in sorted(answers.items())
    }


def run_pipeline(
    topic: str,
    case_id: str,
    api_key: str,
    cache_dir: Path,
    refresh_context: bool,
) -> PipelineResult:
    route = team_registry.route_for(topic)
    context_path = cache_dir / "contexts" / f"{case_id}.json"
    if context_path.exists() and not refresh_context:
        contexts = _load_context(context_path)
    else:
        contexts = notebook_live.build_topic_context(topic, route.mode)
        _save_context(context_path, contexts)

    message_map = telegram_team.build_message_map(
        topic,
        contexts.message_strategy,
        api_key,
    )
    expert_context = contexts.without_roles(
        "voice",
        "ethics",
        "audience",
        "human_text",
    )
    blueprint = telegram_team.build_editorial_blueprint(
        topic,
        expert_context,
        api_key,
        route.mode,
        message_map,
    )
    blueprint_issues = telegram_team.full_blueprint_issues(
        topic,
        blueprint,
        api_key,
    )
    if blueprint_issues:
        blueprint = telegram_team.repair_editorial_blueprint(
            topic,
            blueprint,
            blueprint_issues,
            api_key,
            route.mode,
        )
        blueprint_issues = telegram_team.full_blueprint_issues(
            topic,
            blueprint,
            api_key,
        )
        blockers = telegram_team.blueprint_publication_blockers(blueprint_issues)
        if blockers:
            return PipelineResult(
                topic=topic,
                route_mode=route.mode,
                selected_notebooks=contexts.selected_notebooks,
                answer_fingerprints=_fingerprints(contexts.answers),
                blueprint=blueprint,
                voice_brief="",
                draft="",
                final_text="",
                audit_review="",
                final_audit_review="",
                contract_issues=blockers,
                accepted=False,
            )
        blueprint = telegram_team.add_blueprint_cautions(
            blueprint,
            blueprint_issues,
        )

    voice_brief = telegram_team.build_voice_brief(
        topic,
        contexts.author_voice,
        api_key,
    )
    draft = telegram_team.write_editorial_post(
        topic,
        blueprint,
        voice_brief,
        api_key,
    )
    human_text_context = notebook_live.build_human_text_context(
        topic,
        draft,
        route.mode,
    )
    draft = telegram_team.human_edit_editorial_post(
        topic,
        blueprint,
        draft,
        human_text_context,
        voice_brief,
        api_key,
    )
    draft = telegram_team.clean_human_surface(topic, draft)
    draft_issues = telegram_team.editorial_contract_issues(topic, draft)
    audit = telegram_team.audit_editorial_post(
        topic,
        blueprint,
        draft,
        contexts.ethics,
        api_key,
        draft_issues,
        message_map,
        human_text_context,
    )

    final_text = draft
    final_audit = audit
    final_issues = draft_issues
    if not audit["accepted"]:
        final_text = telegram_team.repair_editorial_post(
            topic,
            blueprint,
            draft,
            audit["review"],
            voice_brief,
            api_key,
            draft_issues,
            human_text_context,
        )
        final_text = telegram_team.clean_human_surface(topic, final_text)
        final_issues = telegram_team.editorial_contract_issues(topic, final_text)
        final_audit = telegram_team.audit_editorial_post(
            topic,
            blueprint,
            final_text,
            contexts.ethics,
            api_key,
            final_issues,
            message_map,
            human_text_context,
        )

    return PipelineResult(
        topic=topic,
        route_mode=route.mode,
        selected_notebooks=contexts.selected_notebooks,
        answer_fingerprints=_fingerprints(contexts.answers),
        blueprint=blueprint,
        voice_brief=voice_brief,
        draft=draft,
        final_text=final_text,
        audit_review=audit["review"],
        final_audit_review=final_audit["review"],
        contract_issues=final_issues,
        accepted=final_audit["accepted"] and not final_issues,
    )


def _parse_json(text: str) -> dict[str, Any]:
    clean = text.strip()
    clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s*```$", "", clean)
    start = clean.find("{")
    end = clean.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"Судья вернул не JSON: {text[:300]}")
    candidate = clean[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        # Gemini occasionally omits a comma in an otherwise complete score
        # object. Keep the expensive editorial run and recover the numeric
        # rubric instead of misclassifying the entire pipeline as broken.
        scores: dict[str, float] = {}
        for key in SCORE_WEIGHTS:
            match = re.search(
                rf'["\']?{re.escape(key)}["\']?\s*:\s*(\d+(?:[.,]\d+)?)',
                candidate,
                flags=re.IGNORECASE,
            )
            if match:
                scores[key] = float(match.group(1).replace(",", "."))
        if set(scores) != set(SCORE_WEIGHTS):
            raise

        def string_list(field: str) -> list[str]:
            match = re.search(
                rf'["\']?{field}["\']?\s*:\s*\[(.*?)\]',
                candidate,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if not match or not match.group(1).strip():
                return []
            return [
                item.strip()
                for item in re.findall(r'"([^"\r\n]+)"', match.group(1))
                if item.strip()
            ]

        return {
            "scores": scores,
            "blocking": string_list("blocking"),
            "strengths": string_list("strengths"),
            "weaknesses": string_list("weaknesses"),
            "parser_recovered_malformed_json": True,
        }


def judge_result(result: PipelineResult, api_key: str) -> dict[str, Any]:
    if not result.final_text:
        return {
            "scores": {key: 0.0 for key in SCORE_WEIGHTS},
            "overall": 0.0,
            "blocking": list(result.contract_issues),
            "strengths": [],
            "weaknesses": ["Автор не был запущен из-за дефекта blueprint"],
        }
    user_msg = (
        f"ТЕМА:\n{result.topic}\n\n"
        f"BLUEPRINT:\n{result.blueprint}\n\n"
        f"НАСТРОЙКИ ГОЛОСА:\n{result.voice_brief}\n\n"
        f"ФИНАЛЬНЫЙ ТЕКСТ:\n{result.final_text}"
    )
    raw = telegram_team.gemini_call(
        api_key,
        telegram_team.EDITOR_MODEL,
        JUDGE_PROMPT,
        user_msg,
        max_tokens=4200,
        temperature=0.05,
        disable_thinking=True,
    )
    judged = _parse_json(raw)
    raw_scores = judged.get("scores") or {}
    scores = {
        key: max(0.0, min(10.0, float(raw_scores.get(key, 0.0))))
        for key in SCORE_WEIGHTS
    }
    overall = round(
        sum(scores[key] * weight for key, weight in SCORE_WEIGHTS.items()),
        2,
    )
    blocking = [str(item) for item in judged.get("blocking") or []]
    if result.contract_issues:
        blocking.extend(result.contract_issues)
    judged["scores"] = scores
    judged["overall"] = overall
    judged["blocking"] = list(dict.fromkeys(blocking))
    judged["critical_floor_failures"] = {
        key: {"score": scores[key], "minimum": minimum}
        for key, minimum in CRITICAL_SCORE_FLOORS.items()
        if scores[key] < minimum
    }
    judged["passed"] = (
        result.accepted
        and not judged["blocking"]
        and not judged["critical_floor_failures"]
        and overall >= TARGET_SCORE
    )
    return judged


def _case_payload(
    case_id: str,
    result: PipelineResult,
    scorecard: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": case_id,
        "technical_error": False,
        "topic": result.topic,
        "route_mode": result.route_mode,
        "selected_notebooks": result.selected_notebooks,
        "answer_fingerprints": result.answer_fingerprints,
        "notebook_participation_proven": bool(result.answer_fingerprints),
        "blueprint": result.blueprint,
        "voice_brief": result.voice_brief,
        "draft": result.draft,
        "final_text": result.final_text,
        "audit_review": result.audit_review,
        "final_audit_review": result.final_audit_review,
        "contract_issues": result.contract_issues,
        "pipeline_accepted": result.accepted,
        "scorecard": scorecard,
    }


def _summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    if not cases:
        return {}
    technical_cases = [
        case["id"] for case in cases if case.get("technical_error")
    ]
    evaluated = [
        case for case in cases if not case.get("technical_error")
    ]
    if not evaluated:
        return {
            "target": TARGET_SCORE,
            "status": "technical_failure",
            "average_overall": None,
            "category_means": {},
            "repeated_weak_categories": {},
            "technical_cases": technical_cases,
            "blocking_cases": [],
            "passed": False,
        }
    category_means = {
        key: round(
            sum(case["scorecard"]["scores"][key] for case in evaluated)
            / len(evaluated),
            2,
        )
        for key in SCORE_WEIGHTS
    }
    repeated = {
        key: sum(
            1
            for case in evaluated
            if case["scorecard"]["scores"][key] < TARGET_SCORE
        )
        for key in SCORE_WEIGHTS
    }
    repeated = {
        key: count
        for key, count in repeated.items()
        if count >= 2
    }
    overall = round(
        sum(case["scorecard"]["overall"] for case in evaluated) / len(evaluated),
        2,
    )
    return {
        "target": TARGET_SCORE,
        "status": "evaluated",
        "average_overall": overall,
        "category_means": category_means,
        "repeated_weak_categories": repeated,
        "technical_cases": technical_cases,
        "blocking_cases": [
            case["id"]
            for case in evaluated
            if case["scorecard"]["blocking"] or not case["pipeline_accepted"]
        ],
        "passed": (
            overall >= TARGET_SCORE
            and not repeated
            and not technical_cases
            and all(case["scorecard"]["passed"] for case in evaluated)
        ),
    }


def _print_case(case: dict[str, Any]) -> None:
    scorecard = case["scorecard"]
    print(f"\n{'=' * 78}")
    print(f"{case['id']}: {scorecard['overall']}/10")
    print(f"NotebookLM: {', '.join(case['selected_notebooks'])}")
    print("Отпечатков ответов:", len(case["answer_fingerprints"]))
    print("Оценки:", json.dumps(scorecard["scores"], ensure_ascii=False))
    if scorecard["blocking"]:
        print("Блокеры:", "; ".join(scorecard["blocking"]))
    if scorecard.get("weaknesses"):
        print("Слабости:", "; ".join(map(str, scorecard["weaknesses"])))
    print("\nТЕКСТ:\n" + (case["final_text"] or "[текст не создан]"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run three representative topics instead of all six.",
    )
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Run only a named case. Can be repeated.",
    )
    parser.add_argument(
        "--refresh-context",
        action="store_true",
        help="Query NotebookLM again instead of using cached expert answers.",
    )
    parser.add_argument(
        "--continue-on-technical-error",
        action="store_true",
        help="Keep running other cases after a transport/authentication error.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="JSON report path. Defaults to eval_runs/editorial_v3/...",
    )
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("GEMINI_API_KEY не найден в .env")
        return 1

    selected = list(CASES)
    if args.quick:
        selected = [case for case in selected if case[0] in QUICK_CASE_IDS]
    if args.case:
        wanted = set(args.case)
        selected = [case for case in selected if case[0] in wanted]
        missing = wanted - {case[0] for case in selected}
        if missing:
            print("Неизвестные кейсы:", ", ".join(sorted(missing)))
            return 2

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = Path(__file__).resolve().parent
    cache_dir = root / "eval_runs" / "editorial_v3"
    output_path = (
        Path(args.output)
        if args.output
        else cache_dir / f"benchmark_{timestamp}.json"
    )
    if not output_path.is_absolute():
        output_path = root / output_path

    report_cases: list[dict[str, Any]] = []
    for case_id, topic in selected:
        print(f"\nЗапуск {case_id}: {topic}", flush=True)
        try:
            result = run_pipeline(
                topic,
                case_id,
                api_key,
                cache_dir,
                args.refresh_context,
            )
            try:
                scorecard = judge_result(result, api_key)
                payload = _case_payload(case_id, result, scorecard)
            except Exception as exc:
                payload = _case_payload(
                    case_id,
                    result,
                    {
                        "scores": {key: 0.0 for key in SCORE_WEIGHTS},
                        "overall": 0.0,
                        "blocking": [f"Ошибка оценщика: {type(exc).__name__}"],
                        "strengths": [],
                        "weaknesses": ["Финальный текст создан, но оценка не разобрана"],
                        "passed": False,
                    },
                )
                payload["technical_error"] = True
                payload["judge_error"] = f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            payload = {
                "id": case_id,
                "technical_error": True,
                "topic": topic,
                "route_mode": "",
                "selected_notebooks": [],
                "answer_fingerprints": {},
                "notebook_participation_proven": False,
                "blueprint": "",
                "voice_brief": "",
                "draft": "",
                "final_text": "",
                "audit_review": "",
                "final_audit_review": "",
                "contract_issues": [f"{type(exc).__name__}: {exc}"],
                "pipeline_accepted": False,
                "scorecard": {
                    "scores": {key: 0.0 for key in SCORE_WEIGHTS},
                    "overall": 0.0,
                    "blocking": [f"{type(exc).__name__}: {exc}"],
                    "strengths": [],
                    "weaknesses": ["Технический сбой прогона"],
                    "passed": False,
                },
            }
        report_cases.append(payload)
        _print_case(payload)

        partial = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "target": TARGET_SCORE,
            "cases": report_cases,
            "summary": _summary(report_cases),
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(partial, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if payload.get("technical_error") and not args.continue_on_technical_error:
            print(
                "\nЭкзамен остановлен после первого технического сбоя. "
                "Качество текста не оценивалось.",
                flush=True,
            )
            break

    summary = _summary(report_cases)
    print(f"\n{'=' * 78}\nИТОГ")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("Отчёт:", output_path)
    return 0 if summary.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
