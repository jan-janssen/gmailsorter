from datetime import datetime
from gmailsorter.daemon.shared import (
    Task,
    JOB_STATUS_INIT,
    JOB_STATUS_WAIT,
    JOB_STATUS_SUCCESS,
)


def create_tasks_for_new_users(session, user_id):
    task_lst = []
    task_update_from_database = (
        session.query(Task)
        .filter(Task.user_id == user_id)
        .filter(Task.task_name == "update")
        .first()
    )
    if task_update_from_database is None:
        task_lst.append(
            Task(
                task_name="update",
                date=datetime.now(),
                status=JOB_STATUS_INIT,
                user_id=user_id,
            )
        )
    task_fetch_from_database = (
        session.query(Task)
        .filter(Task.user_id == user_id)
        .filter(Task.task_name == "fetch")
        .first()
    )
    if task_fetch_from_database is None:
        task_lst.append(
            Task(
                task_name="fetch",
                date=datetime.now(),
                status=JOB_STATUS_WAIT,
                user_id=user_id,
            )
        )
    if len(task_lst) > 0:
        session.add_all(task_lst)
        session.commit()


def update_task_status(session, user_id, task_name, status):
    task = (
        session.query(Task)
        .filter(Task.user_id == user_id)
        .filter(Task.task_name == task_name)
        .first()
    )
    task.status = status
    task.date = datetime.now()
    session.commit()


def get_all_tasks_to_execute(session, task_name="all"):
    if task_name not in ["all", "update", "fetch", "select"]:
        raise ValueError(
            'The task_name parameter has to be one of the following ["all", "update", "fetch", "select"]'
        )
    tasks_to_execute = [JOB_STATUS_INIT, JOB_STATUS_SUCCESS]
    if task_name in ["update", "fetch"]:
        task_dict = {
            task_name: [
                task.user_id
                for task in session.query(Task).filter_by(task_name=task_name).all()
                if task.status in tasks_to_execute
            ]
        }
    elif task_name == "all":
        task_dict = {
            "update": [
                task.user_id
                for task in session.query(Task).filter_by(task_name="update").all()
                if task.status in tasks_to_execute
            ],
            "fetch": [
                task.user_id
                for task in session.query(Task).filter_by(task_name="fetch").all()
                if task.status in tasks_to_execute
            ],
        }
    elif task_name == "select":
        task_dict = {
            "update": [
                task.user_id
                for task in session.query(Task).filter_by(task_name="update").all()
                if task.status == JOB_STATUS_INIT
            ],
            "fetch": [
                task.user_id
                for task in session.query(Task).filter_by(task_name="fetch").all()
                if task.status in tasks_to_execute
            ],
        }
    else:
        task_dict = dict()
    return {k: v for k, v in task_dict.items() if len(v) > 0}
