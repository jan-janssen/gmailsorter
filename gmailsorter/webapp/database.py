from datetime import datetime

from sqlalchemy.orm import Session

from gmailsorter.daemon import (
    GoogleToken,
    SQLUser,
    get_token,
)


def create_user_in_database(
    session: Session,
    google_id: str,
    name: str | None,
    email: str | None,
    profile_pic: str | None,
    token: str | None,
    refresh_token: str | None,
    token_uri: str | None,
    client_id: str | None,
    client_secret: str | None,
    expiry: datetime | None,
) -> int:
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
    session: Session,
    user_id: int,
    token: str | None,
    refresh_token: str | None,
    token_uri: str | None,
    client_id: str | None,
    client_secret: str | None,
    expiry: datetime | None,
) -> None:
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
