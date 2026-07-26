import argparse
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError
from sqlalchemy.orm import sessionmaker

from gmailsorter.daemon.__main__ import _get_execution_mode, command_line_parser
from gmailsorter.daemon.daemon import (
    iterate_over_users,
    load_user_data_from_database,
    update,
)
from gmailsorter.daemon.shared import (
    JOB_STATUS_FAIL,
    JOB_STATUS_INIT,
    JOB_STATUS_PROGRESS,
    JOB_STATUS_SUCCESS,
    JOB_STATUS_WAIT,
    GoogleMail,
    GoogleToken,
    Task,
    get_database_engine,
    get_task_status_for_user,
    get_tasks_status_for_user,
    get_token,
    load_config_file,
)
from gmailsorter.daemon.tasks import (
    create_tasks_for_new_users,
    get_all_tasks_to_execute,
    update_task_status,
)


def _make_mock_service(labels=None):
    service = MagicMock()
    service.users.return_value.labels.return_value.list.return_value.execute.return_value = {
        "labels": labels
        if labels is not None
        else [
            {"name": "Inbox", "id": "LBL_INBOX"},
            {"name": "Spam", "id": "LBL_SPAM"},
        ]
    }
    return service


class TestGoogleMail(unittest.TestCase):
    def setUp(self):
        self.engine = get_database_engine(connection_str="sqlite:///:memory:")

    def _create_mail(self, service):
        with patch(
            "gmailsorter.daemon.shared.googleapiclient.discovery.build",
            return_value=service,
        ):
            return GoogleMail(
                scopes=["scope"],
                database_engine=self.engine,
                token="tok",
                refresh_token="ref",
                token_uri="uri",
                client_id="cid",
                client_secret="csecret",
                expiry=datetime.now(timezone.utc),
                db_user_id=1,
            )

    def test_session_and_close(self):
        mail = self._create_mail(_make_mock_service())
        self.assertIsNotNone(mail.session)
        mail.close_database_connection()

    def test_create_label_existing_and_new(self):
        service = _make_mock_service()
        mail = self._create_mail(service)

        self.assertEqual(mail.create_label(label_name="Inbox"), "LBL_INBOX")

        service.users.return_value.labels.return_value.create.return_value.execute.return_value = {
            "id": "LBL_NEW"
        }
        service.users.return_value.labels.return_value.list.return_value.execute.return_value = {
            "labels": [
                {"name": "Inbox", "id": "LBL_INBOX"},
                {"name": "Spam", "id": "LBL_SPAM"},
                {"name": "New", "id": "LBL_NEW"},
            ]
        }
        result = mail.create_label(label_name="New")
        self.assertEqual(result, "LBL_NEW")
        self.assertEqual(mail._label_dict["New"], "LBL_NEW")

    def test_get_filter_list_empty_and_present(self):
        service = _make_mock_service()
        mail = self._create_mail(service)

        service.users.return_value.settings.return_value.filters.return_value.list.return_value.execute.return_value = {}
        self.assertEqual(mail.get_filter_list(), [])

        service.users.return_value.settings.return_value.filters.return_value.list.return_value.execute.return_value = {
            "filter": [{"id": "f1"}]
        }
        self.assertEqual(mail.get_filter_list(), [{"id": "f1"}])

    def test_create_filter_moving_all_labels_creates_new(self):
        service = _make_mock_service()
        mail = self._create_mail(service)
        service.users.return_value.settings.return_value.filters.return_value.list.return_value.execute.return_value = {}
        service.users.return_value.settings.return_value.filters.return_value.create.return_value.execute.return_value = {
            "id": "FILTER_1"
        }

        filter_id = mail.create_filter_moving_all_labels(label_name="Inbox")
        self.assertEqual(filter_id, "FILTER_1")

    def test_create_filter_moving_all_labels_matches_existing(self):
        service = _make_mock_service()
        mail = self._create_mail(service)
        existing_filter = {
            "id": "FILTER_1",
            "criteria": {"from": "*", "to": "*"},
            "action": {
                "addLabelIds": ["LBL_INBOX"],
                "removeLabelIds": ["INBOX", "SPAM"],
            },
        }
        service.users.return_value.settings.return_value.filters.return_value.list.return_value.execute.return_value = {
            "filter": [existing_filter]
        }

        filter_id = mail.create_filter_moving_all_labels(label_name="Inbox")
        self.assertEqual(filter_id, "FILTER_1")

    def test_create_filter_moving_all_labels_mismatched_raises_value_error(self):
        service = _make_mock_service()
        mail = self._create_mail(service)
        mismatched_filter = {
            "id": "FILTER_1",
            "criteria": {"from": "someone@else.com", "to": "*"},
            "action": {
                "addLabelIds": ["LBL_INBOX"],
                "removeLabelIds": ["INBOX", "SPAM"],
            },
        }
        service.users.return_value.settings.return_value.filters.return_value.list.return_value.execute.return_value = {
            "filter": [mismatched_filter]
        }

        with self.assertRaises(ValueError):
            mail.create_filter_moving_all_labels(label_name="Inbox")

    def test_create_filter_moving_all_labels_multiple_raises_type_error(self):
        service = _make_mock_service()
        mail = self._create_mail(service)
        service.users.return_value.settings.return_value.filters.return_value.list.return_value.execute.return_value = {
            "filter": [{"id": "f1"}, {"id": "f2"}]
        }

        with self.assertRaises(TypeError):
            mail.create_filter_moving_all_labels(label_name="Inbox")

    def test_get_status_dict_success_and_filter_failure(self):
        service = _make_mock_service()
        mail = self._create_mail(service)
        service.users.return_value.settings.return_value.filters.return_value.list.return_value.execute.return_value = {
            "filter": [{"id": "f1"}, {"id": "f2"}]
        }

        status_dict = mail.get_status_dict(label_name="Inbox")
        self.assertEqual(status_dict["label"], JOB_STATUS_SUCCESS)
        self.assertEqual(status_dict["filter"], JOB_STATUS_FAIL)
        self.assertIn("update", status_dict)
        self.assertIn("fetch", status_dict)


