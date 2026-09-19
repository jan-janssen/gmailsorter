from typing import Any

from google.oauth2.credentials import Credentials
from sqlalchemy import Column, DateTime, Engine, Integer, String
from sqlalchemy.orm import Session, declarative_base

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
    def session(self) -> Session:
        return self._session

    def update_token_with_dict(
        self, token: GoogleToken, credentials: Credentials, commit: bool = True
    ) -> None:
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

    def get_token(self, user_id: int) -> GoogleToken:
        token = self._session.query(GoogleToken).filter_by(user_id=user_id).first()
        if token is None:
            return GoogleToken(user_id=user_id)
        else:
            return token

    @staticmethod
    def token_to_dict(token: GoogleToken) -> dict[str, Any]:
        return {
            "token": token.token,
            "refresh_token": token.refresh_token,
            "token_uri": token.token_uri,
            "client_id": token.client_id,
            "client_secret": token.client_secret,
            "scopes": ["https://mail.google.com/"],
            "expiry": token.expiry,
        }


def get_token_database(engine: Engine, session: Session) -> DatabaseInterface:
    Base.metadata.create_all(engine)
    return DatabaseInterface(session=session)
