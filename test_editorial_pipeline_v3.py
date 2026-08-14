import unittest
from unittest.mock import patch

from agents import telegram_team


TOPIC = (
    "Самое болезненное в отношениях начинается не с расставания. "
    "А с момента, когда ты уже чувствуешь, что тебя не выбирают, "
    "но всё ещё пытаешься стать удобнее, чтобы это изменить"
)


def valid_blueprint(hook: str, thesis: str) -> str:
    return f"""КАРКАС: ГОТОВ
НЕИЗМЕНЯЕМЫЙ ФАКТ ТЕМЫ: {TOPIC}
ФАКТИЧЕСКИЙ КОНТРАКТ: факты исходной темы и один явно художественный пример
СМЫСЛОВОЙ ОБЪЕКТ ТЕМЫ:
Отказ от собственного участия в отношениях.
ОТВЕТ НА ВОПРОС ТЕМЫ:
Различить взаимную заботу и одностороннее исчезновение из отношений.
ОБЕЩАНИЕ ЧИТАТЕЛЮ:
Показать разницу между заботой об отношениях и отказом от собственного участия.
ТЕЗИС:
{thesis}
ЭКСПЕРТНАЯ ОПОРА:
- язык и ясность: назвать наблюдаемое без диагноза
- смысловой поворот: удобство не равно самоотмене
- драматургия: от привычного объяснения к точному различению
- этическая граница: не читать намерения другого человека
ХУК:
{hook}
ЕДИНСТВЕННАЯ МИКРОСЦЕНА И ЕЁ ФУНКЦИЯ:
Одна условная сцена показывает центральный выбор, но ничего не доказывает.
ЛОГИКА:
1. Желание сохранить близость само по себе понятно.
2. Постоянное согласие убирает возможность узнать позицию человека.
3. Честное присутствие не гарантирует исход, но возвращает отношениям реальность.
КОНТРПРИМЕР ИЛИ ГРАНИЦА:
Гибкость и забота могут быть зрелым выбором, если собственная позиция не исчезает.
ФИНАЛЬНОЕ РАЗЛИЧЕНИЕ:
Одно наблюдение не доказывает состояние отношений; важен доступный человеку выбор.
ФИНАЛ:
Вопрос не в количестве уступок, а в том, остаётся ли в них собственный выбор.
ЗАПРЕЩЕНО В ТЕКСТЕ:
Диагноз, товарная логика, искусственный дефицит, ложный реальный кейс."""


