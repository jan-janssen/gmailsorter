import importlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError
from sqlalchemy.orm import sessionmaker

from gmailsorter.daemon.shared import (
    JOB_STATUS_FAIL,
    JOB_STATUS_PROGRESS,
    JOB_STATUS_SUCCESS,
    GoogleToken,
    SQLUser,
    get_database_engine,
)
from gmailsorter.webapp import googleapi
from gmailsorter.webapp.database import (
    create_user_in_database,
    update_token_in_database,
)
from gmailsorter.webapp.render import color_for_status
from gmailsorter.webapp.user import FlaskUser, get_flask_user

# --- module-level setup so `gmailsorter.webapp.app`/`config` can be imported ---
_TMP_CREDENTIALS = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
json.dump(
    {"web": {"client_id": "test-client", "client_secret": "test-secret"}},
    _TMP_CREDENTIALS,
)
_TMP_CREDENTIALS.close()

os.environ.setdefault("MAILSORT_ENV_SECRET_KEY", "test-secret-key")
os.environ.setdefault("MAILSORT_ENV_CREDENTIALS_FILE", _TMP_CREDENTIALS.name)
os.environ.setdefault("MAILSORT_ENV_DATABASE_URL", "sqlite:///:memory:")

from gmailsorter.webapp import app as webapp_app  # noqa: E402


class TestRender(unittest.TestCase):
    def test_color_for_status_success(self):
        self.assertIn("MediumSeaGreen", color_for_status(JOB_STATUS_SUCCESS))
        self.assertIn(JOB_STATUS_SUCCESS, color_for_status(JOB_STATUS_SUCCESS))

    def test_color_for_status_fail(self):
        self.assertIn("Tomato", color_for_status(JOB_STATUS_FAIL))

    def test_color_for_status_other(self):
        self.assertIn("Orange", color_for_status(JOB_STATUS_PROGRESS))
        self.assertIn("Orange", color_for_status("wait"))


class TestWebappDatabase(unittest.TestCase):
    def setUp(self):
        self.engine = get_database_engine(connection_str="sqlite:///:memory:")
        self.session = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.session.close()

    def test_create_user_in_database_creates_user_and_token(self):
        user_id = create_user_in_database(
            session=self.session,
            google_id="g1",
            name="Jane",
            email="jane@test.com",
            profile_pic="pic.png",
            token="tok",
            refresh_token="ref",
            token_uri="uri",
            client_id="cid",
            client_secret="csecret",
            expiry=datetime.now(timezone.utc),
        )
        self.assertIsInstance(user_id, int)
        user = self.session.query(SQLUser).filter_by(id=user_id).first()
        self.assertEqual(user.google_id, "g1")
        token = self.session.query(GoogleToken).filter_by(user_id=user_id).first()
        self.assertEqual(token.token, "tok")

    def test_update_token_in_database_creates_new_token(self):
        update_token_in_database(
            session=self.session,
            user_id=5,
            token="tok",
            refresh_token="ref",
            token_uri="uri",
            client_id="cid",
            client_secret="csecret",
            expiry=datetime.now(timezone.utc),
        )
        token = self.session.query(GoogleToken).filter_by(user_id=5).first()
        self.assertEqual(token.token, "tok")

    def test_update_token_in_database_updates_existing_token(self):
        update_token_in_database(
            session=self.session,
            user_id=5,
            token="tok1",
            refresh_token="ref1",
            token_uri="uri1",
            client_id="cid1",
            client_secret="csecret1",
            expiry=datetime.now(timezone.utc),
        )
        update_token_in_database(
            session=self.session,
            user_id=5,
            token="tok2",
            refresh_token="ref2",
            token_uri="uri2",
            client_id="cid2",
            client_secret="csecret2",
            expiry=datetime.now(timezone.utc),
        )
        tokens = self.session.query(GoogleToken).filter_by(user_id=5).all()
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0].token, "tok2")


