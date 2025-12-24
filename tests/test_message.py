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
            email_date_converter("24-01-2022"),
            datetime.strptime("24-01-2022", "%d-%m-%Y")
        )
        self.assertEqual(
            email_date_converter(None),
            None
        )
