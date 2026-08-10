import imaplib
from unittest import TestCase
from unittest.mock import MagicMock, patch

from gmailsorter.imap.authentication import create_service
from gmailsorter.imap.mail import ImapMailBase
from gmailsorter.local import Imap


class ReconnectingImapMailBase(ImapMailBase):
    """
    Test double which reconnects by swapping in the next prepared mock connection.

    This stands in for gmailsorter.local.Imap, which is the class that actually knows
    the connection details, without requiring a real IMAP server.
    """

    def __init__(self, service_lst, **kwargs):
        self.reconnect_count = 0
        self._service_lst = list(service_lst)
        super().__init__(mail_service=self._service_lst.pop(0), **kwargs)

    def _reconnect(self):
        self.reconnect_count += 1
        self._service = self._service_lst.pop(0)


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

    def test_get_label_translate_dict_skips_special_use_attributes(self):
        service = self._create_mock_service_with_folders(
            folders=[
                b'(\\HasNoChildren \\Trash) "/" "Papierkorb"',
                b'(\\HasNoChildren \\Junk) "/" "Unerwuenscht"',
                b'(\\HasNoChildren \\Sent) "/" "Gesendet"',
                b'(\\HasNoChildren \\Drafts) "/" "Entwuerfe"',
                b'(\\HasNoChildren \\Archive) "/" "Ablage"',
                b'(\\HasNoChildren \\All) "/" "Alle"',
                b'(\\HasNoChildren \\Flagged) "/" "Markiert"',
                b'(\\HasNoChildren) "/" "MailSortInbox"',
            ]
        )
        mail = ImapMailBase(mail_service=service)

        self.assertEqual(mail.labels, ["MailSortInbox"])

    def test_get_label_translate_dict_skips_special_names_without_attributes(self):
        service = self._create_mock_service_with_folders(
            folders=[
                b'(\\HasNoChildren) "/" "Trash"',
                b'(\\HasNoChildren) "/" "junk e-mail"',
                b'(\\HasNoChildren) "/" "Deleted Items"',
                b'(\\HasNoChildren) "/" "SPAM"',
                b'(\\HasNoChildren) "/" "Sent Items"',
                b'(\\HasNoChildren) "/" "Drafts"',
                b'(\\HasNoChildren) "/" "All Mail"',
                b'(\\HasNoChildren) "/" "[Gmail]/Trash"',
                b'(\\HasNoChildren) "/" "MailSortInbox"',
            ]
        )
        mail = ImapMailBase(mail_service=service)

        self.assertEqual(mail.labels, ["MailSortInbox"])

    def test_get_label_translate_dict_keeps_custom_folders(self):
        service = self._create_mock_service_with_folders(
            folders=[
                b'(\\HasNoChildren) "/" "MailSortInbox"',
                b'(\\HasNoChildren) "/" "Sorted"',
                b'(\\HasNoChildren) "/" "Archived Projects"',
                b'(\\HasNoChildren) "/" "Trashcan Design"',
                b'(\\HasNoChildren) "/" "INBOX"',
            ]
        )
        mail = ImapMailBase(mail_service=service)

        self.assertEqual(
            sorted(mail.labels),
            [
                "Archived Projects",
                "INBOX",
                "MailSortInbox",
                "Sorted",
                "Trashcan Design",
            ],
        )

    def test_get_label_translate_dict_accepts_nil_delimiter(self):
        service = self._create_mock_service_with_folders(
            folders=[b"(\\HasNoChildren) NIL INBOX"]
        )
        mail = ImapMailBase(mail_service=service)

        self.assertEqual(mail.labels, ["INBOX"])

    def test_get_label_translate_dict_accepts_literal_name_tuple(self):
        service = self._create_mock_service_with_folders(
            folders=[(b'(\\HasNoChildren) "/" {11}', b"MailSortBox"), b")"]
        )
        mail = ImapMailBase(mail_service=service)

        self.assertEqual(mail.labels, ["MailSortBox"])

    def test_get_label_translate_dict_handles_empty_mailbox_list(self):
        service = self._create_mock_service_with_folders(folders=[None])
        mail = ImapMailBase(mail_service=service)

        self.assertEqual(mail.labels, [])

    def test_get_label_translate_dict_returns_empty_on_list_failure(self):
        service = self._create_mock_service_with_folders()
        service.list.return_value = ("NO", None)
        mail = ImapMailBase(mail_service=service)

        self.assertEqual(mail.labels, [])

    def test_get_label_translate_dict_skips_unparseable_entries(self):
        service = self._create_mock_service_with_folders(
            folders=[b"total garbage", b'(\\HasNoChildren) "/" "MailSortInbox"']
        )
        mail = ImapMailBase(mail_service=service)

        self.assertEqual(mail.labels, ["MailSortInbox"])

    def test_parse_list_entry_returns_none_for_unparseable_input(self):
        self.assertIsNone(ImapMailBase._parse_list_entry(None))
        self.assertIsNone(ImapMailBase._parse_list_entry(b"not a list response"))
        self.assertIsNone(ImapMailBase._parse_list_entry((b'(\\Noselect) "/" {3}',)))
        self.assertIsNone(ImapMailBase._parse_list_entry(b'(\\HasNoChildren) "/" '))

    def test_parse_list_entry_returns_none_when_literal_name_undecodable(self):
        self.assertIsNone(
            ImapMailBase._parse_list_entry((b'(\\HasNoChildren) "/" {3}', None))
        )

    def test_parse_list_entry_accepts_plain_str_entry(self):
        result = ImapMailBase._parse_list_entry('(\\HasNoChildren) "/" "INBOX"')

        self.assertEqual(result, (["\\HasNoChildren"], "/", "INBOX"))

    def test_parse_list_entry_falls_back_to_latin1_on_invalid_utf8(self):
        result = ImapMailBase._parse_list_entry(b'(\\HasNoChildren) "/" "Caf\xe9"')

        self.assertEqual(result, (["\\HasNoChildren"], "/", "Caf\xe9"))

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

    def test_search_email_on_server_returns_dicts_by_default(self):
        service = self._create_mock_service_with_folders()
        service.select.return_value = ("OK", [b"1"])
        service.uid.return_value = ("OK", [b"1 2"])
        mail = ImapMailBase(mail_service=service)

        result = mail._search_email_on_server(label_lst=["INBOX"])

        self.assertEqual(result, [{"id": "INBOX\x1f1"}, {"id": "INBOX\x1f2"}])

    def test_search_folder_returns_empty_list_when_select_fails(self):
        service = self._create_mock_service_with_folders()
        service.select.return_value = ("NO", [b"failed"])
        mail = ImapMailBase(mail_service=service)

        ids = mail._search_email_on_server(label_lst=["INBOX"], only_message_ids=True)

        service.uid.assert_not_called()
        self.assertEqual(ids, [])

    def test_search_folder_returns_empty_list_when_search_fails(self):
        service = self._create_mock_service_with_folders()
        service.select.return_value = ("OK", [b"1"])
        service.uid.return_value = ("NO", [None])
        mail = ImapMailBase(mail_service=service)

        ids = mail._search_email_on_server(label_lst=["INBOX"], only_message_ids=True)

        self.assertEqual(ids, [])

    def test_search_folder_returns_empty_list_when_search_data_is_none(self):
        service = self._create_mock_service_with_folders()
        service.select.return_value = ("OK", [b"1"])
        service.uid.return_value = ("OK", [None])
        mail = ImapMailBase(mail_service=service)

        ids = mail._search_email_on_server(label_lst=["INBOX"], only_message_ids=True)

        self.assertEqual(ids, [])

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

    def test_get_message_detail_raises_when_select_fails(self):
        service = self._create_mock_service_with_folders()
        service.select.return_value = ("NO", [b"failed"])
        mail = ImapMailBase(mail_service=service)

        with self.assertRaises(RuntimeError):
            mail._get_message_detail(message_id="INBOX\x1f7")

    def test_get_message_detail_raises_when_fetch_fails(self):
        service = self._create_mock_service_with_folders()
        service.select.return_value = ("OK", [b"1"])
        service.uid.return_value = ("NO", [None])
        mail = ImapMailBase(mail_service=service)

        with self.assertRaises(RuntimeError):
            mail._get_message_detail(message_id="INBOX\x1f7")

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

    def test_modify_message_labels_uses_uid_expunge_with_uidplus(self):
        service = self._create_mock_service_with_folders()
        service.capabilities = ["IMAP4rev1", "UIDPLUS"]
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
                (("expunge", "7"),),
            ],
        )
        service.expunge.assert_not_called()

    def test_modify_message_labels_raises_when_select_fails(self):
        service = self._create_mock_service_with_folders()
        service.select.return_value = ("NO", [b"failed"])
        mail = ImapMailBase(mail_service=service)

        with self.assertRaises(RuntimeError):
            mail._modify_message_labels(
                message_id="INBOX\x1f7", label_id_add_lst=["MailSortInbox"]
            )

    def test_modify_message_labels_raises_when_move_fails(self):
        service = self._create_mock_service_with_folders()
        service.select.return_value = ("OK", [b"1"])
        service.uid.return_value = ("NO", [None])
        mail = ImapMailBase(mail_service=service)

        with self.assertRaises(RuntimeError):
            mail._modify_message_labels(
                message_id="INBOX\x1f7", label_id_add_lst=["MailSortInbox"]
            )

    def test_modify_message_labels_raises_when_copy_fails(self):
        service = self._create_mock_service_with_folders()
        service.capabilities = ["IMAP4rev1"]
        service.select.return_value = ("OK", [b"1"])
        service.uid.return_value = ("NO", [None])
        mail = ImapMailBase(mail_service=service)

        with self.assertRaises(RuntimeError):
            mail._modify_message_labels(
                message_id="INBOX\x1f7", label_id_add_lst=["MailSortInbox"]
            )

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

    def test_close_logs_out(self):
        service = self._create_mock_service_with_folders()
        mail = ImapMailBase(mail_service=service)

        mail.close()

        service.logout.assert_called_once_with()

    def test_close_ignores_logout_failure(self):
        for error in (imaplib.IMAP4.abort("connection lost"), OSError("socket gone")):
            with self.subTest(error=type(error).__name__):
                service = self._create_mock_service_with_folders()
                service.logout.side_effect = error
                mail = ImapMailBase(mail_service=service)

                mail.close()

                service.logout.assert_called_once_with()

    def test_context_manager_closes_connection(self):
        service = self._create_mock_service_with_folders()

        with ImapMailBase(mail_service=service) as mail:
            self.assertEqual(sorted(mail.labels), ["INBOX", "MailSortInbox"])
            service.logout.assert_not_called()

        service.logout.assert_called_once_with()

    def test_abort_propagates_without_reconnect_support(self):
        service = self._create_mock_service_with_folders()
        mail = ImapMailBase(mail_service=service)
        service.select.side_effect = imaplib.IMAP4.abort("connection lost")

        with self.assertRaises(imaplib.IMAP4.abort):
            mail._search_email_on_server(label_lst=["INBOX"], only_message_ids=True)

    def test_search_reconnects_and_retries_once_after_abort(self):
        dead_service = self._create_mock_service_with_folders()
        dead_service.select.side_effect = imaplib.IMAP4.abort("connection lost")
        fresh_service = self._create_mock_service_with_folders()
        fresh_service.select.return_value = ("OK", [b"1"])
        fresh_service.uid.return_value = ("OK", [b"3"])
        mail = ReconnectingImapMailBase(service_lst=[dead_service, fresh_service])

        ids = mail._search_email_on_server(label_lst=["INBOX"], only_message_ids=True)

        self.assertEqual(mail.reconnect_count, 1)
        self.assertEqual(ids, ["INBOX\x1f3"])

    def test_get_message_detail_reconnects_and_retries_once_after_abort(self):
        raw_message = b"Subject: hi\r\nFrom: a@b.com\r\nTo: c@d.com\r\n\r\nbody"
        dead_service = self._create_mock_service_with_folders()
        dead_service.select.side_effect = imaplib.IMAP4.abort("connection lost")
        fresh_service = self._create_mock_service_with_folders()
        fresh_service.select.return_value = ("OK", [b"1"])
        fresh_service.uid.return_value = ("OK", [(b"1 (BODY[] {10}", raw_message)])
        mail = ReconnectingImapMailBase(service_lst=[dead_service, fresh_service])

        folder, uid, message = mail._get_message_detail(message_id="INBOX\x1f7")

        self.assertEqual(mail.reconnect_count, 1)
        self.assertEqual((folder, uid), ("INBOX", "7"))
        self.assertEqual(message["Subject"], "hi")

    def test_retry_is_attempted_only_once(self):
        dead_service = self._create_mock_service_with_folders()
        dead_service.select.side_effect = imaplib.IMAP4.abort("connection lost")
        still_dead_service = self._create_mock_service_with_folders()
        still_dead_service.select.side_effect = imaplib.IMAP4.abort("connection lost")
        mail = ReconnectingImapMailBase(
            service_lst=[dead_service, still_dead_service],
        )

        with self.assertRaises(imaplib.IMAP4.abort):
            mail._search_email_on_server(label_lst=["INBOX"], only_message_ids=True)

        self.assertEqual(mail.reconnect_count, 1)


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

    @patch("gmailsorter.local.ImapMailBase.__init__", return_value=None)
    @patch("gmailsorter.local.create_imap_service")
    @patch("gmailsorter.local.Imap._create_databases")
    def test_imap_reconnect_replaces_the_connection(
        self, create_databases_mock, create_service_mock, base_init_mock
    ):
        create_databases_mock.return_value = (MagicMock(), MagicMock())
        dead_connection, fresh_connection = MagicMock(), MagicMock()
        create_service_mock.side_effect = [dead_connection, fresh_connection]

        imap = Imap(
            host="mail.example.test",
            port=143,
            username="user",
            password="secret",
            connection_str="sqlite:///:memory:",
            use_ssl=False,
        )
        # ImapMailBase.__init__ is mocked out above, so _service is set by hand here
        imap._service = dead_connection

        imap._reconnect()

        dead_connection.logout.assert_called_once_with()
        self.assertIs(imap._service, fresh_connection)
        create_service_mock.assert_called_with(
            host="mail.example.test",
            port=143,
            username="user",
            password="secret",
            use_ssl=False,
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
