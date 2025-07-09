# https://realpython.com/flask-google-login/
# https://github.com/realpython/materials/tree/master/flask-google-login

# Python standard libraries
import os

# Third party libraries
import flask
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)

# Internal imports
from gmailsorter.daemon import SCOPES, MAILSORT_LABEL
from gmailsorter.daemon.shared import (
    JOB_STATUS_FAIL,
    JOB_STATUS_PROGRESS,
)
from gmailsorter.webapp.config import CLIENT_SECRETS_CONFIG, ENGINE, SECRET_KEY
from gmailsorter.webapp.user import get_flask_user
from gmailsorter.webapp.render import color_for_status
from gmailsorter.webapp.googleapi import (
    get_authentication_url,
    get_google_credentials,
    get_user_info,
    get_user_status,
    reset_user_status,
)

# Flask app setup
app = flask.Flask(
    __name__,
    template_folder=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "templates"
    ),
)
app.secret_key = SECRET_KEY

# User session management setup
# https://flask-login.readthedocs.io/en/latest
login_manager = LoginManager()
login_manager.init_app(app)


@login_manager.unauthorized_handler
def unauthorized():
    return "You must be logged in to access this content.", 403


# Flask-Login helper to retrieve a user from our db
@login_manager.user_loader
def load_user(user_id):
    return get_flask_user(engine=ENGINE, google_id=user_id, update=False)


@app.route("/")
def index():
    if current_user.is_authenticated:
        # Access Gmail
        status_dict, error = get_user_status(
            scopes=SCOPES,
            database_engine=ENGINE,
            token=current_user.token,
            refresh_token=current_user.refresh_token,
            token_uri=current_user.token_uri,
            client_id=CLIENT_SECRETS_CONFIG["web"]["client_id"],
            client_secret=CLIENT_SECRETS_CONFIG["web"]["client_secret"],
            expiry=current_user.expiry,
            db_user_id=current_user.database_id,
            label_name=MAILSORT_LABEL,
        )
        if error is None:
            return flask.render_template(
                "user.html",
                username=current_user.name,
                item_list=[
                    "mailsortinbox label configured: "
                    + color_for_status(status=status_dict["label"]),
                    "email filter configured: "
                    + color_for_status(status=status_dict["filter"]),
                    "machine learning model update: "
                    + color_for_status(status=status_dict["update"]),
                    "email sorting: " + color_for_status(status=status_dict["fetch"]),
                ],
                enable_reset=any(
                    [
                        JOB_STATUS_FAIL in status_dict.values(),
                        JOB_STATUS_PROGRESS in status_dict.values(),
                    ]
                ),
            )
        else:
            return flask.render_template(
                "user.html",
                username=current_user.name,
                item_list=["error: " + error],
                enable_reset=False,
            )
    else:
        return flask.render_template("login.html")


@app.route("/authorize")
def authorize():
    authorization_url, state = get_authentication_url(
        client_config=CLIENT_SECRETS_CONFIG,
        scopes=SCOPES,
        redirect_uri=flask.url_for("oauth2callback", _external=True),
    )

    # Store the state so the callback can verify the auth server response.
    flask.session["state"] = state

    return flask.redirect(authorization_url)


@app.route("/reset")
@login_required
def reset_status():
    status_dict, error = reset_user_status(
        scopes=SCOPES,
        database_engine=ENGINE,
        token=current_user.token,
        refresh_token=current_user.refresh_token,
        token_uri=current_user.token_uri,
        client_id=CLIENT_SECRETS_CONFIG["web"]["client_id"],
        client_secret=CLIENT_SECRETS_CONFIG["web"]["client_secret"],
        expiry=current_user.expiry,
        db_user_id=current_user.database_id,
    )
    if error is None:
        return flask.redirect(flask.url_for("index"))
    else:
        return flask.render_template(
            "user.html",
            username=current_user.name,
            item_list=["error: " + error],
            enable_reset=False,
        )


@app.route("/oauth2callback")
def oauth2callback():
    # Specify the state when creating the flow in the callback so that it can
    # verified in the authorization server response.
    state = flask.session["state"]

    credentials_dict = get_google_credentials(
        client_config=CLIENT_SECRETS_CONFIG,
        scopes=SCOPES,
        state=state,
        redirect_uri=flask.url_for("oauth2callback", _external=True),
        authorization_response=flask.request.url,
    )

    flask.session["credentials"] = credentials_dict
    user_info_dict, error_user, _ = get_user_info(
        credentials_dict=credentials_dict, service_name="oauth2", version="v2"
    )

    if user_info_dict is not None and user_info_dict["verified_email"]:
        user = get_flask_user(
            engine=ENGINE,
            google_id=user_info_dict["id"],
            users_name=user_info_dict["given_name"],
            users_email=user_info_dict["email"],
            picture=user_info_dict["picture"],
            token=credentials_dict["token"],
            refresh_token=credentials_dict["refresh_token"],
            token_uri=credentials_dict["token_uri"],
            client_id=credentials_dict["client_id"],
            client_secret=credentials_dict["client_secret"],
            expiry=credentials_dict["expiry"],
            update=True,
        )
        # Begin user session by logging the user in
        login_user(user)

        # Send user back to homepage
        return flask.redirect(flask.url_for("index"))
    else:
        return "User email not available or not verified by Google.", 400


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return flask.redirect(flask.url_for("index"))


def run_app():
    # When running locally, disable OAuthlib's HTTPs verification.
    # ACTION ITEM for developers:
    #     When running in production *do not* leave this option enabled.
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

    # Specify a hostname and port that are set as a valid redirect URI
    # for your API project in the Google API Console.
    app.run(host="0.0.0.0", port=8080, debug=True)
