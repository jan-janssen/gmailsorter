from unittest import TestCase
from datetime import datetime
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
                    {"name": "Date", "value": "Fri, 11 Feb 2022 18:08:46 +0100"}
                ],
                "body": {
                    "data": ""
                }
            }
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
            datetime.strptime("Fri, 11 Feb 2022 18:08:46 +0100", "%a, %d %b %Y %H:%M:%S %z")
        )

    def test_get_content(self):
        self.assertEqual(self.message.get_content(), None)

    def test_get_email_dict(self):
        self.assertEqual(
            get_email_dict(self._message_dict),
            {
                'cc': [],
                'content': None,
                'date': datetime.strptime("Fri, 11 Feb 2022 18:08:46 +0100", "%a, %d %b %Y %H:%M:%S %z"),
                'from': 'sender@server.net',
                'id': 'myid123',
                'labels': ['important', 'Label_123'],
                'subject': 'Test Email Subject',
                'threads': 'abc123',
                'to': ['me@mail.com', 'friend@provider.org']
            })
