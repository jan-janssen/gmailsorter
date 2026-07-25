import os
import smtplib
import time
import unittest
import uuid
from email.message import EmailMessage
from imaplib import IMAP4
from unittest.mock import patch

from gmailsorter.local import Imap

#: When this environment variable is set to any non-empty value, an unreachable IMAP
#: server is a test failure rather than a skip. CI sets it so the imap-integration job
#: cannot report green when the GreenMail service never came up; local runs leave it
#: unset and keep the clean skip.
IMAP_INTEGRATION_REQUIRED = "IMAP_INTEGRATION_REQUIRED"


def imap_integration_required():
    """
    Returns:
        bool: True if a missing IMAP test server must fail instead of skip
    """
    return bool(os.environ.get(IMAP_INTEGRATION_REQUIRED, "").strip())


class TestImapServiceIntegration(unittest.TestCase):
    smtp_host = os.environ.get("TEST_SMTP_HOST", "localhost")
    smtp_port = int(os.environ.get("TEST_SMTP_PORT", "3025"))
    imap_host = os.environ.get("TEST_IMAP_HOST", "localhost")
    imap_port = int(os.environ.get("TEST_IMAP_PORT", "3143"))
    username = os.environ.get("TEST_IMAP_USERNAME", "testuser")
    recipient = os.environ.get("TEST_EMAIL", "testuser@example.test")
    password = os.environ.get("TEST_EMAIL_PASSWORD", "secret")

    @classmethod
    def setUpClass(cls):
        if cls._imap_server_available():
            return
        reason = (
            "No IMAP test server reachable at "
            f"{cls.imap_host}:{cls.imap_port} - start the greenmail container "
            "described in https://github.com/jan-janssen/testing-imap to run this test."
        )
        if imap_integration_required():
            raise AssertionError(
                f"{IMAP_INTEGRATION_REQUIRED} is set, so this test must actually run "
                f"rather than be skipped. {reason}"
            )
        raise unittest.SkipTest(reason)

    @classmethod
    def _imap_server_available(cls, timeout=2.0, attempts=5, delay=1.5):
        for attempt in range(attempts):
            try:
                with IMAP4(cls.imap_host, cls.imap_port, timeout=timeout) as client:
                    status, _ = client.noop()
                    if status == "OK":
                        return True
            except OSError:
                pass
            if attempt < attempts - 1:
                time.sleep(delay)
        return False

    def setUp(self):
        with IMAP4(self.imap_host, self.imap_port, timeout=10) as client:
            client.login(self.username, self.password)
            client.select("INBOX")
            status, data = client.search(None, "ALL")
            for message_id in data[0].split():
                client.store(message_id, "+FLAGS", r"(\Deleted)")
            client.expunge()
            for folder in ("MailSortInbox", "Sorted"):
                client.create(folder)

    def _send_message(self, subject, body):
        message_id = f"<{uuid.uuid4()}@example.test>"
        message = EmailMessage()
        message["From"] = "sender@example.test"
        message["To"] = self.recipient
        message["Subject"] = subject
        message["Message-ID"] = message_id
        message.set_content(body)
        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as smtp:
            smtp.send_message(message)
        return message_id

    def _wait_for_message_in_inbox(self, message_id, timeout=10.0):
        deadline = time.monotonic() + timeout
        with IMAP4(self.imap_host, self.imap_port, timeout=10) as client:
            client.login(self.username, self.password)
            client.select("INBOX")
            while time.monotonic() < deadline:
                status, data = client.search(
                    None, "HEADER", "Message-ID", f'"{message_id}"'
                )
                self.assertEqual(status, "OK")
                if data[0].split():
                    return
                time.sleep(0.2)
        self.fail(f"Message {message_id!r} was not delivered to INBOX")

    def test_update_database_and_move_round_trip(self):
        message_id = self._send_message(
            subject="Integration test message",
            body="Body from gmailsorter IMAP test.",
        )
        self._wait_for_message_in_inbox(message_id)

        imap = Imap(
            host=self.imap_host,
            port=self.imap_port,
            username=self.username,
            password=self.password,
            connection_str="sqlite:///:memory:",
            use_ssl=False,
        )

        imap.update_database(quick=False)
        df = imap.get_all_emails_in_database()

        self.assertIn("Integration test message", df["subject"].tolist())
        stored_id = df.loc[df["subject"] == "Integration test message", "id"].iloc[0]
        self.assertTrue(stored_id.startswith("INBOX\x1f"))

        imap._modify_message_labels(
            message_id=stored_id,
            label_id_remove_lst=["INBOX"],
            label_id_add_lst=["MailSortInbox"],
        )

        imap.update_database(quick=False)
        df_after_move = imap.get_all_emails_in_database()
        moved_row = df_after_move.loc[
            df_after_move["subject"] == "Integration test message"
        ]
        self.assertEqual(len(moved_row), 1)
        self.assertTrue(moved_row.iloc[0]["id"].startswith("MailSortInbox\x1f"))


class TestImapIntegrationRequiredGate(unittest.TestCase):
    """Covers the env-var gate itself, which needs no IMAP server."""

    def test_not_required_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(imap_integration_required())

    def test_not_required_for_empty_value(self):
        with patch.dict(os.environ, {IMAP_INTEGRATION_REQUIRED: "  "}):
            self.assertFalse(imap_integration_required())

    def test_required_for_truthy_value(self):
        with patch.dict(os.environ, {IMAP_INTEGRATION_REQUIRED: "true"}):
            self.assertTrue(imap_integration_required())

    def test_set_up_class_skips_without_server_by_default(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                TestImapServiceIntegration, "_imap_server_available", return_value=False
            ),
            self.assertRaises(unittest.SkipTest),
        ):
            TestImapServiceIntegration.setUpClass()

    def test_set_up_class_fails_without_server_when_required(self):
        with (
            patch.dict(os.environ, {IMAP_INTEGRATION_REQUIRED: "true"}),
            patch.object(
                TestImapServiceIntegration, "_imap_server_available", return_value=False
            ),
            self.assertRaises(AssertionError),
        ):
            TestImapServiceIntegration.setUpClass()


if __name__ == "__main__":
    unittest.main()
