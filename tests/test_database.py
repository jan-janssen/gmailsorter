from unittest import TestCase
from unittest.mock import MagicMock
from datetime import datetime
import pandas
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from gmailsorter.base.database import get_email_database, EmailContent, EmailFrom


class DatabaseTest(TestCase):
    def setUp(self) -> None:
        df = pandas.DataFrame([{
            'content': None,
            'date': datetime.strptime("Fri, 11 Feb 2022 18:08:46 +0100", "%a, %d %b %Y %H:%M:%S %z"),
            'from': 'sender@server.net',
            'id': 'myid123',
            'cc': ['your@friend.com'],
            'labels': ['important', 'Label_123'],
            'subject': 'Test Email Subject',
            'threads': 'abc123',
            'to': ['me@mail.com', 'friend@provider.org']
        }])
        engine = create_engine('sqlite:///:memory:', echo=True)
        self.database = get_email_database(
            engine=engine,
            session=sessionmaker(bind=engine)()
        )
        self.database.store_dataframe(df=df)

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

    def test_get_emails_by_cc(self):
        self.assertEqual(
            self.database.get_emails_by_cc(email_cc="your@friend.com").id.values.tolist(),
            ['myid123']
        )

    def test_mark_emails_as_deleted(self):
        self.database.mark_emails_as_deleted(message_id_lst=['myid123'])
        self.assertEqual(len(self.database.get_all_emails(include_deleted=False)), 0)
        self.assertEqual(len(self.database.get_all_emails(include_deleted=True)), 1)

    def test_get_labels_to_update(self):
        # All new
        new_messages_lst, message_label_updates_lst, deleted_messages_lst = self.database.get_labels_to_update(
            message_id_lst=['myid456', 'myid789']
        )
        self.assertEqual(new_messages_lst, ['myid456', 'myid789'])
        self.assertEqual(message_label_updates_lst, [])
        self.assertEqual(deleted_messages_lst, ['myid123'])

        # All updates
        new_messages_lst, message_label_updates_lst, deleted_messages_lst = self.database.get_labels_to_update(
            message_id_lst=['myid123']
        )
        self.assertEqual(new_messages_lst, [])
        self.assertEqual(message_label_updates_lst, ['myid123'])
        self.assertEqual(deleted_messages_lst, [])

        # All deleted
        new_messages_lst, message_label_updates_lst, deleted_messages_lst = self.database.get_labels_to_update(
            message_id_lst=[]
        )
        self.assertEqual(new_messages_lst, [])
        self.assertEqual(message_label_updates_lst, [])
        self.assertEqual(deleted_messages_lst, ['myid123'])

    def test_update_labels(self):
        self.database.update_labels(message_id_lst=['myid123'], message_meta_lst=[['important', 'Label_456']])
        self.assertEqual(
            self.database.get_emails_by_label(label_id="Label_123").id.values.tolist(),
            []
        )
        self.assertEqual(
            self.database.get_emails_by_label(label_id="Label_456").id.values.tolist(),
            ['myid123']
        )
        self.database.update_labels(message_id_lst=['myid123'], message_meta_lst=[['important']])
        self.assertEqual(
            self.database.get_emails_by_label(label_id="Label_456").id.values.tolist(),
            []
        )
        self.database.update_labels(message_id_lst=['myid123'], message_meta_lst=[['important']])
        self.assertEqual(
            self.database.get_emails_by_label(label_id="Label_456").id.values.tolist(),
            []
        )

    def test_close(self):
        self.database._session.close = MagicMock()
        self.database.close()
        self.database._session.close.assert_called_once()

    def test_session(self):
        self.assertIsNotNone(self.database.session)

    def test_get_email_collection_include_deleted(self):
        self.assertEqual(len(self.database.get_email_collection(email_id_lst=['myid123'], include_deleted=True)), 1)

    def test_create_dataframe_no_from(self):
        df = pandas.DataFrame([{
            'content': None,
            'date': datetime.strptime("Fri, 11 Feb 2022 18:08:46 +0100", "%a, %d %b %Y %H:%M:%S %z"),
            'from': None,
            'id': 'myid456',
            'cc': [],
            'labels': [],
            'subject': 'Test Email Subject',
            'threads': 'abc456',
            'to': []
        }])
        self.database.store_dataframe(df=df)
        self.assertEqual(len(self.database.get_all_emails()), 2)
        self.assertIsNone(self.database.get_all_emails().iloc[1]["from"])
        self.assertEqual(len(self.database.get_emails_by_from(email_from=None)), 1)

    def test_create_dataframe_no_from_in_db(self):
        self.database.session.query(EmailFrom).filter(EmailFrom.id == 1).delete()
        self.database.session.commit()
        self.assertIsNone(self.database.get_all_emails().iloc[0]["from"])
