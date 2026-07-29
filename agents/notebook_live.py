"""Live, fail-closed access to the user's Gemini Notebook library.

Notebook answers are fetched for the exact post topic before the editorial
pipeline starts.  If the live notebook connection is unavailable, callers get
an explicit error; this module never substitutes a static prompt silently.
"""

from __future__ import annotations

import base64
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import httpx
from agents import team_registry


BASE_URL = "https://notebook.google.com"
AUTH_ENV = "NOTEBOOKLM_AUTH_B64"
CACHE_TTL_SECONDS = 4 * 60 * 60

REQUIRED_COOKIES = {"SID", "HSID", "SSID", "APISID", "SAPISID"}


class NotebookLiveError(RuntimeError):
    """A live notebook preflight or query failed."""


@dataclass(frozen=True)
class TopicContexts:
    mode: str
    answers: dict[str, str]
    selected_notebooks: tuple[str, ...]
    skipped_optional: tuple[str, ...] = ()

    def _join_roles(self, *roles: str) -> str:
        selected = [
            answer
            for key, answer in self.answers.items()
            if key.split(":", 1)[0] in roles
        ]
        return "\n\n".join(selected)

    @property
    def audience(self) -> str:
        return self._join_roles("audience", "human_text")

    @property
    def angles(self) -> str:
        return self._join_roles(
            "angles",
            "positioning",
            "brand_architecture",
            "founder_stories",
            "offer",
        )

    @property
    def dramaturgy(self) -> str:
        return self._join_roles(
            "dramaturgy",
            "short_dramaturgy",
            "hooks",
            "educational_clarity",
        )

    @property
    def ethics(self) -> str:
        return self._join_roles("ethics")

    @property
    def voice(self) -> str:
        return self._join_roles("voice", "human_text")

    @property
    def commercial(self) -> str:
        return self._join_roles(
            "offer",
            "positioning",
            "distribution",
            "brand_architecture",
        )

    def for_agents(self, *agent_keys: str) -> str:
        route = team_registry.route_for("", explicit_mode=self.mode)
        allowed_keys = {
            nb.key
            for nb in team_registry.notebooks_for_agents(route, agent_keys)
        }
        return "\n\n".join(
            answer
            for compound_key, answer in self.answers.items()
            if compound_key.split(":", 2)[1] in allowed_keys
        )


_cache: dict[str, tuple[float, TopicContexts]] = {}
_cache_lock = threading.Lock()
_last_success_at: float | None = None


def _load_cookies() -> dict[str, str]:
    encoded = os.environ.get(AUTH_ENV, "").strip()
    if not encoded:
        raise NotebookLiveError(
            f"не задана переменная {AUTH_ENV} с авторизацией Gemini Notebook"
        )
    try:
        payload = json.loads(base64.b64decode(encoded).decode("utf-8"))
        cookies = payload.get("cookies", payload)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise NotebookLiveError("данные авторизации Gemini Notebook повреждены") from exc
    if not isinstance(cookies, dict):
        raise NotebookLiveError("в авторизации Gemini Notebook нет cookie")
    cookies = {
        str(name): str(value)
        for name, value in cookies.items()
        if name and value
    }
    missing = REQUIRED_COOKIES - set(cookies)
    if missing:
        raise NotebookLiveError(
            "в авторизации Gemini Notebook не хватает обязательных cookie: "
            + ", ".join(sorted(missing))
        )
    return cookies


