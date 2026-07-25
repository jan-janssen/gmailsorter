import json

from gmailsorter.google import GoogleMailBase, create_service
from gmailsorter.imap import ImapMailBase
from gmailsorter.imap import create_service as create_imap_service


class Gmail(GoogleMailBase):
    def __init__(
        self,
        client_config,
        connection_str,
        user_id="me",
        db_user_id=1,
        port=8080,
        email_download_format="metadata",
    ):
        """
        Gmail class to manage Emails via the Gmail API directly from Python

        Args:
            client_config (dict): client configuration provided by Google as credentials.json file
            connection_str (str): SQLalchemy compatible connection string to connect to the SQL database
            user_id (str): in most cases this should be simply "me"
            db_user_id (int): Default 1 - set a user id when sharing a database with multiple users
            port (int): system communication port to start authentication webserver
            email_download_format (str): API response format [full, metadata]
        """
        connect_dict = {
            "api_name": "gmail",
            "api_version": "v1",
            "scopes": ["https://mail.google.com/"],
        }

        # Create config directory
        self._client_config = client_config
        self._connection_str = connection_str

        # Initialize database
        database_email, database_ml, database_token = self._create_databases(
            connection_str=self._connection_str
        )

        # Initialise service
        google_mail_service = create_service(
            client_config=self._client_config,
            api_name=connect_dict["api_name"],
            api_version=connect_dict["api_version"],
            scopes=connect_dict["scopes"],
            database=database_token,
            database_user_id=db_user_id,
            port=port,
        )

        super().__init__(
            google_mail_service=google_mail_service,
            database_email=database_email,
            database_ml=database_ml,
            database_token=database_token,
            user_id=user_id,
            db_user_id=db_user_id,
            email_download_format=email_download_format,
        )


def load_client_secrets_file(client_secrets_file):
    with open(client_secrets_file) as json_file:
        return json.load(json_file)


class Imap(ImapMailBase):
    def __init__(
        self,
        host,
        port,
        username,
        password,
        connection_str,
        db_user_id=1,
        use_ssl=True,
        email_download_format="metadata",
    ):
        """
        Imap class to manage Emails via a plain IMAP connection directly from Python

        The IMAP connection is kept open for the lifetime of the object. Call close()
        when done, or use the object as a context manager:

        >>> with Imap(...) as imap:
        ...     imap.update_database()

        Args:
            host (str): IMAP server hostname
            port (int): IMAP server port, typically 993 for IMAP4_SSL or 143 for IMAP4
            username (str): IMAP account username
            password (str): IMAP account password
            connection_str (str): SQLalchemy compatible connection string to connect to the SQL database
            db_user_id (int): Default 1 - set a user id when sharing a database with multiple users
            use_ssl (bool): connect via IMAP4_SSL (default) or plain IMAP4
            email_download_format (str): unused for IMAP, kept for interface parity with Gmail
        """
        self._connection_str = connection_str
        # kept so the connection can be re-established when the server drops it
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._use_ssl = use_ssl

        database_email, database_ml = self._create_databases(
            connection_str=self._connection_str
        )

        imap_connection = self._connect()

        super().__init__(
            mail_service=imap_connection,
            database_email=database_email,
            database_ml=database_ml,
            user_id=username,
            db_user_id=db_user_id,
            email_download_format=email_download_format,
        )

    def _connect(self):
        return create_imap_service(
            host=self._host,
            port=self._port,
            username=self._username,
            password=self._password,
            use_ssl=self._use_ssl,
        )

    def _reconnect(self):
        """
        Re-establish the IMAP connection after the server dropped it, discarding the
        old connection first.
        """
        self.close()
        self._service = self._connect()
