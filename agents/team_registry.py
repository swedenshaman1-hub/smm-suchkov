"""Single source of truth for the SMM team and its NotebookLM routes.

The registry separates three concerns:
1. what kind of result the user asked for;
2. which agents are responsible for that result;
3. which NotebookLM libraries may advise each agent.

Notebook experts advise the team. They never replace the role prompts and they
are not all queried for every task.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Iterable


EDITORIAL = "editorial"
BRAND = "brand"
COMMERCIAL = "commercial"
TASK_MODES = (EDITORIAL, BRAND, COMMERCIAL)

MODE_LABELS = {
    EDITORIAL: "редакционный пост",
    BRAND: "личный бренд и позиционирование",
    COMMERCIAL: "коммерческий материал",
}

# A bounded council for each mode. Required notebooks are always queried;
# these are the only additional advisers invited automatically.
DEFAULT_OPTIONAL_NOTEBOOKS = {
    EDITORIAL: ("smm02c_human_text",),
    BRAND: (
        "smm02c_human_text",
        "smm05a_positioning",
        "smm07_brand_architecture",
        "smm08_creator_system",
    ),
    COMMERCIAL: (
        "smm02c_human_text",
        "smm05a_positioning",
        "smm07_brand_architecture",
        "smm05b_distribution",
    ),
}


@dataclass(frozen=True)
class AgentSpec:
    key: str
    name: str
    responsibility: str
    stage: int
    modes: tuple[str, ...]


@dataclass(frozen=True)
class NotebookSpec:
    key: str
    title: str
    adviser_role: str
    modes: tuple[str, ...]
    agents: tuple[str, ...]
    notebook_id: str = ""
    env_var: str = ""
    required_modes: tuple[str, ...] = ()

    def resolved_id(self) -> str:
        if self.env_var:
            configured = os.environ.get(self.env_var, "").strip()
            if configured:
                return configured
        return self.notebook_id

    def is_required(self, mode: str) -> bool:
        return mode in self.required_modes


@dataclass(frozen=True)
class TeamRoute:
    mode: str
    topic: str
    agents: tuple[AgentSpec, ...]
    notebooks: tuple[NotebookSpec, ...]

    @property
    def required_notebooks(self) -> tuple[NotebookSpec, ...]:
        return tuple(nb for nb in self.notebooks if nb.is_required(self.mode))

    @property
    def optional_notebooks(self) -> tuple[NotebookSpec, ...]:
        return tuple(nb for nb in self.notebooks if not nb.is_required(self.mode))

    @property
    def missing_required(self) -> tuple[NotebookSpec, ...]:
        return tuple(nb for nb in self.required_notebooks if not nb.resolved_id())

    @property
    def configured_notebooks(self) -> tuple[NotebookSpec, ...]:
        return tuple(nb for nb in self.notebooks if nb.resolved_id())


AGENTS = (
    AgentSpec(
        "researcher",
        "Нина Соколова",
        "Советник по языку аудитории: решение NotebookLM входит в blueprint; отдельный текст в /post не пишет",
        10,
        TASK_MODES,
    ),
    AgentSpec(
        "strategist",
        "Артём Волков",
        "Главред blueprint: сводит решения NotebookLM и один раз фиксирует тезис, хук, логику и границы",
        20,
        TASK_MODES,
    ),
    AgentSpec(
        "hook_editor",
        "Кирилл Романов",
        "SMM-09 предлагает пять входов; окончательный хук выбирает главред внутри blueprint",
        24,
        TASK_MODES,
    ),
    AgentSpec(
        "marketer",
        "Олег Савин",
        "Цель, площадка, распространение и измеримый результат",
        25,
        (BRAND, COMMERCIAL),
    ),
    AgentSpec(
        "writer",
        "Маша Лебедева",
        "Один Telegram-текст по утверждённому blueprint; максимум одна исправленная версия",
        30,
        TASK_MODES,
    ),
    AgentSpec(
        "instagram_writer",
        "Катя Миронова",
        "Instagram-адаптация без потери мысли",
        31,
        TASK_MODES,
    ),
    AgentSpec(
        "editor",
        "Игорь Орлов",
        "Один аудит смысла, этики, хука и завершённости; не переписывает текст",
        40,
        TASK_MODES,
    ),
    AgentSpec(
        "instagram_editor",
        "Лена Волкова",
        "Редактура Instagram-версии и соответствие формату",
        41,
        TASK_MODES,
    ),
    AgentSpec(
        "offer_architect",
        "Виктор Самойлов",
        "Оффер, ценность, возражения, риск и честный призыв",
        45,
        (COMMERCIAL,),
    ),
    AgentSpec(
        "voice",
        "Даша Козлова",
        "Сохраняет пять правил формы SMM-06, фильтрует содержание и не меняет blueprint",
        25,
        TASK_MODES,
    ),
    AgentSpec(
        "publisher",
        "Света Громова",
        "Технический шлюз длины, разметки и брендовых ограничений",
        60,
        TASK_MODES,
    ),
    AgentSpec(
        "planner",
        "Соня Белова",
        "Контент-план, баланс задач и кампаний",
        70,
        TASK_MODES,
    ),
    AgentSpec(
        "community",
        "Миша Захаров",
        "Комментарии, обратная связь и сигналы аудитории",
        80,
        TASK_MODES,
    ),
    AgentSpec(
        "comment_analyst",
        "Таня Серова",
        "Паттерны языка аудитории и репутационные риски",
        81,
        TASK_MODES,
    ),
    AgentSpec(
        "team_architect",
        "Алекс Громов",
        "Аудит всей цепочки и устранение системных сбоев",
        90,
        TASK_MODES,
    ),
)


NOTEBOOKS = (
    NotebookSpec(
        "smm02a_audience",
        "SMM-02A — Язык аудитории — Joanna Wiebe",
        "audience",
        TASK_MODES,
        ("researcher", "writer"),
        "7355a001-65df-4b77-9c88-8283e8d387ca",
        required_modes=TASK_MODES,
    ),
    NotebookSpec(
        "smm02b_audience_archive",
        "SMM-02B — Язык аудитории — Joanna Wiebe — архив",
        "audience",
        TASK_MODES,
        ("researcher",),
        "6c2de40e-1a42-43c5-b31a-9d35fee7b763",
    ),
    NotebookSpec(
        "smm02c_human_text",
        "SMM-02C — Человеческий текст — Ann Handley",
        "human_text",
        TASK_MODES,
        ("writer", "voice"),
        "231941f1-9d5d-4a5e-8cf2-7749014705df",
    ),
    NotebookSpec(
        "smm03a_angles",
        "SMM-03A — Неожиданные углы — Rory Sutherland",
        "angles",
        TASK_MODES,
        ("strategist", "editor"),
        "b96549af-5e0f-42d7-932e-be302858673b",
        required_modes=TASK_MODES,
    ),
    NotebookSpec(
        "smm03b_dramaturgy",
        "SMM-03B — Драматургия — Nancy Duarte",
        "dramaturgy",
        TASK_MODES,
        ("strategist", "editor"),
        "6832c99c-d0f9-4f25-82d8-adceb080e22f",
        required_modes=TASK_MODES,
    ),
    NotebookSpec(
        "smm03c_short_dramaturgy",
        "SMM-03C — Драматургия Shorts — Nancy Duarte",
        "short_dramaturgy",
        (BRAND, COMMERCIAL),
        ("instagram_writer", "instagram_editor"),
        "90401cd4-8590-428a-a1e9-6e60b0da4f6b",
    ),
    NotebookSpec(
        "smm04_ethics",
        "SMM-04 — Психология влияния и этика — Robert Cialdini",
        "ethics",
        (BRAND, COMMERCIAL),
        ("editor", "offer_architect"),
        "ef84c490-11c3-4b6a-b41a-bde6bd07864f",
        required_modes=(COMMERCIAL,),
    ),
    NotebookSpec(
        "smm05a_positioning",
        "SMM-05A — Личный бренд и позиционирование — Chris Do",
        "positioning",
        (BRAND, COMMERCIAL),
        ("strategist", "marketer", "offer_architect"),
        "00e19391-3b48-4a92-85f9-c04a60f16945",
    ),
    NotebookSpec(
        "smm05b_distribution",
        "SMM-05B — Контент и распространение — GaryVee",
        "distribution",
        (BRAND, COMMERCIAL),
        ("marketer", "planner"),
        "acdad30e-c5d8-4740-8723-bf0070206f6a",
        env_var="NOTEBOOKLM_SMM05B_ID",
    ),
    NotebookSpec(
        "smm06_voice",
        "SMM-06 — Голос Дмитрия",
        "voice",
        TASK_MODES,
        ("voice",),
        "4625852e-4428-4eeb-9902-d2794865d45d",
        required_modes=TASK_MODES,
    ),
    NotebookSpec(
        "hormozi_1",
        "Alex Hormozi 1 — оффер и рост",
        "offer",
        (COMMERCIAL,),
        ("offer_architect", "marketer"),
        "ffaa56e0-22c4-4d28-81e9-652e6454053b",
        required_modes=(COMMERCIAL,),
    ),
    NotebookSpec(
        "hormozi_2",
        "Alex Hormozi 2 — оффер и монетизация",
        "offer",
        (COMMERCIAL,),
        ("offer_architect", "marketer"),
        "5a7bfeb2-6bc3-42e8-8ea9-da690485fb39",
        required_modes=(COMMERCIAL,),
    ),
    NotebookSpec(
        "smm07_brand_architecture",
        "SMM-07 — Архитектура личного бренда — Caleb Ralston",
        "brand_architecture",
        (BRAND, COMMERCIAL),
        ("strategist", "marketer"),
        "a1b5d5b2-e07d-40fd-a6a6-7bff2107eb29",
        env_var="NOTEBOOKLM_SMM07_ID",
    ),
    NotebookSpec(
        "smm08_creator_system",
        "SMM-08 — Система создателя — Creator Science",
        "creator_system",
        (BRAND,),
        ("planner", "marketer"),
        "8a7c00d1-45f6-4138-a296-c98a928f8106",
        env_var="NOTEBOOKLM_SMM08_ID",
    ),
    NotebookSpec(
        "smm09_hooks",
        "SMM-09 — Хуки и удержание внимания — Paddy Galloway / 1of10",
        "hooks",
        TASK_MODES,
        ("hook_editor", "writer", "editor", "instagram_writer"),
        "fad9e5d4-4765-40f6-b7e7-5700dd8a966e",
        env_var="NOTEBOOKLM_SMM09_ID",
        required_modes=TASK_MODES,
    ),
    NotebookSpec(
        "smm10_founder_stories",
        "SMM-10 — Истории основателей — Founders",
        "founder_stories",
        (BRAND, COMMERCIAL),
        ("strategist", "writer"),
        "41fd3c0c-293f-4666-8300-abb1971f9185",
        env_var="NOTEBOOKLM_SMM10_ID",
    ),
    NotebookSpec(
        "smm11_educational_clarity",
        "SMM-11 — Образовательный контент — Ali Abdaal",
        "educational_clarity",
        (EDITORIAL, BRAND),
        ("writer", "editor", "planner"),
        "ea6ff04b-afbf-4780-b2b5-3f6d5f6daf66",
        env_var="NOTEBOOKLM_SMM11_ID",
    ),
    NotebookSpec(
        "smm12_ethical_boundaries",
        "SMM-12 — Этические границы коммуникации — Michael Sandel",
        "ethics",
        TASK_MODES,
        ("editor", "instagram_editor", "offer_architect", "comment_analyst"),
        "d49008c1-61a0-4ab1-99c2-a4a9c06f6c38",
        env_var="NOTEBOOKLM_SMM12_ID",
        required_modes=TASK_MODES,
    ),
)


_COMMERCIAL_PATTERNS = (
    r"\bоффер\w*",
    r"\bпродаж\w*",
    r"\bпродающ\w*",
    r"\bкуп(?:и|ить|лю|ят|ка|ки)\w*",
    r"\bцен[аеуы]\b",
    r"\bстоимост\w*",
    r"\bзапис\w*\s+(?:на|в)",
    r"\bрегистрац\w*",
    r"\bмест\w*\s+(?:остал\w*|в\s+групп\w*|на\s+курс\w*)",
    r"\b(?:открыт\w*|ид[её]т|старт\w*)\s+набор\b",
    r"\bнабор\s+(?:в|на)\s+\w+",
    r"\bлендинг\w*",
    r"\bконверси\w*",
)

_BRAND_PATTERNS = (
    r"\bличн\w*\s+бренд\w*",
    r"\bпозиционирован\w*",
    r"\bэкспертност\w*",
    r"\bузнаваемост\w*",
    r"\bаудитори\w*",
    r"\bконтент[- ]?стратег\w*",
    r"\bпродвижени\w*",
    r"\bохват\w*",
    r"\bворонк\w*",
)


def classify_task(text: str, explicit_mode: str | None = None) -> str:
    """Classify a request conservatively; selling is never inferred loosely."""
    if explicit_mode:
        normalized_mode = explicit_mode.strip().lower()
        if normalized_mode not in TASK_MODES:
            raise ValueError(f"Неизвестный режим: {explicit_mode}")
        return normalized_mode

    normalized = " ".join((text or "").lower().split())
    if any(re.search(pattern, normalized) for pattern in _COMMERCIAL_PATTERNS):
        return COMMERCIAL
    if any(re.search(pattern, normalized) for pattern in _BRAND_PATTERNS):
        return BRAND
    return EDITORIAL


def route_for(text: str, explicit_mode: str | None = None) -> TeamRoute:
    mode = classify_task(text, explicit_mode)
    agents = tuple(
        sorted((agent for agent in AGENTS if mode in agent.modes), key=lambda a: a.stage)
    )
    notebooks = tuple(nb for nb in NOTEBOOKS if mode in nb.modes)
    return TeamRoute(mode=mode, topic=text, agents=agents, notebooks=notebooks)


def notebooks_for_agents(
    route: TeamRoute,
    agent_keys: Iterable[str],
) -> tuple[NotebookSpec, ...]:
    requested = set(agent_keys)
    return tuple(
        notebook
        for notebook in route.configured_notebooks
        if requested.intersection(notebook.agents)
    )


def route_summary(text: str, explicit_mode: str | None = None) -> str:
    route = route_for(text, explicit_mode)
    required = ", ".join(nb.key for nb in route.required_notebooks)
    active_optional_keys = set(DEFAULT_OPTIONAL_NOTEBOOKS[route.mode])
    optional_ready = ", ".join(
        nb.key
        for nb in route.optional_notebooks
        if nb.key in active_optional_keys and nb.resolved_id()
    ) or "нет"
    optional_missing = ", ".join(
        nb.key
        for nb in route.optional_notebooks
        if nb.key in active_optional_keys and not nb.resolved_id()
    ) or "нет"
    # /post is the default workflow shown to the user. Instagram specialists,
    # planning and community roles are available to /pack and other commands,
    # but listing them here made the ordinary Telegram route look as if every
    # agent rewrote the same text.
    telegram_keys = {"strategist", "voice", "writer", "editor"}
    chain = " → ".join(
        agent.name for agent in route.agents if agent.key in telegram_keys
    )
    return (
        f"Режим: {MODE_LABELS[route.mode]}\n"
        f"Рабочая цепочка: {chain}\n"
        f"Обязательные блокноты: {required}\n"
        f"Дополнительные советники этого прогона: {optional_ready}\n"
        f"Ожидают ID: {optional_missing}"
    )


def team_manifest() -> str:
    """Compact machine-readable context for the meta-agent and other systems."""
    agent_lines = [
        f"- {agent.key}: {agent.name}; {agent.responsibility}; "
        f"режимы={','.join(agent.modes)}"
        for agent in sorted(AGENTS, key=lambda item: item.stage)
    ]
    notebook_lines = [
        f"- {nb.key}: {nb.title}; советует={','.join(nb.agents)}; "
        f"режимы={','.join(nb.modes)}; "
        f"состояние={'подключён' if nb.resolved_id() else 'ожидает ID'}"
        for nb in NOTEBOOKS
    ]
    return (
        "ЕДИНЫЙ РЕЕСТР SMM-КОМАНДЫ\n"
        "Режимы: editorial=экспертный/рефлексивный пост без продажи; "
        "brand=позиционирование; commercial=оффер/продажа.\n"
        "Блокноты дают сырьё только назначенным агентам. Нина отвечает за факты, "
        "Артём за угол, Кирилл за хук, Игорь выбирает и ставит правки, Даша только "
        "советует по голосу, Маша один раз собирает финал, Света проверяет технику.\n\n"
        "АГЕНТЫ:\n"
        + "\n".join(agent_lines)
        + "\n\nБЛОКНОТЫ:\n"
        + "\n".join(notebook_lines)
    )


def registry_status() -> str:
    configured = sum(1 for nb in NOTEBOOKS if nb.resolved_id())
    return f"{configured}/{len(NOTEBOOKS)} блокнотов имеют ID; 3 режима маршрутизации"
