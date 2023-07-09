from gmailsorter.daemon import (
    GoogleToken,
    SQLUser,
    get_token,
)


def create_user_in_database(
    session,
    google_id,
    name,
    email,
    profile_pic,
    token,
    refresh_token,
    token_uri,
    client_id,
    client_secret,
    expiry,
):
    user = SQLUser(
        google_id=google_id,
        name=name,
        email=email,
        profile_pic=profile_pic,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    update_token_in_database(
        session=session,
        user_id=user.id,
        token=token,
        refresh_token=refresh_token,
        token_uri=token_uri,
        client_id=client_id,
        client_secret=client_secret,
        expiry=expiry,
    )
    return int(user.id)


def update_token_in_database(
    session, user_id, token, refresh_token, token_uri, client_id, client_secret, expiry
):
    token_obj = get_token(session=session, user_id=user_id)
    if token_obj is None:
        token_obj = GoogleToken(user_id=user_id)
    token_obj.token = token
    token_obj.refresh_token = refresh_token
    token_obj.token_uri = token_uri
    token_obj.client_id = client_id
    token_obj.client_secret = client_secret
    token_obj.expiry = expiry
    if token_obj.id is None:
        session.add(token_obj)
    session.commit()
