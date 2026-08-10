from abc import ABC, abstractmethod

import pandas
from tqdm import tqdm

from gmailsorter.ml import (
    encode_df_for_machine_learning,
    fit_machine_learning_models,
    get_predictions_from_machine_learning_models,
)


class AbstractMailBox(ABC):
    def __init__(
        self,
        mail_service,
        database_email=None,
        database_ml=None,
        user_id="me",
        db_user_id=1,
        email_download_format="metadata",
    ):
        """
        Shared fetch-store-train-predict-move loop for a mailbox backend, independent of
        whether the backend is the Gmail API or a plain IMAP connection.

        Args:
            mail_service: backend-specific connection object (Gmail API service resource,
                imaplib connection, ...)
            database_email (gmailsorter.base.database.DatabaseInterface): SQLalchemy interface for email database
            database_ml (gmailsorter.ml.database.DatabaseInterface): SQLalchemy interface for machine learning database
            user_id (str): backend-specific user identifier
            db_user_id (int): Default 1 - set a user id when sharing a database with multiple users
            email_download_format (str): backend-specific download format hint
        """
        self._service = mail_service
        self._db_email = database_email
        self._db_ml = database_ml
        self._db_user_id = db_user_id
        self._userid = user_id
        self._email_download_format = email_download_format
        self._label_dict = self._get_label_translate_dict()
        self._label_dict_inverse = {v: k for k, v in self._label_dict.items()}

    @property
    def labels(self):
        return list(self._label_dict.keys())

    def download_emails_for_label(self, label):
        """
        Download emails for a specific label

        Args:
            label (str): label to download emails for

        Returns:
            pandas.DataFrame: Email content for the downloaded emails
        """
        return self._download_messages_to_dataframe(
            message_id_lst=self._search_email_on_server(
                label_lst=[label], only_message_ids=True
            )
        )

    def filter_messages_from_server(
        self,
        label,
        recommendation_ratio=0.9,
    ):
        """
        Filter new emails based on machine learning model recommendations.

        Args:
            label (str): Email label to filter for
            recommendation_ratio (float): Only accept recommendation above this ratio (0<r<1)
        """
        df_partial = self.download_emails_for_label(label=label)
        if len(df_partial) > 0:
            model_reload_dict, feature_reload_lst = self._db_ml.load_models()
            df_partial_features = encode_df_for_machine_learning(
                df=df_partial,
                feature_lst=feature_reload_lst,
                label_lst=list(model_reload_dict.keys()),
                return_labels=False,
            )
            df_partial_features = df_partial_features.reindex(
                sorted(df_partial_features.columns), axis=1
            )
            model_recommendation_dict = get_predictions_from_machine_learning_models(
                df_features=df_partial_features,
                model_dict=model_reload_dict,
                recommendation_ratio=recommendation_ratio,
            )
            self._move_emails(
                move_email_dict=model_recommendation_dict, label_to_ignore=label
            )

    def fit_machine_learning_model_to_database(
        self,
        n_estimators=100,
        max_features=400,
        random_state=42,
        bootstrap=True,
        include_deleted=False,
        max_workers=None,
    ):
        """
        Fit machine learning models to emails stored in database and afterwards store machine learning models in
        database.

        Args:
            n_estimators (int): Number of estimators
            max_features (int): Number of features
            random_state (int): Random state
            bootstrap (boolean): Whether bootstrap samples are used when building trees. If False, the whole dataset is
                                 used to build each tree. (default: true)
            include_deleted (bool): Flag to include deleted emails - default False
            max_workers (int): maximum number of workers for the machine learning models
        """
        df_all = self.get_all_emails_in_database(include_deleted=include_deleted)
        df_all_features, df_all_labels = encode_df_for_machine_learning(
            df=df_all, feature_lst=[], label_lst=[], return_labels=True
        )
        df_all_features = df_all_features.loc[
            :, ~df_all_features.columns.duplicated()
        ].copy()
        df_all_features = df_all_features.reindex(
            sorted(df_all_features.columns), axis=1
        )
        model_dict = fit_machine_learning_models(
            df_all_features=df_all_features,
            df_all_labels=df_all_labels,
            n_estimators=n_estimators,
            max_features=max_features,
            random_state=random_state,
            bootstrap=bootstrap,
            max_workers=max_workers,
        )
        self._db_ml.store_models(
            model_dict=model_dict,
            feature_lst=df_all_features.columns.values.tolist(),
            user_id=self._db_user_id,
            commit=True,
        )

    def get_all_emails_in_database(self, include_deleted=False):
        """
        Get all emails stored in the local database

        Args:
            include_deleted (bool): Flag to include deleted emails - default False

        Returns:
            pandas.DataFrame: With all emails and the corresponding information
        """
        return self._db_email.get_all_emails(
            include_deleted=include_deleted, user_id=self._db_user_id
        )

    def update_database(self, quick=False, label_lst=None, email_format=None):
        """
        Update local email database

        Args:
            quick (boolean): Only add new emails, do not update existing labels - by default: False
            label_lst (list): list of labels to be searched
            email_format (str/None): Email format to download
        """
        if label_lst is None:
            label_lst = []
        if self._db_email is not None:
            message_id_lst = self._search_email_on_server(
                label_lst=label_lst, only_message_ids=True
            )
            (
                new_messages_lst,
                message_label_updates_lst,
                deleted_messages_lst,
            ) = self._db_email.get_labels_to_update(
                message_id_lst=message_id_lst, user_id=self._db_user_id
            )
            if not quick:
                self._db_email.mark_emails_as_deleted(
                    message_id_lst=deleted_messages_lst, user_id=self._db_user_id
                )
                self._db_email.update_labels(
                    message_id_lst=message_label_updates_lst,
                    message_meta_lst=self._get_labels_for_emails(
                        message_id_lst=message_label_updates_lst
                    ),
                    user_id=self._db_user_id,
                )
            self._store_emails_in_database(
                message_id_lst=new_messages_lst, email_format=email_format
            )

    def _download_messages_to_dataframe(self, message_id_lst, email_format=None):
        """
        Download a list of messages based on their email IDs and store the content in a pandas.DataFrame.

        Args:
            message_id_lst (list): list of emails IDs
            email_format (str): Email format to download - default: "full"

        Returns:
            pandas.DataFrame: pandas.DataFrame which contains the rendered emails
        """
        return pandas.DataFrame(
            [
                message
                for message in [
                    self._parse_message(
                        message=self._get_message_detail(
                            message_id=message_id,
                            email_format=email_format,
                            metadata_headers=[],
                        )
                    )
                    for message_id in tqdm(
                        iterable=message_id_lst, desc="Download messages to DataFrame"
                    )
                ]
                if message is not None
            ]
        )

    def _get_labels_for_emails(self, message_id_lst):
        """
        Get labels for a list of emails

        Args:
            message_id_lst (list): list of emails IDs

        Returns:
            list: Nested list of email labels for each email
        """
        return [
            self._get_labels_for_email(message_id=message_id)
            for message_id in tqdm(
                iterable=message_id_lst, desc="Get labels for emails"
            )
        ]

    def _move_emails(self, move_email_dict, label_to_ignore):
        label_existing = self._label_dict[label_to_ignore]
        for message_id, label_add in tqdm(
            iterable=move_email_dict.items(), desc="Move emails"
        ):
            if label_add is not None and label_add != label_existing:
                self._modify_message_labels(
                    message_id=message_id,
                    label_id_remove_lst=[label_existing],
                    label_id_add_lst=[label_add],
                )

    def _store_emails_in_database(self, message_id_lst, email_format=None):
        df = self._download_messages_to_dataframe(
            message_id_lst=message_id_lst, email_format=email_format
        )
        if len(df) > 0:
            self._db_email.store_dataframe(df=df, user_id=self._db_user_id)

    @abstractmethod
    def _search_email_on_server(
        self, query_string="", label_lst=None, only_message_ids=False
    ):
        """
        Search emails either by a specific query or optionally limit your search to a list of labels

        Args:
            query_string (str): query string to search for
            label_lst (list): list of labels to be searched
            only_message_ids (bool): return only the email IDs not the thread IDs - default: false

        Returns:
            list: list of message ids (or backend-specific list items) matching the search
        """

    @abstractmethod
    def _get_message_detail(self, message_id, email_format=None, metadata_headers=None):
        """
        Get the raw, backend-specific representation of a single email message.

        Args:
            message_id (str): id used by this backend to uniquely identify the email
            email_format (str/None): backend-specific format hint
            metadata_headers (list): backend-specific list of metadata headers

        Returns:
            The backend-specific raw message representation, passed on to `_parse_message`.
        """

    @abstractmethod
    def _get_label_translate_dict(self):
        """
        Returns:
            dict: mapping of label/folder display name to the backend-specific label/folder id
        """

    @abstractmethod
    def _modify_message_labels(
        self, message_id, label_id_remove_lst=None, label_id_add_lst=None
    ):
        """
        Apply a label/folder change to a single email message.
        """

    @abstractmethod
    def _get_labels_for_email(self, message_id):
        """
        Args:
            message_id (str): id used by this backend to uniquely identify the email

        Returns:
            list: list of labels/folders currently assigned to the email
        """

    @abstractmethod
    def _parse_message(self, message):
        """
        Args:
            message: the backend-specific raw message representation returned by `_get_message_detail`

        Returns:
            dict/None: the common gmailsorter email dict (see `gmailsorter.base.message.AbstractMessage.to_dict`),
                       or None if the message could not be parsed
        """
