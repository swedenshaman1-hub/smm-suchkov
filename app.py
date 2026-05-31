"""
SMM-команда Дмитрия Сучкова
8 агентов | Telegram + Instagram | Groq API
"""

import streamlit as st
import os
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from agents import analyst, strategist, copywriter, editor, publisher
from agents import marketer, instagram_writer

API_KEY = os.getenv("GROQ_API_KEY", "")

st.set_page_config(
    page_title="SMM-команда | Дмитрий Сучков",
    page_icon="🎭",
    layout="wide"
)

st.markdown("""
<style>
.agent-block {
    border-left: 4px solid #7B68EE;
    padding: 12px 16px;
    margin: 10px 0;
    background: #f8f7ff;
    border-radius: 0 8px 8px 0;
}
.agent-name {
    font-weight: bold;
    color: #5B4FBB;
    font-size: 13px;
    margin-bottom: 6px;
}
.accepted { border-left-color: #28a745; background: #f0fff4; }
.rejected { border-left-color: #dc3545; background: #fff5f5; }
.final    { border-left-color: #FFA500; background: #fffaf0; }
.marketing{ border-left-color: #17a2b8; background: #f0faff; }
</style>
""", unsafe_allow_html=True)

# ── Заголовок ──────────────────────────────────────────────────────────────
st.title("🎭 SMM-команда Дмитрия Сучкова")
st.caption("GREM · Танец Души · 8 агентов · Telegram + Instagram")

# ── Боковая панель — состояние памяти ──────────────────────────────────────
with st.sidebar:
    st.header("🧠 Команда и память")

    memory_dir = os.path.join(os.path.dirname(__file__), "memory")
    agents_info = {
        "🔍 Нина (Аналитик)":     "analyst_memory.json",
        "🎯 Артём (Стратег)":     "strategist_memory.json",
        "💡 Олег (Маркетолог)":   "marketer_memory.json",
        "✍️ Маша (Telegram)":     "copywriter_memory.json",
        "🌸 Катя (Instagram)":    "instagram_writer_memory.json",
        "🔎 Игорь (Редактор)":    "editor_memory.json",
        "📊 Рита (СММ-менеджер)": "publisher_memory.json",
        "📤 Соня (Публикатор)":   "publisher_memory.json",
    }

    for agent_name, filename in agents_info.items():
        path = os.path.join(memory_dir, filename)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                mem = json.load(f)
            lessons = len(mem.get("lessons", [])) + len(mem.get("common_errors", []))
            tasks = len(mem.get("analyses", mem.get("strategies", mem.get("texts",
                        mem.get("reviews", mem.get("publications", []))))))
            st.metric(agent_name, f"{tasks} задач", f"{lessons} уроков")
        else:
            st.metric(agent_name, "Новый", "—")

    st.divider()
    if st.button("🗑 Очистить всю память", type="secondary", use_container_width=True):
        for filename in set(agents_info.values()):
            path = os.path.join(memory_dir, filename)
            if os.path.exists(path):
                os.remove(path)
        st.success("Память очищена")
        st.rerun()

# ── Основная область ────────────────────────────────────────────────────────
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("📋 Задача команде")

    topic = st.text_area(
        "Тема или запрос",
        placeholder="Например:\n• выгорание у женщин-лидеров\n• страх потерять контроль\n• тело как ресурс лидера",
        height=130
    )

    st.caption("Быстрый выбор темы:")
    quick_topics = [
        "Выгорание как сигнал тела",
        "Страх успеха у женщин",
        "Почему контроль не работает",
        "Пустота после достижений",
        "Как тело хранит стресс",
    ]
    for qt in quick_topics:
        if st.button(qt, key=f"q_{qt}", use_container_width=True):
            st.session_state["quick_topic"] = qt
            st.rerun()

    if "quick_topic" in st.session_state and not topic:
        topic = st.session_state["quick_topic"]

    st.divider()
    show_process = st.toggle("Показывать процесс обсуждения", value=True)

    run_btn = st.button(
        "🚀 Запустить команду",
        type="primary",
        use_container_width=True,
        disabled=not topic or not API_KEY
    )

    if not API_KEY:
        st.error("GROQ_API_KEY не найден в .env")

