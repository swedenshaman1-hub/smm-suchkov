import hashlib
import hmac
import json
import os
import unittest
from unittest.mock import patch

from agents import instagram_messaging as im


class InstagramMessagingTests(unittest.TestCase):
    def setUp(self):
        im._seen_events.clear()
        self.env = patch.dict(
            os.environ,
            {
                "IG_BUSINESS_ACCOUNT_ID": "business-1",
                "IG_ACCESS_TOKEN": "token",
                "IG_APP_SECRET": "secret",
                "IG_WEBHOOK_VERIFY_TOKEN": "verify",
                "IG_FREEBIE_URL": "https://example.test/freebie",
            },
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_keyword_is_case_insensitive(self):
        self.assertTrue(im.is_keyword_comment("Хочу МЕДИТАЦИЮ"))
        self.assertFalse(im.is_keyword_comment("Спасибо за пост"))

    def test_signature(self):
        body = b'{"object":"instagram"}'
        digest = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
        self.assertTrue(im.verify_signature(body, f"sha256={digest}"))
        self.assertFalse(im.verify_signature(body, "sha256=bad"))

    @patch.object(im, "send_private_comment_reply")
    def test_comment_gets_only_one_private_reply(self, send_reply):
        payload = {
            "object": "instagram",
            "entry": [{
                "changes": [{
                    "field": "comments",
                    "value": {
                        "id": "comment-1",
                        "text": "медитация",
                        "from": {"id": "person-1"},
                    },
                }],
            }],
        }
        im.process_webhook(payload)
        im.process_webhook(payload)
        send_reply.assert_called_once()

    @patch.object(im, "send_direct_message")
    @patch.object(im, "get_user_profile")
    def test_follower_receives_link(self, get_profile, send_message):
        get_profile.return_value = {"is_user_follow_business": True}
        payload = {
            "object": "instagram",
            "entry": [{
                "messaging": [{
                    "sender": {"id": "person-1"},
                    "message": {"mid": "message-1", "text": "ПОЛУЧИТЬ"},
                }],
            }],
        }
        im.process_webhook(payload)
        sent_text = send_message.call_args.args[1]
        self.assertIn("https://example.test/freebie", sent_text)

    @patch.object(im, "send_direct_message")
    @patch.object(im, "get_user_profile")
    def test_non_follower_is_asked_to_follow(self, get_profile, send_message):
        get_profile.return_value = {"is_user_follow_business": False}
        payload = {
            "object": "instagram",
            "entry": [{
                "messaging": [{
                    "sender": {"id": "person-1"},
                    "message": {"mid": "message-2", "text": "готово"},
                }],
            }],
        }
        im.process_webhook(payload)
        sent_text = send_message.call_args.args[1]
        self.assertIn("подпишитесь", sent_text.lower())


if __name__ == "__main__":
    unittest.main()
