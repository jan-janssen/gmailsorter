from unittest import TestCase
from unittest.mock import MagicMock, patch

from gmailsorter.imap.authentication import create_service
from gmailsorter.imap.mail import ImapMailBase
from gmailsorter.local import Imap


class TestImapAuthentication(TestCase):
    @patch("gmailsorter.imap.authentication.IMAP4_SSL")
    def test_create_service_uses_ssl_by_default(self, imap_ssl_cls):
        connection = imap_ssl_cls.return_value

        result = create_service(
            host="localhost", port=993, username="user", password="secret"
        )

        imap_ssl_cls.assert_called_once_with("localhost", 993)
        connection.login.assert_called_once_with("user", "secret")
        self.assertIs(result, connection)

    @patch("gmailsorter.imap.authentication.IMAP4")
    def test_create_service_without_ssl(self, imap_cls):
        connection = imap_cls.return_value

        result = create_service(
            host="localhost",
            port=143,
            username="user",
            password="secret",
            use_ssl=False,
        )

        imap_cls.assert_called_once_with("localhost", 143)
        connection.login.assert_called_once_with("user", "secret")
        self.assertIs(result, connection)


class TestImapMailBase(TestCase):
    def _create_mock_service_with_folders(self, folders=None):
        service = MagicMock()
        service.capabilities = ["IMAP4rev1", "MOVE"]
        if folders is None:
            folders = [
                b'(\\HasNoChildren) "/" "INBOX"',
                b'(\\HasNoChildren) "/" "MailSortInbox"',
                b'(\\Noselect \\HasChildren) "/" "[Gmail]"',
            ]
        service.list.return_value = ("OK", folders)
        return service

    def test_get_label_translate_dict_skips_noselect(self):
        service = self._create_mock_service_with_folders()
        mail = ImapMailBase(mail_service=service)

        self.assertEqual(sorted(mail.labels), ["INBOX", "MailSortInbox"])

    def test_search_email_on_server_single_folder(self):
        service = self._create_mock_service_with_folders()
        service.select.return_value = ("OK", [b"1"])
        service.uid.return_value = ("OK", [b"1 2"])
        mail = ImapMailBase(mail_service=service)

        ids = mail._search_email_on_server(label_lst=["INBOX"], only_message_ids=True)

        service.select.assert_called_once_with('"INBOX"')
        service.uid.assert_called_once_with("search", None, "ALL")
        self.assertEqual(ids, ["INBOX\x1f1", "INBOX\x1f2"])

    def test_search_email_on_server_all_folders_when_no_label(self):
        service = self._create_mock_service_with_folders()
        service.select.return_value = ("OK", [b"1"])
        service.uid.return_value = ("OK", [b"5"])
        mail = ImapMailBase(mail_service=service)

        ids = mail._search_email_on_server(only_message_ids=True)

        self.assertEqual(
            service.select.call_args_list,
            [(('"INBOX"',),), (('"MailSortInbox"',),)],
        )
        self.assertEqual(ids, ["INBOX\x1f5", "MailSortInbox\x1f5"])

    def test_search_email_on_server_rejects_query_string(self):
        service = self._create_mock_service_with_folders()
        mail = ImapMailBase(mail_service=service)

        with self.assertRaises(NotImplementedError):
            mail._search_email_on_server(query_string="SUBJECT foo")

    def test_get_message_detail_selects_and_fetches(self):
        service = self._create_mock_service_with_folders()
        raw_message = b"Subject: hi\r\nFrom: a@b.com\r\nTo: c@d.com\r\n\r\nbody"
        service.select.return_value = ("OK", [b"1"])
        service.uid.return_value = ("OK", [(b"1 (BODY[] {10}", raw_message)])
        mail = ImapMailBase(mail_service=service)

        folder, uid, message = mail._get_message_detail(message_id="INBOX\x1f7")

        service.select.assert_called_once_with('"INBOX"')
        service.uid.assert_called_once_with("fetch", "7", "(BODY.PEEK[])")
        self.assertEqual(folder, "INBOX")
        self.assertEqual(uid, "7")
        self.assertEqual(message["Subject"], "hi")

    def test_get_labels_for_email_from_composite_id(self):
        service = self._create_mock_service_with_folders()
        mail = ImapMailBase(mail_service=service)

        self.assertEqual(mail._get_labels_for_email("INBOX\x1f7"), ["INBOX"])

    def test_modify_message_labels_uses_move_when_supported(self):
        service = self._create_mock_service_with_folders()
        service.select.return_value = ("OK", [b"1"])
        service.uid.return_value = ("OK", [b"1"])
        mail = ImapMailBase(mail_service=service)

        mail._modify_message_labels(
            message_id="INBOX\x1f7",
            label_id_remove_lst=["INBOX"],
            label_id_add_lst=["MailSortInbox"],
        )

        service.select.assert_called_once_with('"INBOX"')
        service.uid.assert_called_once_with("move", "7", '"MailSortInbox"')
        service.expunge.assert_not_called()

    def test_modify_message_labels_falls_back_to_copy_delete(self):
        service = self._create_mock_service_with_folders()
        service.capabilities = ["IMAP4rev1"]
        service.select.return_value = ("OK", [b"1"])
        service.uid.return_value = ("OK", [b"1"])
        mail = ImapMailBase(mail_service=service)

        mail._modify_message_labels(
            message_id="INBOX\x1f7",
            label_id_remove_lst=["INBOX"],
            label_id_add_lst=["MailSortInbox"],
        )

        self.assertEqual(
            service.uid.call_args_list,
            [
                (("copy", "7", '"MailSortInbox"'),),
                (("store", "7", "+FLAGS", r"(\Deleted)"),),
            ],
        )
        service.expunge.assert_called_once()

    def test_modify_message_labels_noop_without_target(self):
        service = self._create_mock_service_with_folders()
        mail = ImapMailBase(mail_service=service)

        mail._modify_message_labels(message_id="INBOX\x1f7")

        service.select.assert_not_called()

    @patch("gmailsorter.imap.mail.get_email_dict")
    def test_parse_message_delegates_to_get_email_dict(self, get_email_dict_mock):
        service = self._create_mock_service_with_folders()
        mail = ImapMailBase(mail_service=service)
        get_email_dict_mock.return_value = {"id": "INBOX\x1f7"}

        result = mail._parse_message(("INBOX", "7", "raw"))

        get_email_dict_mock.assert_called_once_with(
            message="raw", folder="INBOX", uid="7"
        )
        self.assertEqual(result, {"id": "INBOX\x1f7"})

    def test_create_databases(self):
        with (
            patch("gmailsorter.imap.mail.create_engine") as create_engine_mock,
            patch("gmailsorter.imap.mail.sessionmaker") as sessionmaker_mock,
            patch("gmailsorter.imap.mail.get_email_database") as get_email_db_mock,
            patch(
                "gmailsorter.imap.mail.get_machine_learning_database"
            ) as get_ml_db_mock,
        ):
            engine = MagicMock()
            session = MagicMock()
            create_engine_mock.return_value = engine
            sessionmaker_mock.return_value.return_value = session
            get_email_db_mock.return_value = "EMAIL_DB"
            get_ml_db_mock.return_value = "ML_DB"

            dbs = ImapMailBase._create_databases("sqlite:///file.db")

        self.assertEqual(dbs, ("EMAIL_DB", "ML_DB"))


class TestImapLocalHelpers(TestCase):
    @patch("gmailsorter.local.ImapMailBase.__init__", return_value=None)
    @patch("gmailsorter.local.create_imap_service")
    @patch("gmailsorter.local.Imap._create_databases")
    def test_imap_initialization_wiring(
        self, create_databases_mock, create_service_mock, base_init_mock
    ):
        db_email, db_ml = MagicMock(), MagicMock()
        create_databases_mock.return_value = (db_email, db_ml)
        connection = MagicMock()
        create_service_mock.return_value = connection

        Imap(
            host="localhost",
            port=993,
            username="user",
            password="secret",
            connection_str="sqlite:///:memory:",
            db_user_id=4,
        )

        create_databases_mock.assert_called_once_with(
            connection_str="sqlite:///:memory:"
        )
        create_service_mock.assert_called_once_with(
            host="localhost",
            port=993,
            username="user",
            password="secret",
            use_ssl=True,
        )
        base_init_mock.assert_called_once_with(
            mail_service=connection,
            database_email=db_email,
            database_ml=db_ml,
            user_id="user",
            db_user_id=4,
            email_download_format="metadata",
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
