import json
from sqlalchemy import create_engine
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base
import googleapiclient.discovery
import google.oauth2.credentials
from sqlalchemy.orm import sessionmaker
from gmailsorter.google import GoogleMailBase
from gmailsorter.base import get_email_database
from gmailsorter.google.database import get_token_database
from gmailsorter.ml import get_machine_learning_database

# Modifying the labels of emails requires /auth/gmail.modify
# https://developers.google.com/gmail/api/reference/rest/v1/users.messages/modify
SCOPES = [
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.settings.basic",
    "openid",
]


MAILSORT_LABEL = "mailsortinbox"

# Job Status Constants
JOB_STATUS_SUCCESS = "success"
JOB_STATUS_FAIL = "fail"
JOB_STATUS_PROGRESS = "progress"
JOB_STATUS_WAIT = "wait"
JOB_STATUS_INIT = "init"


Base = declarative_base()


class GoogleToken(Base):
    __tablename__ = "google_token"
    id = Column(Integer, primary_key=True)
    token = Column(String)
    refresh_token = Column(String)
    token_uri = Column(String)
    client_id = Column(String)
    client_secret = Column(String)
    scopes = Column(String)
    expiry = Column(DateTime)
    user_id = Column(Integer)


class SQLUser(Base):
    __tablename__ = "google_user"
    id = Column(Integer, primary_key=True)
    google_id = Column(String)
    name = Column(String)
    email = Column(String)
    profile_pic = Column(String)


class Task(Base):
    __tablename__ = "google_task"
    id = Column(Integer, primary_key=True)
    task_name = Column(String)
    date = Column(DateTime)
    status = Column(String)
    user_id = Column(Integer)


