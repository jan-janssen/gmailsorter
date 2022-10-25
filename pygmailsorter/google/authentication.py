from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google_auth_oauthlib.flow import InstalledAppFlow


def create_service(
    client_config,
    api_name,
    api_version,
    scopes,
    database,
    database_user_id,
    port=8080,
):
    cred = None

    token = database.get_token(user_id=database_user_id)
    if token.token is not None:
        cred = Credentials(
            token=token.token,
            refresh_token=token.refresh_token,
            id_token=None,
            token_uri=token.token_uri,
            client_id=token.client_id,
            client_secret=token.client_secret,
            scopes=["https://mail.google.com/"],
            default_scopes=None,
            quota_project_id=None,
            expiry=token.expiry,
            rapt_token=None,
            refresh_handler=None,
            enable_reauth_refresh=False,
        )

    if not cred or not cred.valid:
        cred = validate_token(
            cred=cred, client_config=client_config, scopes=scopes, port=port
        )
        database.update_token_with_dict(token=token, credentials=cred, commit=True)

    return build(api_name, api_version, credentials=cred)


def validate_token(cred, client_config, scopes, port=8080):
    token_valid = False
    if cred and cred.expired and cred.refresh_token:
        try:
            cred.refresh(Request())
        except RefreshError:
            pass
        else:
            token_valid = True

    if not token_valid:
        flow = InstalledAppFlow.from_client_config(
            client_config=client_config, scopes=scopes
        )
        cred = flow.run_local_server(open_browser=False, port=port)

    return cred