class TestWebappUser(unittest.TestCase):
    def setUp(self):
        self.engine = get_database_engine(connection_str="sqlite:///:memory:")

    def test_get_flask_user_no_update_missing_user_returns_none(self):
        result = get_flask_user(engine=self.engine, google_id="missing", update=False)
        self.assertIsNone(result)

    def test_get_flask_user_no_update_existing_user(self):
        session = sessionmaker(bind=self.engine)()
        create_user_in_database(
            session=session,
            google_id="g1",
            name="Jane",
            email="jane@test.com",
            profile_pic="pic.png",
            token="tok",
            refresh_token="ref",
            token_uri="uri",
            client_id="cid",
            client_secret="csecret",
            expiry=datetime.now(timezone.utc),
        )
        session.close()

        flask_user = get_flask_user(engine=self.engine, google_id="g1", update=False)
        self.assertIsInstance(flask_user, FlaskUser)
        self.assertEqual(flask_user.name, "Jane")
        self.assertEqual(flask_user.token, "tok")

    def test_get_flask_user_update_creates_new_user(self):
        flask_user = get_flask_user(
            engine=self.engine,
            google_id="g2",
            users_name="Bob",
            users_email="bob@test.com",
            picture="bob.png",
            token="tok2",
            refresh_token="ref2",
            token_uri="uri2",
            client_id="cid2",
            client_secret="csecret2",
            expiry=datetime.now(timezone.utc),
            update=True,
        )
        self.assertEqual(flask_user.name, "Bob")
        self.assertIsInstance(flask_user.database_id, int)

        session = sessionmaker(bind=self.engine)()
        stored_user = session.query(SQLUser).filter_by(google_id="g2").first()
        self.assertIsNotNone(stored_user)
        session.close()

    def test_get_flask_user_update_existing_user_with_refresh_token(self):
        session = sessionmaker(bind=self.engine)()
        create_user_in_database(
            session=session,
            google_id="g3",
            name="Ann",
            email="ann@test.com",
            profile_pic="ann.png",
            token="tok3",
            refresh_token="ref3",
            token_uri="uri3",
            client_id="cid3",
            client_secret="csecret3",
            expiry=datetime.now(timezone.utc),
        )
        session.close()

        get_flask_user(
            engine=self.engine,
            google_id="g3",
            users_name="Ann",
            users_email="ann@test.com",
            picture="ann.png",
            token="tok3-new",
            refresh_token="ref3-new",
            token_uri="uri3-new",
            client_id="cid3-new",
            client_secret="csecret3-new",
            expiry=datetime.now(timezone.utc),
            update=True,
        )

        session = sessionmaker(bind=self.engine)()
        stored_user = session.query(SQLUser).filter_by(google_id="g3").first()
        token = session.query(GoogleToken).filter_by(user_id=stored_user.id).first()
        self.assertEqual(token.token, "tok3-new")
        session.close()

    def test_get_flask_user_update_existing_user_without_refresh_token(self):
        session = sessionmaker(bind=self.engine)()
        create_user_in_database(
            session=session,
            google_id="g4",
            name="Sam",
            email="sam@test.com",
            profile_pic="sam.png",
            token="tok4",
            refresh_token="ref4",
            token_uri="uri4",
            client_id="cid4",
            client_secret="csecret4",
            expiry=datetime.now(timezone.utc),
        )
        session.close()

        flask_user = get_flask_user(
            engine=self.engine,
            google_id="g4",
            users_name="Sam",
            users_email="sam@test.com",
            picture="sam.png",
            token=None,
            refresh_token=None,
            update=True,
        )
        self.assertEqual(flask_user.name, "Sam")

        session = sessionmaker(bind=self.engine)()
        stored_user = session.query(SQLUser).filter_by(google_id="g4").first()
        token = session.query(GoogleToken).filter_by(user_id=stored_user.id).first()
        # Token was not touched because refresh_token was None.
        self.assertEqual(token.token, "tok4")
        session.close()