class GoogleMail(GoogleMailBase):
    def __init__(
        self,
        scopes,
        database_engine,
        token,
        refresh_token,
        token_uri,
        client_id,
        client_secret,
        expiry,
        user_id="me",
        db_user_id=1,
        email_download_format="metadata",
        serviceName="gmail",
        version="v1",
    ):
        """
        Gmail class to manage Emails via the Gmail API directly from Python

        Args:
            database_engine: SQLalchemy database engine
            user_id (str): in most cases this should be simply "me"
            db_user_id (int): Default 1 - set a user id when sharing a database with multiple users
            port (int): system communication port to start authentication webserver
            email_download_format (str): API response format [full, metadata]
        """
        # Create config directory
        self._database_engine = database_engine

        # Initialize database
        database_email, database_ml, database_token = self._create_databases(
            engine=database_engine
        )

        # Initialise service
        cred = google.oauth2.credentials.Credentials(
            token=token,
            refresh_token=refresh_token,
            id_token=None,
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret,
            scopes=scopes,
            default_scopes=None,
            quota_project_id=None,
            expiry=expiry,
            rapt_token=None,
            refresh_handler=None,
            enable_reauth_refresh=False,
        )
        google_mail_service = googleapiclient.discovery.build(
            serviceName=serviceName, version=version, credentials=cred
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

    @property
    def session(self):
        return self._session

    def close_database_connection(self):
        self._session.close()

    def create_filter_moving_all_labels(self, label_name):
        """
        Create a filter to move all emails to the selected label.

        Args:
            label_name (str): Name of the new email label

        Returns:
            str: Filter ID of the newly created label
        """
        label_google_name = self._label_dict[label_name]
        filter_lst = self.get_filter_list()
        if len(filter_lst) > 1:
            raise TypeError(
                "Multiple filter exist already, so no new filter is created."
            )
        elif len(filter_lst) == 1:
            filter_dict = filter_lst[0]
            if (
                "from" in filter_dict["criteria"].keys()
                and "to" in filter_dict["criteria"].keys()
                and "addLabelIds" in filter_dict["action"].keys()
                and "removeLabelIds" in filter_dict["action"].keys()
                and filter_dict["criteria"]["from"] == "*"
                and filter_dict["criteria"]["to"] == "*"
                and len(filter_dict["action"]["addLabelIds"]) == 1
                and filter_dict["action"]["addLabelIds"][0] == label_google_name
                and len(filter_dict["action"]["removeLabelIds"]) == 2
                and "INBOX" in filter_dict["action"]["removeLabelIds"]
                and "SPAM" in filter_dict["action"]["removeLabelIds"]
            ):
                return filter_dict["id"]
            else:
                raise ValueError("A filter exists but it does not match the signature.")
        else:
            filter_content = {
                "criteria": {"from": "*", "to": "*"},
                "action": {
                    "addLabelIds": [label_google_name],
                    "removeLabelIds": ["INBOX", "SPAM"],
                },
            }
            result = (
                self._service.users()
                .settings()
                .filters()
                .create(userId="me", body=filter_content)
                .execute()
            )
            return result["id"]

    def create_label(
        self,
        label_name,
        label_list_visibility="labelHide",
        message_list_visibility="hide",
    ):
        """
        Create a new email label using the Google API and return the label ID. If the label already exists this function
        still returns the label ID. More information can be found in the Google API documentation:
        https://developers.google.com/gmail/api/reference/rest/v1/users.labels/create

        Args:
            label_name (str): Name of the new email label
            label_list_visibility (str): can be one of the following ["labelHide", "labelShow", "labelShowIfUnread"]
            message_list_visibility (str): can be one of the following ["hide", "show"]

        Returns:
            str: Label ID of the newly created label
        """
        if label_name in self._label_dict.keys():
            return self._label_dict[label_name]
        else:
            label_request = {
                "labelListVisibility": label_list_visibility,
                "messageListVisibility": message_list_visibility,
                "name": label_name,
            }
            result = (
                self._service.users()
                .labels()
                .create(userId="me", body=label_request)
                .execute()
            )
            self._label_dict = self._get_label_translate_dict()
            self._label_dict_inverse = {v: k for k, v in self._label_dict.items()}
            return result["id"]

    def get_filter_list(self):
        results = self._service.users().settings().filters().list(userId="me").execute()
        if "filter" in results.keys():
            return results["filter"]
        else:
            return []

    def get_status_dict(self, label_name):
        status_dict = get_tasks_status_for_user(
            session=self._session, user_id=self._db_user_id
        )
        label_id = self.create_label(
            label_name=label_name,
            label_list_visibility="labelHide",
            message_list_visibility="show",
        )
        if isinstance(label_id, str):
            status_dict["label"] = JOB_STATUS_SUCCESS
        else:
            status_dict["label"] = JOB_STATUS_FAIL
        try:
            filter_id = self.create_filter_moving_all_labels(label_name=label_name)
            if isinstance(filter_id, str):
                status_dict["filter"] = JOB_STATUS_SUCCESS
            else:
                status_dict["filter"] = JOB_STATUS_FAIL
        except (ValueError, TypeError):
            status_dict["filter"] = JOB_STATUS_FAIL
        return status_dict

    def _create_databases(self, engine):
        self._session = sessionmaker(bind=engine)()
        db_email = get_email_database(engine=engine, session=self._session)
        db_ml = get_machine_learning_database(engine=engine, session=self._session)
        db_token = get_token_database(engine=engine, session=self._session)
        return db_email, db_ml, db_token


def get_database_engine(connection_str):
    engine = create_engine(connection_str)
    Base.metadata.create_all(engine)
    return engine


def get_task_status_for_user(session, user_id, task_name):
    status_obj = (
        session.query(Task)
        .filter(Task.user_id == user_id)
        .filter(Task.task_name == task_name)
        .first()
    )
    if status_obj is not None:
        return status_obj.status
    else:
        return None


def get_tasks_status_for_user(session, user_id):
    return {
        task_name: get_task_status_for_user(
            session=session, user_id=user_id, task_name=task_name
        )
        for task_name in ["update", "fetch"]
    }


def get_token(session, user_id):
    return session.query(GoogleToken).filter_by(user_id=user_id).first()


def load_config_file(file_name):
    with open(file_name, "r") as json_file:
        return json.load(json_file)