def _patched_client_class():
    """Patch the connector for Google's 2026 NotebookLM domain rename."""
    try:
        from notebooklm_mcp_2026 import config, protocol
        from notebooklm_mcp_2026.auth import (
            extract_csrf_from_html,
            extract_session_id_from_html,
        )
        from notebooklm_mcp_2026.client import (
            AuthenticationError,
            NotebookLMClient,
        )
    except ImportError as exc:
        raise NotebookLiveError(
            "пакет notebooklm-mcp-2026 не установлен"
        ) from exc

    batchexecute_url = f"{BASE_URL}/_/LabsTailwindUi/data/batchexecute"
    config.BASE_URL = BASE_URL
    config.BATCHEXECUTE_URL = batchexecute_url
    config.DEFAULT_HEADERS["Origin"] = BASE_URL
    config.DEFAULT_HEADERS["Referer"] = f"{BASE_URL}/"
    protocol.BASE_URL = BASE_URL
    protocol.BATCHEXECUTE_URL = batchexecute_url

    class PatchedNotebookClient(NotebookLMClient):
        def _cookie_jar(self) -> httpx.Cookies:
            jar = httpx.Cookies()
            for name, value in self.cookies.items():
                if name in {"OSID", "__Secure-OSID"}:
                    jar.set(name, value, domain="notebook.google.com")
                else:
                    jar.set(name, value, domain=".google.com")
                    jar.set(name, value, domain=".googleusercontent.com")
            return jar

        def _get_client(self) -> httpx.Client:
            if self._client is None:
                self._client = httpx.Client(
                    cookies=self._cookie_jar(),
                    headers=config.DEFAULT_HEADERS,
                    timeout=config.DEFAULT_TIMEOUT,
                )
            return self._client

        def _refresh_auth_tokens(self) -> None:
            with httpx.Client(
                cookies=self._cookie_jar(),
                headers=config.PAGE_FETCH_HEADERS,
                follow_redirects=True,
                timeout=20.0,
            ) as client:
                response = client.get(f"{BASE_URL}/")
            if "accounts.google.com" in str(response.url):
                raise AuthenticationError(
                    "Gemini Notebook перенаправил запрос на вход: cookie истекли"
                )
            if response.status_code != 200:
                raise AuthenticationError(
                    f"Gemini Notebook вернул HTTP {response.status_code}"
                )
            csrf = extract_csrf_from_html(response.text)
            if not csrf:
                raise AuthenticationError(
                    "не удалось получить CSRF-токен Gemini Notebook"
                )
            self.csrf_token = csrf
            session_id = extract_session_id_from_html(response.text)
            if session_id:
                self._session_id = session_id

        def _persist_tokens(self) -> None:
            # Railway gets its credentials only from an encrypted environment
            # variable. Never copy the user's cookies into container storage.
            return None

    return PatchedNotebookClient


