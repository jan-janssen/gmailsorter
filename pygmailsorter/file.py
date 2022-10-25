import os
import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from pygmailsorter.google.mail import GoogleMailBase
from pygmailsorter.google.token import validate_token


class GmailFile(GoogleMailBase):
    def __init__(
        self,
        client_service_file=None,
        user_id="me",
        config_folder="~/.pygmailsorter",
        db_user_id=1,
        port=8080,
    ):
        """
        Gmail class to manage Emails via the Gmail API directly from Python

        Args:
            client_service_file (str/ None): path to the credentials.json file
                                             typically "~/.pygmailsorter/credentials.json"
            user_id (str): in most cases this should be simply "me"
            config_folder (str): the folder for the configuration, typically "~/.pygmailsorter"
            db_user_id (int): Default 1 - set a user id when sharing a database with multiple users
            port (int): system communication port to start authentication webserver
        """
        connect_dict = {
            "api_name": "gmail",
            "api_version": "v1",
            "scopes": ["https://mail.google.com/"],
        }

        # Create config directory
        self._config_path = _create_config_folder(config_folder=config_folder)
        if client_service_file is None:
            client_service_file = os.path.join(self._config_path, "credentials.json")
        self._client_service_file = client_service_file
        self._connection_str = "sqlite:///" + self._config_path + "/email.db"

        # Initialise service
        google_mail_service = _create_service(
            client_secret_file=self._client_service_file,
            api_name=connect_dict["api_name"],
            api_version=connect_dict["api_version"],
            scopes=connect_dict["scopes"],
            prefix="",
            working_dir=self._config_path,
            port=port,
        )

        # Initialize database
        database_email, database_ml, database_token = self.create_database(
            connection_str=self._connection_str
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
    client_secret_file,
    api_name,
    api_version,
    scopes,
    prefix="",
    working_dir=None,
    port=8080,
):
    cred = None
    if working_dir is None:
        working_dir = os.getcwd()
    token_dir = "token_files"
    json_file = f"token_{api_name}_{api_version}{prefix}.json"

    os.makedirs(os.path.join(working_dir, token_dir), exist_ok=True)
    token_file = os.path.join(working_dir, token_dir, json_file)
    if os.path.exists(token_file):
        cred = Credentials.from_authorized_user_file(token_file, scopes)

    if not cred or not cred.valid:
        cred = validate_token(
            cred=cred,
            client_config=load_client_secrets_file(
                client_secrets_file=client_secret_file
            ),
            scopes=scopes,
            port=port,
        )

        with open(os.path.join(working_dir, token_dir, json_file), "w") as token:
            token.write(cred.to_json())

    return build(api_name, api_version, credentials=cred)


def _create_config_folder(config_folder="~/.pygmailsorter"):
    config_path = os.path.abspath(os.path.expanduser(config_folder))
    os.makedirs(config_path, exist_ok=True)
    return config_path


def load_client_secrets_file(client_secrets_file):
    with open(client_secrets_file, "r") as json_file:
        return json.load(json_file)
