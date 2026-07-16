"""
Локальный прогон полного пайплайна на одну тему — без Telegram и без деплоя.
Повторяет порядок вызовов из telegram_bot.py::_run_post_inner, но синхронно и с
выводом в консоль + сохранением в файл, чтобы можно было быстро проверить
эффект правок в промптах агентов.

Запуск: python test_pipeline.py "тема поста"
"""
import os
import re
import sys
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from agents import analyst, strategist, copywriter, instagram_writer
from agents import editor, instagram_editor, humanizer, marketer

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


def _split_instagram_sections(text: str) -> list:
    labels = {
        "ОСНОВНОЙ ПОСТ": "ПОСТ",
        "СТОРИС-ПРОГРЕВ": "СТОРИС",
        "КАРУСЕЛЬ": "КАРУСЕЛЬ",
        "REELS": "REELS",
    }
    pattern = r"^[#\s]*\**\s*\d*[.\)]?\s*(ОСНОВНОЙ ПОСТ|СТОРИС[- ]ПРОГРЕВ|КАРУСЕЛЬ|REELS)\**\s*[^\n]*$"
    matches = list(re.finditer(pattern, text, re.MULTILINE | re.IGNORECASE))
    if not matches:
        return [("INSTAGRAM-ПАКЕТ", text)]
    sections = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        matched = m.group(1).upper().replace("-", " ")
        matched = re.sub(r"\s+", " ", matched).replace("СТОРИС ПРОГРЕВ", "СТОРИС-ПРОГРЕВ")
        label = labels.get(matched, matched)
        sections.append((label, text[start:end].strip()))
    return sections


def _extract_variant(text: str, letter: str) -> str:
    pattern_for = lambda l: rf"ВАРИАНТ\s+{l}\b.*?(?=ВАРИАНТ\s+[АБ]\b|ПОЧЕМУ\s+ЭТИ\s+ДВА\s+ВАРИАНТА|\Z)"

    def _try_extract(l: str):
        match = re.search(pattern_for(l), text, re.DOTALL | re.IGNORECASE)
        if not match:
            return None
        chunk = match.group(0).strip()
        lines = chunk.split("\n", 1)
        return lines[1].strip() if len(lines) > 1 else chunk

    if letter:
        result = _try_extract(letter)
        if result:
            return result
    fallback = _try_extract("А")
    return fallback if fallback else text


def log(section: str, content: str, out):
    banner = f"\n{'='*70}\n{section}\n{'='*70}\n"
    print(banner)
    print(content)
    out.write(banner)
    out.write(content + "\n")


