import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
from google.auth.exceptions import RefreshError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gmailsorter.google.authentication import create_service, validate_token
from gmailsorter.google.database import (
    Base,
    DatabaseInterface,
    GoogleToken,
    get_token_database,
)
from gmailsorter.google.mail import GoogleMailBase
from gmailsorter.local import Gmail, load_client_secrets_file


class TestGoogleAuthentication(unittest.TestCase):
    @patch("gmailsorter.google.authentication.InstalledAppFlow")
    def test_validate_token_uses_flow_when_refresh_fails(self, flow_cls):
        cred = MagicMock(expired=True, refresh_token="refresh")
        cred.refresh.side_effect = RefreshError("fail")
        new_cred = MagicMock()
        flow = flow_cls.from_client_config.return_value
        flow.run_local_server.return_value = new_cred

        result = validate_token(
            cred=cred,
            client_config={"installed": {}},
            scopes=["scope"],
            port=9999,
        )

        self.assertIs(result, new_cred)
        flow_cls.from_client_config.assert_called_once_with(
            client_config={"installed": {}}, scopes=["scope"]
        )
        flow.run_local_server.assert_called_once_with(open_browser=False, port=9999)

    @patch("gmailsorter.google.authentication.Request")
    @patch("gmailsorter.google.authentication.InstalledAppFlow")
    def test_validate_token_refreshes_valid_token(self, flow_cls, request_cls):
        cred = MagicMock(expired=True, refresh_token="refresh")

        result = validate_token(
            cred=cred,
            client_config={"installed": {}},
            scopes=["scope"],
        )

        self.assertIs(result, cred)
        cred.refresh.assert_called_once_with(request_cls.return_value)
        flow_cls.from_client_config.assert_not_called()

    @patch("gmailsorter.google.authentication.build")
    @patch("gmailsorter.google.authentication.validate_token")
    @patch("gmailsorter.google.authentication.Credentials")
    def test_create_service_with_existing_valid_token(
        self, credentials_cls, validate_token_mock, build_mock
    ):
        token = MagicMock(
            token="token",
            refresh_token="refresh",
            token_uri="uri",
            client_id="client",
            client_secret="secret",
            expiry=datetime.now(timezone.utc),
        )
        database = MagicMock()
        database.get_token.return_value = token
        cred = MagicMock(valid=True)
        credentials_cls.return_value = cred

        create_service(
            client_config={"installed": {}},
            api_name="gmail",
            api_version="v1",
            scopes=["scope"],
            database=database,
            database_user_id=7,
        )

        validate_token_mock.assert_not_called()
        database.update_token_with_dict.assert_not_called()
        build_mock.assert_called_once_with("gmail", "v1", credentials=cred)

    @patch("gmailsorter.google.authentication.build")
    @patch("gmailsorter.google.authentication.validate_token")
    def test_create_service_updates_token_after_validation(
        self, validate_token_mock, build_mock
    ):
        token = MagicMock(token=None)
        database = MagicMock()
        database.get_token.return_value = token
        fresh_cred = MagicMock(valid=True)
        validate_token_mock.return_value = fresh_cred

        create_service(
            client_config={"installed": {}},
            api_name="gmail",
            api_version="v1",
            scopes=["scope"],
            database=database,
            database_user_id=3,
        )

        validate_token_mock.assert_called_once()
        database.update_token_with_dict.assert_called_once_with(
            token=token, credentials=fresh_cred, commit=True
        )
        build_mock.assert_called_once_with("gmail", "v1", credentials=fresh_cred)


