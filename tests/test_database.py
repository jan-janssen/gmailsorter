from unittest import TestCase
from datetime import datetime
import pandas
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from gmailsorter.base.database import get_email_database


class DatabaseTest(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        df = pandas.DataFrame([{
            'content': None,
            'date': datetime.strptime("Fri, 11 Feb 2022 18:08:46 +0100", "%a, %d %b %Y %H:%M:%S %z"),
            'from': 'sender@server.net',
            'id': 'myid123',
            'cc': 'your@friend.com',
            'labels': ['important', 'Label_123'],
            'subject': 'Test Email Subject',
            'threads': 'abc123',
            'to': ['me@mail.com', 'friend@provider.org']
        }])
        engine = create_engine('sqlite:///:memory:', echo=True)
        cls.database = get_email_database(
            engine=engine,
            session=sessionmaker(bind=engine)()
        )
        cls.database.store_dataframe(df=df)

    def test_list_email_ids(self):
        self.assertEqual(self.database.list_email_ids(), ['myid123'])

    def test_get_all_emails(self):
        self.assertEqual(len(self.database.get_all_emails()), 1)

    def test_get_emails_by_label(self):
        self.assertEqual(
            self.database.get_emails_by_label(label_id="Label_123").id.values.tolist(),
            ['myid123']
        )

    def test_get_emails_by_from(self):
        self.assertEqual(
            self.database.get_emails_by_from(email_from="sender@server.net").id.values.tolist(),
            ['myid123']
        )

    def test_get_emails_by_to(self):
        self.assertEqual(
            self.database.get_emails_by_to(email_to="me@mail.com").id.values.tolist(),
            ['myid123']
        )

    def test_get_emails_by_thread(self):
        self.assertEqual(
            self.database.get_emails_by_thread(thread_id="abc123").id.values.tolist(),
            ['myid123']
        )
