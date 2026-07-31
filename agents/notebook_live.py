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
PROMPT_VERSION = "2026-07-31-message-map-human-edit-v1"
QUERY_ATTEMPTS = 2

REQUIRED_COOKIES = {"SID", "HSID", "SSID", "APISID", "SAPISID"}


class NotebookLiveError(RuntimeError):
    """A live notebook preflight or query failed."""


@dataclass(frozen=True)
class NotebookAuth:
    """Complete connector credentials, with cookies-only compatibility."""

    cookies: dict[str, str]
    csrf_token: str = ""
    session_id: str = ""


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
    def message_strategy(self) -> str:
        """Joanna Wiebe only: message architecture before the blueprint."""
        return self._join_roles("audience")

    @property
    def human_text(self) -> str:
        """Ann Handley only: a bounded human-language edit after drafting."""
        return self._join_roles("human_text")

    @property
    def author_voice(self) -> str:
        """Dmitry's own voice sources, without another author's style."""
        return self._join_roles("voice")

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

    def without_roles(self, *roles: str) -> str:
        """Return expert decisions except the named adviser roles.

        The blueprint builder uses this to keep raw voice material out of
        content strategy. Voice is distilled separately and can affect only
        syntax, rhythm and diction.
        """
        excluded = set(roles)
        return "\n\n".join(
            answer
            for compound_key, answer in self.answers.items()
            if compound_key.split(":", 1)[0] not in excluded
        )


_cache: dict[str, tuple[float, TopicContexts]] = {}
_answer_cache: dict[str, tuple[float, str]] = {}
_cache_lock = threading.Lock()
_last_success_at: float | None = None


def _load_auth() -> NotebookAuth:
    encoded = os.environ.get(AUTH_ENV, "").strip()
    if not encoded:
        raise NotebookLiveError(
            f"не задана переменная {AUTH_ENV} с авторизацией Gemini Notebook"
        )
    try:
        payload = json.loads(base64.b64decode(encoded).decode("utf-8"))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise NotebookLiveError("данные авторизации Gemini Notebook повреждены") from exc
    if not isinstance(payload, dict):
        raise NotebookLiveError("данные авторизации Gemini Notebook повреждены")
    cookies = payload.get("cookies", payload)
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
    return NotebookAuth(
        cookies=cookies,
        csrf_token=str(payload.get("csrf_token", "") or ""),
        session_id=str(payload.get("session_id", "") or ""),
    )