with col2:
    st.subheader("💬 Обсуждение команды")

    if run_btn and topic:
        st.session_state["topic"] = topic
        st.session_state["running"] = True

    if st.session_state.get("running") and st.session_state.get("topic"):
        topic = st.session_state["topic"]

        # ── 1. НИНА — Аналитик ────────────────────────────────────────────
        with st.status("🔍 Нина анализирует аудиторию...", expanded=show_process) as s:
            r_analyst = analyst.run(topic, API_KEY)
            s.update(label="✅ Нина Соколова — анализ готов", state="complete")
            if show_process:
                st.markdown(f'<div class="agent-block"><div class="agent-name">🔍 Нина Соколова (Аналитик ЦА)</div>{r_analyst["analysis"]}</div>', unsafe_allow_html=True)
                if r_analyst.get("new_lessons"):
                    st.caption("💡 Нина запомнила: " + " | ".join(r_analyst["new_lessons"]))

        # ── 2. АРТЁМ — Стратег ────────────────────────────────────────────
        with st.status("🎯 Артём разрабатывает стратегию...", expanded=show_process) as s:
            r_strategist = strategist.run(topic, r_analyst["analysis"], API_KEY)
            s.update(label="✅ Артём Волков — стратегия готова", state="complete")
            if show_process:
                st.markdown(f'<div class="agent-block"><div class="agent-name">🎯 Артём Волков (Стратег)</div>{r_strategist["strategy"]}</div>', unsafe_allow_html=True)

        # ── 3. ОЛЕГ — Маркетолог ─────────────────────────────────────────
        with st.status("💡 Олег оценивает маркетинговый потенциал...", expanded=show_process) as s:
            r_marketer = marketer.run(topic, r_analyst["analysis"], r_strategist["strategy"], API_KEY)
            s.update(label="✅ Олег Савин — маркетинговая оценка готова", state="complete")
            if show_process:
                st.markdown(f'<div class="agent-block marketing"><div class="agent-name">💡 Олег Савин (Маркетолог)</div>{r_marketer["marketing"]}</div>', unsafe_allow_html=True)

        # ── 4+5. МАША + КАТЯ пишут параллельно ───────────────────────────
        editor_feedback_tg = None
        editor_feedback_ig = None
        final_tg = None
        final_ig = None

        for iteration in range(1, 3):

            # Маша — Telegram
            with st.status(f"✍️ Маша пишет для Telegram (итерация {iteration})...", expanded=show_process) as s:
                r_copy = copywriter.run(
                    topic, r_analyst["analysis"], r_strategist["strategy"],
                    API_KEY, editor_feedback=editor_feedback_tg, iteration=iteration
                )
                s.update(label=f"✅ Маша Лебедева — Telegram, итерация {iteration}", state="complete")
                if show_process:
                    st.markdown(f'<div class="agent-block"><div class="agent-name">✍️ Маша Лебедева (Telegram)</div>{r_copy["texts"]}</div>', unsafe_allow_html=True)

            # Катя — Instagram
            with st.status(f"🌸 Катя пишет для Instagram (итерация {iteration})...", expanded=show_process) as s:
                r_insta = instagram_writer.run(
                    topic, r_analyst["analysis"], r_strategist["strategy"],
                    r_marketer["marketing"], API_KEY,
                    editor_feedback=editor_feedback_ig, iteration=iteration
                )
                s.update(label=f"✅ Катя Миронова — Instagram, итерация {iteration}", state="complete")
                if show_process:
                    st.markdown(f'<div class="agent-block"><div class="agent-name">🌸 Катя Миронова (Instagram)</div>{r_insta["texts"]}</div>', unsafe_allow_html=True)

            # ── 6. ИГОРЬ — Редактор ───────────────────────────────────────
            with st.status(f"🔎 Игорь проверяет оба текста (итерация {iteration})...", expanded=show_process) as s:
                combined_texts = f"=== TELEGRAM (Маша) ===\n{r_copy['texts']}\n\n=== INSTAGRAM (Катя) ===\n{r_insta['texts']}"
                r_editor = editor.run(
                    topic, r_analyst["analysis"], r_strategist["strategy"],
                    combined_texts, API_KEY, iteration=iteration
                )

                if r_editor["accepted"]:
                    s.update(label=f"✅ Игорь Орлов — ПРИНЯТО (итерация {iteration})", state="complete")
                    final_tg = r_copy["texts"]
                    final_ig = r_insta["texts"]
                    if show_process:
                        st.markdown(f'<div class="agent-block accepted"><div class="agent-name">✅ Игорь Орлов (Редактор) — ПРИНЯТО</div>{r_editor["review"]}</div>', unsafe_allow_html=True)
                    break
                else:
                    s.update(label=f"⚠️ Игорь Орлов — ОТКЛОНЕНО (итерация {iteration})", state="error")
                    editor_feedback_tg = r_editor["review"]
                    editor_feedback_ig = r_editor["review"]
                    if show_process:
                        st.markdown(f'<div class="agent-block rejected"><div class="agent-name">❌ Игорь Орлов (Редактор) — ОТКЛОНЕНО</div>{r_editor["review"]}</div>', unsafe_allow_html=True)
                    if iteration == 2:
                        final_tg = r_copy["texts"]
                        final_ig = r_insta["texts"]
                        st.warning("⚠️ Лимит итераций. Публикуем лучший вариант.")

        # ── 7. РИТА — СММ-менеджер (план публикаций) ─────────────────────
        with st.status("📊 Рита составляет план публикаций...", expanded=show_process) as s:
            smm_prompt = f"""Тема: «{topic}»
Telegram-текст: {final_tg[:400]}
Instagram-текст: {final_ig[:400]}

Составь краткий план публикаций: когда и в каком порядке публиковать на Telegram и Instagram, чтобы получить максимальный охват и вовлечённость."""

            from groq import Groq
            groq_client = Groq(api_key=API_KEY)
            rита_resp = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "Ты — Рита Захарова, СММ-менеджер. Практик, думаешь о регулярности, охватах и плане публикаций. Только русский язык."},
                    {"role": "user", "content": smm_prompt}
                ],
                max_tokens=800,
                temperature=0.6
            )
            r_smm = rита_resp.choices[0].message.content
            s.update(label="✅ Рита Захарова — план готов", state="complete")
            if show_process:
                st.markdown(f'<div class="agent-block"><div class="agent-name">📊 Рита Захарова (СММ-менеджер)</div>{r_smm}</div>', unsafe_allow_html=True)

        # ── 8. СОНЯ — Публикатор ─────────────────────────────────────────
        with st.status("📤 Соня упаковывает финальный контент...", expanded=show_process) as s:
            combined_final = f"TELEGRAM:\n{final_tg}\n\nINSTAGRAM:\n{final_ig}"
            r_pub = publisher.run(topic, combined_final, r_strategist["strategy"], API_KEY)
            s.update(label="✅ Соня Крылова — контент готов к публикации", state="complete")

        # ── ФИНАЛЬНЫЙ РЕЗУЛЬТАТ ───────────────────────────────────────────
        st.divider()
        st.subheader("🎯 Финальный контент")

        tab_tg, tab_ig, tab_report = st.tabs(["📱 Telegram", "📸 Instagram", "📋 Отчёт"])

        with tab_tg:
            st.text_area("Готовый текст для Telegram", final_tg, height=400)

        with tab_ig:
            st.text_area("Готовый контент для Instagram", final_ig, height=400)

        with tab_report:
            st.markdown(r_pub["final_content"])
            st.divider()
            st.markdown("**План публикаций от Риты:**")
            st.markdown(r_smm)

        col_a, col_b = st.columns(2)
        with col_a:
            full_content = f"=== TELEGRAM ===\n{final_tg}\n\n=== INSTAGRAM ===\n{final_ig}\n\n=== ПЛАН ===\n{r_smm}"
            st.download_button(
                "💾 Скачать весь контент",
                data=full_content,
                file_name=f"smm_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                mime="text/plain",
                use_container_width=True
            )
        with col_b:
            if st.button("🔄 Новая задача", use_container_width=True):
                for key in ["running", "topic", "quick_topic"]:
                    st.session_state.pop(key, None)
                st.rerun()

    elif not st.session_state.get("running"):
        st.info("👈 Введи тему слева и нажми «Запустить команду»")
        st.markdown("""
**Твоя команда из 8 человек:**

🔍 **Нина Соколова** — находит настоящую боль ЦА
🎯 **Артём Волков** — строит стратегию и угол подачи
💡 **Олег Савин** — оценивает конверсионный потенциал
✍️ **Маша Лебедева** — пишет глубокие тексты для Telegram
🌸 **Катя Миронова** — создаёт контент для Instagram
🔎 **Игорь Орлов** — критически редактирует, принимает или возвращает
📊 **Рита Захарова** — составляет план публикаций
📤 **Соня Крылова** — финальная упаковка с хэштегами и временем

Каждый агент накапливает опыт и становится лучше с каждой задачей.
        """)
