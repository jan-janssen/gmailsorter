from unittest import TestCase
from datetime import datetime
from gmailsorter.base.message import email_date_converter, AbstractMessage


class MessageTest(TestCase):
    def test_email_date_converter(self):
        self.assertEqual(
            email_date_converter("Fri, 11 Feb 2022 18:08:46 +0100"),
            datetime.strptime("Fri, 11 Feb 2022 18:08:46 +0100", "%a, %d %b %Y %H:%M:%S %z")
        )
        self.assertEqual(
            email_date_converter("11 Feb 2022 18:08:46 +0100"),
            datetime.strptime("11 Feb 2022 18:08:46 +0100", "%d %b %Y %H:%M:%S %z")
        )
        self.assertEqual(
            email_date_converter("Fri, 11 Feb 2022 18:08:46"),
            datetime.strptime("Fri, 11 Feb 2022 18:08:46", "%a, %d %b %Y %H:%M:%S")
        )
        self.assertEqual(
            email_date_converter("11-02-2022"),
            datetime.strptime("11-02-2022", "%d-%m-%Y")
        )
        self.assertEqual(
            email_date_converter("Fri, 11 Feb 2022 18:08:46 +0100 (UTC)"),
            datetime.strptime("Fri, 11 Feb 2022 18:08:46 +0100", "%a, %d %b %Y %H:%M:%S %z")
        )
        self.assertEqual(
            email_date_converter("\xa0Fri, 11 Feb 2022 18:08:46 +0100"),
            datetime.strptime("Fri, 11 Feb 2022 18:08:46 +0100", "%a, %d %b %Y %H:%M:%S %z")
        )
        self.assertEqual(
            email_date_converter("Mon, 24 Jan 2022 08:32:02 +0000 (UTC)"),
            datetime.strptime("Mon, 24 Jan 2022 08:32:02 +0000", "%a, %d %b %Y %H:%M:%S %z")
        )
        self.assertEqual(
            email_date_converter("Mon, 24 Jan 2022 08:32:02 +0000 (CET)"),
            datetime.strptime("Mon, 24 Jan 2022 08:32:02 +0000", "%a, %d %b %Y %H:%M:%S %z")
        )
        self.assertEqual(
            email_date_converter("Mon, 24 Jan 2022 08:32:02 +0000 (CEST)"),
            datetime.strptime("Mon, 24 Jan 2022 08:32:02 +0000", "%a, %d %b %Y %H:%M:%S %z")
        )
        self.assertEqual(
            email_date_converter("Tue, 25 Jan 2022 09:45:12 +0100 (CET)"),
            datetime.strptime("Tue, 25 Jan 2022 09:45:12 +0100", "%a, %d %b %Y %H:%M:%S %z")
        )
        self.assertEqual(
            email_date_converter("Wed, 26 Jan 2022 10:58:22 +0200 (EET)"),
            datetime.strptime("Wed, 26 Jan 2022 10:58:22 +0200", "%a, %d %b %Y %H:%M:%S %z")
        )
        self.assertEqual(
            email_date_converter("Thu, 27 Jan 2022 11:12:32 +0300 (MSK)"),
            datetime.strptime("Thu, 27 Jan 2022 11:12:32 +0300", "%a, %d %b %Y %H:%M:%S %z")
        )
        self.assertEqual(
            email_date_converter("Thu, 27 Jan 2022 11:12:32 +0300 (MSK)a"),
            datetime.strptime("Thu, 27 Jan 2022 11:12:32 +0300", "%a, %d %b %Y %H:%M:%S %z")
        )
        self.assertEqual(
            email_date_converter("24 Jan 2022, 08:32:02 +0000"),
            datetime.strptime("24 Jan 2022 08:32:02 +0000", "%d %b %Y %H:%M:%S %z")
        )
        self.assertEqual(
            email_date_converter("24-01-2022"),
            datetime.strptime("24-01-2022", "%d-%m-%Y")
        )
        self.assertEqual(
            email_date_converter("Fri, 11 Feb 2022 18:08:46.123+0100"),
            datetime.strptime("Fri, 11 Feb 2022 18:08:46", "%a, %d %b %Y %H:%M:%S")
        )
        self.assertEqual(
            email_date_converter("Fri, 11 Feb 2022 18:08:46.123"),
            datetime.strptime("Fri, 11 Feb 2022 18:08:46", "%a, %d %b %Y %H:%M:%S")
        )
        self.assertEqual(
            email_date_converter("\xa0, 11 Feb 2022 18:08:46"),
            datetime.strptime("11 Feb 2022 18:08:46", "%d %b %Y %H:%M:%S")
        )
        self.assertEqual(
            email_date_converter("Fri, 11 Feb 2022 18:08:46.123"),
            datetime.strptime("Fri, 11 Feb 2022 18:08:46", "%a, %d %b %Y %H:%M:%S")
        )
        self.assertEqual(
            email_date_converter("\xa0, 11 Feb 2022 18:08:46"),
            datetime.strptime("11 Feb 2022 18:08:46", "%d %b %Y %H:%M:%S")
        )
        self.assertEqual(
            email_date_converter(None),
            None
        )

    def test_abstract_message(self):
        class MyMessage(AbstractMessage):
            def get_from(self):
                return "from"

            def get_to(self):
                return "to"

            def get_cc(self):
                return "cc"

            def get_label_ids(self):
                return ["label1", "label2"]

            def get_subject(self):
                return "subject"

            def get_date(self):
                return "date"

            def get_content(self):
                return "content"

            def get_thread_id(self):
                return "thread_id"

            def get_email_id(self):
                return "email_id"

        message = MyMessage({})
        self.assertEqual(message.get_from(), "from")
        self.assertEqual(message.get_to(), "to")
        self.assertEqual(message.get_cc(), "cc")
        self.assertEqual(message.get_label_ids(), ["label1", "label2"])
        self.assertEqual(message.get_subject(), "subject")
        self.assertEqual(message.get_date(), "date")
        self.assertEqual(message.get_content(), "content")
        self.assertEqual(message.get_thread_id(), "thread_id")
        self.assertEqual(message.get_email_id(), "email_id")
        self.assertEqual(
            message.to_dict(),
            {
                "id": "email_id",
                "threads": "thread_id",
                "labels": ["label1", "label2"],
                "to": "to",
                "from": "from",
                "cc": "cc",
                "subject": "subject",
                "content": "content",
                "date": "date",
            },
        )

    def test_abstract_message_not_implemented(self):
        class MyMessage(AbstractMessage):
            pass

        message = MyMessage({})
        with self.assertRaises(NotImplementedError):
            message.get_from()
        with self.assertRaises(NotImplementedError):
            message.get_to()
        with self.assertRaises(NotImplementedError):
            message.get_cc()
        with self.assertRaises(NotImplementedError):
            message.get_label_ids()
        with self.assertRaises(NotImplementedError):
            message.get_subject()
        with self.assertRaises(NotImplementedError):
            message.get_date()
        with self.assertRaises(NotImplementedError):
            message.get_content()
        with self.assertRaises(NotImplementedError):
            message.get_thread_id()
        with self.assertRaises(NotImplementedError):
            message.get_email_id()
