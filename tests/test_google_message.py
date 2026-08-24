import base64
from unittest import TestCase
from datetime import datetime
from datetime import datetime, timezone, timedelta
from gmailsorter.base.message import strip_html_tags
from gmailsorter.google.message import Message, get_email_dict


class MessageTest(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._message_dict = {
            "threadId": "abc123",
            "id": "myid123",
            "labelIds": ["important", "Label_123"],
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test Email Subject"},
                    {"name": "From", "value": "sender@server.net"},
                    {"name": "To", "value": "me@mail.com, friend@provider.org"},
                    {"name": "Date", "value": "Fri, 11 Feb 2022 18:08:46 +0100"},
                ],
                "body": {"data": ""},
            },
        }
        cls.message = Message(message_dict=cls._message_dict)

    def test_subject(self):
        self.assertEqual(self.message.get_subject(), "Test Email Subject")

    def test_from(self):
        self.assertEqual(self.message.get_from(), "sender@server.net")

    def test_to(self):
        self.assertEqual(self.message.get_to(), ["me@mail.com", "friend@provider.org"])

    def test_email_id(self):
        self.assertEqual(self.message.get_email_id(), "myid123")

    def test_thread_id(self):
        self.assertEqual(self.message.get_thread_id(), "abc123")

    def test_label_ids(self):
        self.assertEqual(self.message.get_label_ids(), ["important", "Label_123"])

    def test_get_date(self):
        self.assertEqual(
            self.message.get_date(),
            datetime.strptime(
                "Fri, 11 Feb 2022 18:08:46 +0100", "%a, %d %b %Y %H:%M:%S %z"
            ).astimezone(timezone.utc),
        )

    def test_get_content(self):
        self.assertEqual(self.message.get_content(), None)

    def test_get_from_multiple_addresses_returns_none(self):
        message = Message(
            message_dict={
                "threadId": "t",
                "id": "i",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "a@test.com, b@test.com"},
                    ]
                },
            }
        )
        self.assertIsNone(message.get_from())

    def test_get_from_with_display_name_and_angle_brackets(self):
        message = Message(
            message_dict={
                "threadId": "t",
                "id": "i",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "Jane Doe <Jane.Doe@Test.com>"},
                    ]
                },
            }
        )
        self.assertEqual(message.get_from(), "jane.doe@test.com")

    def test_get_cc_none_header_returns_empty_list(self):
        message = Message(
            message_dict={
                "threadId": "t",
                "id": "i",
                "payload": {"headers": []},
            }
        )
        self.assertEqual(message.get_cc(), [])

    def test_get_label_ids_missing_key_returns_empty_list(self):
        message = Message(
            message_dict={
                "threadId": "t",
                "id": "i",
                "payload": {"headers": []},
            }
        )
        self.assertEqual(message.get_label_ids(), [])

    def test_get_content_text_plain_in_parts(self):
        encoded = base64.urlsafe_b64encode(b"Hello World").decode("UTF-8")
        message = Message(
            message_dict={
                "threadId": "t",
                "id": "i",
                "payload": {
                    "headers": [],
                    "parts": [
                        {"mimeType": "text/plain", "body": {"data": encoded}},
                    ],
                },
            }
        )
        self.assertEqual(message.get_content(), "Hello World")

    def test_get_content_text_html_strips_tags(self):
        html = "<html><body><p>Hello <b>World</b></p></body></html>"
        encoded = base64.urlsafe_b64encode(html.encode("UTF-8")).decode("UTF-8")
        message = Message(
            message_dict={
                "threadId": "t",
                "id": "i",
                "payload": {
                    "headers": [],
                    "parts": [
                        {"mimeType": "text/html", "body": {"data": encoded}},
                    ],
                },
            }
        )
        self.assertEqual(message.get_content(), "Hello World")

    def test_get_content_multipart_alternative_nested(self):
        encoded = base64.urlsafe_b64encode(b"Nested body").decode("UTF-8")
        message = Message(
            message_dict={
                "threadId": "t",
                "id": "i",
                "payload": {
                    "headers": [],
                    "parts": [
                        {
                            "mimeType": "multipart/alternative",
                            "parts": [
                                {
                                    "mimeType": "text/plain",
                                    "body": {"data": encoded},
                                }
                            ],
                        }
                    ],
                },
            }
        )
        self.assertEqual(message.get_content(), "Nested body")

    def test_get_content_multipart_alternative_without_nested_parts(self):
        message = Message(
            message_dict={
                "threadId": "t",
                "id": "i",
                "payload": {
                    "headers": [],
                    "parts": [{"mimeType": "multipart/alternative"}],
                },
            }
        )
        self.assertIsNone(message.get_content())

    def test_get_content_unknown_mimetype_returns_none(self):
        message = Message(
            message_dict={
                "threadId": "t",
                "id": "i",
                "payload": {
                    "headers": [],
                    "parts": [{"mimeType": "application/octet-stream"}],
                },
            }
        )
        self.assertIsNone(message.get_content())

    def test_get_content_missing_body_data_returns_empty_string(self):
        message = Message(
            message_dict={
                "threadId": "t",
                "id": "i",
                "payload": {
                    "headers": [],
                    "parts": [{"mimeType": "text/plain", "body": {}}],
                },
            }
        )
        self.assertEqual(message.get_content(), "")

    def test_mlstripper_removes_tags(self):
        self.assertEqual(
            strip_html_tags("<div>Hello <span>World</span></div>"), "Hello World"
        )

    def test_get_email_dict_catches_value_error_and_returns_none(self):
        message_dict = {
            "threadId": "t",
            "id": "i",
            "payload": {
                "headers": [
                    {"name": "Date", "value": "Zzz, 40 Foo 2022 99:99:99 +0100"},
                ]
            },
        }
        self.assertIsNone(get_email_dict(message_dict))

    def test_get_email_dict(self):
        self.assertEqual(
            get_email_dict(self._message_dict),
            {
                "cc": [],
                "content": None,
                "date": datetime.strptime(
                    "Fri, 11 Feb 2022 18:08:46 +0100", "%a, %d %b %Y %H:%M:%S %z"
                ).astimezone(timezone.utc),
                "from": "sender@server.net",
                "id": "myid123",
                "labels": ["important", "Label_123"],
                "subject": "Test Email Subject",
                "threads": "abc123",
                "to": ["me@mail.com", "friend@provider.org"],
            },
        )
