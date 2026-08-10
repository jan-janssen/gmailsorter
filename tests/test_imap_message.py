from datetime import datetime
from email.header import Header
from email.message import EmailMessage, Message as EmailLibMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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

    def test_subject_encoded_word(self):
        msg = EmailMessage()
        msg["Subject"] = "Exclusieve Nieuwsbrief • Binobet"
        message = Message(message=msg, folder="INBOX", uid="1")
        self.assertEqual(
            message.get_subject(), "Exclusieve Nieuwsbrief • Binobet"
        )

    def test_subject_header_object_is_coerced_to_str(self):
        # Some servers/Python versions cause Message.get() to return an
        # email.header.Header instance instead of a str, which used to crash
        # SQLAlchemy's parameter binding when inserted into the database.
        msg = EmailLibMessage()
        msg["Subject"] = Header("Exclusieve Nieuwsbrief • Binobet", "utf-8")
        message = Message(message=msg, folder="INBOX", uid="1")
        subject = message.get_subject()
        self.assertIsInstance(subject, str)
        self.assertEqual(subject, "Exclusieve Nieuwsbrief • Binobet")

    def test_from(self):
        self.assertEqual(self.message.get_from(), "sender@server.net")

    def test_to(self):
        self.assertEqual(self.message.get_to(), ["me@mail.com", "friend@provider.org"])

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

    def test_get_from_missing_header_returns_none(self):
        msg = EmailMessage()
        message = Message(message=msg, folder="INBOX", uid="46")

        self.assertIsNone(message.get_from())

    def test_get_date_missing_header_returns_none(self):
        msg = EmailMessage()
        message = Message(message=msg, folder="INBOX", uid="47")

        self.assertIsNone(message.get_date())

    def test_get_content_multipart_prefers_plain_over_html(self):
        outer = MIMEMultipart("mixed")
        inner = MIMEMultipart("alternative")
        inner.attach(MIMEText("Hello world", "plain"))
        inner.attach(MIMEText("<p>Hello <b>World</b></p>", "html"))
        outer.attach(inner)
        message = Message(message=outer, folder="INBOX", uid="48")

        self.assertEqual(message.get_content().strip(), "Hello world")

    def test_get_content_returns_none_for_unknown_mimetype(self):
        msg = EmailMessage()
        msg.set_content(b"\x00\x01", maintype="application", subtype="octet-stream")
        message = Message(message=msg, folder="INBOX", uid="49")

        self.assertIsNone(message.get_content())

    def test_thread_id_uses_in_reply_to_when_no_references(self):
        msg = EmailMessage()
        msg["In-Reply-To"] = " <parent@server.net> "
        msg["Message-ID"] = "<mid@server.net>"
        message = Message(message=msg, folder="INBOX", uid="50")

        self.assertEqual(message.get_thread_id(), "<parent@server.net>")

    def test_thread_id_falls_back_to_email_id_without_any_headers(self):
        msg = EmailMessage()
        message = Message(message=msg, folder="INBOX", uid="51")

        self.assertEqual(message.get_thread_id(), "INBOX\x1f51")

    def test_decode_part_returns_empty_string_when_payload_is_none(self):
        multipart_msg = MIMEMultipart("mixed")

        self.assertEqual(Message._decode_part(multipart_msg), "")

    def test_get_email_dict_catches_value_error_and_returns_none(self):
        msg = EmailMessage()
        msg["Date"] = "Mon, 32 Jan 2024 25:99:99 +0000"

        self.assertIsNone(get_email_dict(msg, folder="INBOX", uid="52"))

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
