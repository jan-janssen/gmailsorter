from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from pygmailsorter.google.mail import GoogleMailBase
from pygmailsorter.google.token import validate_token


class GmailDatabase(GoogleMailBase):
    def __init__(
        self,
        client_config,
        connection_str,
        user_id="me",
        db_user_id=1,
        port=8080,
    ):
        """
        Gmail class to manage Emails via the Gmail API directly from Python

        Args:
            client_config (dict): client configuration provided by Google as credentials.json file
            connection_str (str): SQLalchemy compatible connection string to connect to the SQL database
            user_id (str): in most cases this should be simply "me"
            db_user_id (int): Default 1 - set a user id when sharing a database with multiple users
            port (int): system communication port to start authentication webserver
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
        database_email, database_ml, database_token = self.create_database(
            connection_str=self._connection_str
        )

        # Initialise service
        google_mail_service = _create_service(
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
        )


def _create_service(
    client_config,
    api_name,
    api_version,
    scopes,
    database,
    database_user_id,
    port=8080,
):
    cred = None

    token = database.get_token(user_id=database_user_id)
    if token.token is not None:
        cred = Credentials(
            token=token.token,
            refresh_token=token.refresh_token,
            id_token=None,
            token_uri=token.token_uri,
            client_id=token.client_id,
            client_secret=token.client_secret,
            scopes=["https://mail.google.com/"],
            default_scopes=None,
            quota_project_id=None,
            expiry=token.expiry,
            rapt_token=None,
            refresh_handler=None,
            enable_reauth_refresh=False,
        )

    if not cred or not cred.valid:
        cred = validate_token(
            cred=cred, client_config=client_config, scopes=scopes, port=port
        )
        database.update_token_with_dict(token=token, credentials=cred, commit=True)

    return build(api_name, api_version, credentials=cred)
