from unittest import TestCase
from unittest.mock import patch

from gmailsorter.imap.authentication import create_service


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


if __name__ == "__main__":
    import unittest

    unittest.main()