class TestGoogleApi(unittest.TestCase):
    @patch("gmailsorter.webapp.googleapi.google_auth_oauthlib.flow.Flow")
    def test_get_authentication_url(self, flow_cls):
        flow = flow_cls.from_client_config.return_value
        flow.authorization_url.return_value = ("http://auth.url", "state123")
        flow.code_verifier = "verifier123"

        url, state, code_verifier = googleapi.get_authentication_url(
            client_config={"web": {}}, scopes=["scope"], redirect_uri="http://cb"
        )

        self.assertEqual(url, "http://auth.url")
        self.assertEqual(state, "state123")
        self.assertEqual(code_verifier, "verifier123")
        self.assertEqual(flow.redirect_uri, "http://cb")
        flow.authorization_url.assert_called_once_with(
            access_type="offline", include_granted_scopes="true"
        )

    @patch("gmailsorter.webapp.googleapi.google_auth_oauthlib.flow.Flow")
    def test_get_google_credentials(self, flow_cls):
        flow = flow_cls.from_client_config.return_value
        credentials = MagicMock(
            token="tok",
            refresh_token="ref",
            token_uri="uri",
            client_id="cid",
            client_secret="csecret",
            scopes=["scope"],
            expiry=datetime.now(timezone.utc),
        )
        flow.credentials = credentials

        result = googleapi.get_google_credentials(
            client_config={"web": {}},
            scopes=["scope"],
            state="state123",
            code_verifier="verifier123",
            redirect_uri="http://cb",
            authorization_response="http://cb?code=abc",
        )

        self.assertEqual(result["token"], "tok")
        self.assertEqual(result["refresh_token"], "ref")
        flow.fetch_token.assert_called_once_with(
            authorization_response="http://cb?code=abc"
        )

    def test_credentials_to_dict(self):
        credentials = MagicMock(
            token="tok",
            refresh_token="ref",
            token_uri="uri",
            client_id="cid",
            client_secret="csecret",
            scopes=["scope"],
            expiry=datetime.now(timezone.utc),
        )
        result = googleapi._credentials_to_dict(credentials=credentials)
        self.assertEqual(result["token"], "tok")
        self.assertEqual(result["scopes"], ["scope"])

    @patch("gmailsorter.webapp.googleapi.create_tasks_for_new_users")
    @patch("gmailsorter.webapp.googleapi.GoogleMail")
    def test_get_user_status_success(self, mail_cls, create_tasks_mock):
        mail_instance = MagicMock()
        mail_instance.get_status_dict.return_value = {"label": JOB_STATUS_SUCCESS}
        mail_cls.return_value = mail_instance

        status_dict, error = googleapi.get_user_status(
            scopes=["scope"],
            database_engine=MagicMock(),
            token="t",
            refresh_token="r",
            token_uri="u",
            client_id="cid",
            client_secret="csecret",
            expiry=datetime.now(timezone.utc),
            db_user_id=1,
            label_name="Inbox",
        )

        self.assertIsNone(error)
        self.assertEqual(status_dict, {"label": JOB_STATUS_SUCCESS})
        mail_instance.close_database_connection.assert_called_once()

    @patch("gmailsorter.webapp.googleapi.GoogleMail")
    def test_get_user_status_http_error(self, mail_cls):
        mail_cls.side_effect = HttpError(resp=MagicMock(status=403), content=b"err")

        status_dict, error = googleapi.get_user_status(
            scopes=["scope"],
            database_engine=MagicMock(),
            token="t",
            refresh_token="r",
            token_uri="u",
            client_id="cid",
            client_secret="csecret",
            expiry=datetime.now(timezone.utc),
            db_user_id=1,
            label_name="Inbox",
        )

        self.assertEqual(status_dict, {})
        self.assertEqual(error, "Insufficient Permission")

    @patch("gmailsorter.webapp.googleapi.GoogleMail")
    def test_get_user_status_refresh_error(self, mail_cls):
        mail_cls.side_effect = RefreshError("expired")

        status_dict, error = googleapi.get_user_status(
            scopes=["scope"],
            database_engine=MagicMock(),
            token="t",
            refresh_token="r",
            token_uri="u",
            client_id="cid",
            client_secret="csecret",
            expiry=datetime.now(timezone.utc),
            db_user_id=1,
            label_name="Inbox",
        )

        self.assertEqual(status_dict, {})
        self.assertEqual(error, "Token has been expired or revoked.")

    @patch("gmailsorter.webapp.googleapi.update_task_status")
    @patch("gmailsorter.webapp.googleapi.GoogleMail")
    def test_reset_user_status_success(self, mail_cls, update_status_mock):
        mail_instance = MagicMock()
        mail_cls.return_value = mail_instance

        status_dict, error = googleapi.reset_user_status(
            scopes=["scope"],
            database_engine=MagicMock(),
            token="t",
            refresh_token="r",
            token_uri="u",
            client_id="cid",
            client_secret="csecret",
            expiry=datetime.now(timezone.utc),
            db_user_id=1,
        )

        self.assertIsNone(error)
        self.assertEqual(status_dict, {"update": "success", "fetch": "success"})
        self.assertEqual(update_status_mock.call_count, 2)
        mail_instance.close_database_connection.assert_called_once()

    @patch("gmailsorter.webapp.googleapi.GoogleMail")
    def test_reset_user_status_http_error(self, mail_cls):
        mail_cls.side_effect = HttpError(resp=MagicMock(status=403), content=b"err")

        status_dict, error = googleapi.reset_user_status(
            scopes=["scope"],
            database_engine=MagicMock(),
            token="t",
            refresh_token="r",
            token_uri="u",
            client_id="cid",
            client_secret="csecret",
            expiry=datetime.now(timezone.utc),
            db_user_id=1,
        )
        self.assertEqual(status_dict, {})
        self.assertEqual(error, "Insufficient Permission")

    @patch("gmailsorter.webapp.googleapi.GoogleMail")
    def test_reset_user_status_refresh_error(self, mail_cls):
        mail_cls.side_effect = RefreshError("expired")

        status_dict, error = googleapi.reset_user_status(
            scopes=["scope"],
            database_engine=MagicMock(),
            token="t",
            refresh_token="r",
            token_uri="u",
            client_id="cid",
            client_secret="csecret",
            expiry=datetime.now(timezone.utc),
            db_user_id=1,
        )
        self.assertEqual(status_dict, {})
        self.assertEqual(error, "Token has been expired or revoked.")

    @patch("gmailsorter.webapp.googleapi.googleapiclient.discovery.build")
    @patch("gmailsorter.webapp.googleapi.google.oauth2.credentials.Credentials")
    def test_get_user_info_success(self, credentials_cls, build_mock):
        service = MagicMock()
        service.userinfo.return_value.get.return_value.execute.return_value = {
            "id": "1",
            "verified_email": True,
        }
        build_mock.return_value = service

        user_info, error, credentials = googleapi.get_user_info(
            credentials_dict={"token": "t"}
        )

        self.assertEqual(user_info["id"], "1")
        self.assertIsNone(error)

    @patch("gmailsorter.webapp.googleapi.googleapiclient.discovery.build")
    @patch("gmailsorter.webapp.googleapi.google.oauth2.credentials.Credentials")
    def test_get_user_info_refresh_error(self, credentials_cls, build_mock):
        service = MagicMock()
        service.userinfo.return_value.get.return_value.execute.side_effect = (
            RefreshError("bad")
        )
        build_mock.return_value = service

        user_info, error, credentials = googleapi.get_user_info(
            credentials_dict={"token": "t"}
        )

        self.assertIsNone(user_info)
        self.assertEqual(error, "Your token has been revoked.")