class TestSharedHelpers(unittest.TestCase):
    def setUp(self):
        self.engine = get_database_engine(connection_str="sqlite:///:memory:")
        self.session = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.session.close()

    def test_get_token_missing_and_present(self):
        self.assertIsNone(get_token(session=self.session, user_id=42))

        token = GoogleToken(user_id=42, token="tok")
        self.session.add(token)
        self.session.commit()
        fetched = get_token(session=self.session, user_id=42)
        self.assertEqual(fetched.token, "tok")

    def test_get_task_status_for_user_missing_and_present(self):
        self.assertIsNone(
            get_task_status_for_user(
                session=self.session, user_id=1, task_name="update"
            )
        )
        self.session.add(
            Task(
                task_name="update",
                date=datetime.now(),
                status=JOB_STATUS_INIT,
                user_id=1,
            )
        )
        self.session.commit()
        self.assertEqual(
            get_task_status_for_user(
                session=self.session, user_id=1, task_name="update"
            ),
            JOB_STATUS_INIT,
        )

    def test_get_tasks_status_for_user(self):
        self.session.add_all(
            [
                Task(
                    task_name="update",
                    date=datetime.now(),
                    status=JOB_STATUS_INIT,
                    user_id=1,
                ),
                Task(
                    task_name="fetch",
                    date=datetime.now(),
                    status=JOB_STATUS_WAIT,
                    user_id=1,
                ),
            ]
        )
        self.session.commit()
        self.assertEqual(
            get_tasks_status_for_user(session=self.session, user_id=1),
            {"update": JOB_STATUS_INIT, "fetch": JOB_STATUS_WAIT},
        )

    def test_load_config_file(self):
        import json
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"web": {"client_id": "abc"}}, f)
            file_name = f.name
        try:
            loaded = load_config_file(file_name=file_name)
        finally:
            os.remove(file_name)
        self.assertEqual(loaded["web"]["client_id"], "abc")


