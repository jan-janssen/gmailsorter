import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from gmailsorter.__main__ import command_line_parser


class TestMainCommandLineParser(unittest.TestCase):
    @patch("gmailsorter.__main__.Gmail")
    @patch("gmailsorter.__main__.load_client_secrets_file")
    def test_update_flag_triggers_update_and_fit(self, load_secrets_mock, gmail_cls):
        load_secrets_mock.return_value = {"installed": {}}
        gmail_instance = MagicMock()
        gmail_cls.return_value = gmail_instance

        with patch(
            "sys.argv",
            [
                "gmailsorter",
                "-c",
                "creds.json",
                "-d",
                "sqlite:///:memory:",
                "-u",
            ],
        ):
            command_line_parser()

        load_secrets_mock.assert_called_once_with(client_secrets_file="creds.json")
        gmail_cls.assert_called_once_with(
            client_config={"installed": {}},
            connection_str="sqlite:///:memory:",
            user_id="me",
            db_user_id=1,
            port=8080,
            email_download_format="metadata",
        )
        gmail_instance.update_database.assert_called_once_with(quick=False)
        gmail_instance.fit_machine_learning_model_to_database.assert_called_once()
        gmail_instance.filter_messages_from_server.assert_not_called()

    @patch("gmailsorter.__main__.Gmail")
    @patch("gmailsorter.__main__.load_client_secrets_file")
    def test_tasks_flag_sets_max_workers(self, load_secrets_mock, gmail_cls):
        load_secrets_mock.return_value = {"installed": {}}
        gmail_instance = MagicMock()
        gmail_cls.return_value = gmail_instance

        with patch(
            "sys.argv",
            [
                "gmailsorter",
                "-c",
                "creds.json",
                "-d",
                "sqlite:///:memory:",
                "-u",
                "-t",
                "4",
            ],
        ):
            command_line_parser()

        gmail_instance.fit_machine_learning_model_to_database.assert_called_once_with(
            n_estimators=100,
            max_features="sqrt",
            random_state=42,
            bootstrap=True,
            max_depth=20,
            min_samples_leaf=2,
            include_deleted=False,
            max_workers=4,
        )

    @patch("gmailsorter.__main__.Gmail")
    @patch("gmailsorter.__main__.load_client_secrets_file")
    def test_label_flag_triggers_filter(self, load_secrets_mock, gmail_cls):
        load_secrets_mock.return_value = {"installed": {}}
        gmail_instance = MagicMock()
        gmail_cls.return_value = gmail_instance

        with patch(
            "sys.argv",
            [
                "gmailsorter",
                "-c",
                "creds.json",
                "-d",
                "sqlite:///:memory:",
                "-l",
                "Inbox",
                "-p",
                "9090",
                "-i",
                "7",
            ],
        ):
            command_line_parser()

        gmail_cls.assert_called_once_with(
            client_config={"installed": {}},
            connection_str="sqlite:///:memory:",
            user_id="me",
            db_user_id=7,
            port="9090",
            email_download_format="metadata",
        )
        gmail_instance.filter_messages_from_server.assert_called_once_with(
            label="Inbox",
            recommendation_ratio=0.9,
            label_prefix="labels_Label_",
        )
        gmail_instance.update_database.assert_not_called()

    @patch("gmailsorter.__main__.Gmail")
    @patch("gmailsorter.__main__.load_client_secrets_file")
    def test_no_update_or_label_prints_help(self, load_secrets_mock, gmail_cls):
        load_secrets_mock.return_value = {"installed": {}}
        gmail_cls.return_value = MagicMock()

        with patch(
            "sys.argv",
            ["gmailsorter", "-c", "creds.json", "-d", "sqlite:///:memory:"],
        ):
            command_line_parser()

        gmail_cls.return_value.update_database.assert_not_called()
        gmail_cls.return_value.filter_messages_from_server.assert_not_called()

    @patch("gmailsorter.__main__.Gmail")
    def test_missing_credentials_skips_gmail_creation(self, gmail_cls):
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.chdir(tmp_dir)
            try:
                with patch("sys.argv", ["gmailsorter"]):
                    command_line_parser()
            finally:
                os.chdir(cwd)
        gmail_cls.assert_not_called()

    @patch("gmailsorter.__main__.Gmail")
    @patch("gmailsorter.__main__.load_client_secrets_file")
    def test_credentials_found_in_current_directory(self, load_secrets_mock, gmail_cls):
        load_secrets_mock.return_value = {"installed": {}}
        gmail_cls.return_value = MagicMock()
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.chdir(tmp_dir)
            try:
                with open("credentials.json", "w") as f:
                    f.write("{}")
                with patch("sys.argv", ["gmailsorter"]):
                    command_line_parser()
                load_secrets_mock.assert_called_once_with(
                    client_secrets_file=os.path.abspath("credentials.json")
                )
            finally:
                os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