class TestWebappConfig(unittest.TestCase):
    def _reload_config(self):
        import gmailsorter.webapp.config as config_module

        return importlib.reload(config_module)

    def tearDown(self):
        # Restore the module to a working state for any later imports.
        with patch(
            "gmailsorter.daemon.load_config_file", return_value={"web": {}}
        ), patch("gmailsorter.daemon.get_database_engine", return_value=MagicMock()):
            with patch.dict(
                os.environ,
                {
                    "MAILSORT_ENV_SECRET_KEY": "test-secret-key",
                    "MAILSORT_ENV_CREDENTIALS_FILE": _TMP_CREDENTIALS.name,
                    "MAILSORT_ENV_DATABASE_URL": "sqlite:///:memory:",
                },
            ):
                self._reload_config()

    def test_missing_secret_key_raises_value_error(self):
        env = dict(os.environ)
        env.pop("MAILSORT_ENV_SECRET_KEY", None)
        env["MAILSORT_ENV_CREDENTIALS_FILE"] = _TMP_CREDENTIALS.name
        env["MAILSORT_ENV_DATABASE_URL"] = "sqlite:///:memory:"
        with patch(
            "gmailsorter.daemon.load_config_file", return_value={"web": {}}
        ), patch("gmailsorter.daemon.get_database_engine", return_value=MagicMock()):
            with patch.dict(os.environ, env, clear=True):
                with self.assertRaises(ValueError):
                    self._reload_config()

    def test_env_vars_are_used_when_provided(self):
        with patch(
            "gmailsorter.daemon.load_config_file",
            return_value={"web": {"client_id": "abc"}},
        ) as load_mock, patch(
            "gmailsorter.daemon.get_database_engine", return_value="ENGINE"
        ) as engine_mock, patch.dict(
            os.environ,
            {
                "MAILSORT_ENV_SECRET_KEY": "supersecret",
                "MAILSORT_ENV_CREDENTIALS_FILE": "custom_creds.json",
                "MAILSORT_ENV_DATABASE_URL": "sqlite:///custom.db",
            },
        ):
            config_module = self._reload_config()
            self.assertEqual(config_module.SECRET_KEY, "supersecret")
            self.assertEqual(config_module.ENGINE, "ENGINE")
            self.assertEqual(
                config_module.CLIENT_SECRETS_CONFIG, {"web": {"client_id": "abc"}}
            )
            load_mock.assert_called_once_with(file_name="custom_creds.json")
            engine_mock.assert_called_once_with(connection_str="sqlite:///custom.db")

    def test_defaults_used_when_env_vars_absent(self):
        env = dict(os.environ)
        env.pop("MAILSORT_ENV_CREDENTIALS_FILE", None)
        env.pop("MAILSORT_ENV_DATABASE_URL", None)
        env["MAILSORT_ENV_SECRET_KEY"] = "supersecret"
        with patch(
            "gmailsorter.daemon.load_config_file", return_value={"web": {}}
        ) as load_mock, patch(
            "gmailsorter.daemon.get_database_engine", return_value="ENGINE"
        ) as engine_mock, patch.dict(os.environ, env, clear=True):
            self._reload_config()
            load_mock.assert_called_once_with(file_name="credentials.json")
            engine_mock.assert_called_once_with(connection_str="sqlite:///email.db")