class TestTasks(unittest.TestCase):
    def setUp(self):
        self.engine = get_database_engine(connection_str="sqlite:///:memory:")
        self.session = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.session.close()

    def test_create_tasks_for_new_users_creates_both(self):
        create_tasks_for_new_users(session=self.session, user_id=1)
        tasks = self.session.query(Task).filter(Task.user_id == 1).all()
        self.assertEqual({t.task_name for t in tasks}, {"update", "fetch"})
        self.assertEqual(
            {t.task_name: t.status for t in tasks},
            {"update": JOB_STATUS_INIT, "fetch": JOB_STATUS_WAIT},
        )

    def test_create_tasks_for_new_users_skips_existing(self):
        create_tasks_for_new_users(session=self.session, user_id=1)
        create_tasks_for_new_users(session=self.session, user_id=1)
        tasks = self.session.query(Task).filter(Task.user_id == 1).all()
        self.assertEqual(len(tasks), 2)

    def test_update_task_status(self):
        create_tasks_for_new_users(session=self.session, user_id=1)
        update_task_status(
            session=self.session,
            user_id=1,
            task_name="update",
            status=JOB_STATUS_SUCCESS,
        )
        self.assertEqual(
            get_task_status_for_user(
                session=self.session, user_id=1, task_name="update"
            ),
            JOB_STATUS_SUCCESS,
        )

    def test_get_all_tasks_to_execute_invalid_task_name(self):
        with self.assertRaises(ValueError):
            get_all_tasks_to_execute(session=self.session, task_name="bogus")

    def test_get_all_tasks_to_execute_all(self):
        self.session.add_all(
            [
                Task(
                    task_name="update",
                    date=datetime.now(),
                    status=JOB_STATUS_INIT,
                    user_id=1,
                ),
                Task(
                    task_name="fetch",
                    date=datetime.now(),
                    status=JOB_STATUS_WAIT,
                    user_id=1,
                ),
                Task(
                    task_name="update",
                    date=datetime.now(),
                    status=JOB_STATUS_SUCCESS,
                    user_id=2,
                ),
            ]
        )
        self.session.commit()
        result = get_all_tasks_to_execute(session=self.session, task_name="all")
        self.assertEqual(set(result["update"]), {1, 2})
        self.assertNotIn("fetch", result)

    def test_get_all_tasks_to_execute_update_and_fetch(self):
        self.session.add_all(
            [
                Task(
                    task_name="update",
                    date=datetime.now(),
                    status=JOB_STATUS_INIT,
                    user_id=1,
                ),
                Task(
                    task_name="fetch",
                    date=datetime.now(),
                    status=JOB_STATUS_WAIT,
                    user_id=1,
                ),
            ]
        )
        self.session.commit()
        result_update = get_all_tasks_to_execute(
            session=self.session, task_name="update"
        )
        self.assertEqual(result_update, {"update": [1]})

        result_fetch = get_all_tasks_to_execute(session=self.session, task_name="fetch")
        self.assertEqual(result_fetch, {})

    def test_get_all_tasks_to_execute_select(self):
        self.session.add_all(
            [
                Task(
                    task_name="update",
                    date=datetime.now(),
                    status=JOB_STATUS_INIT,
                    user_id=1,
                ),
                Task(
                    task_name="fetch",
                    date=datetime.now(),
                    status=JOB_STATUS_SUCCESS,
                    user_id=1,
                ),
            ]
        )
        self.session.commit()
        result = get_all_tasks_to_execute(session=self.session, task_name="select")
        self.assertEqual(result, {"update": [1], "fetch": [1]})


