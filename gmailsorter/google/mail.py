import pandas
from tqdm import tqdm
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from gmailsorter.base import get_email_database
from gmailsorter.google.database import get_token_database
from gmailsorter.google.message import get_email_dict
from gmailsorter.ml import (
    encode_df_for_machine_learning,
    get_machine_learning_database,
    fit_machine_learning_models,
    get_predictions_from_machine_learning_models,
)


class GoogleMailBase:
    def __init__(
        self,
        google_mail_service,
        database_email=None,
        database_ml=None,
        database_token=None,
        user_id="me",
        db_user_id=1,
        email_download_format="metadata",
    ):
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
        self._service = google_mail_service
        self._db_email = database_email
        self._db_ml = database_ml
        self._db_token = database_token
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

    def update_database(self, quick=False, label_lst=[], email_format=None):
        """
        Update local email database

        Args:
            quick (boolean): Only add new emails, do not update existing labels - by default: False
            label_lst (list): list of labels to be searched
            email_format (str/None): Email format to download
        """
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
                    get_email_dict(
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

    def _get_labels_for_email(self, message_id):
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
        if "labelIds" in message_dict.keys():
            return message_dict["labelIds"]
        else:
            return []

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

    def _get_label_translate_dict(self):
        results = self._service.users().labels().list(userId=self._userid).execute()
        labels = results.get("labels", [])
        return {label["name"]: label["id"] for label in labels}

    def _get_message_detail(self, message_id, email_format=None, metadata_headers=[]):
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

    def _get_messages_page(self, label_ids, query_string, next_page_token=None):
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
            message_list_response.get("messages"),
            message_list_response.get("nextPageToken"),
        ]

    def _get_messages(self, query_string="", label_ids=[]):
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

        if message_items_lst is None:
            return []
        else:
            return message_items_lst

    def _modify_message_labels(
        self, message_id, label_id_remove_lst=[], label_id_add_lst=[]
    ):
        body_dict = {}
        if len(label_id_remove_lst) > 0:
            body_dict["removeLabelIds"] = label_id_remove_lst
        if len(label_id_add_lst) > 0:
            body_dict["addLabelIds"] = label_id_add_lst
        if len(body_dict) > 0:
            self._service.users().messages().modify(
                userId=self._userid, id=message_id, body=body_dict
            ).execute()

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

    def _search_email_on_server(
        self, query_string="", label_lst=[], only_message_ids=False
    ):
        """
        Search emails either by a specific query or optionally limit your search to a list of labels

        Args:
            query_string (str): query string to search for
            label_lst (list): list of labels to be searched
            only_message_ids (bool): return only the email IDs not the thread IDs - default: false

        Returns:
            list: list with email IDs and thread IDs of the messages which match the search
        """
        label_ids = [self._label_dict[label] for label in label_lst]
        message_id_lst = self._get_messages(
            query_string=query_string, label_ids=label_ids
        )
        if not only_message_ids:
            return message_id_lst
        else:
            return [d["id"] for d in message_id_lst]

    def _store_emails_in_database(self, message_id_lst, email_format=None):
        df = self._download_messages_to_dataframe(
            message_id_lst=message_id_lst, email_format=email_format
        )
        if len(df) > 0:
            self._db_email.store_dataframe(df=df, user_id=self._db_user_id)

    @staticmethod
    def _create_databases(connection_str):
        engine = create_engine(connection_str)
        session = sessionmaker(bind=engine)()
        db_email = get_email_database(engine=engine, session=session)
        db_ml = get_machine_learning_database(engine=engine, session=session)
        db_token = get_token_database(engine=engine, session=session)
        return db_email, db_ml, db_token

    @staticmethod
    def _get_message_ids(message_lst):
        return [d["id"] for d in message_lst]