def main():
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY не найден в .env")
        sys.exit(1)

    topic = sys.argv[1] if len(sys.argv) > 1 else "что такое любовь"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = f"test_run_{ts}.txt"

    with open(out_path, "w", encoding="utf-8") as out:
        out.write(f"ТЕМА: {topic}\nВРЕМЯ: {datetime.now().isoformat()}\n")

        print(f"\nТема: «{topic}»\n")

        print("Нина Соколова — анализирую аудиторию...")
        r_analyst = analyst.run(topic, GEMINI_API_KEY)
        log("НИНА СОКОЛОВА (Аналитик ЦА)", r_analyst["analysis"], out)

        print("\nАртём Волков — строю стратегию...")
        r_strategist = strategist.run(topic, r_analyst["analysis"], GEMINI_API_KEY)
        log("АРТЁМ ВОЛКОВ (Стратег)", r_strategist["strategy"], out)

        print("\nМаша Лебедева — пишу два варианта Telegram...")
        r_copy = copywriter.run(topic, r_analyst["analysis"], r_strategist["strategy"], GEMINI_API_KEY)
        log("МАША ЛЕБЕДЕВА (Telegram, 2 варианта)", r_copy["texts"], out)

        print("\nКатя Миронова — собираю Instagram-пакет...")
        r_insta = instagram_writer.run(topic, r_analyst["analysis"], r_strategist["strategy"], "", GEMINI_API_KEY)
        log("КАТЯ МИРОНОВА (Instagram-пакет)", r_insta["texts"], out)

        print("\nИгорь Орлов — проверяю варианты Маши...")
        r_editor = editor.run(topic, r_analyst["analysis"], r_strategist["strategy"], r_copy["texts"], GEMINI_API_KEY)
        log("ИГОРЬ ОРЛОВ (Редактор Telegram)", r_editor["review"], out)
        final_tg = _extract_variant(r_copy["texts"], r_editor.get("chosen_variant"))

        if not r_editor["accepted"]:
            print("\nИгорь вернул на доработку — Маша переписывает...")
            r_copy2 = copywriter.run(topic, r_analyst["analysis"], r_strategist["strategy"], GEMINI_API_KEY,
                                      editor_feedback=r_editor["review"], iteration=2)
            log("МАША ЛЕБЕДЕВА (переработка, итерация 2)", r_copy2["texts"], out)
            r_editor2 = editor.run(topic, r_analyst["analysis"], r_strategist["strategy"], r_copy2["texts"],
                                    GEMINI_API_KEY, iteration=2)
            log("ИГОРЬ ОРЛОВ (повторная проверка)", r_editor2["review"], out)
            final_tg = _extract_variant(r_copy2["texts"], r_editor2.get("chosen_variant"))

        print("\nЛена Волкова — проверяю Instagram-пакет...")
        r_ig_ed = instagram_editor.run(topic, r_analyst["analysis"], r_strategist["strategy"], r_insta["texts"], GEMINI_API_KEY)
        log("ЛЕНА ВОЛКОВА (Редактор Instagram)", r_ig_ed["review"], out)
        final_ig = r_insta["texts"]

        if not r_ig_ed["accepted"]:
            print("\nЛена вернула на доработку — Катя переписывает...")
            r_insta2 = instagram_writer.run(topic, r_analyst["analysis"], r_strategist["strategy"], "", GEMINI_API_KEY,
                                             editor_feedback=r_ig_ed["review"], iteration=2)
            log("КАТЯ МИРОНОВА (переработка, итерация 2)", r_insta2["texts"], out)
            final_ig = r_insta2["texts"]

        print("\nДаша Козлова — очеловечиваю тексты...")
        final_ig_sections = dict(_split_instagram_sections(final_ig))
        ig_post_raw = final_ig_sections.pop("ПОСТ", final_ig)
        r_human = humanizer.run(topic, final_tg, ig_post_raw, GEMINI_API_KEY)
        log("ДАША КОЗЛОВА — TELEGRAM (очеловечено)", r_human["telegram_humanized"], out)
        log("ДАША КОЗЛОВА — INSTAGRAM ПОСТ (очеловечено)", r_human["instagram_humanized"], out)

        for key, label in (("telegram_humanized", "Telegram"), ("instagram_humanized", "Instagram")):
            found = humanizer.find_denylisted(r_human[key])
            if found:
                print(f"Найдены запрещённые штампы в {label}: {found} — исправляю...")
                r_human[key] = humanizer.force_remove_cliches(r_human[key], found, topic, GEMINI_API_KEY)
                log(f"ДАША — {label} (после чистки штампов)", r_human[key], out)

        full_ig_text = r_human["instagram_humanized"] + "\n\n" + "\n\n".join(
            f"{label}:\n{content}" for label, content in final_ig_sections.items()
        )

        print("\nОлег Савин — маркетинговая оценка...")
        r_marketer = marketer.run(topic, r_analyst["analysis"], r_strategist["strategy"], GEMINI_API_KEY,
                                   final_content=f"TELEGRAM:\n{r_human['telegram_humanized']}\n\nINSTAGRAM:\n{full_ig_text}")
        log("ОЛЕГ САВИН (Маркетолог)", r_marketer["marketing"], out)

        print(f"\nГотово. Полный лог сохранён в {out_path}")


if __name__ == "__main__":
    main()