class EditorialPipelineV3Tests(unittest.TestCase):
    def test_simple_pipeline_prompts_have_one_authoritative_copy_pass(self):
        self.assertIn("один цельный черновик", telegram_team.SIMPLE_DRAFT_PROMPT)
        self.assertIn("главный мастер-копирайтер", telegram_team.JOANNA_MASTER_PROMPT)
        self.assertIn("SMM-06", telegram_team.DMITRY_VOICE_PASS_PROMPT)
        self.assertNotIn("blueprint", telegram_team.SIMPLE_DRAFT_PROMPT.lower())
        self.assertNotIn("этическ", telegram_team.SIMPLE_DRAFT_PROMPT.lower())

    def test_one_pass_prompt_assigns_bounded_roles_and_single_author(self):
        prompt = telegram_team.ONE_PASS_EDITORIAL_PROMPT
        self.assertIn("единственный автор", prompt)
        self.assertIn("SMM-06 даёт один экспертный тезис", prompt)
        self.assertIn("Paddy Galloway предлагает три входа", prompt)
        self.assertIn("Ann Handley даёт только правила живого языка", prompt)
        self.assertIn("Смысловой preflight обязателен", prompt)
        self.assertIn("Архитектурный preflight обязателен", prompt)
        self.assertIn("Напиши текст один раз", prompt)
        self.assertNotIn("blueprint", prompt.lower())

    def test_one_pass_prompt_blocks_copywriting_showmanship(self):
        prompt = telegram_team.ONE_PASS_EDITORIAL_PROMPT
        self.assertIn("Не подменяй точность эффектной фразой", prompt)
        self.assertIn("ложные развилки", prompt)
        self.assertIn("крайними примерами", prompt)
        self.assertIn("Не добавляй вторую трактовку автоматически", prompt)
        self.assertIn("HYPOTHESIS", prompt)
        self.assertIn("OBSERVATION", prompt)
        self.assertIn("Не выдумывай сцены, случаи клиентов", prompt)

    @patch("agents.telegram_team.gemini_call")
    def test_message_map_is_built_before_blueprint_without_invented_voc(self, call):
        call.return_value = """КАРТА СООБЩЕНИЯ: ГОТОВА
ДАННЫЕ АУДИТОРИИ: прямых данных нет
НАБЛЮДАЕМЫЙ КОНФЛИКТ: простая просьба стала трудной
ОБЕЩАНИЕ ЧИТАТЕЛЮ: различить просьбу и проверку отношений
НОВОЕ РАЗЛИЧЕНИЕ: трудность просьбы не доказывает одну причину
ХУК 1: Первый хук
ХУК 2: Второй хук
ХУК 3: Третий хук
НЕ ДОКАЗЫВАТЬ: скрытый мотив"""

        message_map = telegram_team.build_message_map(
            "Почему стало трудно попросить о простом?",
            "Метод Joanna Wiebe",
            "test-key",
        )

        self.assertIn("КАРТА СООБЩЕНИЯ: ГОТОВА", message_map)
        system_prompt = call.call_args.args[2]
        user_prompt = call.call_args.args[3]
        self.assertIn("не являются реальной речью\nаудитории", system_prompt)
        self.assertIn("не используй агрессивный PAS", system_prompt)
        self.assertIn("Нет данных для этой темы", user_prompt)
        self.assertIn("Метод Joanna Wiebe", user_prompt)

    @patch("agents.telegram_team.gemini_call")
    def test_message_map_rejects_missing_contract_fields(self, call):
        call.return_value = "ОБЕЩАНИЕ ЧИТАТЕЛЮ: что-то полезное"

        with self.assertRaisesRegex(ValueError, "неполную карту сообщения"):
            telegram_team.build_message_map(
                "Тестовая тема",
                "Метод Joanna Wiebe",
                "test-key",
            )

    @patch("agents.telegram_team._reasoning_call")
    def test_blueprint_receives_message_map_as_separate_input(self, call):
        call.return_value = valid_blueprint(
            "Новый хук.",
            "Наблюдаемое различие.",
        )

        telegram_team.build_editorial_blueprint(
            TOPIC,
            "Решения Рори и Нэнси",
            "test-key",
            message_map="КАРТА СООБЩЕНИЯ: ГОТОВА\nОБЕЩАНИЕ: ясный ответ",
        )

        user_prompt = call.call_args.args[3]
        self.assertIn("КАРТА СООБЩЕНИЯ JOANNA WIEBE", user_prompt)
        self.assertIn("ОБЕЩАНИЕ: ясный ответ", user_prompt)
        self.assertIn("Решения Рори и Нэнси", user_prompt)

    @patch("agents.telegram_team.gemini_call")
    def test_ann_human_edit_cannot_change_blueprint(self, call):
        call.return_value = "Живой готовый текст."

        result = telegram_team.human_edit_editorial_post(
            TOPIC,
            valid_blueprint("Новый хук.", "Наблюдаемое различие."),
            "Лекционный черновик.",
            "Метод Ann Handley",
            "Голос Дмитрия",
            "test-key",
        )

        self.assertEqual("Живой готовый текст.", result)
        system_prompt = call.call_args.args[2]
        user_prompt = call.call_args.args[3]
        self.assertIn("Не меняй blueprint", system_prompt)
        self.assertIn("перестрой её в косвенную речь", system_prompt)
        self.assertIn("не имеет права улучшать смысл", system_prompt)
        self.assertIn("Метод Ann Handley", user_prompt)
        self.assertIn("Голос Дмитрия", user_prompt)

    @patch("agents.telegram_team._reasoning_call")
    def test_single_repair_keeps_ann_boundaries(self, call):
        call.return_value = "Исправленный живой текст."

        result = telegram_team.repair_editorial_post(
            TOPIC,
            valid_blueprint("Новый хук.", "Наблюдаемое различие."),
            "Исходный живой текст.",
            "Исправить только грамматику.",
            "Голос Дмитрия.",
            "test-key",
            ["исправь грамматику"],
            "Ann просит убрать лекционный тон.",
        )

        self.assertEqual("Исправленный живой текст.", result)
        user_prompt = call.call_args.args[3]
        self.assertIn("ГРАНИЦЫ ЖИВОЙ РЕДАКТУРЫ ANN HANDLEY", user_prompt)
        self.assertIn("Ann просит убрать лекционный тон", user_prompt)

    def test_reasoning_call_falls_back_when_pro_returns_only_thoughts(self):
        with patch(
            "agents.telegram_team.gemini_call",
            side_effect=[
                ValueError("Gemini вернул пустой ответ"),
                "готовый текст",
            ],
        ) as mocked:
            result = telegram_team._reasoning_call(
                "key",
                "gemini-2.5-pro",
                "system",
                "user",
                max_tokens=7200,
                temperature=0.2,
            )

        self.assertEqual("готовый текст", result)
        self.assertEqual("gemini-2.5-pro", mocked.call_args_list[0].args[1])
        self.assertEqual(telegram_team.MODEL, mocked.call_args_list[1].args[1])
        self.assertFalse(mocked.call_args_list[1].kwargs["disable_thinking"])

    def test_reasoning_call_falls_back_when_pro_stays_overloaded(self):
        with patch(
            "agents.telegram_team.gemini_call",
            side_effect=[
                RuntimeError("503 UNAVAILABLE: model is experiencing high demand"),
                "готовый текст через резервную модель",
            ],
        ) as mocked:
            result = telegram_team._reasoning_call(
                "key",
                "gemini-2.5-pro",
                "system",
                "user",
                max_tokens=7200,
                temperature=0.2,
            )

        self.assertEqual("готовый текст через резервную модель", result)
        self.assertEqual("gemini-2.5-pro", mocked.call_args_list[0].args[1])
        self.assertEqual(telegram_team.MODEL, mocked.call_args_list[1].args[1])

    def test_reasoning_call_does_not_hide_invalid_request(self):
        with patch(
            "agents.telegram_team.gemini_call",
            side_effect=RuntimeError("400 INVALID_ARGUMENT"),
        ) as mocked:
            with self.assertRaisesRegex(RuntimeError, "INVALID_ARGUMENT"):
                telegram_team._reasoning_call(
                    "key",
                    "gemini-2.5-pro",
                    "system",
                    "user",
                    max_tokens=7200,
                    temperature=0.2,
                )

        self.assertEqual(1, mocked.call_count)

    def test_blueprint_fidelity_audit_accepts_grounded_carкас(self):
        with patch(
            "agents.telegram_team._reasoning_call",
            return_value="КАРКАС: ПРИНЯТ",
        ):
            issues = telegram_team.audit_blueprint_fidelity(
                TOPIC,
                valid_blueprint("Новый хук.", "Наблюдаемое различие."),
                "key",
            )

        self.assertEqual([], issues)

    def test_blueprint_fidelity_audit_blocks_fiction_presented_as_fact(self):
        with patch(
            "agents.telegram_team._reasoning_call",
            return_value=(
                "КАРКАС: ИСПРАВИТЬ\n"
                "- Художественная сцена выдана за реальный клиентский случай.\n"
                "- Переживание персонажа объявлено универсальным психологическим законом."
            ),
        ):
            issues = telegram_team.audit_blueprint_fidelity(
                TOPIC,
                valid_blueprint("Новый хук.", "Наблюдаемое различие."),
                "key",
            )

        self.assertEqual(2, len(issues))
        self.assertTrue(all("семантический аудит" in issue for issue in issues))
        self.assertEqual(
            issues,
            telegram_team.blueprint_publication_blockers(issues),
        )

    def test_blueprint_fidelity_prompt_allows_one_fictional_micro_scene(self):
        with patch(
            "agents.telegram_team._reasoning_call",
            return_value="КАРКАС: ПРИНЯТ",
        ) as mocked:
            issues = telegram_team.audit_blueprint_fidelity(
                TOPIC,
                valid_blueprint("Новый хук.", "Наблюдаемое различие."),
                "key",
            )

        self.assertEqual([], issues)
        prompt = mocked.call_args.args[2]
        self.assertIn(
            "Свежий смысловой угол и один вымышленный пример разрешены",
            prompt,
        )

    def test_blueprint_rejects_relationship_commodity_logic(self):
        blueprint = valid_blueprint(
            "Чем доступнее человек, тем меньше его выбирают.",
            "Чтобы вернуть ценность, нужно создать дефицит внимания.",
        )

        issues = telegram_team.blueprint_contract_issues(TOPIC, blueprint)

        self.assertTrue(
            any("товарную логику" in issue for issue in issues),
            issues,
        )

    def test_blueprint_allows_price_of_a_choice_as_non_market_metaphor(self):
        blueprint = valid_blueprint(
            "Уступка может сохранить тишину, но не обязательно диалог.",
            "Ценой такого подхода иногда становится отсутствие ясности "
            "о собственной позиции.",
        )

        issues = telegram_team.blueprint_contract_issues(TOPIC, blueprint)

        self.assertFalse(
            any("товарную логику" in issue for issue in issues),
            issues,
        )

    def test_blueprint_answers_means_question_with_explicit_uncertainty(self):
        topic = (
            "После честного разговора стало тяжелее. Означает ли это, "
            "что разговор был ошибкой?"
        )
        unsafe = valid_blueprint(
            "После разговора стало тяжелее.",
            "Тяжесть показывает, что близость требует времени.",
        ).replace(TOPIC, topic).replace(
            "Различить взаимную заботу и одностороннее исчезновение из отношений.",
            "Тяжесть означает, что разговор открыл важную правду.",
        )
        safe = unsafe.replace(
            "Тяжесть означает, что разговор открыл важную правду.",
            "Не обязательно: сама тяжесть не доказывает, что разговор был ошибкой.",
        )

        unsafe_issues = telegram_team.blueprint_contract_issues(topic, unsafe)
        safe_issues = telegram_team.blueprint_contract_issues(topic, safe)

        self.assertTrue(any("не отвечает честно" in issue for issue in unsafe_issues))
        self.assertFalse(any("не отвечает честно" in issue for issue in safe_issues))

    def test_blueprint_rejects_binary_final_relationship_verdict(self):
        blueprint = valid_blueprint(
            "Разговор не всегда приносит облегчение.",
            "Тяжесть сама по себе не доказывает ошибку.",
        ).replace(
            "Одно наблюдение не доказывает состояние отношений; важен доступный человеку выбор.",
            "После разговора рядом либо союзник, либо чужой человек.",
        )

        issues = telegram_team.blueprint_contract_issues(TOPIC, blueprint)

        self.assertTrue(any("ложной бинарностью" in issue for issue in issues), issues)

    def test_blueprint_rejects_gesture_as_proof_of_contact(self):
        blueprint = valid_blueprint(
            "После разговора остаётся тишина.",
            "Один жест не доказывает состояние отношений.",
        ).replace(
            "Одна условная сцена показывает центральный выбор, но ничего не доказывает.",
            "Кивок подтверждает, что между людьми сохранился контакт.",
        )

        issues = telegram_team.blueprint_contract_issues(TOPIC, blueprint)

        self.assertTrue(any("доказательство отношений" in issue for issue in issues), issues)

    def test_contract_rejects_binary_final_relationship_verdict(self):
        text = """После честного разговора может стать тяжелее. Само это чувство не доказывает, что разговор был ошибкой.

Иногда требуется время, чтобы понять услышанное. Иногда трудность связана с формой разговора или его содержанием.

Одна возможная сцена ничего не доказывает. Люди могут замолчать, а затем вернуться к разговору позже.

Значение имеют безопасность разговора, возможность отвечать и последующие действия. Одного ощущения для вывода недостаточно.

Главное понять, рядом с тобой союзник или чужой человек."""

        issues = telegram_team.editorial_contract_issues(TOPIC, text)

        self.assertTrue(any("ложную бинарность" in issue for issue in issues), issues)

    def test_quality_rejects_chain_of_metaphor_families(self):
        text = (
            "Правда работает как обезболивающее и выносит проблему на свет. "
            "Потом начинается новый путь, а между людьми растёт пропасть."
        )

        warnings = telegram_team.quality_warnings(text)

        self.assertTrue(any("цепочку метафор" in item for item in warnings), warnings)

    def test_blueprint_rejects_human_value_tied_to_availability(self):
        blueprint = valid_blueprint(
            "Чем недоступнее человек, тем сильнее его выбирают.",
            "Доступность снижает ценность человека, поэтому нужно отдалиться.",
        )

        issues = telegram_team.blueprint_contract_issues(TOPIC, blueprint)

        self.assertTrue(
            any("товарную логику" in issue for issue in issues),
            issues,
        )

    def test_blueprint_rejects_copied_topic_as_hook(self):
        blueprint = valid_blueprint(
            TOPIC,
            "Постоянная уступчивость может скрыть собственную позицию.",
        )

        issues = telegram_team.blueprint_contract_issues(TOPIC, blueprint)

        self.assertIn(
            "blueprint копирует исходную тему вместо нового хука",
            issues,
        )

    def test_blueprint_rejects_unsupported_psychological_mechanism(self):
        blueprint = valid_blueprint(
            "Удобство иногда выглядит как близость, пока не исчезает несогласие.",
            "Мозг запускает защитный механизм и заставляет человека "
            "минимизировать будущую вину.",
        )

        issues = telegram_team.blueprint_contract_issues(TOPIC, blueprint)

        self.assertIn(
            "blueprint подменяет наблюдение недоказанным психологическим механизмом",
            issues,
        )

    def test_blueprint_allows_rejected_motive_named_only_as_boundary(self):
        blueprint = valid_blueprint(
            "Удобство иногда выглядит как близость, пока не исчезает несогласие.",
            "Постоянное согласие может скрыть собственную позицию.",
        ).replace(
            "Гибкость и забота могут быть зрелым выбором, если собственная позиция не исчезает.",
            "Нельзя считать, что такая уступчивость обязательно продиктована тревогой.",
        )

        issues = telegram_team.blueprint_contract_issues(TOPIC, blueprint)

        self.assertFalse(
            any("скрытый мотив" in issue for issue in issues),
            issues,
        )

    def test_blueprint_rejects_hidden_motive_inside_thesis(self):
        blueprint = valid_blueprint(
            "Удобство иногда выглядит как близость, пока не исчезает несогласие.",
            "Постоянная уступчивость продиктована тревогой потерять отношения.",
        )

        issues = telegram_team.blueprint_contract_issues(TOPIC, blueprint)

        self.assertTrue(
            any("скрытый мотив" in issue for issue in issues),
            issues,
        )

    def test_soft_blueprint_issue_becomes_caution_instead_of_blocker(self):
        issues = [
            "blueprint приписывает человеку скрытый мотив, вину, тревогу или оправдание"
        ]

        self.assertEqual(
            [],
            telegram_team.blueprint_publication_blockers(issues),
        )
        cautioned = telegram_team.add_blueprint_cautions(
            valid_blueprint("Новый хук.", "Наблюдаемое различие."),
            issues,
        )
        self.assertIn("ПРОГРАММНАЯ ОГОВОРКА К КАРКАСУ", cautioned)
        self.assertIn(issues[0], cautioned)

    def test_gesture_interpretation_cannot_stop_writer_after_repair(self):
        issues = [
            "blueprint превращает жест или предмет сцены в доказательство отношений"
        ]

        self.assertEqual([], telegram_team.blueprint_publication_blockers(issues))
        cautioned = telegram_team.add_blueprint_cautions(
            valid_blueprint("Новый хук.", "Наблюдаемое различие."),
            issues,
        )
        self.assertIn("не использовать жест или предмет как доказательство", cautioned)

    def test_unsafe_relationship_blueprint_remains_blocking(self):
        issues = [
            "blueprint переносит товарную логику или искусственный дефицит на отношения"
        ]

        self.assertEqual(
            issues,
            telegram_team.blueprint_publication_blockers(issues),
        )

    def test_program_replaces_model_written_blueprint_guardrails(self):
        blueprint = valid_blueprint(
            "Удобство иногда выглядит как близость, пока не исчезает несогласие.",
            "Постоянное согласие не позволяет увидеть позицию человека.",
        ).replace(
            "- этическая граница: не читать намерения другого человека",
            "- этическая граница: товар, дефицит, цена и инвестиции",
        )

        finalized = telegram_team._finalize_blueprint(blueprint, TOPIC)
        semantic = finalized.split("ЗАПРЕЩЕНО В ТЕКСТЕ:", 1)[0]

        self.assertNotIn("товар, дефицит", semantic)
        self.assertIn(
            "не приписывать партнёру мотивы и отделять наблюдаемое от вывода",
            semantic,
        )
        self.assertEqual(1, finalized.count("ЗАПРЕЩЕНО В ТЕКСТЕ:"))
        self.assertIn(
            f"НЕИЗМЕНЯЕМЫЙ ФАКТ ТЕМЫ: {TOPIC}",
            finalized,
        )

    def test_program_overwrites_model_written_topic_invariant(self):
        blueprint = valid_blueprint(
            "Новый хук.",
            "Наблюдаемое различие.",
        ).replace(
            f"НЕИЗМЕНЯЕМЫЙ ФАКТ ТЕМЫ: {TOPIC}",
            "НЕИЗМЕНЯЕМЫЙ ФАКТ ТЕМЫ: Соседняя тема о комфортной тишине",
        )

        finalized = telegram_team._finalize_blueprint(blueprint, TOPIC)

        self.assertIn(
            f"НЕИЗМЕНЯЕМЫЙ ФАКТ ТЕМЫ: {TOPIC}",
            finalized,
        )
        self.assertNotIn("Соседняя тема", finalized)

    def test_contract_catches_real_rejected_generation(self):
        rejected = f"""{TOPIC}.

Ты перечитывал своё сообщение и отправил его снова. Вы всегда доступны.
Представьте редкую книгу или украшение. Когда товар лежит без дефицита,
в него нет необходимости вкладываться.

Чтобы снова стать тем, кого выбирают."""

        issues = telegram_team.editorial_contract_issues(TOPIC, rejected)

        self.assertTrue(any("исходную тему" in issue for issue in issues), issues)
        self.assertTrue(any("не смешивай" in issue for issue in issues), issues)
        self.assertFalse(any("выдуманное событие" in issue for issue in issues), issues)
        self.assertTrue(any("товаром" in issue for issue in issues), issues)
        self.assertTrue(any("главным" in issue for issue in issues), issues)

    def test_contract_rejects_gendered_reader_role(self):
        text = (
            "Иногда желание сохранить отношения постепенно убирает из них "
            "собственную позицию. " * 10
            + "Ты раньше отстаивала своё, а теперь всё чаще соглашаешься."
        )

        issues = telegram_team.editorial_contract_issues(TOPIC, text)

        self.assertIn(
            "убери женскую форму из обращения к смешанной аудитории",
            issues,
        )

    def test_contract_rejects_scene_that_needs_topic_as_heading(self):
        topic = (
            "Как отличить внутреннюю свободу от привычки заранее "
            "отказываться от своих желаний"
        )
        text = """Палец замирает над кнопкой отправить. В сообщении осталось робкое предложение сходить куда-то вместе.

Со стороны это может выглядеть как сила и самодостаточность. Но иногда отказ от желания лишь сохраняет привычный порядок и не создаёт нового выбора.

Разница становится заметна по результату. Свободное решение оставляет ясность, а автоматический отказ не позволяет даже проверить возможность.

Важно не назначать единственную причину такого поведения. Один эпизод ничего не доказывает и требует честного наблюдения.

В конкретной ситуации полезно спросить: это решение действительно выражает моё желание или заранее отменяет его?"""

        issues = telegram_team.editorial_contract_issues(topic, text)

        self.assertTrue(
            any("самостоятельный смысловой хук" in issue for issue in issues),
            issues,
        )

    def test_contract_accepts_semantically_framed_opening_before_scene(self):
        topic = (
            "Как отличить внутреннюю свободу от привычки заранее "
            "отказываться от своих желаний"
        )
        text = """Отказ от собственного желания не всегда означает свободу. Иногда он лишь не даёт проверить, чего человеку действительно хочется.

Палец замирает над кнопкой отправить. В сообщении осталось предложение сходить куда-то вместе, но через секунду текст исчезает.

Смысл не в том, чтобы обязательно отправить сообщение. Важно заметить, было ли решение принято после выбора или появилось ещё до него.

Один такой эпизод не доказывает скрытую причину и ничего не говорит обо всех отношениях. Он только даёт материал для честной проверки.

Свобода оставляет контакт с желанием, даже когда ответом становится нет. Привычный отказ не позволяет желанию прозвучать."""

        issues = telegram_team.editorial_contract_issues(topic, text)

        self.assertFalse(
            any("самостоятельный смысловой хук" in issue for issue in issues),
            issues,
        )

    def test_contract_rejects_reader_partner_perspective_switch(self):
        topic = "Как отличить свободу от привычки заранее отказываться от желаний"
        text = """Отказ от желания не всегда означает свободу. Иногда человек просто не позволяет просьбе прозвучать.

Близкий человек говорит, что ему ничего не нужно. А ты помнишь, как раньше он хотел многого и легко просил о важном.

Один эпизод ничего не доказывает. Различие видно не по силе желания, а по тому, остаётся ли сама возможность его назвать.

Свободный отказ появляется после выбора. Автоматический отказ отменяет выбор заранее, хотя причина может быть разной.

Полезно не назначать человеку скрытый мотив, а заметить доступные варианты. Так наблюдение остаётся честным и не становится диагнозом."""

        issues = telegram_team.editorial_contract_issues(topic, text)

        self.assertTrue(any("нейтральный пол" in issue for issue in issues), issues)
        self.assertTrue(any("не смешивай перспективы" in issue for issue in issues), issues)

    def test_contract_rejects_stock_door_metaphor_in_final(self):
        topic = "Как отличить свободу от привычки заранее отказываться от желаний"
        text = """Отказ от собственного желания не всегда означает свободу. Иногда он не позволяет даже проверить возможный выбор.

В сообщении остаётся предложение сходить куда-то вместе, но через секунду текст исчезает. Это возможная сцена, а не универсальное объяснение.

Смысл не в обязательной отправке сообщения. Значение имеет доступность обоих решений после честной проверки желания.

Один эпизод не доказывает скрытую причину. Он лишь помогает отделить решение от автоматического отказа.

Ответ показывает, открыта ли ещё дверь к собственным желаниям или она уже заперта."""

        issues = telegram_team.editorial_contract_issues(topic, text)

        self.assertTrue(any("метафору двери" in issue for issue in issues), issues)

    def test_contract_preserves_required_hyphen(self):
        text = ("Свобода и привычный отказ выглядят по разному. " * 18).strip()

        issues = telegram_team.editorial_contract_issues(TOPIC, text)

        self.assertIn("сохрани обязательный дефис в слове «по-разному»", issues)

    def test_gender_form_is_eligible_for_one_technical_cleanup(self):
        self.assertTrue(
            telegram_team.only_technical_surface_blockers(
                ["убери мужскую форму из обращения к смешанной аудитории"]
            )
        )
        self.assertFalse(
            telegram_team.only_technical_surface_blockers(
                ["не приписывай человеку мотив сохранять образ или роль сильного"]
            )
        )

    @patch("agents.telegram_team.gemini_call")
    def test_technical_cleanup_cannot_change_meaning(self, call):
        call.return_value = "Нейтрально исправленный пост."

        result = telegram_team.technical_surface_cleanup(
            TOPIC,
            "Ты решил попросить о помощи.",
            ["убери мужскую форму из обращения к смешанной аудитории"],
            "test-key",
        )

        self.assertEqual("Нейтрально исправленный пост.", result)
        system_prompt = call.call_args.args[2]
        self.assertIn("Запрещено менять хук", system_prompt)
        self.assertIn("Нейтрализуй род", system_prompt)

    def test_contract_rejects_assigned_strong_person_motive_and_reader_thought(self):
        topic = "Как отличить самостоятельность от привычки не просить поддержку"
        text = """Самостоятельность не требует всегда справляться в одиночку. Иногда просьба помогает увидеть доступные варианты.

Так проще сохранить образ сильного человека и не просить о помощи. Ты думаешь, что оберегаешь близкого от своих трудностей.

Возможная сцена проста. Человек собирает шкаф и прямо отвечает на предложение помочь, не превращая эпизод в доказательство общей причины.

Один ответ ничего не говорит обо всех отношениях. Он только показывает, было ли решение принято после выбора.

Самостоятельность допускает и помощь, и отказ от неё. Привычка заранее оставляет только один вариант."""

        issues = telegram_team.editorial_contract_issues(topic, text)

        self.assertTrue(any("образ или роль сильного" in issue for issue in issues), issues)
        self.assertTrue(any("мысль или объяснение" in issue for issue in issues), issues)

    @patch("agents.telegram_team._reasoning_call")
    def test_audit_receives_message_map_and_ann_notes(self, call):
        call.return_value = "АУДИТ: ПРИНЯТО"

        telegram_team.audit_editorial_post(
            TOPIC,
            valid_blueprint("Ясный хук.", "Наблюдаемое различие."),
            "Готовый текст.",
            "Этическая граница.",
            "test-key",
            [],
            "СТАТУС ДАННЫХ: НЕТ ПРЯМЫХ ДАННЫХ",
            "ГДЕ ЗВУЧИТ КАК ЛЕКЦИЯ: второй абзац",
        )

        system_prompt = call.call_args.args[2]
        user_prompt = call.call_args.args[3]
        self.assertIn("Blueprint не является доказательством", system_prompt)
        self.assertIn("СТАТУС ДАННЫХ: НЕТ ПРЯМЫХ ДАННЫХ", user_prompt)
        self.assertIn("ГДЕ ЗВУЧИТ КАК ЛЕКЦИЯ", user_prompt)

    def test_voice_brief_preserves_safe_smm06_settings(self):
        raw = """1. ритм: длинная фраза, затем короткая точка
2. синтаксис: сначала наблюдение, затем спокойное уточнение
3. лексика: заметить, сказать прямо, остановиться
4. дистанция: тепло, но без назидания
5. финал: закончить конкретным различием
НЕ ИМИТИРОВАТЬ: канцелярит"""

        brief = telegram_team._finalize_voice_brief(raw)

        self.assertIn("длинная фраза, затем короткая точка", brief)
        self.assertIn("сначала наблюдение", brief)
        self.assertIn("заметить, сказать прямо, остановиться", brief)
        self.assertIn("тепло, но без назидания", brief)
        self.assertIn("конкретным различием", brief)
        self.assertIn("канцелярит", brief)
        self.assertIn("два–пять естественных обращений на «ты»", brief)
        self.assertIn("без «вы»", brief)
        self.assertIn("финальное различие", brief)

    def test_distinct_safe_voice_briefs_do_not_collapse_to_one_template(self):
        first = telegram_team._finalize_voice_brief(
            "1. плавный ритм с редким коротким акцентом\n"
            "2. переход через конкретное наблюдение\n"
            "3. простые бытовые глаголы\n"
            "4. спокойная близкая дистанция\n"
            "5. тихое ясное различение"
        )
        second = telegram_team._finalize_voice_brief(
            "1. плотные фразы средней длины\n"
            "2. переход через прямой вопрос\n"
            "3. точные разговорные глаголы\n"
            "4. сдержанная взрослая дистанция\n"
            "5. короткий завершённый вывод"
        )

        self.assertNotEqual(first, second)
        self.assertIn("плавный ритм", first)
        self.assertIn("плотные фразы", second)

    def test_voice_brief_removes_content_leak_and_keeps_safe_clause(self):
        raw = """1. разговорные фразы средней длины; отношения разрушаются из-за скрытой тревоги
2. переход через наблюдаемое действие
3. использовать слова башка, заметить и сказать
4. рассказывать про тантру, терапию и клиентов
5. закончить ясным различием"""

        brief = telegram_team._finalize_voice_brief(raw)
        lowered = brief.casefold()

        self.assertIn("разговорные фразы средней длины", brief)
        self.assertIn("заметить и сказать", brief)
        self.assertNotRegex(
            lowered,
            r"\b(?:башк|блин|головастик|тантр|терап|сомат|клиент)\w*",
        )
        self.assertIn(
            "4. дистанция с читателем: тёплое прямое общение без назидания",
            brief,
        )

    def test_voice_brief_rejects_conflicting_address_and_abrupt_ending(self):
        raw = """1. коротко
2. просто
3. обращайся через вас и ваши чувства
4. прямое обращение на ты в каждом абзаце
5. оставляй финал открытым и заканчивай многоточием"""

        brief = telegram_team._finalize_voice_brief(raw)

        self.assertIn("полные фразы средней длины", brief)
        self.assertIn("без цепочек обрывков", brief)
        self.assertIn("два–пять естественных обращений на «ты»", brief)
        self.assertIn("без «вы»", brief)
        self.assertIn("последняя фраза должна быть завершённой", brief)
        self.assertNotIn("вас и ваши", brief)
        self.assertNotIn("каждом абзаце", brief.splitlines()[3])
        self.assertNotIn("финал открытым", brief)
        self.assertNotIn("многоточием", brief)

    def test_voice_brief_removes_biography_and_adjacent_source_topics(self):
        raw = """1. после десяти лет жизни в Швеции говорить спокойнее
2. упоминать бывшую жену и детей
3. использовать телесную и эзотерическую лексику через медитацию
4. сохранять тёплую взрослую дистанцию
5. заканчивать ясным конкретным различием"""

        brief = telegram_team._finalize_voice_brief(raw)
        lowered = brief.casefold()

        self.assertNotRegex(
            lowered,
            r"\b(?:швец|бывш\w*\s+жен|дет(?:и|ей)|телесн|эзотер|медитац)\w*",
        )
        self.assertIn("4. сохранять тёплую взрослую дистанцию", brief)
        self.assertIn("5. заканчивать ясным конкретным различием", brief)

    @patch("agents.telegram_team.gemini_call")
    def test_build_voice_brief_is_sanitized_but_not_generic(self, call):
        call.return_value = """1. чередовать спокойную длинную фразу с коротким акцентом
2. переходить через наблюдаемое действие
3. использовать слова башка, заметить и сказать
4. обращаться тепло и без назидания
5. закончить ясным различием"""

        brief = telegram_team.build_voice_brief(
            "Тестовая тема",
            "Сырая речь о тантре, терапии и клиентах",
            "test-key",
        )

        self.assertIn("спокойную длинную фразу", brief)
        self.assertIn("наблюдаемое действие", brief)
        self.assertIn("заметить и сказать", brief)
        self.assertNotRegex(
            brief.casefold(),
            r"\b(?:башк|тантр|терап|клиент)\w*",
        )
        self.assertIn("без «вы»", brief)
        self.assertIn("финальное различие", brief)

    def test_contract_accepts_bounded_human_post(self):
        text = """Иногда человек так старается сохранить отношения, что постепенно
убирает из них собственную позицию.

Сначала это почти незаметно. Один раз проще согласиться. В другой раз не хочется
начинать тяжёлый разговор. Затем привычным становится ответ, который не отражает
ни желания, ни несогласия.

Само по себе умение уступать здесь ни при чём. Гибкость может быть зрелым
выбором. Разница появляется в другом: остаётся ли возможность сказать, чего
хочется, и выдержать ответ другого человека.

Удобство не способно заставить кого-либо любить или разлюбить. Оно также не
доказывает, что близость закончилась. Но постоянное отсутствие собственной
позиции лишает отношения важной информации. Другой человек встречается уже не
с живым выбором, а только с согласием.

Вернуть эту информацию можно без игр в холодность. Иногда достаточно заметить,
где согласие было свободным, а где стало единственным разрешённым ответом.

Количество уступок ничего не решает само по себе. Важнее, остаётся ли в каждой
из них человек, который действительно выбирает."""

        issues = telegram_team.editorial_contract_issues(TOPIC, text)

        self.assertEqual([], issues)

    def test_publication_gate_does_not_discard_post_for_direct_address_count(self):
        text = """Иногда попытка сохранить отношения превращается в постоянную
подстройку. Ты всё чаще выбираешь удобный ответ. Тебе проще промолчать, твои
желания откладываются, а твоё несогласие кажется лишним. Твой выбор сужается.

Само по себе умение уступать здесь ни при чём. Гибкость может быть зрелым
выбором. Разница появляется там, где у тебя остаётся возможность сказать,
чего хочется, и выдержать ответ другого человека.

Удобство не способно заставить кого-либо любить или разлюбить. Но постоянное
отсутствие собственной позиции лишает отношения важной информации. Другой
человек встречается уже не с живым выбором, а только с согласием.

Количество уступок ничего не решает само по себе. Важнее, остаётся ли в каждой
из них человек, который действительно выбирает."""

        issues = telegram_team.editorial_contract_issues(TOPIC, text)
        blockers = telegram_team.editorial_publication_blockers(TOPIC, text)

        self.assertTrue(any("пяти" in issue for issue in issues), issues)
        self.assertFalse(any("пяти" in issue for issue in blockers), blockers)

    def test_publication_gate_keeps_relationship_commodity_logic_blocking(self):
        text = """Иногда попытка сохранить отношения превращается в подстройку.
Собственная позиция постепенно исчезает, а согласие становится единственным
ответом. Это может выглядеть как гибкость, хотя выбора уже почти не остаётся.

Человеческая ценность здесь устроена как цена товара. Нужно создать дефицит,
чтобы партнёр снова начал вкладываться и выбирать. Доступность снижает цену,
поэтому холодность возвращает интерес.

Такой способ предлагает управлять вниманием другого человека, а не говорить о
том, что происходит между людьми. В результате близость подменяется расчётом,
а отношения становятся способом доказать собственную ценность."""

        blockers = telegram_team.editorial_publication_blockers(TOPIC, text)

        self.assertTrue(any("товаром" in issue for issue in blockers), blockers)

    def test_contract_catches_defects_from_latest_real_generation(self):
        text = """В какой момент забота о другом превращается в отказ от себя?
Эта граница часто стирается незаметно, когда в отношениях появляется холод.

Когда возникает ощущение, что тебя больше не выбирают, первая мысль в башке —
нужно срочно что-то исправить. Стать лучше, понятнее, удобнее. Это кажется
логичным способом удержать связь.

Но есть огромная разница между компромиссом ради двоих и односторонними
уступками, в которых один человек постепенно исчезает.

Забота — это усилие для контакта, даже если оно требует временных неудобств.
А попытка стать удобнее — это желание избежать конфликта или молчания ценой
собственных интересов и чувств.

Такая стратегия не возвращает близость. Она создаёт иллюзию контакта, где
партнёр общается уже не с живым человеком, а с удобной ролью.

Конечно, бывают ситуации, когда партнёр проходит через объективно тяжёлый
период вроде болезни или потери работы.

Временно подстроиться под его нужды — это не стирание себя, а поддержка.

Ключевое отличие в том, что это временный процесс, а не новый стандарт.

Поэтому главный вопрос здесь не в том, любит ли он. Этот вопрос ведёт в тупик.

Гораздо честнее спросить: остаётся ли собственная позиция в этих отношениях?
Ответ отделяет заботу от самоотмены."""

        issues = telegram_team.editorial_contract_issues(TOPIC, text)

        self.assertTrue(any("шаблонный хук" in issue for issue in issues), issues)
        self.assertTrue(any("скрытый мотив" in issue for issue in issues), issues)
        self.assertTrue(any("не возвращает близость" in issue for issue in issues), issues)
        self.assertTrue(any("мужской пол" in issue for issue in issues), issues)
        self.assertTrue(any("абстрактные ярлыки" in issue for issue in issues), issues)
        self.assertTrue(any("6–9" in issue for issue in issues), issues)
        cleaned = telegram_team.clean_human_surface(TOPIC, text)
        self.assertNotIn("башк", cleaned.lower())
        self.assertNotRegex(cleaned, r"[«»“”„\"'‐‑‒–—−]")

    def test_surface_replaces_bashka_and_preserves_required_hyphens(self):
        raw = (
            "Первая мысль в башке — нужно что-то исправить. "
            "Это «по-настоящему» важный вопрос."
        )

        cleaned = telegram_team.clean_human_surface("Другая тема", raw)

        self.assertEqual(
            "Первая мысль в голове нужно что-то исправить. "
            "Это по-настоящему важный вопрос.",
            cleaned,
        )

    def test_contract_blocks_defects_from_music_request_generation(self):
        text = """Партнёр читает, а тебе мешает громкая музыка. Раньше ты бы
сказал: Сделай, пожалуйста, потише. Теперь проще надеть наушники.

Есть просьбы инструкции. Они решают бытовую задачу.

А есть просьбы вопросы. Они будто проверяют отношение.

Перед разговором полезно спросить себя, что именно сейчас важно.

Если ответ второе, возможно, нужен другой разговор.

Такая пауза помогает точнее назвать происходящее и не делать лишних выводов."""

        issues = telegram_team.editorial_contract_issues(
            "Почему стало трудно попросить о простом?",
            text,
        )
        blockers = telegram_team.editorial_publication_blockers(
            "Почему стало трудно попросить о простом?",
            text,
        )

        self.assertTrue(any("мужскую форму" in issue for issue in issues), issues)
        self.assertTrue(any("просьбы инструкции" in issue for issue in issues), issues)
        self.assertTrue(any("если ответ второе" in issue for issue in issues), issues)
        self.assertTrue(any("прямую речь" in issue for issue in issues), issues)
        self.assertTrue(any("мужскую форму" in issue for issue in blockers), blockers)
        self.assertTrue(any("просьбы инструкции" in issue for issue in blockers), blockers)
        self.assertTrue(any("если ответ второе" in issue for issue in blockers), blockers)
        self.assertTrue(any("прямую речь" in issue for issue in blockers), blockers)

    def test_quality_contract_rejects_dash_removal_that_breaks_grammar(self):
        text = (
            "Есть два способа помочь близкому. Первый стать для него проводником. "
            "Жизнь близкого это его путь. Попытка решить всё за него это контроль. "
            "Его задача остановить опасное действие."
        )

        warnings = telegram_team.quality_warnings(text)

        self.assertTrue(
            any("пропущенной связкой" in item for item in warnings),
            warnings,
        )

    def test_quality_contract_rejects_extended_light_metaphor(self):
        text = (
            "Партнёр был источником света и знал, где находится выключатель. "
            "Комната могла наполниться светом. Потом выключатель исчез, "
            "но провода остались подключены."
        )

        warnings = telegram_team.quality_warnings(text)

        self.assertTrue(
            any("метафору света" in item for item in warnings),
            warnings,
        )

    def test_quality_contract_rejects_extended_key_metaphor(self):
        text = (
            "Человек был ключом к твоей радости и открывал нужную дверь. "
            "Теперь старый замок сменился, доступ пропал, а эта часть заперта."
        )

        warnings = telegram_team.quality_warnings(text)

        self.assertTrue(
            any("метафору ключа" in item for item in warnings),
            warnings,
        )

    def test_quality_contract_rejects_bookish_nominalization(self):
        text = (
            "Смысл в том, чтобы найти новый контекст для проявления "
            "собственной способности радоваться."
        )

        warnings = telegram_team.quality_warnings(text)

        self.assertTrue(
            any("книжную связку" in item for item in warnings),
            warnings,
        )
        self.assertTrue(
            any("номинализацию" in item for item in warnings),
            warnings,
        )

    def test_quality_contract_rejects_bookish_catalyst_and_generic_advice(self):
        text = (
            "Партнёр был катализатором лёгкости. Теперь нужно сместить фокус "
            "и искать крошечные моменты лёгкости."
        )

        warnings = telegram_team.quality_warnings(text)

        self.assertTrue(any("катализатор" in item for item in warnings), warnings)
        self.assertTrue(any("общий совет" in item for item in warnings), warnings)

    def test_quality_contract_rejects_concept_language_and_missing_link(self):
        text = (
            "Эта часть личности осталась в прошлом. Авторство настоящего "
            "возвращается тебе. Привычка делиться этим с кем-то это другое."
        )

        warnings = telegram_team.quality_warnings(text)

        self.assertTrue(any("язык концепции" in item for item in warnings), warnings)
        self.assertTrue(
            any("пропущенной связкой" in item for item in warnings),
            warnings,
        )

    def test_fictional_first_thought_is_not_a_safety_blocker(self):
        text = (
            "Девушка увидела смешной плакат. Первая мысль: он бы посмеялся. "
            "Она остановилась и дочитала его сама."
        )

        blockers = telegram_team.blocking_quality_warnings(text)

        self.assertFalse(
            any("первой или типичной" in item for item in blockers),
            blockers,
        )

    def test_quality_contract_rejects_gendered_past_self_formula(self):
        warnings = telegram_team.quality_warnings(
            "Иногда скучаешь по прошлой себе."
        )

        self.assertTrue(
            any("прежняя версия себя" in item for item in warnings),
            warnings,
        )

    def test_missing_self_blueprint_rejects_source_catalyst_frame(self):
        topic = (
            "После расставания скучаешь по себе рядом с человеком. "
            "Как вернуть эту часть себя?"
        )
        blueprint = valid_blueprint(
            "Открываешь меню и долго не можешь выбрать десерт.",
            (
                "Партнёр был катализатором лёгкости, а её источник находился "
                "внутри человека."
            ),
        )
        blueprint = blueprint.replace(TOPIC, topic)

        issues = telegram_team.blueprint_contract_issues(topic, blueprint)

        self.assertTrue(
            any("источника и катализатора" in item for item in issues),
            issues,
        )

    def test_relationship_hook_rejects_implicit_male_reader_form(self):
        topic = "После расставания трудно вернуть лёгкость в отношения с собой"
        text = (
            "Открываешь меню в кафе и вспоминаешь человека, с которым сюда "
            "ходил. Выбрать десерт почему-то трудно."
        )

        warnings = telegram_team.structural_warnings(topic, text)

        self.assertTrue(
            any("неявную мужскую форму" in item for item in warnings),
            warnings,
        )

    def test_contract_catches_defects_from_second_real_generation(self):
        text = """Бывает состояние острее, чем сам разрыв. Это момент, когда вы
формально вместе, но ты себя в этих отношениях уже не находишь.

Всё начинается с едва уловимого сдвига. Разговоры становятся короче, общие
планы теряют ясность, а привычного тепла будто стало меньше. Вы ещё не
расстались, но уже появилось ощущение, что тебя больше не выбирают по умолчанию.

В ответ на эту тревожную тишину может появиться желание стать удобнее.
Сглаживать острые углы и пытаться угадать желания партнёра.

Со стороны это может выглядеть как работа над отношениями. Но вопрос как нам
быть вместе превращается в вопрос что сделать, чтобы меня не оставили.

Такая стратегия не имеет ничего общего со здоровым компромиссом, где двое
меняются ради общего будущего. Один человек отказывается от своих потребностей
и границ, чтобы отсрочить финал, который уже предчувствует.

Задай себе вопрос. Я меняюсь ради будущего или удерживаю то, что уходит?
Это отделяет заботу от самоотмены."""

        issues = telegram_team.editorial_contract_issues(TOPIC, text)
        blockers = telegram_team.editorial_publication_blockers(TOPIC, text)

        self.assertIn("не смешивай обращения «ты» и «вы»", issues)
        self.assertFalse(
            any("придуманный признак охлаждения" in issue for issue in issues),
            issues,
        )
        self.assertTrue(any("скрытый мотив" in issue for issue in issues), issues)
        self.assertTrue(
            any("дежурную психологическую лексику" in issue for issue in issues),
            issues,
        )
        self.assertTrue(
            any("абстрактные ярлыки" in issue for issue in issues),
            issues,
        )
        self.assertTrue(
            any("не смешивай обращения" in issue for issue in blockers),
            blockers,
        )
        self.assertFalse(
            any("придуманный признак охлаждения" in issue for issue in blockers),
            blockers,
        )
        self.assertTrue(any("скрытый мотив" in issue for issue in blockers), blockers)

    def test_v3_prompts_bound_number_of_drafts(self):
        self.assertIn("Напиши один текст", telegram_team.SINGLE_WRITER_PROMPT)
        self.assertIn(
            "НЕИЗМЕНЯЕМЫЙ ФАКТ ТЕМЫ",
            telegram_team.SINGLE_WRITER_PROMPT,
        )
        self.assertIn(
            "один раз",
            telegram_team.SINGLE_REPAIR_PROMPT,
        )
        self.assertIn(
            "Не переписывай пост",
            telegram_team.SINGLE_AUDIT_PROMPT,
        )
        self.assertIn(
            "подменяет соседней темой",
            telegram_team.SINGLE_AUDIT_PROMPT,
        )
        self.assertIn(
            "за этим скрывается",
            telegram_team.SINGLE_AUDIT_PROMPT,
        )
        self.assertIn(
            "Не возвращайся к сырым ответам NotebookLM",
            telegram_team.BLUEPRINT_REPAIR_PROMPT,
        )
        self.assertIn(
            "разрешён один короткий художественный пример",
            telegram_team.SINGLE_WRITER_PROMPT,
        )
        self.assertIn(
            "Художественный пример допустим",
            telegram_team.SINGLE_AUDIT_PROMPT,
        )
        self.assertIn(
            "Можно сохранить или улучшить один художественный",
            telegram_team.SINGLE_REPAIR_PROMPT,
        )
        self.assertIn(
            "одно наблюдаемое действие",
            telegram_team.SINGLE_WRITER_PROMPT,
        )
        self.assertIn(
            "Художественный пример сохрани",
            telegram_team.BLUEPRINT_REPAIR_PROMPT,
        )
        self.assertIn(
            "тест холодного читателя",
            telegram_team.BLUEPRINT_CREATION_ADDENDUM,
        )
        self.assertIn(
            "Холодный читатель",
            telegram_team.SINGLE_AUDIT_PROMPT,
        )
        self.assertIn(
            "два–пять естественных обращений на «ты»",
            telegram_team.SINGLE_WRITER_PROMPT.lower(),
        )
        self.assertIn(
            "художественная сцена выдана за реального клиента",
            telegram_team.FINAL_REVIEW_PROMPT,
        )
        self.assertNotIn(
            "никаких новых сцен",
            telegram_team.SINGLE_REPAIR_PROMPT.lower(),
        )
        self.assertIn("обе стороны сравнения", telegram_team.FINAL_AUTHOR_CONTRACT)
        self.assertIn("Примени две или три настройки", telegram_team.FINAL_AUTHOR_CONTRACT)

    def test_editorial_output_removes_only_service_wrapper(self):
        self.assertEqual(
            telegram_team.clean_editorial_output("ГОТОВЫЙ ПОСТ:\nЖивой хук."),
            "Живой хук.",
        )
        self.assertEqual(
            telegram_team.clean_editorial_output("После одиночества бывает страшно."),
            "После одиночества бывает страшно.",
        )

    def test_comparative_topic_requires_direct_comparative_answer(self):
        topic = (
            "Почему хорошие отношения иногда пугают сильнее, "
            "чем возможность снова остаться одному?"
        )
        vague = "Новые отношения могут пугать. Иногда привычное кажется безопасным."
        direct = (
            "Новые отношения иногда пугают сильнее одиночества, потому что "
            "одиночество уже знакомо, а близость требует рискнуть привычным укладом."
        )
        self.assertTrue(
            any("пугает сильнее" in issue for issue in telegram_team.editorial_contract_issues(topic, vague))
        )
        self.assertFalse(
            any("пугает сильнее" in issue for issue in telegram_team.editorial_contract_issues(topic, direct))
        )

    def test_editorial_contract_flags_stock_metaphors(self):
        issues = telegram_team.editorial_contract_issues(
            "Почему перемены пугают?",
            "Жизнь стала хорошо отлаженной системой. Это шаг в неизвестность.",
        )
        self.assertTrue(any("клише" in issue for issue in issues), issues)


if __name__ == "__main__":
    unittest.main()
