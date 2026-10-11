from datetime import datetime
from unittest import TestCase

from sqlalchemy import String, Text, create_engine
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateTable

from gmailsorter.daemon.shared import Base as DaemonBase
from gmailsorter.daemon.shared import GoogleToken, SQLUser
from gmailsorter.google.database import Base as TokenBase


def _mysql_column_types(base):
    dialect = mysql.dialect()
    return {
        f"{table.name}.{column.name}": column.type.compile(dialect=dialect)
        for table in base.metadata.sorted_tables
        for column in table.columns
    }


class MySQLSchemaTest(TestCase):
    def test_all_string_columns_have_length_or_are_text(self):
        for base in [DaemonBase, TokenBase]:
            for table in base.metadata.sorted_tables:
                for column in table.columns:
                    if isinstance(column.type, String) and not isinstance(
                        column.type, Text
                    ):
                        self.assertIsNotNone(
                            column.type.length, f"{table.name}.{column.name}"
                        )

    def test_daemon_column_types(self):
        column_types = _mysql_column_types(DaemonBase)
        for column in [
            "google_token.token_uri",
            "google_token.client_id",
            "google_token.client_secret",
            "google_user.google_id",
            "google_user.name",
            "google_user.email",
            "google_task.task_name",
            "google_task.status",
        ]:
            self.assertEqual(column_types[column], "VARCHAR(255)", column)
        for column in [
            "google_token.token",
            "google_token.refresh_token",
            "google_token.scopes",
            "google_user.profile_pic",
        ]:
            self.assertEqual(column_types[column], "TEXT", column)

    def test_token_tables_are_identical(self):
        # The google_token table is defined twice, both definitions must match
        self.assertEqual(
            {
                k: v
                for k, v in _mysql_column_types(DaemonBase).items()
                if k.startswith("google_token.")
            },
            _mysql_column_types(TokenBase),
        )

    def test_create_table_compiles_for_mysql(self):
        dialect = mysql.dialect()
        for base in [DaemonBase, TokenBase]:
            for table in base.metadata.sorted_tables:
                ddl = str(CreateTable(table).compile(dialect=dialect))
                self.assertNotIn("VARCHAR,", ddl)
                self.assertNotIn("VARCHAR\n", ddl)


class LongValuesRoundTripTest(TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        DaemonBase.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()

    def tearDown(self) -> None:
        self.session.close()

    def test_long_token_and_profile_pic(self):
        token = "t" * 2048
        refresh_token = "r" * 512
        profile_pic = "https://lh3.googleusercontent.com/a/" + "p" * 500
        self.session.add(SQLUser(google_id="123", profile_pic=profile_pic))
        self.session.add(
            GoogleToken(
                user_id=1,
                token=token,
                refresh_token=refresh_token,
                expiry=datetime(2026, 10, 11, 12, 0, 0),
            )
        )
        self.session.commit()
        user = self.session.query(SQLUser).first()
        stored = self.session.query(GoogleToken).first()
        self.assertEqual(user.profile_pic, profile_pic)
        self.assertEqual(stored.token, token)
        self.assertEqual(stored.refresh_token, refresh_token)
