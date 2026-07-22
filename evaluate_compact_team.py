"""Offline quality loop for the compact Telegram editorial team."""
import json
import os
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from agents import channel_stats, telegram_team
from agents.gemini_utils import gemini_call


API_KEY = os.getenv("GEMINI_API_KEY", "")
CHANNEL_CHAT_ID = -1001800141714
EVAL_MODEL = os.getenv("GEMINI_EVAL_MODEL", "gemini-2.5-flash")

TOPICS = [
    "Как отличить поддержку близкого человека от попытки незаметно управлять его выбором?",
    "Почему после долгожданного достижения иногда приходит не радость, а пустота — и обязательно ли с этим что-то делать?",
    "Где заканчивается честность с собой и начинается привычка оправдывать отказ от сложного шага?",
]

EVALUATOR_PROMPT = """Ты — строгий независимый главный редактор. Оцени Telegram-пост, не помогая команде и не
завышая баллы за грамотность. 9.5 означает текст, который можно уверенно публиковать сильному автору без правок.

Поставь 0–10 по критериям:
hook — первые две строки мгновенно создают узнавание или напряжение;
retention — каждый абзац добавляет шаг и ведёт до финала;
humanity — живой голос без назидания и чтения мыслей читателя;
originality — свежий угол, не шаблонное психологическое эссе;
precision — осторожная причинность, контрпримеры, отсутствие диагноза;
rhythm — естественная устная музыка и длина;
no_ai_patterns — нет симметричных формул, россыпи метафор, повторов и гладкого AI-языка.

Ограничения:
- выдуманный реальный случай или именованный герой: общий балл не выше 6;
- уверенное объяснение скрытых мотивов читателя: не выше 6.5;
- одна мысль повторяется трижды: retention не выше 6;
- тема обещает различие, но не даёт наблюдаемых критериев: precision не выше 6;
- 9.5 ставь только при отсутствии содержательной правки, а не из вежливости.

Верни ТОЛЬКО JSON без Markdown:
{"scores":{"hook":0,"retention":0,"humanity":0,"originality":0,"precision":0,"rhythm":0,"no_ai_patterns":0},
"mean":0,"publish_ready":false,"strongest":"...","weakest":"...","required_change":"..."}"""


def parse_json(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    return json.loads(cleaned)


def evaluate(topic: str, post: str) -> dict:
    raw = gemini_call(
        API_KEY, EVAL_MODEL, EVALUATOR_PROMPT,
        f"ТЕМА:\n{topic}\n\nПОСТ:\n{post}",
        max_tokens=5000, temperature=0.1, disable_thinking=False,
    )
    return parse_json(raw)


def run_topic(topic: str, voice_samples: str) -> dict:
    research = telegram_team.research(topic, API_KEY)
    strategy = telegram_team.strategize(topic, research, API_KEY)
    strategy = telegram_team.curate_strategy(topic, research, strategy, API_KEY)
    variants = telegram_team.write(topic, research, strategy, API_KEY, voice_samples=voice_samples)
    review = telegram_team.review(topic, strategy, variants, API_KEY)
    selected = telegram_team.extract_variant(variants, review["variant"])
    if not review["accepted"]:
        variants = telegram_team.write(
            topic, research, strategy, API_KEY,
            feedback=review["review"], previous_text=selected, voice_samples=voice_samples,
        )
        review = telegram_team.review(topic, strategy, variants, API_KEY)
        selected = telegram_team.extract_variant(variants, review["variant"])
    post = telegram_team.polish(
        topic, selected, API_KEY, voice_samples=voice_samples,
        issues=telegram_team.quality_warnings(selected),
    )
    warnings = telegram_team.quality_warnings(post)
    if warnings:
        post = telegram_team.polish(topic, post, API_KEY, voice_samples=voice_samples, issues=warnings)
    internal_audits = []
    for audit_attempt in range(3):
        audit = telegram_team.audit_final(topic, post, API_KEY)
        internal_audits.append(audit)
        if audit.get("accepted") or audit_attempt == 2:
            break
        post = telegram_team.rewrite_final(topic, post, audit, API_KEY, voice_samples=voice_samples)
    technical_errors = telegram_team.validate_post(post)
    if technical_errors:
        repaired = telegram_team.polish(
            topic, post, API_KEY, voice_samples=voice_samples,
            issues=["Исправь техническую незавершённость: " + item for item in technical_errors],
        )
        post = repaired if not telegram_team.validate_post(repaired) else selected
    return {
        "topic": topic, "post": post, "editor": review,
        "internal_audits": internal_audits, "evaluation": evaluate(topic, post),
    }


def main():
    if not API_KEY:
        raise SystemExit("GEMINI_API_KEY is missing")
    recent = channel_stats.get_recent_posts(CHANNEL_CHAT_ID, 8)
    voice_samples = telegram_team.build_voice_samples(recent)
    out_dir = Path(__file__).parent / "eval_runs"
    out_dir.mkdir(exist_ok=True)
    run_stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    checkpoint_path = out_dir / f"compact_{run_stamp}_checkpoint.json"
    results = []
    for index, topic in enumerate(TOPICS, 1):
        print(f"[{index}/{len(TOPICS)}] {topic}", flush=True)
        result = run_topic(topic, voice_samples)
        results.append(result)
        checkpoint_path.write_text(
            json.dumps({"created_at": datetime.now().isoformat(), "results": results}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(result["evaluation"], ensure_ascii=False), flush=True)
    means = [float(item["evaluation"]["mean"]) for item in results]
    report = {
        "created_at": datetime.now().isoformat(),
        "mean": round(sum(means) / len(means), 2),
        "minimum": min(means),
        "target_reached": min(means) >= 9.5,
        "results": results,
    }
    out_path = out_dir / f"compact_{run_stamp}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"REPORT={out_path}")
    print(json.dumps({k: report[k] for k in ("mean", "minimum", "target_reached")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