class TestDaemon(unittest.TestCase):
    def setUp(self):
        self.engine = get_database_engine(connection_str="sqlite:///:memory:")
        self.session = sessionmaker(bind=self.engine)()
        self.session.add(
            GoogleToken(
                user_id=1,
                token="tok",
                refresh_token="ref",
                token_uri="uri",
                expiry=datetime.now(timezone.utc),
            )
        )
        self.session.add_all(
            [
                Task(
                    task_name="update",
                    date=datetime.now(),
                    status=JOB_STATUS_INIT,
                    user_id=1,
                ),
                Task(
                    task_name="fetch",
                    date=datetime.now(),
                    status=JOB_STATUS_WAIT,
                    user_id=1,
                ),
            ]
        )
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def test_load_user_data_from_database(self):
        job_dict, token_detail_dict = load_user_data_from_database(
            session=self.session, mode="update"
        )
        self.assertEqual(job_dict, {"update": [1]})
        self.assertEqual(token_detail_dict[1]["token"], "tok")

    @patch("gmailsorter.daemon.daemon.GoogleMail")
    def test_iterate_over_users_refresh_error_marks_failed(self, mail_cls):
        mail_cls.side_effect = RefreshError("bad token")
        iterate_over_users(
            user_id_lst=[1],
            token_detail_dict={
                1: {
                    "token": "t",
                    "refresh_token": "r",
                    "token_uri": "u",
                    "expiry": datetime.now(timezone.utc),
                }
            },
            scopes=["scope"],
            engine=self.engine,
            session=self.session,
            client_secrets_config={"web": {"client_id": "cid", "client_secret": "sec"}},
        )
        self.assertEqual(
            get_task_status_for_user(
                session=self.session, user_id=1, task_name="update"
            ),
            JOB_STATUS_FAIL,
        )
        self.assertEqual(
            get_task_status_for_user(
                session=self.session, user_id=1, task_name="fetch"
            ),
            JOB_STATUS_FAIL,
        )

    @patch("gmailsorter.daemon.daemon.GoogleMail")
    def test_iterate_over_users_database_update_success(self, mail_cls):
        mail_instance = MagicMock()
        mail_cls.return_value = mail_instance

        iterate_over_users(
            user_id_lst=[1],
            token_detail_dict={
                1: {
                    "token": "t",
                    "refresh_token": "r",
                    "token_uri": "u",
                    "expiry": datetime.now(timezone.utc),
                }
            },
            scopes=["scope"],
            engine=self.engine,
            session=self.session,
            client_secrets_config={"web": {"client_id": "cid", "client_secret": "sec"}},
            database_update=True,
            filter_messages=False,
        )
        mail_instance.update_database.assert_called_once_with(quick=False)
        mail_instance.fit_machine_learning_model_to_database.assert_called_once()
        self.assertEqual(
            get_task_status_for_user(
                session=self.session, user_id=1, task_name="update"
            ),
            JOB_STATUS_SUCCESS,
        )
        self.assertEqual(
            get_task_status_for_user(
                session=self.session, user_id=1, task_name="fetch"
            ),
            JOB_STATUS_INIT,
        )

    @patch("gmailsorter.daemon.daemon.GoogleMail")
    def test_iterate_over_users_filter_messages_success(self, mail_cls):
        mail_instance = MagicMock()
        mail_cls.return_value = mail_instance
        update_task_status(
            session=self.session, user_id=1, task_name="fetch", status=JOB_STATUS_WAIT
        )

        iterate_over_users(
            user_id_lst=[1],
            token_detail_dict={
                1: {
                    "token": "t",
                    "refresh_token": "r",
                    "token_uri": "u",
                    "expiry": datetime.now(timezone.utc),
                }
            },
            scopes=["scope"],
            engine=self.engine,
            session=self.session,
            client_secrets_config={"web": {"client_id": "cid", "client_secret": "sec"}},
            database_update=False,
            filter_messages=True,
        )
        mail_instance.filter_messages_from_server.assert_called_once()
        self.assertEqual(
            get_task_status_for_user(
                session=self.session, user_id=1, task_name="fetch"
            ),
            JOB_STATUS_SUCCESS,
        )

    @patch("gmailsorter.daemon.daemon.GoogleMail")
    def test_iterate_over_users_filter_messages_http_error(self, mail_cls):
        mail_instance = MagicMock()
        mail_instance.filter_messages_from_server.side_effect = HttpError(
            resp=MagicMock(status=403), content=b"error"
        )
        mail_cls.return_value = mail_instance
        update_task_status(
            session=self.session, user_id=1, task_name="fetch", status=JOB_STATUS_WAIT
        )

        iterate_over_users(
            user_id_lst=[1],
            token_detail_dict={
                1: {
                    "token": "t",
                    "refresh_token": "r",
                    "token_uri": "u",
                    "expiry": datetime.now(timezone.utc),
                }
            },
            scopes=["scope"],
            engine=self.engine,
            session=self.session,
            client_secrets_config={"web": {"client_id": "cid", "client_secret": "sec"}},
            database_update=False,
            filter_messages=True,
        )
        self.assertEqual(
            get_task_status_for_user(
                session=self.session, user_id=1, task_name="fetch"
            ),
            JOB_STATUS_FAIL,
        )

    @patch("gmailsorter.daemon.daemon.GoogleMail")
    def test_iterate_over_users_neither_flag_raises(self, mail_cls):
        mail_cls.return_value = MagicMock()
        with self.assertRaises(ValueError):
            iterate_over_users(
                user_id_lst=[1],
                token_detail_dict={
                    1: {
                        "token": "t",
                        "refresh_token": "r",
                        "token_uri": "u",
                        "expiry": datetime.now(timezone.utc),
                    }
                },
                scopes=["scope"],
                engine=self.engine,
                session=self.session,
                client_secrets_config={
                    "web": {"client_id": "cid", "client_secret": "sec"}
                },
                database_update=False,
                filter_messages=False,
            )

    @patch("gmailsorter.daemon.daemon.iterate_over_users")
    def test_update_dispatches_per_mode(self, iterate_mock):
        update(
            engine=self.engine,
            client_secrets_config={"web": {"client_id": "cid", "client_secret": "sec"}},
            mode="update",
        )
        iterate_mock.assert_called_once()
        _, kwargs = iterate_mock.call_args
        self.assertEqual(kwargs["user_id_lst"], [1])
        self.assertTrue(kwargs["database_update"])
        self.assertFalse(kwargs["filter_messages"])