class TestGoogleTokenDatabase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        session = sessionmaker(bind=self.engine)
        self.session = session()
        self.db = DatabaseInterface(session=self.session)

    def tearDown(self):
        self.session.close()

    def test_get_token_returns_new_token_when_missing(self):
        token = self.db.get_token(user_id=11)
        self.assertIsNone(token.token)
        self.assertEqual(token.user_id, 11)

    def test_update_token_with_dict_adds_new_and_updates_existing(self):
        token = GoogleToken(user_id=5)
        cred = MagicMock(
            token="tok",
            refresh_token="ref",
            token_uri="uri",
            client_id="id",
            client_secret="sec",
            expiry=datetime.now(timezone.utc),
        )

        self.db.update_token_with_dict(token=token, credentials=cred, commit=True)
        self.assertEqual(self.session.query(GoogleToken).count(), 1)

        stored = self.db.get_token(user_id=5)
        cred_new = MagicMock(
            token="tok2",
            refresh_token="ref2",
            token_uri="uri2",
            client_id="id2",
            client_secret="sec2",
            expiry=datetime.now(timezone.utc) + timedelta(days=1),
        )
        self.db.update_token_with_dict(token=stored, credentials=cred_new, commit=True)

        updated = self.db.get_token(user_id=5)
        self.assertEqual(updated.token, "tok2")
        self.assertEqual(updated.refresh_token, "ref2")

    def test_token_to_dict_and_get_token_database(self):
        token = GoogleToken(
            token="tok",
            refresh_token="ref",
            token_uri="uri",
            client_id="id",
            client_secret="sec",
            expiry=datetime.now(timezone.utc),
            user_id=2,
        )
        self.session.add(token)
        self.session.commit()

        token_dict = DatabaseInterface.token_to_dict(token)
        self.assertEqual(token_dict["token"], "tok")
        self.assertEqual(token_dict["scopes"], ["https://mail.google.com/"])

        db_interface = get_token_database(self.engine, self.session)
        self.assertIsInstance(db_interface, DatabaseInterface)


