# Based on https://developers.google.com/identity/protocols/oauth2/web-server#python
import google_auth_oauthlib.flow
import googleapiclient.discovery
import google.oauth2.credentials
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError
from gmailsorter.daemon import (
    GoogleMail,
    create_tasks_for_new_users,
    update_task_status,
)


def get_authentication_url(client_config, scopes, redirect_uri):
    # Create flow instance to manage the OAuth 2.0 Authorization Grant Flow steps.
    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        client_config=client_config, scopes=scopes
    )

    # The URI created here must exactly match one of the authorized redirect URIs
    # for the OAuth 2.0 client, which you configured in the API Console. If this
    # value doesn't match an authorized URI, you will get a 'redirect_uri_mismatch'
    # error.
    flow.redirect_uri = redirect_uri

    authorization_url, state = flow.authorization_url(
        # Enable offline access so that you can refresh an access token without
        # re-prompting the user for permission. Recommended for web server apps.
        access_type="offline",
        # Enable incremental authorization. Recommended as a best practice.
        include_granted_scopes="true",
    )
    return authorization_url, state


def get_google_credentials(
    client_config, scopes, state, redirect_uri, authorization_response
):
    # Create flow instance to manage the OAuth 2.0 Authorization Grant Flow steps.
    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        client_config=client_config, scopes=scopes, state=state
    )
    flow.redirect_uri = redirect_uri

    # Use the authorization server's response to fetch the OAuth 2.0 tokens.
    flow.fetch_token(authorization_response=authorization_response)

    # Store credentials in the session.
    # ACTION ITEM: In a production app, you likely want to save these
    #              credentials in a persistent database instead.
    return _credentials_to_dict(credentials=flow.credentials)


def get_user_status(
    scopes,
    database_engine,
    token,
    refresh_token,
    token_uri,
    client_id,
    client_secret,
    expiry,
    db_user_id,
    label_name,
):
    try:
        gmail = GoogleMail(
            scopes=scopes,
            database_engine=database_engine,
            token=token,
            refresh_token=refresh_token,
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret,
            expiry=expiry,
            user_id="me",
            db_user_id=db_user_id,
            email_download_format="metadata",
            serviceName="gmail",
            version="v1",
        )
        create_tasks_for_new_users(session=gmail.session, user_id=db_user_id)
        status_dict = gmail.get_status_dict(label_name)
        gmail.close_database_connection()
    except HttpError:
        return dict(), "Insufficient Permission"
    except RefreshError:
        return dict(), "Token has been expired or revoked."
    else:
        return status_dict, None


def reset_user_status(
    scopes,
    database_engine,
    token,
    refresh_token,
    token_uri,
    client_id,
    client_secret,
    expiry,
    db_user_id,
):
    try:
        gmail = GoogleMail(
            scopes=scopes,
            database_engine=database_engine,
            token=token,
            refresh_token=refresh_token,
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret,
            expiry=expiry,
            user_id="me",
            db_user_id=db_user_id,
            email_download_format="metadata",
            serviceName="gmail",
            version="v1",
        )
        _ = [
            update_task_status(
                session=gmail.session,
                user_id=db_user_id,
                task_name=task_name,
                status="success",
            )
            for task_name in ["update", "fetch"]
        ]
        gmail.close_database_connection()
    except HttpError:
        return dict(), "Insufficient Permission"
    except RefreshError:
        return dict(), "Token has been expired or revoked."
    else:
        return {"update": "success", "fetch": "success"}, None


def get_user_info(credentials_dict, service_name="oauth2", version="v2"):
    # {'id', 'email', 'verified_email', 'name', 'given_name', 'family_name', 'picture', 'locale'}
    credentials = google.oauth2.credentials.Credentials(**credentials_dict)
    user_info_service = googleapiclient.discovery.build(
        serviceName=service_name, version=version, credentials=credentials
    )
    user_info, error = None, None
    try:
        user_info = user_info_service.userinfo().get().execute()
    except RefreshError:
        error = "Your token has been revoked."
    return user_info, error, credentials


def _credentials_to_dict(credentials):
    return {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
        "expiry": credentials.expiry,
    }
