from typing import Any

from googleapiclient.discovery import Resource
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gmailsorter.base import get_email_database
from gmailsorter.base.database import DatabaseInterface as EmailDatabaseInterface
from gmailsorter.base.mail import AbstractMailBox
from gmailsorter.google.database import DatabaseInterface as TokenDatabaseInterface
from gmailsorter.google.database import get_token_database
from gmailsorter.google.message import get_email_dict
from gmailsorter.ml import (
    get_machine_learning_database,
)
from gmailsorter.ml.database import MachineLearningDatabase

_DatabaseTriple = tuple[
    EmailDatabaseInterface, MachineLearningDatabase, TokenDatabaseInterface
]


class GoogleMailBase(AbstractMailBox):
    def __init__(
        self,
        google_mail_service: Resource,
        database_email: EmailDatabaseInterface | None = None,
        database_ml: MachineLearningDatabase | None = None,
        database_token: TokenDatabaseInterface | None = None,
        user_id: str = "me",
        db_user_id: int = 1,
        email_download_format: str = "metadata",
    ) -> None:
        """
        Gmail class to manage Emails via the Gmail API directly from Python

        Args:
            google_mail_service: A Resource object with methods for interacting with the service.
            database_email (gmailsorter.base.database.DatabaseInterface): SQLalchemy interface for email database
            database_ml (gmailsorter.ml.database.DatabaseInterface): SQLalchemy interface for machine learning database
            database_token (gmailsorter.google.database.DatabaseInterface): SQLalchemy interface for google database
            user_id (str): in most cases this should be simply "me"
            db_user_id (int): Default 1 - set a user id when sharing a database with multiple users
            email_download_format (str): API response format [full, metadata]
        """
        self._db_token = database_token
        super().__init__(
            mail_service=google_mail_service,
            database_email=database_email,
            database_ml=database_ml,
            user_id=user_id,
            db_user_id=db_user_id,
            email_download_format=email_download_format,
        )

    def _get_label_translate_dict(self) -> dict[str, str]:
        results = self._service.users().labels().list(userId=self._userid).execute()
        labels = results.get("labels", [])
        return {label["name"]: label["id"] for label in labels}

    def _get_message_detail(
        self,
        message_id: str,
        email_format: str | None = None,
        metadata_headers: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Get details of a specific email message based on its email ID

        Args:
            message_id (str): email IDs used by Google Mail to uniquely identify emails
            email_format (str/None): API response format [raw, minimal, full, metadata]
            metadata_headers (list): list of meta data headers

        Returns:
            dict: details of the email as python dictionary
        """
        if email_format is None:
            email_format = self._email_download_format
        if metadata_headers is None:
            metadata_headers = []
        return (
            self._service.users()
            .messages()
            .get(
                userId=self._userid,
                id=message_id,
                format=email_format,
                metadataHeaders=metadata_headers,
            )
            .execute()
        )

    def _get_messages_page(
        self,
        label_ids: list[str],
        query_string: str,
        next_page_token: str | None = None,
    ) -> list[Any]:
        message_list_response = (
            self._service.users()
            .messages()
            .list(
                userId=self._userid,
                labelIds=label_ids,
                q=query_string,
                pageToken=next_page_token,
            )
            .execute()
        )

        return [
            message_list_response.get("messages", []),
            message_list_response.get("nextPageToken"),
        ]

    def _get_messages(
        self, query_string: str = "", label_ids: list[str] | None = None
    ) -> list[dict[str, Any]]:
        if label_ids is None:
            label_ids = []
        message_items_lst, next_page_token = self._get_messages_page(
            label_ids=label_ids, query_string=query_string, next_page_token=None
        )

        while next_page_token:
            message_items, next_page_token = self._get_messages_page(
                label_ids=label_ids,
                query_string=query_string,
                next_page_token=next_page_token,
            )
            message_items_lst.extend(message_items)

        return message_items_lst

    def _modify_message_labels(
        self,
        message_id: str,
        label_id_remove_lst: list[str] | None = None,
        label_id_add_lst: list[str] | None = None,
    ) -> None:
        if label_id_remove_lst is None:
            label_id_remove_lst = []
        if label_id_add_lst is None:
            label_id_add_lst = []
        body_dict: dict[str, list[str]] = {}
        if len(label_id_remove_lst) > 0:
            body_dict["removeLabelIds"] = label_id_remove_lst
        if len(label_id_add_lst) > 0:
            body_dict["addLabelIds"] = label_id_add_lst
        if len(body_dict) > 0:
            self._service.users().messages().modify(
                userId=self._userid, id=message_id, body=body_dict
            ).execute()

    def _search_email_on_server(
        self,
        query_string: str = "",
        label_lst: list[str] | None = None,
        only_message_ids: bool = False,
    ) -> list[dict[str, Any]] | list[str]:
        """
        Search emails either by a specific query or optionally limit your search to a list of labels

        Args:
            query_string (str): query string to search for
            label_lst (list): list of labels to be searched
            only_message_ids (bool): return only the email IDs not the thread IDs - default: false

        Returns:
            list: list with email IDs and thread IDs of the messages which match the search
        """
        if label_lst is None:
            label_lst = []
        label_ids = [self._label_dict[label] for label in label_lst]
        message_id_lst = self._get_messages(
            query_string=query_string, label_ids=label_ids
        )
        if not only_message_ids:
            return message_id_lst
        else:
            return [d["id"] for d in message_id_lst]

    def _get_labels_for_email(self, message_id: str) -> list[str]:
        """
        Get labels for email

        Args:
            message_id (str): email ID

        Returns:
            list: List of email labels
        """
        message_dict = self._get_message_detail(
            message_id=message_id,
            email_format="metadata",
            metadata_headers=["labelIds"],
        )
        if "labelIds" in message_dict:
            return message_dict["labelIds"]
        else:
            return []

    def _parse_message(self, message):
        return get_email_dict(message=message)

    @staticmethod
    def _create_databases(connection_str: str) -> _DatabaseTriple:
        engine = create_engine(connection_str)
        session = sessionmaker(bind=engine)()
        db_email = get_email_database(engine=engine, session=session)
        db_ml = get_machine_learning_database(engine=engine, session=session)
        db_token = get_token_database(engine=engine, session=session)
        return db_email, db_ml, db_token

    @staticmethod
    def _get_message_ids(message_lst: list[dict[str, Any]]) -> list[str]:
        return [d["id"] for d in message_lst]