class TestGoogleMailBase(unittest.TestCase):
    def _service_with_labels(self, labels=None):
        service = MagicMock()
        service.users.return_value.labels.return_value.list.return_value.execute.return_value = {
            "labels": labels
            if labels is not None
            else [{"name": "Inbox", "id": "LBL_INBOX"}, {"name": "Spam", "id": "LBL_SPAM"}]
        }
        return service

    def test_search_messages_and_paginate(self):
        service = self._service_with_labels()
        service.users.return_value.messages.return_value.list.return_value.execute.side_effect = [
            {"messages": [{"id": "a"}], "nextPageToken": "NEXT"},
            {"messages": [{"id": "b"}]},
        ]
        mail = GoogleMailBase(google_mail_service=service)

        full = mail._search_email_on_server(label_lst=["Inbox"], only_message_ids=False)
        service.users.return_value.messages.return_value.list.return_value.execute.side_effect = [
            {"messages": [{"id": "a"}], "nextPageToken": "NEXT"},
            {"messages": [{"id": "b"}]},
        ]
        ids = mail._search_email_on_server(label_lst=["Inbox"], only_message_ids=True)

        self.assertEqual(full, [{"id": "a"}, {"id": "b"}])
        self.assertEqual(ids, ["a", "b"])

    def test_get_message_detail_default_arguments(self):
        service = self._service_with_labels()
        get_execute = service.users.return_value.messages.return_value.get.return_value.execute
        get_execute.return_value = {"id": "x"}
        mail = GoogleMailBase(google_mail_service=service, email_download_format="full")

        result = mail._get_message_detail(message_id="x")

        self.assertEqual(result, {"id": "x"})
        service.users.return_value.messages.return_value.get.assert_called_once_with(
            userId="me", id="x", format="full", metadataHeaders=[]
        )

    def test_modify_message_labels_only_when_needed(self):
        service = self._service_with_labels()
        mail = GoogleMailBase(google_mail_service=service)

        mail._modify_message_labels(message_id="x")
        service.users.return_value.messages.return_value.modify.assert_not_called()

        mail._modify_message_labels(
            message_id="x", label_id_remove_lst=["old"], label_id_add_lst=["new"]
        )
        service.users.return_value.messages.return_value.modify.assert_called_once_with(
            userId="me", id="x", body={"removeLabelIds": ["old"], "addLabelIds": ["new"]}
        )

    @patch("gmailsorter.google.mail.get_email_dict")
    def test_download_messages_dataframe_filters_none(self, get_email_dict_mock):
        service = self._service_with_labels()
        mail = GoogleMailBase(google_mail_service=service)
        message_a = {"id": "a"}
        message_b = {"id": "b"}
        get_email_dict_mock.side_effect = [
            {
                "id": "a",
                "threads": "t",
                "labels": [],
                "to": [],
                "from": None,
                "cc": [],
                "subject": "s",
                "content": "c",
                "date": datetime.now(timezone.utc),
            },
            None,
        ]

        with patch.object(mail, "_get_message_detail", side_effect=[message_a, message_b]):
            df = mail._download_messages_to_dataframe(["a", "b"])

        self.assertEqual(df["id"].tolist(), ["a"])

    def test_get_labels_for_email_and_emails(self):
        service = self._service_with_labels()
        mail = GoogleMailBase(google_mail_service=service)

        with patch.object(mail, "_get_message_detail", return_value={"labelIds": ["L1"]}):
            self.assertEqual(mail._get_labels_for_email("x"), ["L1"])

        with patch.object(mail, "_get_message_detail", return_value={}):
            self.assertEqual(mail._get_labels_for_email("x"), [])

        with patch.object(mail, "_get_labels_for_email", side_effect=[["L1"], []]):
            labels = mail._get_labels_for_emails(["a", "b"])
        self.assertEqual(labels, [["L1"], []])

    def test_move_emails_and_store_to_database(self):
        service = self._service_with_labels()
        db_email = MagicMock()
        mail = GoogleMailBase(google_mail_service=service, database_email=db_email)

        with patch.object(mail, "_modify_message_labels") as modify_mock:
            mail._move_emails(
                {"id1": None, "id2": "LBL_INBOX", "id3": "LBL_SPAM"},
                label_to_ignore="Inbox",
            )
        modify_mock.assert_called_once_with(
            message_id="id3",
            label_id_remove_lst=["LBL_INBOX"],
            label_id_add_lst=["LBL_SPAM"],
        )

        with patch.object(
            mail,
            "_download_messages_to_dataframe",
            return_value=pd.DataFrame([{"id": "x"}]),
        ):
            mail._store_emails_in_database(["x"])
        db_email.store_dataframe.assert_called_once()

        db_email.store_dataframe.reset_mock()
        with patch.object(mail, "_download_messages_to_dataframe", return_value=pd.DataFrame()):
            mail._store_emails_in_database(["x"])
        db_email.store_dataframe.assert_not_called()

    def test_update_database_quick_and_full_paths(self):
        service = self._service_with_labels()
        db_email = MagicMock()
        db_email.get_labels_to_update.return_value = (["new"], ["update"], ["deleted"])
        mail = GoogleMailBase(google_mail_service=service, database_email=db_email)

        with patch.object(mail, "_search_email_on_server", return_value=["new", "update"]), patch.object(
            mail, "_get_labels_for_emails", return_value=[["LBL_INBOX"]]
        ), patch.object(mail, "_store_emails_in_database") as store_mock:
            mail.update_database(quick=False, label_lst=["Inbox"])

        db_email.mark_emails_as_deleted.assert_called_once_with(
            message_id_lst=["deleted"], user_id=1
        )
        db_email.update_labels.assert_called_once()
        store_mock.assert_called_once_with(message_id_lst=["new"], email_format=None)

        db_email.reset_mock()
        db_email.get_labels_to_update.return_value = (["new2"], ["update2"], ["deleted2"])
        with patch.object(mail, "_search_email_on_server", return_value=["new2", "update2"]), patch.object(
            mail, "_store_emails_in_database"
        ) as store_mock:
            mail.update_database(quick=True)

        db_email.mark_emails_as_deleted.assert_not_called()
        db_email.update_labels.assert_not_called()
        store_mock.assert_called_once_with(message_id_lst=["new2"], email_format=None)

    @patch("gmailsorter.google.mail.get_predictions_from_machine_learning_models")
    @patch("gmailsorter.google.mail.encode_df_for_machine_learning")
    def test_filter_messages_from_server(self, encode_mock, predict_mock):
        service = self._service_with_labels()
        db_ml = MagicMock()
        db_ml.load_models.return_value = ({"LBL_SPAM": MagicMock()}, ["f1"])
        mail = GoogleMailBase(google_mail_service=service, database_ml=db_ml)

        df = pd.DataFrame([{"id": "x", "from": "a", "to": [], "cc": [], "labels": [], "threads": "t"}])
        encoded = pd.DataFrame([{"email_id": "x", "f1": 1}])
        encode_mock.return_value = encoded
        predict_mock.return_value = {"x": "LBL_SPAM"}

        with patch.object(mail, "download_emails_for_label", return_value=df), patch.object(
            mail, "_move_emails"
        ) as move_mock:
            mail.filter_messages_from_server("Inbox", recommendation_ratio=0.6)

        encode_mock.assert_called_once()
        predict_mock.assert_called_once()
        move_mock.assert_called_once_with(
            move_email_dict={"x": "LBL_SPAM"}, label_to_ignore="Inbox"
        )

        encode_mock.reset_mock()
        with patch.object(mail, "download_emails_for_label", return_value=pd.DataFrame()):
            mail.filter_messages_from_server("Inbox")
        encode_mock.assert_not_called()

    @patch("gmailsorter.google.mail.fit_machine_learning_models")
    @patch("gmailsorter.google.mail.encode_df_for_machine_learning")
    def test_fit_machine_learning_model_to_database(self, encode_mock, fit_mock):
        service = self._service_with_labels()
        db_ml = MagicMock()
        db_email = MagicMock()
        mail = GoogleMailBase(google_mail_service=service, database_email=db_email, database_ml=db_ml)

        df_all = pd.DataFrame(
            [
                {
                    "id": "x",
                    "from": "from@test.com",
                    "to": ["to@test.com"],
                    "cc": [],
                    "labels": ["LBL_INBOX"],
                    "threads": "t",
                }
            ]
        )
        db_email.get_all_emails.return_value = df_all
        features = pd.DataFrame([{"email_id": "x", "f1": 1, "f1": 1}])
        labels = pd.DataFrame([{"labels_LBL_INBOX": 1}])
        encode_mock.return_value = (features, labels)
        fit_mock.return_value = {"LBL_INBOX": MagicMock()}

        mail.fit_machine_learning_model_to_database(n_estimators=5, max_features=2)

        db_ml.store_models.assert_called_once()
        self.assertEqual(mail.get_all_emails_in_database().iloc[0]["id"], "x")

    @patch("gmailsorter.google.mail.get_token_database")
    @patch("gmailsorter.google.mail.get_machine_learning_database")
    @patch("gmailsorter.google.mail.get_email_database")
    @patch("gmailsorter.google.mail.sessionmaker")
    @patch("gmailsorter.google.mail.create_engine")
    def test_create_databases_and_get_message_ids(
        self,
        create_engine_mock,
        sessionmaker_mock,
        get_email_db_mock,
        get_ml_db_mock,
        get_token_db_mock,
    ):
        engine = MagicMock()
        session = MagicMock()
        create_engine_mock.return_value = engine
        sessionmaker_mock.return_value.return_value = session
        get_email_db_mock.return_value = "EMAIL_DB"
        get_ml_db_mock.return_value = "ML_DB"
        get_token_db_mock.return_value = "TOKEN_DB"

        dbs = GoogleMailBase._create_databases("sqlite:///file.db")
        ids = GoogleMailBase._get_message_ids([{"id": "a"}, {"id": "b"}])

        self.assertEqual(dbs, ("EMAIL_DB", "ML_DB", "TOKEN_DB"))
        self.assertEqual(ids, ["a", "b"])