def _load_cookies() -> dict[str, str]:
    """Backward-compatible cookie accessor used by status and older callers."""
    return _load_auth().cookies


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
                http_timeout = float(
                    os.environ.get("NOTEBOOKLM_HTTP_TIMEOUT", "60")
                )
                self._client = httpx.Client(
                    cookies=self._cookie_jar(),
                    headers=config.DEFAULT_HEADERS,
                    timeout=httpx.Timeout(http_timeout, connect=http_timeout),
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
        "Опирайся только на источники этого блокнота. Назови применённый принцип "
        "из источников и отдельно сформулируй редакционное решение для этой темы. "
        "Не пиши готовый пост, не выдумывай психологические факты, исследования, "
        "истории Дмитрия или скрытые мотивы читателя. Если источники не дают "
        "основания для вывода, прямо отметь границу. Ответ по-русски, до 1000 знаков."
    )
    instructions = {
        "audience": common + """

Примени метод Joanna Wiebe как архитектуру сообщения до написания текста.
Ты не автор поста. Не используй агрессивный PAS и не усиливай боль ради
удержания внимания. Опирайся на реальную речь аудитории только тогда, когда
она передана во входных данных; методические материалы о Voice of Customer
не являются самими данными Voice of Customer. Ответ строго:
ПРИНЦИП ИЗ ИСТОЧНИКОВ:
НАБЛЮДАЕМЫЙ КОНФЛИКТ:
ОБЕЩАНИЕ ЧИТАТЕЛЮ:
НОВОЕ РАЗЛИЧЕНИЕ:
ТРИ ЧЕСТНЫХ ХУКА:
ЧЕГО НЕЛЬЗЯ ПРИПИСЫВАТЬ ЧИТАТЕЛЮ:
Не описывай реальную аудиторию без исследований и не пиши готовый пост.""",
        "angles": common + """

Примени принципы Рори Сазерленда только как инструмент редакционного мышления.
Дай три разных угла. Для каждого укажи: принцип из источников, тезис, свежий
поворот, контрпример и риск ложной причинности. Не переноси рыночные модели
дефицита, цены, инвестиций и ценности товара на достоинство человека или
интимные отношения. Не советуй становиться менее доступным ради повышения
своей ценности. Не выбирай победителя: окончательный выбор сделает главный
редактор после этической проверки.""",
        "dramaturgy": common + """

Примени принципы драматургии Нэнси Дуарте. Ответ строго:
ПРИНЦИП ИЗ ИСТОЧНИКОВ:
ИСХОДНОЕ ПРЕДСТАВЛЕНИЕ:
ПРОТИВОРЕЧИЕ:
НОВОЕ РАЗЛИЧЕНИЕ:
ФИНАЛЬНЫЙ ЖЕСТ:
Не придумывай сцену, сообщение, встречу или действия читателя. Если конкретных
обстоятельств нет в теме, работай только с ходом мысли.""",
        "ethics": common + """

Используй этические принципы блокнота как право вето до написания текста.
Ответ строго:
ПРИНЦИП ИЗ ИСТОЧНИКОВ:
ЭТИЧЕСКИЙ РИСК ТЕМЫ:
ЗАПРЕЩЁННЫЕ ВЫВОДЫ:
УСЛОВИЯ ЧЕСТНОГО ТЕЗИСА:
Отдельно отклони превращение человека в товар, создание искусственного
дефицита внимания, совет манипулировать доступностью, чтение намерений партнёра,
стыд и утверждение единственной скрытой причины без данных.""",
        "voice": common + """

Ты консультируешь только по слышимой форме речи Дмитрия, а не по содержанию
рабочей темы. Используй его собственную речь, явно одобренные тексты и прямую
обратную связь. Старые AI-черновики не считай образцом.

Извлеки только: длину и ритм фраз, синтаксис, разговорную лексику, дистанцию с
читателем, степень прямоты, переходы между абзацами и характер начала/финала.
Полностью игнорируй мировоззрение и тематику источников. Не переноси факты,
объяснения причин, психологические механизмы, клиентские истории, темы головы и
тела, энергии, терапии или соматического подхода. Не объясняй рабочую тему и не
пиши пример поста. Не предлагай копировать отдельный сленг, междометия, слова
«башка», «блин», «головастики», профессиональное позиционирование,
биографические детали, эзотерическую, телесную или энергетическую лексику.

Ответ строго: 6 коротких правил формы и 5 речевых шаблонов, которых автору
следует избегать. Если признак нельзя уверенно подтвердить несколькими
фрагментами живой речи, не включай его.""",
        "human_text": common + """

Примени метод Ann Handley только как редактуру уже написанного черновика.
Не создавай психологический тезис, не меняй факты, этическую границу и
композиционное решение. Выдели приёмы, которые помогут говорить с одним
умным живым человеком, а не с безликим сегментом. Ответ строго:
ПРИНЦИП ИЗ ИСТОЧНИКОВ:
ЕСТЕСТВЕННЫЙ ВХОД:
РИТМ И КОНКРЕТИКА:
СПОСОБ ЗАКОНЧИТЬ:
ПЯТЬ ШТАМПОВ ПОД ЗАПРЕТОМ:
Не копируй фразы автора источников, не добавляй юмор ради эффекта и не
подменяй голос Дмитрия чужим стилем.""",
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

Предложи пять первых фраз с разной механикой: наблюдение, противоречие, точный
вопрос, контраст, незавершённость. Не повторяй исходную тему или её первые
восемь слов. Не выдумывай сцену от второго лица. Не используй сенсацию,
обещание, диагноз и чтение мыслей. Не используй шаблонный вопрос
«В какой момент X превращается в Y?» и вопрос, который просто пересказывает
тему. Для каждой фразы в трёх словах назови механику. Победителя выберет
главный редактор после проверки всего каркаса.""",
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
    attempts: int = QUERY_ATTEMPTS,
    csrf_token: str = "",
    session_id: str = "",
) -> tuple[str, str]:
    client_class = _patched_client_class()
    notebook_id = notebook.resolved_id()
    if not notebook_id:
        raise NotebookLiveError(f"для «{notebook.title}» не задан ID")
    timeout = float(os.environ.get("NOTEBOOKLM_QUERY_TIMEOUT", "120"))
    last_error: Exception | None = None
    attempts = max(1, attempts)
    for attempt in range(1, attempts + 1):
        try:
            with client_class(
                cookies=cookies,
                csrf_token=csrf_token,
                session_id=session_id,
            ) as client:
                result = client.query(notebook_id, prompt, timeout=timeout)
            answer = (result.get("answer") or "").strip()
            if not answer:
                raise NotebookLiveError(
                    f"блокнот «{notebook.title}» вернул пустой ответ"
                )
            return notebook.key, answer
        except Exception as exc:
            last_error = exc
            if attempt >= attempts or not _is_retryable_query_error(exc):
                break
            time.sleep(0.75 * attempt)
    raise NotebookLiveError(
        f"блокнот «{notebook.title}» не ответил после "
        f"{attempts if _is_retryable_query_error(last_error) else 1} "
        f"попыток: {last_error}"
    ) from last_error


def _is_retryable_query_error(exc: Exception | None) -> bool:
    """Retry only transient transport/server failures, never auth or bad data."""
    if exc is None:
        return False
    if isinstance(
        exc,
        (
            httpx.TimeoutException,
            httpx.NetworkError,
            TimeoutError,
            ConnectionError,
        ),
    ):
        return True
    if "пустой ответ" in str(exc).casefold():
        return True
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "timed out",
            "timeout",
            "handshake operation",
            "connection reset",
            "temporarily unavailable",
            "server disconnected",
            "status 429",
            "status 500",
            "status 502",
            "status 503",
            "status 504",
        )
    )


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
        f"{PROMPT_VERSION}|{route.mode}|"
        f"{' '.join(topic.lower().split())}|{selected_signature}"
    )
    with _cache_lock:
        cached = _cache.get(normalized)
        if cached and time.time() - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]

    auth = _load_auth()
    cookies = auth.cookies
    prompts = {
        notebook.key: _query_prompt(topic, notebook.adviser_role)
        for notebook in configured
    }
    answers: dict[str, str] = {}
    required_failures: list[tuple[team_registry.NotebookSpec, Exception]] = []
    skipped_errors: list[str] = list(skipped_unconfigured)
    pending: list[team_registry.NotebookSpec] = []
    now = time.time()
    with _cache_lock:
        for notebook in configured:
            answer_key = (
                f"{PROMPT_VERSION}|{notebook.resolved_id()}|"
                f"{prompts[notebook.key]}"
            )
            cached_answer = _answer_cache.get(answer_key)
            if cached_answer and now - cached_answer[0] < CACHE_TTL_SECONDS:
                compound_key = f"{notebook.adviser_role}:{notebook.key}"
                answers[compound_key] = (
                    f"Источник: {notebook.title}\n{cached_answer[1]}"
                )
            else:
                pending.append(notebook)

    # Google becomes unreliable when many authenticated NotebookLM sessions
    # negotiate TLS at once. Two workers keep the route bounded and stable.
    configured_workers = int(os.environ.get("NOTEBOOKLM_WORKERS", "2"))
    if pending:
        workers = min(max(1, configured_workers), len(pending))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _query_one,
                    notebook,
                    prompts[notebook.key],
                    cookies,
                    QUERY_ATTEMPTS,
                    auth.csrf_token,
                    auth.session_id,
                ): notebook
                for notebook in pending
            }
            for future in as_completed(futures):
                notebook = futures[future]
                try:
                    answer_key, answer = future.result()
                    compound_key = f"{notebook.adviser_role}:{answer_key}"
                    answers[compound_key] = (
                        f"Источник: {notebook.title}\n{answer}"
                    )
                    cache_key = (
                        f"{PROMPT_VERSION}|{notebook.resolved_id()}|"
                        f"{prompts[notebook.key]}"
                    )
                    with _cache_lock:
                        _answer_cache[cache_key] = (time.time(), answer)
                except Exception as exc:
                    if notebook.is_required(route.mode):
                        required_failures.append((notebook, exc))
                    else:
                        skipped_errors.append(notebook.key)

    # One calm sequential recovery pass for only the required notebooks that
    # failed while other TLS sessions were active. This is the third and final
    # transport attempt; it never restarts successful expert queries.
    required_errors: list[str] = []
    for notebook, _first_error in required_failures:
        try:
            answer_key, answer = _query_one(
                notebook,
                prompts[notebook.key],
                cookies,
                attempts=1,
                csrf_token=auth.csrf_token,
                session_id=auth.session_id,
            )
            compound_key = f"{notebook.adviser_role}:{answer_key}"
            answers[compound_key] = f"Источник: {notebook.title}\n{answer}"
            cache_key = (
                f"{PROMPT_VERSION}|{notebook.resolved_id()}|"
                f"{prompts[notebook.key]}"
            )
            with _cache_lock:
                _answer_cache[cache_key] = (time.time(), answer)
        except Exception as exc:
            required_errors.append(f"{notebook.key}: {exc}")

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


def build_human_text_context(
    topic: str,
    draft: str,
    explicit_mode: str | None = None,
) -> str:
    """Query Ann Handley only after the concrete draft exists."""
    route = team_registry.route_for(topic, explicit_mode)
    notebook = next(
        (
            item
            for item in route.notebooks
            if item.key == "smm02c_human_text"
        ),
        None,
    )
    if notebook is None or not notebook.resolved_id():
        raise NotebookLiveError(
            "для отдельной редактуры Ann Handley не задан ID блокнота"
        )

    prompt = (
        f"Рабочая тема Telegram-поста: «{topic}».\n\n"
        f"КОНКРЕТНЫЙ ЧЕРНОВИК ДЛЯ РЕДАКТУРЫ:\n{draft}\n\n"
        "Опирайся только на источники этого блокнота. Проведи редакционный "
        "разбор именно этого черновика по принципам Ann Handley. Не пиши новый "
        "пост и не меняй тезис, факты, хук-механику, этическую границу или "
        "вывод. Не добавляй психологические причины, сцены, метафоры, юмор и "
        "чужой авторский голос.\n\n"
        "Ответ строго:\n"
        "ЧТО СОХРАНИТЬ:\n"
        "ГДЕ ЗВУЧИТ КАК ЛЕКЦИЯ:\n"
        "ГДЕ НАРУШЕН ЖИВОЙ РУССКИЙ:\n"
        "КАК УБРАТЬ ПОВТОР:\n"
        "ЧТО ПРОВЕРИТЬ ВСЛУХ:\n"
        "СМЫСЛОВАЯ ГРАНИЦА РЕДАКТУРЫ:"
    )
    auth = _load_auth()
    answer_key = (
        f"{PROMPT_VERSION}|ann-draft|{notebook.resolved_id()}|{prompt}"
    )
    now = time.time()
    with _cache_lock:
        cached = _answer_cache.get(answer_key)
        if cached and now - cached[0] < CACHE_TTL_SECONDS:
            return f"Источник: {notebook.title}\n{cached[1]}"

    _key, answer = _query_one(
        notebook,
        prompt,
        auth.cookies,
        max(2, QUERY_ATTEMPTS),
        auth.csrf_token,
        auth.session_id,
    )
    with _cache_lock:
        _answer_cache[answer_key] = (time.time(), answer)
    return f"Источник: {notebook.title}\n{answer}"


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