class TestDaemonMain(unittest.TestCase):
    def test_get_execution_mode(self):
        self.assertEqual(
            _get_execution_mode(
                argparse.Namespace(update=True, filter=True, scheduled=False)
            ),
            "all",
        )
        self.assertEqual(
            _get_execution_mode(
                argparse.Namespace(update=True, filter=False, scheduled=False)
            ),
            "update",
        )
        self.assertEqual(
            _get_execution_mode(
                argparse.Namespace(update=False, filter=False, scheduled=True)
            ),
            "select",
        )
        self.assertEqual(
            _get_execution_mode(
                argparse.Namespace(update=False, filter=True, scheduled=False)
            ),
            "fetch",
        )
        with self.assertRaises(ValueError):
            _get_execution_mode(
                argparse.Namespace(update=False, filter=False, scheduled=False)
            )

    @patch("gmailsorter.daemon.__main__.update")
    @patch("gmailsorter.daemon.__main__.get_database_engine")
    @patch("gmailsorter.daemon.__main__.load_config_file")
    def test_command_line_parser_runs_update(
        self, load_config_mock, get_engine_mock, update_mock
    ):
        load_config_mock.return_value = {"web": {}}
        get_engine_mock.return_value = "ENGINE"

        with patch(
            "sys.argv",
            [
                "gmailsortdaemon",
                "-c",
                "creds.json",
                "-d",
                "sqlite:///:memory:",
                "-u",
            ],
        ):
            command_line_parser()

        load_config_mock.assert_called_once_with(file_name="creds.json")
        get_engine_mock.assert_called_once_with(connection_str="sqlite:///:memory:")
        update_mock.assert_called_once()
        _, kwargs = update_mock.call_args
        self.assertEqual(kwargs["mode"], "update")
        self.assertEqual(kwargs["engine"], "ENGINE")

    @patch("gmailsorter.daemon.__main__.update")
    def test_command_line_parser_missing_credentials_raises(self, update_mock):
        import os
        import tempfile

        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.chdir(tmp_dir)
            try:
                with patch("sys.argv", ["gmailsortdaemon"]):
                    with self.assertRaises(ValueError):
                        command_line_parser()
            finally:
                os.chdir(cwd)
        update_mock.assert_not_called()

    @patch("gmailsorter.daemon.__main__.get_database_engine")
    @patch("gmailsorter.daemon.__main__.load_config_file", return_value={"web": {}})
    def test_command_line_parser_missing_database_raises(
        self, load_config_mock, get_engine_mock
    ):
        import os
        import tempfile

        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.chdir(tmp_dir)
            try:
                with patch("sys.argv", ["gmailsortdaemon", "-c", "creds.json"]):
                    with self.assertRaises(ValueError):
                        command_line_parser()
            finally:
                os.chdir(cwd)
        get_engine_mock.assert_not_called()

    @patch("gmailsorter.daemon.__main__.update")
    @patch("gmailsorter.daemon.__main__.get_database_engine", return_value="ENGINE")
    @patch("gmailsorter.daemon.__main__.load_config_file", return_value={"web": {}})
    def test_command_line_parser_prints_help_without_flags(
        self, load_config_mock, get_engine_mock, update_mock
    ):
        with patch(
            "sys.argv",
            ["gmailsortdaemon", "-c", "creds.json", "-d", "sqlite:///:memory:"],
        ):
            command_line_parser()
        update_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
