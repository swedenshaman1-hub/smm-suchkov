import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import telegram_bot


class EditorialCallbackTests(unittest.IsolatedAsyncioTestCase):
    CHAT_ID = 12345
    DRAFT_ID = "draft-1"

    def _callback(self, action: str):
        query = SimpleNamespace(
            answer=AsyncMock(),
            data=f"{action}:{self.DRAFT_ID}",
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_chat=SimpleNamespace(id=self.CHAT_ID),
        )
        context = SimpleNamespace(user_data={})
        return update, context, query

    def _record(self):
        return {
            "topic": "Тема принятого поста",
            "actual_fingerprint": {"entrance": "concrete_moment"},
        }

    async def test_accepted_updated_registers_published_once(self):
        update, context, query = self._callback("post_accept")
        record = self._record()
        with (
            patch.object(telegram_bot, "_hydrate_session"),
            patch.object(telegram_bot, "_persist_session"),
            patch.object(telegram_bot.editorial_history, "decide", return_value=("updated", record)),
            patch.object(telegram_bot.memory_utils, "register_published") as register_published,
        ):
            await telegram_bot.handle_button(update, context)

        register_published.assert_called_once_with(
            "Тема принятого поста",
            angle="concrete_moment",
            formats=["telegram_post"],
        )
        self.assertIn("Текст принят", query.edit_message_text.await_args.args[0])

    async def test_accepted_without_entrance_registers_empty_angle(self):
        update, context, _query = self._callback("post_accept")
        record = {
            "topic": "Тема без распознанного входа",
            "actual_fingerprint": {},
        }
        with (
            patch.object(telegram_bot, "_hydrate_session"),
            patch.object(telegram_bot, "_persist_session"),
            patch.object(telegram_bot.editorial_history, "decide", return_value=("updated", record)),
            patch.object(telegram_bot.memory_utils, "register_published") as register_published,
        ):
            await telegram_bot.handle_button(update, context)

        register_published.assert_called_once_with(
            "Тема без распознанного входа",
            angle="",
            formats=["telegram_post"],
        )

    async def test_rejected_updated_does_not_register_published(self):
        update, context, query = self._callback("post_reject")
        with (
            patch.object(telegram_bot, "_hydrate_session"),
            patch.object(telegram_bot, "_persist_session"),
            patch.object(
                telegram_bot.editorial_history,
                "decide",
                return_value=("updated", self._record()),
            ),
            patch.object(telegram_bot.memory_utils, "register_published") as register_published,
        ):
            await telegram_bot.handle_button(update, context)

        register_published.assert_not_called()
        self.assertIn("Текст отклонён", query.edit_message_text.await_args.args[0])

    async def test_already_decided_does_not_register_published(self):
        update, context, query = self._callback("post_accept")
        with (
            patch.object(telegram_bot, "_hydrate_session"),
            patch.object(telegram_bot, "_persist_session"),
            patch.object(
                telegram_bot.editorial_history,
                "decide",
                return_value=("already_decided", self._record()),
            ),
            patch.object(telegram_bot.memory_utils, "register_published") as register_published,
        ):
            await telegram_bot.handle_button(update, context)

        register_published.assert_not_called()
        self.assertIn("уже сохранено", query.edit_message_text.await_args.args[0])

    async def test_not_found_does_not_register_or_dereference_none(self):
        update, context, query = self._callback("post_accept")
        with (
            patch.object(telegram_bot, "_hydrate_session"),
            patch.object(telegram_bot, "_persist_session"),
            patch.object(
                telegram_bot.editorial_history,
                "decide",
                return_value=("not_found", None),
            ),
            patch.object(telegram_bot.memory_utils, "register_published") as register_published,
        ):
            await telegram_bot.handle_button(update, context)

        register_published.assert_not_called()
        self.assertIn("черновик не найден", query.edit_message_text.await_args.args[0])

    async def test_registry_failure_keeps_accepted_response_and_logs_context(self):
        update, context, query = self._callback("post_accept")
        with (
            patch.object(telegram_bot, "_hydrate_session"),
            patch.object(telegram_bot, "_persist_session"),
            patch.object(
                telegram_bot.editorial_history,
                "decide",
                return_value=("updated", self._record()),
            ) as decide,
            patch.object(
                telegram_bot.memory_utils,
                "register_published",
                side_effect=RuntimeError("registry unavailable"),
            ),
            patch.object(telegram_bot.logger, "exception") as log_exception,
        ):
            await telegram_bot.handle_button(update, context)

        decide.assert_called_once_with(self.DRAFT_ID, self.CHAT_ID, "accepted")
        log_exception.assert_called_once()
        logged_args = log_exception.call_args.args
        self.assertEqual(logged_args[1:], (self.DRAFT_ID, self.CHAT_ID, "Тема принятого поста", "post_accept"))
        self.assertIn("Текст принят", query.edit_message_text.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
