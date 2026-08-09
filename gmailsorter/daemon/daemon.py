from typing import Any

from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from gmailsorter.daemon.shared import (
    JOB_STATUS_FAIL,
    JOB_STATUS_INIT,
    JOB_STATUS_PROGRESS,
    JOB_STATUS_SUCCESS,
    MAILSORT_LABEL,
    SCOPES,
    GoogleMail,
    GoogleToken,
    get_task_status_for_user,
)
from gmailsorter.daemon.tasks import (
    get_all_tasks_to_execute,
    update_task_status,
)


def load_user_data_from_database(
    session: Session, mode: str
) -> tuple[dict[str, list[int]], dict[int, dict[str, Any]]]:
    job_dict = get_all_tasks_to_execute(session=session, task_name=mode)
    user_id_lst = []
    for lst in job_dict.values():
        user_id_lst += lst
    token_dict = {
        user_id: session.query(GoogleToken).filter_by(user_id=user_id).first()
        for user_id in user_id_lst
    }
    token_detail_dict = {
        key: {
            "token": token.token,
            "refresh_token": token.refresh_token,
            "token_uri": token.token_uri,
            "expiry": token.expiry,
        }
        for key, token in token_dict.items()
    }
    return job_dict, token_detail_dict


def iterate_over_users(
    user_id_lst: list[int],
    token_detail_dict: dict[int, dict[str, Any]],
    scopes: list[str],
    engine: Engine,
    session: Session,
    client_secrets_config: dict[str, Any],
    database_update: bool = True,
    filter_messages: bool = True,
    n_estimators: int = 100,
    max_features: int = 400,
    random_state: int = 42,
    bootstrap: bool = True,
    include_deleted: bool = False,
    recommendation_ratio: float = 0.9,
    max_workers: int | None = None,
) -> None:
    for user_database_id in user_id_lst:
        token_user_dict = token_detail_dict[user_database_id]
        try:
            gmail = GoogleMail(
                scopes=scopes,
                database_engine=engine,
                token=token_user_dict["token"],
                refresh_token=token_user_dict["refresh_token"],
                token_uri=token_user_dict["token_uri"],
                client_id=client_secrets_config["web"]["client_id"],
                client_secret=client_secrets_config["web"]["client_secret"],
                expiry=token_user_dict["expiry"],
                user_id="me",
                db_user_id=user_database_id,
                email_download_format="metadata",
                serviceName="gmail",
                version="v1",
            )
        except (RefreshError, HttpError):
            _ = [
                update_task_status(
                    session=session,
                    user_id=user_database_id,
                    task_name=task_name,
                    status=JOB_STATUS_FAIL,
                )
                for task_name in ["update", "fetch"]
            ]
        else:
            if database_update:
                status_start = get_task_status_for_user(
                    session=session, user_id=user_database_id, task_name="update"
                )
                update_task_status(
                    session=session,
                    user_id=user_database_id,
                    task_name="update",
                    status=JOB_STATUS_PROGRESS,
                )
                gmail.update_database(quick=False)
                gmail.fit_machine_learning_model_to_database(
                    n_estimators=n_estimators,
                    max_features=max_features,
                    random_state=random_state,
                    bootstrap=bootstrap,
                    include_deleted=include_deleted,
                    max_workers=max_workers,
                )
                if status_start == JOB_STATUS_INIT:
                    update_task_status(
                        session=session,
                        user_id=user_database_id,
                        task_name="fetch",
                        status=JOB_STATUS_INIT,
                    )
                update_task_status(
                    session=session,
                    user_id=user_database_id,
                    task_name="update",
                    status=JOB_STATUS_SUCCESS,
                )
            elif filter_messages:
                update_task_status(
                    session=session,
                    user_id=user_database_id,
                    task_name="fetch",
                    status=JOB_STATUS_PROGRESS,
                )
                try:  # Fails when email labels cannot be modified.
                    gmail.filter_messages_from_server(
                        label=MAILSORT_LABEL,
                        recommendation_ratio=recommendation_ratio,
                    )
                except HttpError:
                    update_task_status(
                        session=session,
                        user_id=user_database_id,
                        task_name="fetch",
                        status=JOB_STATUS_FAIL,
                    )
                else:
                    update_task_status(
                        session=session,
                        user_id=user_database_id,
                        task_name="fetch",
                        status=JOB_STATUS_SUCCESS,
                    )
            else:
                raise ValueError(
                    "Neither database_update or filter_messages was selected."
                )


def update(
    engine: Engine,
    client_secrets_config: dict[str, Any],
    mode: str,
    n_estimators: int = 100,
    max_features: int = 400,
    random_state: int = 42,
    bootstrap: bool = True,
    include_deleted: bool = False,
    recommendation_ratio: float = 0.9,
    max_workers: int | None = None,
) -> None:
    session = sessionmaker(bind=engine)()
    job_dict, token_detail_dict = load_user_data_from_database(
        session=session, mode=mode
    )
    for k, lst in job_dict.items():
        if k == "fetch":
            filter_messages = True
            database_update = False
        else:
            filter_messages = False
            database_update = True
        iterate_over_users(
            user_id_lst=lst,
            token_detail_dict=token_detail_dict,
            scopes=SCOPES,
            engine=engine,
            session=session,
            client_secrets_config=client_secrets_config,
            database_update=database_update,
            filter_messages=filter_messages,
            n_estimators=n_estimators,
            max_features=max_features,
            random_state=random_state,
            bootstrap=bootstrap,
            include_deleted=include_deleted,
            recommendation_ratio=recommendation_ratio,
            max_workers=max_workers,
        )
