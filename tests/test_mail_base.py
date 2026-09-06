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

    @patch("gmailsorter.base.mail.fit_machine_learning_models")
    @patch("gmailsorter.base.mail.encode_df_for_machine_learning")
    def test_fit_machine_learning_model_forwards_max_depth_and_min_samples_leaf(
        self, encode_mock, fit_mock
    ):
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
        fit_mock.return_value = (MagicMock(), ["labels_Inbox"])

        mailbox.fit_machine_learning_model_to_database(
            n_estimators=5, max_features=2, max_depth=10, min_samples_leaf=3
        )

        call_kwargs = fit_mock.call_args.kwargs
        self.assertEqual(call_kwargs["max_depth"], 10)
        self.assertEqual(call_kwargs["min_samples_leaf"], 3)

    @patch("gmailsorter.base.mail.get_predictions_from_machine_learning_models")
    @patch("gmailsorter.base.mail.encode_df_for_machine_learning")
    def test_filter_messages_from_server_no_model_skips(
        self, encode_mock, predict_mock
    ):
        db_ml = MagicMock()
        db_ml.load_model.return_value = (None, [], [])
        mailbox = _StubMailBox(database_ml=db_ml)
        df = pd.DataFrame(
            [{"id": "x", "from": "a", "to": [], "cc": [], "labels": [], "threads": "t"}]
        )
        with patch.object(mailbox, "download_emails_for_label", return_value=df):
            mailbox.filter_messages_from_server("Inbox")

        encode_mock.assert_not_called()
        predict_mock.assert_not_called()

    @patch("gmailsorter.base.mail.get_predictions_from_machine_learning_models")
    @patch("gmailsorter.base.mail.encode_df_for_machine_learning")
    def test_filter_messages_from_server_empty_df_skips(
        self, encode_mock, predict_mock
    ):
        db_ml = MagicMock()
        mailbox = _StubMailBox(database_ml=db_ml)
        with patch.object(
            mailbox, "download_emails_for_label", return_value=pd.DataFrame()
        ):
            mailbox.filter_messages_from_server("Inbox")

        encode_mock.assert_not_called()
        predict_mock.assert_not_called()

    @patch("gmailsorter.base.mail.get_predictions_from_machine_learning_models")
    @patch("gmailsorter.base.mail.encode_df_for_machine_learning")
    def test_filter_messages_from_server_with_model(self, encode_mock, predict_mock):
        db_ml = MagicMock()
        mock_model = MagicMock()
        db_ml.load_model.return_value = (mock_model, ["labels_Inbox"], ["f1"])
        mailbox = _StubMailBox(database_ml=db_ml)
        df = pd.DataFrame(
            [{"id": "x", "from": "a", "to": [], "cc": [], "labels": [], "threads": "t"}]
        )
        encoded = pd.DataFrame([{"email_id": "x", "f1": 1}])
        encode_mock.return_value = encoded
        predict_mock.return_value = {"x": "Spam"}

        with (
            patch.object(mailbox, "download_emails_for_label", return_value=df),
            patch.object(mailbox, "_move_emails") as move_mock,
        ):
            mailbox.filter_messages_from_server("Inbox", recommendation_ratio=0.7)

        encode_mock.assert_called_once()
        predict_mock.assert_called_once()
        move_mock.assert_called_once_with(
            move_email_dict={"x": "Spam"}, label_to_ignore="Inbox"
        )
