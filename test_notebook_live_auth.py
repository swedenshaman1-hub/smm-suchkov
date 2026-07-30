import base64
import json
import os
import unittest
from unittest.mock import patch

from agents import notebook_live


COOKIES = {
    "SID": "sid",
    "HSID": "hsid",
    "SSID": "ssid",
    "APISID": "apisid",
    "SAPISID": "sapisid",
}


def encoded(payload: dict) -> str:
    raw = json.dumps(payload).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


class NotebookAuthTests(unittest.TestCase):
    def test_loads_complete_connector_credentials(self):
        payload = {
            "cookies": COOKIES,
            "csrf_token": "csrf",
            "session_id": "session",
        }
        with patch.dict(
            os.environ,
            {notebook_live.AUTH_ENV: encoded(payload)},
            clear=False,
        ):
            auth = notebook_live._load_auth()

        self.assertEqual(COOKIES, auth.cookies)
        self.assertEqual("csrf", auth.csrf_token)
        self.assertEqual("session", auth.session_id)

    def test_keeps_legacy_cookie_only_payload_compatible(self):
        with patch.dict(
            os.environ,
            {notebook_live.AUTH_ENV: encoded(COOKIES)},
            clear=False,
        ):
            auth = notebook_live._load_auth()

        self.assertEqual(COOKIES, auth.cookies)
        self.assertEqual("", auth.csrf_token)
        self.assertEqual("", auth.session_id)

    def test_query_uses_saved_tokens_without_forcing_page_refresh(self):
        captured = {}

        class FakeClient:
            def __init__(self, *, cookies, csrf_token, session_id):
                captured.update(
                    cookies=cookies,
                    csrf_token=csrf_token,
                    session_id=session_id,
                )

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def query(self, notebook_id, prompt, timeout):
                captured.update(
                    notebook_id=notebook_id,
                    prompt=prompt,
                    timeout=timeout,
                )
                return {"answer": "Живой ответ блокнота"}

        class Notebook:
            title = "Тестовый блокнот"
            key = "test"

            @staticmethod
            def resolved_id():
                return "notebook-id"

        with patch(
            "agents.notebook_live._patched_client_class",
            return_value=FakeClient,
        ):
            key, answer = notebook_live._query_one(
                Notebook(),
                "Вопрос",
                COOKIES,
                attempts=1,
                csrf_token="csrf",
                session_id="session",
            )

        self.assertEqual("test", key)
        self.assertEqual("Живой ответ блокнота", answer)
        self.assertEqual("csrf", captured["csrf_token"])
        self.assertEqual("session", captured["session_id"])


if __name__ == "__main__":
    unittest.main()