class TestWebappApp(unittest.TestCase):
    def setUp(self):
        webapp_app.app.testing = True
        self.client = webapp_app.app.test_client()

    def _login(self, google_id="google123"):
        with self.client.session_transaction() as sess:
            sess["_user_id"] = google_id

    def test_index_unauthenticated_renders_login_page(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Sign in with Google", response.data)

    @patch("gmailsorter.webapp.app.get_flask_user")
    @patch("gmailsorter.webapp.app.get_user_status")
    def test_index_authenticated_success(self, status_mock, get_user_mock):
        get_user_mock.return_value = FlaskUser(
            database_id=1,
            google_id="google123",
            name="Jane",
            email="jane@test.com",
            profile_pic="pic.png",
            token="tok",
            refresh_token="ref",
            token_uri="uri",
            expiry=datetime.now(timezone.utc),
        )
        status_mock.return_value = (
            {
                "label": JOB_STATUS_SUCCESS,
                "filter": JOB_STATUS_SUCCESS,
                "update": JOB_STATUS_SUCCESS,
                "fetch": JOB_STATUS_SUCCESS,
            },
            None,
        )
        self._login()

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"mailsortinbox label configured", response.data)

    @patch("gmailsorter.webapp.app.get_flask_user")
    @patch("gmailsorter.webapp.app.get_user_status")
    def test_index_authenticated_error(self, status_mock, get_user_mock):
        get_user_mock.return_value = FlaskUser(
            database_id=1,
            google_id="google123",
            name="Jane",
            email="jane@test.com",
            profile_pic="pic.png",
            token="tok",
            refresh_token="ref",
            token_uri="uri",
            expiry=datetime.now(timezone.utc),
        )
        status_mock.return_value = ({}, "Token has been expired or revoked.")
        self._login()

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"error: Token has been expired or revoked.", response.data)

    @patch("gmailsorter.webapp.app.get_authentication_url")
    def test_authorize_redirects_and_stores_state(self, auth_url_mock):
        auth_url_mock.return_value = ("http://auth.url", "state123", "verifier123")

        response = self.client.get("/authorize")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "http://auth.url")
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["state"], "state123")
            self.assertEqual(sess["code_verifier"], "verifier123")

    def test_reset_status_requires_login(self):
        response = self.client.get("/reset")
        self.assertEqual(response.status_code, 403)
        self.assertIn(b"You must be logged in", response.data)

    @patch("gmailsorter.webapp.app.get_flask_user")
    @patch("gmailsorter.webapp.app.reset_user_status")
    def test_reset_status_success(self, reset_mock, get_user_mock):
        get_user_mock.return_value = FlaskUser(
            database_id=1,
            google_id="google123",
            name="Jane",
            email="jane@test.com",
            profile_pic="pic.png",
            token="tok",
            refresh_token="ref",
            token_uri="uri",
            expiry=datetime.now(timezone.utc),
        )
        reset_mock.return_value = (
            {"update": "success", "fetch": "success"},
            None,
        )
        self._login()

        response = self.client.get("/reset")

        self.assertEqual(response.status_code, 302)

    @patch("gmailsorter.webapp.app.get_flask_user")
    @patch("gmailsorter.webapp.app.reset_user_status")
    def test_reset_status_error(self, reset_mock, get_user_mock):
        get_user_mock.return_value = FlaskUser(
            database_id=1,
            google_id="google123",
            name="Jane",
            email="jane@test.com",
            profile_pic="pic.png",
            token="tok",
            refresh_token="ref",
            token_uri="uri",
            expiry=datetime.now(timezone.utc),
        )
        reset_mock.return_value = ({}, "Insufficient Permission")
        self._login()

        response = self.client.get("/reset")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"error: Insufficient Permission", response.data)

    @patch("gmailsorter.webapp.app.get_flask_user")
    @patch("gmailsorter.webapp.app.get_user_info")
    @patch("gmailsorter.webapp.app.get_google_credentials")
    def test_oauth2callback_success_logs_in_user(
        self, credentials_mock, user_info_mock, get_flask_user_mock
    ):
        credentials_mock.return_value = {
            "token": "tok",
            "refresh_token": "ref",
            "token_uri": "uri",
            "client_id": "cid",
            "client_secret": "csecret",
            "expiry": datetime.now(timezone.utc),
        }
        user_info_mock.return_value = (
            {
                "id": "google123",
                "given_name": "Jane",
                "email": "jane@test.com",
                "picture": "pic.png",
                "verified_email": True,
            },
            None,
            MagicMock(),
        )
        get_flask_user_mock.return_value = FlaskUser(
            database_id=1,
            google_id="google123",
            name="Jane",
            email="jane@test.com",
            profile_pic="pic.png",
            token="tok",
            refresh_token="ref",
            token_uri="uri",
            expiry=datetime.now(timezone.utc),
        )
        with self.client.session_transaction() as sess:
            sess["state"] = "state123"
            sess["code_verifier"] = "verifier123"

        response = self.client.get("/oauth2callback?state=state123&code=abc")

        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["_user_id"], "google123")

    @patch("gmailsorter.webapp.app.get_user_info")
    @patch("gmailsorter.webapp.app.get_google_credentials")
    def test_oauth2callback_unverified_email_returns_400(
        self, credentials_mock, user_info_mock
    ):
        credentials_mock.return_value = {"token": "tok"}
        user_info_mock.return_value = (
            {"id": "google123", "verified_email": False},
            None,
            MagicMock(),
        )
        with self.client.session_transaction() as sess:
            sess["state"] = "state123"
            sess["code_verifier"] = "verifier123"

        response = self.client.get("/oauth2callback?state=state123&code=abc")

        self.assertEqual(response.status_code, 400)

    @patch("gmailsorter.webapp.app.get_flask_user")
    def test_logout_clears_session(self, get_flask_user_mock):
        get_flask_user_mock.return_value = FlaskUser(
            database_id=1,
            google_id="google123",
            name="Jane",
            email="jane@test.com",
            profile_pic="pic.png",
            token="tok",
            refresh_token="ref",
            token_uri="uri",
            expiry=datetime.now(timezone.utc),
        )
        self._login()

        response = self.client.get("/logout")

        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as sess:
            self.assertNotIn("_user_id", sess)


if __name__ == "__main__":
    unittest.main()
