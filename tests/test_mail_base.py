from unittest import TestCase
from unittest.mock import MagicMock, patch

import pandas as pd

from gmailsorter.base.mail import AbstractMailBox


class _StubMailBox(AbstractMailBox):
    """Minimal concrete AbstractMailBox used to test the shared loop in isolation."""

    def __init__(self, label_dict_fixture=None, **kwargs):
        self.label_dict_fixture = label_dict_fixture or {
            "Inbox": "Inbox",
            "Spam": "Spam",
        }
        self.search_result = []
        self.message_detail_dict = {}
        self.modify_calls = []
        self.labels_for_email_dict = {}
        super().__init__(mail_service=MagicMock(), **kwargs)

    def _search_email_on_server(
        self, query_string="", label_lst=None, only_message_ids=False
    ):
        return self.search_result

    def _get_message_detail(self, message_id, email_format=None, metadata_headers=None):
        return self.message_detail_dict.get(message_id)

    def _get_label_translate_dict(self):
        return self.label_dict_fixture

    def _modify_message_labels(
        self, message_id, label_id_remove_lst=None, label_id_add_lst=None
    ):
        self.modify_calls.append((message_id, label_id_remove_lst, label_id_add_lst))

    def _get_labels_for_email(self, message_id):
        return self.labels_for_email_dict.get(message_id, [])

    def _parse_message(self, message):
        return message


class AbstractMailBoxTest(TestCase):
    def test_labels_property(self):
        mailbox = _StubMailBox()
        self.assertEqual(sorted(mailbox.labels), ["Inbox", "Spam"])

    def test_download_emails_for_label(self):
        mailbox = _StubMailBox()
        mailbox.search_result = ["id1", "id2"]
        mailbox.message_detail_dict = {
            "id1": {
                "id": "id1",
                "threads": "t1",
                "labels": [],
                "to": [],
                "from": None,
                "cc": [],
                "subject": "s1",
                "content": "c1",
                "date": None,
            },
            "id2": None,
        }

        df = mailbox.download_emails_for_label(label="Inbox")

        self.assertEqual(df["id"].tolist(), ["id1"])

    def test_move_emails_skips_matching_or_none_labels(self):
        mailbox = _StubMailBox()

        mailbox._move_emails(
            move_email_dict={"id1": None, "id2": "Inbox", "id3": "Spam"},
            label_to_ignore="Inbox",
        )

        self.assertEqual(mailbox.modify_calls, [("id3", ["Inbox"], ["Spam"])])

    def test_update_database_marks_missing_as_deleted(self):
        db_email = MagicMock()
        db_email.get_labels_to_update.return_value = (["new"], [], ["deleted"])
        mailbox = _StubMailBox(database_email=db_email)
        mailbox.search_result = ["new"]
        mailbox.message_detail_dict = {
            "new": {
                "id": "new",
                "threads": "t",
                "labels": [],
                "to": [],
                "from": None,
                "cc": [],
                "subject": "s",
                "content": "c",
                "date": None,
            }
        }

        mailbox.update_database(quick=False)

        db_email.mark_emails_as_deleted.assert_called_once_with(
            message_id_lst=["deleted"], user_id=1
        )
        db_email.store_dataframe.assert_called_once()

    @patch("gmailsorter.base.mail.fit_machine_learning_models")
    @patch("gmailsorter.base.mail.encode_df_for_machine_learning")
    def test_fit_machine_learning_model_to_database(self, encode_mock, fit_mock):
        db_email = MagicMock()
        db_email.get_all_emails.return_value = pd.DataFrame(
            [
                {
                    "id": "x",
                    "from": "a@b.com",
                    "to": [],
                    "cc": [],
                    "labels": [],
                    "threads": "t",
                }
            ]
        )
        db_ml = MagicMock()
        mailbox = _StubMailBox(database_email=db_email, database_ml=db_ml)
        features = pd.DataFrame([{"email_id": "x", "f1": 1}])
        labels = pd.DataFrame([{"labels_Inbox": 1}])
        encode_mock.return_value = (features, labels)
        mock_model = MagicMock()
        fit_mock.return_value = (mock_model, ["labels_Inbox"])

        mailbox.fit_machine_learning_model_to_database(n_estimators=5, max_features=2)

        db_ml.store_model.assert_called_once()