def _query_prompt(topic: str, adviser_role: str) -> str:
    common = (
        f"Рабочая тема Telegram-поста: «{topic}».\n"
        "Опирайся только на источники этого блокнота. Не пиши готовый пост, "
        "не выдумывай психологические факты, исследования, истории Дмитрия или "
        "скрытые мотивы читателя. Ответ по-русски, конкретно, до 1200 знаков."
    )
    instructions = {
        "audience": common + """

Ты консультируешь автора только по копирайтингу и языку аудитории.
Предложи: 1) три ясные человеческие формулировки темы; 2) два типа захода,
способных удержать внимание без кликбейта; 3) слова и штампы, которых стоит
избегать. Не делай выводов о психологии читателя.""",
        "angles": common + """

Примени принципы Рори Сазерленда только как инструмент редакционного мышления.
Дай пять действительно разных смысловых углов. Для каждого: тезис, честный
парадокс, ограничение или контрпример. Выбери самый свежий угол, который не
требует недоказанного объяснения психики.""",
        "dramaturgy": common + """

Примени принципы драматургии Нэнси Дуарте. Предложи компактную дугу Telegram-
поста: как сейчас → противоречие → новое различение. Укажи, какая одна
конкретная сцена допустима как условное наблюдение, где должен произойти
поворот и как закончить без морализаторства.""",
        "ethics": common + """

Используй только этические принципы и разборы из этого блокнота. Проверь:
1) манипуляцию, ложную причинность, чтение мыслей, давление страхом/виной и
скрытый авторитет; 2) уважение достоинства и автономии человека; 3) честность
условий, обещаний и ограничений; 4) справедливость обмена и риск эксплуатации
уязвимости. Отдельно назови принцип из источников и свой вывод о его применении
к этому тексту. Дай короткий список требований, при которых текст останется
убедительным, но сохранит свободу выбора читателя.""",
        "voice": common + """

Используй только надёжные материалы о живом голосе Дмитрия: его собственную
речь, явно одобренные тексты и прямую обратную связь. Старые AI-черновики не
считай образцом. Не позиционируй Дмитрия как соматического терапевта и не
переноси терапевтические обещания. Дай 8 точных правил голоса именно для этой
темы: ритм, лексика, степень прямоты, начало и финал.""",
        "human_text": common + """

Выдели приёмы человеческого авторского текста, применимые к этой теме:
естественный вход, ритм, конкретика и способ закончить без назидания.
Не копируй фразы автора источников и не подменяй голос Дмитрия чужим стилем.""",
        "short_dramaturgy": common + """

Предложи только компактные приёмы удержания для короткого формата:
первый смысловой кадр, один поворот и финальный жест. Не используй кликбейт
и не превращай Telegram-пост в сценарий Reels.""",
        "positioning": common + """

Проверь, помогает ли тема ясно показать позицию и компетентность Дмитрия без
самовосхваления. Предложи один точный ракурс позиционирования и перечисли,
какие заявления нельзя делать без доказательств.""",
        "distribution": common + """

Дай рекомендации только по упаковке и распространению материала: формат,
первый контакт, возможная нарезка и площадка. Не меняй авторский голос и не
предлагай публиковать чаще ради количества.""",
        "offer": common + """

Если задача коммерческая, выдели: желаемый результат, препятствия, механизм
ценности, реальные доказательства, снижение риска и один честный следующий
шаг. Не придумывай цену, гарантии, дефицит, результаты клиентов или свойства
продукта. Если входных данных мало — явно перечисли, чего не хватает.""",
        "brand_architecture": common + """

Рассмотри тему как часть архитектуры личного бренда. Укажи: какую устойчивую
ассоциацию она должна усиливать, чем подтверждается компетентность и как не
потерять человеческий голос. Не предлагай искусственно поляризовать автора.""",
        "creator_system": common + """

Рассмотри материал как проверяемую контент-гипотезу. Предложи цель, один
наблюдаемый сигнал качества и возможное продолжение серии. Не оптимизируй
смысл только ради метрик.""",
        "hooks": common + """

Предложи пять разных первых фраз, каждая с иной механикой внимания: конкретное
наблюдение, напряжение, вопрос, контраст, незавершённость. Хуки должны честно
соответствовать тексту, без сенсации, обещания и чтения мыслей читателя.""",
        "founder_stories": common + """

Предложи структуру правдивой истории основателя или автора: ставка, решение,
цена решения и вывод. Не выдумывай события, реплики или биографические детали;
пометь, какие факты должен дать Дмитрий.""",
        "educational_clarity": common + """

Помоги превратить тему в ясный образовательный материал: одно обещание
понимания, три логических шага, один пример и один применимый вывод.
Не упрощай до банальности и не выдавай мнение за проверенный факт.""",
    }
    return instructions.get(
        adviser_role,
        common
        + "\n\nДай только рекомендации, относящиеся к своей экспертной области.",
    )


def _selected_notebooks(
    route: team_registry.TeamRoute,
) -> tuple[team_registry.NotebookSpec, ...]:
    optional_keys = set(team_registry.DEFAULT_OPTIONAL_NOTEBOOKS[route.mode])
    return tuple(
        notebook
        for notebook in route.notebooks
        if notebook.is_required(route.mode) or notebook.key in optional_keys
    )


