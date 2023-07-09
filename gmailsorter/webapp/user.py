from sqlalchemy.orm import sessionmaker
from flask_login import UserMixin
from gmailsorter.daemon import SQLUser, get_token
from gmailsorter.webapp.database import (
    create_user_in_database,
    update_token_in_database,
)


class FlaskUser(UserMixin):
    def __init__(
        self,
        database_id,
        google_id,
        name,
        email,
        profile_pic,
        token,
        refresh_token,
        token_uri,
        expiry,
    ):
        self.id = google_id
        self.database_id = database_id
        self.name = name
        self.email = email
        self.profile_pic = profile_pic
        self.token = token
        self.refresh_token = refresh_token
        self.token_uri = token_uri
        self.expiry = expiry


def get_flask_user(
    engine,
    google_id,
    users_name=None,
    users_email=None,
    picture=None,
    token=None,
    refresh_token=None,
    token_uri=None,
    client_id=None,
    client_secret=None,
    expiry=None,
    update=True,
):
    session = sessionmaker(bind=engine)()
    user = session.query(SQLUser).filter_by(google_id=google_id).first()
    if not update:
        if user is not None:
            database_user_id = int(user.id)
            token_obj = get_token(session=session, user_id=database_user_id)
            flask_user = FlaskUser(
                database_id=database_user_id,
                google_id=user.google_id,
                name=user.name,
                email=user.email,
                profile_pic=user.profile_pic,
                token=token_obj.token,
                refresh_token=token_obj.refresh_token,
                token_uri=token_obj.token_uri,
                expiry=token_obj.expiry,
            )
            session.close()
            return flask_user
        else:
            session.close()
            return None
    else:
        # Doesn't exist? Add to database
        if user is None:
            database_user_id = create_user_in_database(
                session=session,
                google_id=google_id,
                name=users_name,
                email=users_email,
                profile_pic=picture,
                token=token,
                refresh_token=refresh_token,
                token_uri=token_uri,
                client_id=client_id,
                client_secret=client_secret,
                expiry=expiry,
            )
        else:
            database_user_id = int(user.id)
            if refresh_token is not None:
                update_token_in_database(
                    session=session,
                    user_id=database_user_id,
                    token=token,
                    refresh_token=refresh_token,
                    token_uri=token_uri,
                    client_id=client_id,
                    client_secret=client_secret,
                    expiry=expiry,
                )
        session.close()

        # Create a user in our db with the information provided
        # by Google
        return FlaskUser(
            google_id=google_id,
            database_id=database_user_id,
            name=users_name,
            email=users_email,
            profile_pic=picture,
            token=token,
            refresh_token=refresh_token,
            token_uri=token_uri,
            expiry=expiry,
        )
