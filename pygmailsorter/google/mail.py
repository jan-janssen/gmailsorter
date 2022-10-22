import pandas
from tqdm import tqdm
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pygmailsorter.google.message import Message, get_email_dict
from pygmailsorter.base.database import get_email_database
from pygmailsorter.ml.base import (
    get_machine_learning_database,
    gather_data_for_machine_learning,
    train_model,
    get_machine_learning_recommendations,
)


class GoogleMailBase:
    def __init__(
        self,
        google_mail_service,
        database_email=None,
        database_ml=None,
        user_id="me",
        db_user_id=1,
    ):
        self._service = google_mail_service
        self._db_email = database_email
        self._db_ml = database_ml
        self._db_user_id = db_user_id
        self._userid = user_id
        self._label_dict = self._get_label_translate_dict()
        self._label_dict_inverse = {v: k for k, v in self._label_dict.items()}

    @property
    def labels(self):
        return list(self._label_dict.keys())

    def filter_only_new_messages(
        self,
        label,
        n_estimators=100,
        max_features=400,
        random_state=42,
        bootstrap=True,
        recalculate=False,
        include_deleted=False,
        recommendation_ratio=0.9,
    ):
        """
        Filter new emails based on machine learning model recommendations.

        Args:
            label (str): Email label to filter for
            n_estimators (int): Number of estimators
            max_features (int): Number of features
            random_state (int): Random state
            bootstrap (boolean): Whether bootstrap samples are used when building trees. If False, the whole dataset is
                                 used to build each tree. (default: true)
            recalculate (boolean): Train the model again
            include_deleted (boolean): Include deleted emails in training
            recommendation_ratio (float): Only accept recommendation above this ratio (0<r<1)
        """
        message_id_lst = self.search_email(label_lst=[label], only_message_ids=True)
        df = self._db_email.get_email_collection(
            email_id_lst=message_id_lst,
            include_deleted=False,
            user_id=1,
            desc="Create dataframe from email id list",
        )
        if len(df) > 0:
            model_recommendation_dict = self._get_machine_learning_recommendations(
                df=df,
                label=label,
                n_estimators=n_estimators,
                max_features=max_features,
                random_state=random_state,
                bootstrap=bootstrap,
                recalculate=recalculate,
                include_deleted=include_deleted,
                recommendation_ratio=recommendation_ratio,
            )
            self._move_emails(
                move_email_dict=model_recommendation_dict, label_to_ignore=label
            )

    def filter_label_by_machine_learning(
        self,
        label,
        n_estimators=100,
        max_features=400,
        random_state=42,
        bootstrap=True,
        recalculate=False,
        include_deleted=False,
        recommendation_ratio=0.9,
    ):
        """
        Filter emails based on machine learning model recommendations.

        Args:
            label (str): Email label to filter for
            n_estimators (int): Number of estimators
            max_features (int): Number of features
            random_state (int): Random state
            bootstrap (boolean): Whether bootstrap samples are used when building trees. If False, the whole dataset is
                                 used to build each tree. (default: true)
            recalculate (boolean): Train the model again
            include_deleted (boolean): Include deleted emails in training
            recommendation_ratio (float): Only accept recommendation above this ratio (0<r<1)
        """
        df = self.get_emails_by_label(label=label, include_deleted=False)
        if len(df) > 0:
            model_recommendation_dict = self._get_machine_learning_recommendations(
                df=df,
                label=label,
                n_estimators=n_estimators,
                max_features=max_features,
                random_state=random_state,
                bootstrap=bootstrap,
                recalculate=recalculate,
                include_deleted=include_deleted,
                recommendation_ratio=recommendation_ratio,
            )
            self._move_emails(
                move_email_dict=model_recommendation_dict, label_to_ignore=label
            )

    def download_emails_for_label(self, label):
        """
        Download emails for a specific label

        Args:
            label (str): label to download emails for

        Returns:
            pandas.DataFrame: Email content for the downloaded emails
        """
        return self._download_messages_to_dataframe(
            message_id_lst=self.search_email(label_lst=[label], only_message_ids=True)
        )

    def update_database(self, quick=False, label_lst=[], format="full"):
        """
        Update local email database

        Args:
            quick (boolean): Only add new emails, do not update existing labels - by default: False
            label_lst (list): list of labels to be searched
            format (str): Email format to download - default: "full"
        """
        if self._db_email is not None:
            message_id_lst = self.search_email(
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
                message_id_lst=new_messages_lst, format=format
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
            message_id=message_id, format="metadata", metadata_headers=["labelIds"]
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

    def get_emails_by_label(self, label, include_deleted=False):
        """
        Get all emails stored in the local database for a specific label

        Args:
            label (str): Email label to filter for
            include_deleted (bool): Flag to include deleted emails - default False

        Returns:
            pandas.DataFrame: With all emails and the corresponding information
        """
        return self._db_email.get_emails_by_label(
            label_id=self._label_dict[label],
            include_deleted=include_deleted,
            user_id=self._db_user_id,
        )

    def train_machine_learning_model(
        self,
        n_estimators=100,
        max_features=400,
        random_state=42,
        bootstrap=True,
        include_deleted=False,
        labels_to_exclude_lst=[],
    ):
        """
        Train internal machine learning models

        Args:
            n_estimators (int): Number of estimators
            max_features (int): Number of features
            random_state (int): Random state
            bootstrap (boolean): Whether bootstrap samples are used when building trees. If False, the whole dataset is
                                 used to build each tree. (default: true)
            include_deleted (boolean): Include deleted emails in training
            labels_to_exclude_lst (list): list of email labels which are excluded from the fitting process
        """
        df_all_encode_red = gather_data_for_machine_learning(
            df_all=self.get_all_emails_in_database(include_deleted=include_deleted),
            labels_dict=self._label_dict,
            feature_lst=[],
            labels_to_exclude_lst=labels_to_exclude_lst,
        )
        model_dict = train_model(
            df=df_all_encode_red,
            labels_to_learn=None,
            n_estimators=n_estimators,
            max_features=max_features,
            random_state=random_state,
            bootstrap=bootstrap,
        )
        self._db_ml.store_models(model_dict=model_dict, user_id=self._db_user_id)
        return model_dict

    def train_machine_learning_models(
        self,
        label,
        n_estimators=100,
        max_features=400,
        random_state=42,
        bootstrap=True,
        recalculate=False,
        include_deleted=False,
    ):
        """
        Train internal machine learning models to predict email sorting.

        Args:
            label (str): Email label to filter for
            n_estimators (int): Number of estimators
            max_features (int): Number of features
            random_state (int): Random state
            bootstrap (boolean): Whether bootstrap samples are used when building trees. If False, the whole dataset is
                                 used to build each tree. (default: true)
            recalculate (boolean): Train the model again
            include_deleted (boolean): Include deleted emails in training

        Returns:
            dict: Email IDs and the corresponding label ID.
        """
        df_all = self.get_all_emails_in_database(include_deleted=include_deleted)
        if not recalculate:
            df_all_encode = gather_data_for_machine_learning(
                df_all=df_all,
                labels_dict=self._label_dict,
                feature_lst=self._db_ml.get_features(),
                labels_to_exclude_lst=[label],
            )
        else:
            df_all_encode = gather_data_for_machine_learning(
                df_all=df_all,
                labels_dict=self._label_dict,
                feature_lst=[],
                labels_to_exclude_lst=[label],
            )
        models, feature_lst = self._db_ml.get_models(
            df=df_all_encode,
            n_estimators=n_estimators,
            max_features=max_features,
            random_state=random_state,
            bootstrap=bootstrap,
            user_id=self._db_user_id,
            recalculate=recalculate,
        )
        return models, feature_lst, df_all_encode

    def search_email(self, query_string="", label_lst=[], only_message_ids=False):
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

    def remove_labels_from_emails(self, label_lst):
        """
        Remove a list of labels from all emails in Gmail. A typical application is removing the Gmail smart labels:
            label_lst=["CATEGORY_FORUMS", "CATEGORY_UPDATES", "CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL"]

        Args:
            label_lst (list): list of labels
        """
        label_convert_lst = [self._label_dict[label] for label in label_lst]
        for label in tqdm(iterable=label_convert_lst, desc="Remove labels from Emails"):
            message_list_response = self._get_messages(
                query_string="", label_ids=[label]
            )
            for message_id in tqdm(
                iterable=self._get_message_ids(message_lst=message_list_response)
            ):
                self._modify_message_labels(
                    message_id=message_id, label_id_remove_lst=[label]
                )

    def _download_messages_to_dataframe(self, message_id_lst, format="full"):
        """
        Download a list of messages based on their email IDs and store the content in a pandas.DataFrame.

        Args:
            message_id_lst (list): list of emails IDs
            format (str): Email format to download - default: "full"

        Returns:
            pandas.DataFrame: pandas.DataFrame which contains the rendered emails
        """
        return pandas.DataFrame(
            [
                get_email_dict(
                    message=self._get_message_detail(message_id=message_id, format=format)
                )
                for message_id in tqdm(
                    iterable=message_id_lst, desc="Download messagees to DataFrame"
                )
            ]
        )

    def _get_machine_learning_recommendations(
        self,
        df,
        label,
        n_estimators=100,
        max_features=400,
        random_state=42,
        bootstrap=True,
        recalculate=False,
        include_deleted=False,
        recommendation_ratio=0.9,
    ):
        """
        Train internal machine learning models to predict email sorting.

        Args:
            df (pandas.DataFrame): Dataframe with emails to be sorted
            label (str): Email label to filter for
            n_estimators (int): Number of estimators
            max_features (int): Number of features
            random_state (int): Random state
            bootstrap (boolean): Whether bootstrap samples are used when building trees. If False, the whole dataset is
                                 used to build each tree. (default: true)
            recalculate (boolean): Train the model again
            include_deleted (boolean): Include deleted emails in training
            recommendation_ratio (float): Only accept recommendation above this ratio (0<r<1)

        Returns:
            dict: Email IDs and the corresponding label ID.
        """
        if len(df) > 0:
            models, feature_lst, df_all_encode = self.train_machine_learning_models(
                label=label,
                n_estimators=n_estimators,
                max_features=max_features,
                random_state=random_state,
                bootstrap=bootstrap,
                recalculate=recalculate,
                include_deleted=include_deleted,
            )
            return get_machine_learning_recommendations(
                models=models,
                df_select=df,
                df_all_encode=df_all_encode,
                feature_lst=feature_lst,
                recommendation_ratio=recommendation_ratio,
            )
        else:
            return {}

    def _get_label_translate_dict(self):
        results = self._service.users().labels().list(userId=self._userid).execute()
        labels = results.get("labels", [])
        return {label["name"]: label["id"] for label in labels}

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

    def _get_message_detail(self, message_id, format="metadata", metadata_headers=[]):
        return (
            self._service.users()
            .messages()
            .get(
                userId=self._userid,
                id=message_id,
                format=format,
                metadataHeaders=metadata_headers,
            )
            .execute()
        )

    def _filter_message_by_sender(self, filter_dict_lst, message_id):
        message = Message(
            self._get_message_detail(
                message_id=message_id, format="metadata", metadata_headers=[]
            )
        )
        for filter_dict in filter_dict_lst:
            message_from = message.get_from()
            message_to = message.get_to()
            message_subject = message.get_subject()
            if (
                "from" in filter_dict.keys()
                and message_from is not None
                and filter_dict["from"] in message_from
            ):
                return self._label_dict[filter_dict["label"]]
            if (
                "to" in filter_dict.keys()
                and message_to is not None
                and filter_dict["to"] in message_to
            ):
                return self._label_dict[filter_dict["label"]]
            if (
                "subject" in filter_dict.keys()
                and message_subject is not None
                and filter_dict["subject"] in message_subject
            ):
                return self._label_dict[filter_dict["label"]]
        return None

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

    def _store_emails_in_database(self, message_id_lst, format="full"):
        df = self._download_messages_to_dataframe(
            message_id_lst=message_id_lst, format=format
        )
        if len(df) > 0:
            self._db_email.store_dataframe(df=df, user_id=self._db_user_id)

    @staticmethod
    def _get_message_ids(message_lst):
        return [d["id"] for d in message_lst]

    @classmethod
    def create_database(cls, connection_str):
        engine = create_engine(connection_str)
        session = sessionmaker(bind=engine)()
        db_email = get_email_database(engine=engine, session=session)
        db_ml = get_machine_learning_database(engine=engine, session=session)
        return db_email, db_ml
