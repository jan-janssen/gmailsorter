from datetime import datetime
from email.message import EmailMessage
from unittest import TestCase

from gmailsorter.imap.message import Message, get_email_dict


class MessageTest(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        msg = EmailMessage()
        msg["Subject"] = "Test Email Subject"
        msg["From"] = "sender@server.net"
        msg["To"] = "me@mail.com, friend@provider.org"
        msg["Date"] = "Fri, 11 Feb 2022 18:08:46 +0100"
        msg["Message-ID"] = "<abc123@server.net>"
        msg.set_content("Hello world")
        cls._message = msg
        cls.message = Message(message=msg, folder="INBOX", uid="42")

    def test_subject(self):
        self.assertEqual(self.message.get_subject(), "Test Email Subject")

    def test_from(self):
        self.assertEqual(self.message.get_from(), "sender@server.net")

    def test_to(self):
        self.assertEqual(
            self.message.get_to(), ["me@mail.com", "friend@provider.org"]
        )

    def test_cc_empty(self):
        self.assertEqual(self.message.get_cc(), [])

    def test_email_id(self):
        self.assertEqual(self.message.get_email_id(), "INBOX\x1f42")

    def test_thread_id_falls_back_to_message_id(self):
        self.assertEqual(self.message.get_thread_id(), "<abc123@server.net>")

    def test_label_ids(self):
        self.assertEqual(self.message.get_label_ids(), ["INBOX"])

    def test_get_date(self):
        self.assertEqual(
            self.message.get_date(),
            datetime.strptime(
                "Fri, 11 Feb 2022 18:08:46 +0100", "%a, %d %b %Y %H:%M:%S %z"
            ),
        )

    def test_get_content(self):
        self.assertEqual(self.message.get_content().strip(), "Hello world")

    def test_get_content_html_fallback(self):
        html_msg = EmailMessage()
        html_msg["Subject"] = "HTML"
        html_msg["From"] = "sender@server.net"
        html_msg["To"] = "me@mail.com"
        html_msg["Date"] = "Fri, 11 Feb 2022 18:08:46 +0100"
        html_msg.set_content("<p>Hello <b>World</b></p>", subtype="html")
        message = Message(message=html_msg, folder="INBOX", uid="43")

        self.assertEqual(message.get_content().strip(), "Hello World")

    def test_thread_id_uses_references_header(self):
        msg = EmailMessage()
        msg["Subject"] = "Re: Test"
        msg["References"] = "<root@server.net> <mid@server.net>"
        msg["Message-ID"] = "<mid@server.net>"
        message = Message(message=msg, folder="INBOX", uid="44")

        self.assertEqual(message.get_thread_id(), "<root@server.net>")

    def test_from_with_multiple_addresses_is_none(self):
        msg = EmailMessage()
        msg["From"] = "a@server.net, b@server.net"
        message = Message(message=msg, folder="INBOX", uid="45")

        self.assertIsNone(message.get_from())

    def test_get_email_dict(self):
        result = get_email_dict(self._message, folder="INBOX", uid="42")
        content = result.pop("content")

        self.assertEqual(content.strip(), "Hello world")
        self.assertEqual(
            result,
            {
                "cc": [],
                "date": datetime.strptime(
                    "Fri, 11 Feb 2022 18:08:46 +0100", "%a, %d %b %Y %H:%M:%S %z"
                ),
                "from": "sender@server.net",
                "id": "INBOX\x1f42",
                "labels": ["INBOX"],
                "subject": "Test Email Subject",
                "threads": "<abc123@server.net>",
                "to": ["me@mail.com", "friend@provider.org"],
            },
        )