def _query_one(
    notebook: team_registry.NotebookSpec,
    prompt: str,
    cookies: dict[str, str],
) -> tuple[str, str]:
    client_class = _patched_client_class()
    notebook_id = notebook.resolved_id()
    if not notebook_id:
        raise NotebookLiveError(f"для «{notebook.title}» не задан ID")
    try:
        with client_class(cookies=cookies, csrf_token="", session_id="") as client:
            result = client.query(
                notebook_id,
                prompt,
                timeout=float(os.environ.get("NOTEBOOKLM_QUERY_TIMEOUT", "120")),
            )
    except Exception as exc:
        raise NotebookLiveError(
            f"блокнот «{notebook.title}» не ответил: {exc}"
        ) from exc
    answer = (result.get("answer") or "").strip()
    if not answer:
        raise NotebookLiveError(f"блокнот «{notebook.title}» вернул пустой ответ")
    return notebook.key, answer


def build_topic_context(
    topic: str,
    explicit_mode: str | None = None,
) -> TopicContexts:
    """Fetch only the NotebookLM advisers relevant to this task."""
    global _last_success_at

    route = team_registry.route_for(topic, explicit_mode)
    selected = _selected_notebooks(route)
    missing_required = tuple(
        notebook
        for notebook in selected
        if notebook.is_required(route.mode) and not notebook.resolved_id()
    )
    if missing_required:
        raise NotebookLiveError(
            "не заданы ID обязательных блокнотов: "
            + ", ".join(notebook.key for notebook in missing_required)
        )

    configured = tuple(nb for nb in selected if nb.resolved_id())
    skipped_unconfigured = tuple(nb.key for nb in selected if not nb.resolved_id())
    selected_signature = ",".join(
        f"{nb.key}:{nb.resolved_id()}" for nb in configured
    )
    normalized = (
        f"{route.mode}|{' '.join(topic.lower().split())}|{selected_signature}"
    )
    with _cache_lock:
        cached = _cache.get(normalized)
        if cached and time.time() - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]

    cookies = _load_cookies()
    prompts = {
        notebook.key: _query_prompt(topic, notebook.adviser_role)
        for notebook in configured
    }
    answers: dict[str, str] = {}
    required_errors: list[str] = []
    skipped_errors: list[str] = list(skipped_unconfigured)
    configured_workers = int(os.environ.get("NOTEBOOKLM_WORKERS", "6"))
    workers = min(max(1, configured_workers), len(prompts))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_query_one, notebook, prompts[notebook.key], cookies): notebook
            for notebook in configured
        }
        for future in as_completed(futures):
            notebook = futures[future]
            try:
                answer_key, answer = future.result()
                compound_key = f"{notebook.adviser_role}:{answer_key}"
                answers[compound_key] = (
                    f"Источник: {notebook.title}\n{answer}"
                )
            except Exception as exc:
                if notebook.is_required(route.mode):
                    required_errors.append(f"{notebook.key}: {exc}")
                else:
                    skipped_errors.append(notebook.key)

    if required_errors:
        raise NotebookLiveError(
            "живой маршрут через Gemini Notebook остановлен — "
            + " | ".join(required_errors)
        )

    bundle = TopicContexts(
        mode=route.mode,
        answers=answers,
        selected_notebooks=tuple(nb.key for nb in configured),
        skipped_optional=tuple(dict.fromkeys(skipped_errors)),
    )
    now = time.time()
    with _cache_lock:
        _cache[normalized] = (now, bundle)
        _last_success_at = now
    return bundle


def is_configured() -> bool:
    try:
        _load_cookies()
        return True
    except NotebookLiveError:
        return False


def status_line() -> str:
    if not is_configured():
        return (
            "LIVE не настроен; создание постов заблокировано; "
            + team_registry.registry_status()
        )
    if _last_success_at:
        age_minutes = max(0, int((time.time() - _last_success_at) / 60))
        return (
            f"LIVE настроен; последний успешный прогон {age_minutes} мин. назад; "
            + team_registry.registry_status()
        )
    return "LIVE настроен; ожидает первого прогона; " + team_registry.registry_status()
