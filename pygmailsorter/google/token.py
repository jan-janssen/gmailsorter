from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google_auth_oauthlib.flow import InstalledAppFlow


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
