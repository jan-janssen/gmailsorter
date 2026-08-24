import os
from unittest import TestCase
from unittest.mock import patch

from gmailsorter.imap.__main__ import command_line_parser


class ImapCliTest(TestCase):
    @patch("gmailsorter.imap.__main__.Imap")
    def test_update_wires_imap_and_triggers_update(self, imap_cls):
        imap_instance = imap_cls.return_value
        os.environ["IMAP_PASSWORD"] = "secret"
        try:
            with patch(
                "sys.argv",
                [
                    "gmailsorter-imap",
                    "--host",
                    "localhost",
                    "--port",
                    "993",
                    "--username",
                    "user",
                    "-d",
                    "sqlite:///:memory:",
                    "-u",
                ],
            ):
                command_line_parser()
        finally:
            del os.environ["IMAP_PASSWORD"]

        imap_cls.assert_called_once_with(
            host="localhost",
            port=993,
            username="user",
            password="secret",
            connection_str="sqlite:///:memory:",
            db_user_id=1,
            use_ssl=True,
            email_download_format="metadata",
        )
        imap_instance.update_database.assert_called_once_with(quick=False)
        imap_instance.fit_machine_learning_model_to_database.assert_called_once_with(
            n_estimators=100,
            max_features=400,
            random_state=42,
            bootstrap=True,
            include_deleted=False,
        )

    @patch("gmailsorter.imap.__main__.Imap")
    def test_label_wires_imap_and_triggers_filter(self, imap_cls):
        imap_instance = imap_cls.return_value
        os.environ["IMAP_PASSWORD"] = "secret"
        try:
            with patch(
                "sys.argv",
                [
                    "gmailsorter-imap",
                    "--host",
                    "localhost",
                    "--username",
                    "user",
                    "-d",
                    "sqlite:///:memory:",
                    "-l",
                    "MailSortInbox",
                ],
            ):
                command_line_parser()
        finally:
            del os.environ["IMAP_PASSWORD"]

        imap_instance.filter_messages_from_server.assert_called_once_with(
            label="MailSortInbox",
            recommendation_ratio=0.9,
            label_prefix="labels_",
        )

    @patch("gmailsorter.imap.__main__.Imap")
    def test_no_update_or_label_prints_help(self, imap_cls):
        imap_instance = imap_cls.return_value
        os.environ["IMAP_PASSWORD"] = "secret"
        try:
            with patch(
                "sys.argv",
                [
                    "gmailsorter-imap",
                    "--host",
                    "localhost",
                    "--username",
                    "user",
                    "-d",
                    "sqlite:///:memory:",
                ],
            ):
                command_line_parser()
        finally:
            del os.environ["IMAP_PASSWORD"]

        imap_instance.update_database.assert_not_called()
        imap_instance.filter_messages_from_server.assert_not_called()

    @patch("gmailsorter.imap.__main__.Imap")
    def test_missing_password_env_skips_wiring(self, imap_cls):
        os.environ.pop("IMAP_PASSWORD", None)
        with patch(
            "sys.argv",
            ["gmailsorter-imap", "--host", "localhost", "--username", "user"],
        ):
            command_line_parser()

        imap_cls.assert_not_called()

    @patch("gmailsorter.imap.__main__.Imap")
    def test_missing_host_skips_wiring(self, imap_cls):
        with patch("sys.argv", ["gmailsorter-imap", "--username", "user"]):
            command_line_parser()

        imap_cls.assert_not_called()


if __name__ == "__main__":
    import unittest

    unittest.main()