class TestLocalHelpers(unittest.TestCase):
    def test_load_client_secrets_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as f:
            json.dump({"installed": {"client_id": "abc"}}, f)
            f.flush()
            loaded = load_client_secrets_file(f.name)
        self.assertEqual(loaded["installed"]["client_id"], "abc")

    @patch("gmailsorter.local.GoogleMailBase.__init__", return_value=None)
    @patch("gmailsorter.local.create_service")
    @patch("gmailsorter.local.Gmail._create_databases")
    def test_gmail_initialization_wiring(
        self, create_databases_mock, create_service_mock, base_init_mock
    ):
        db_email, db_ml, db_token = MagicMock(), MagicMock(), MagicMock()
        create_databases_mock.return_value = (db_email, db_ml, db_token)
        service = MagicMock()
        create_service_mock.return_value = service

        Gmail(
            client_config={"installed": {}},
            connection_str="sqlite:///:memory:",
            user_id="me",
            db_user_id=4,
            port=9090,
            email_download_format="full",
        )

        create_databases_mock.assert_called_once_with(connection_str="sqlite:///:memory:")
        create_service_mock.assert_called_once_with(
            client_config={"installed": {}},
            api_name="gmail",
            api_version="v1",
            scopes=["https://mail.google.com/"],
            database=db_token,
            database_user_id=4,
            port=9090,
        )
        base_init_mock.assert_called_once_with(
            google_mail_service=service,
            database_email=db_email,
            database_ml=db_ml,
            database_token=db_token,
            user_id="me",
            db_user_id=4,
            email_download_format="full",
        )


if __name__ == "__main__":
    unittest.main()
