from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base
from gmailsorter.base.database import DatabaseTemplate


Base = declarative_base()


class GoogleToken(Base):
    __tablename__ = "google_token"
    id = Column(Integer, primary_key=True)
    token = Column(String)
    refresh_token = Column(String)
    token_uri = Column(String)
    client_id = Column(String)
    client_secret = Column(String)
    scopes = Column(String)
    expiry = Column(DateTime)
    user_id = Column(Integer)


class DatabaseInterface(DatabaseTemplate):
    @property
    def session(self):
        return self._session

    def update_token_with_dict(self, token, credentials, commit=True):
        token.token = credentials.token
        token.refresh_token = credentials.refresh_token
        token.token_uri = credentials.token_uri
        token.client_id = credentials.client_id
        token.client_secret = credentials.client_secret
        token.expiry = credentials.expiry
        if token.id is None:
            self._session.add(token)
        if commit:
            self._session.commit()

    def get_token(self, user_id):
        token = self._session.query(GoogleToken).filter_by(user_id=user_id).first()
        if token is None:
            return GoogleToken(user_id=user_id)
        else:
            return token

    @staticmethod
    def token_to_dict(token):
        return {
            "token": token.token,
            "refresh_token": token.refresh_token,
            "token_uri": token.token_uri,
            "client_id": token.client_id,
            "client_secret": token.client_secret,
            "scopes": ["https://mail.google.com/"],
            "expiry": token.expiry,
        }


def get_token_database(engine, session):
    Base.metadata.create_all(engine)
    return DatabaseInterface(session=session)
