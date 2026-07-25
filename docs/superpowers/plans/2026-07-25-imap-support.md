# IMAP Backend Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a second, IMAP-based backend to gmailsorter (username/password auth, one IMAP folder = one Gmail-style label) that reuses the existing fetch-store-train-predict-move loop, ships a `gmailsorter-imap` CLI, and is exercised in CI against a real GreenMail IMAP/SMTP server.

**Architecture:** Extract the backend-agnostic loop currently living in `GoogleMailBase` into a new `gmailsorter.base.mail.AbstractMailBox` (mirroring the existing `base/` vs `google/` split for `message.py`/`database.py`), then add a parallel `gmailsorter/imap/` package (`authentication.py`, `message.py`, `mail.py`) plus an `Imap` class in `local.py` and a `gmailsorter-imap` console script.

**Tech Stack:** Python stdlib `imaplib`/`email` (no new dependencies), existing `sqlalchemy`/`pandas`/`scikit-learn` stack, `unittest` + `unittest.mock`, GitHub Actions `services:` container (`greenmail/standalone:2.1.11`).

## Global Constraints

- Target Python: `>=3.10` (repo classifiers test 3.11–3.14) — avoid syntax newer than that.
- Lint: `ruff` with rules `E, F, UP, B, SIM, I, C4, ERA, PL` (ignoring `E501`, `PLR0913`) via `.pre-commit-config.yaml`, applied to files under `gmailsorter/`. Keep new code consistent with this (no unused imports, no commented-out code, etc).
- No new runtime dependencies: `imaplib` and `email` are stdlib; do not add packages to `pyproject.toml` `dependencies`.
- Follow existing docstring style (Google-style `Args:`/`Returns:`) used throughout `gmailsorter/`.
- Existing public API (`gmailsorter.Gmail`, `gmailsorter.load_client_secrets_file`, `GoogleMailBase.__init__` signature) must not change — `tests/test_google_integration_units.py` must keep passing with, at most, its `@patch(...)` target strings updated to follow code that moved (no assertion or behavior changes).
- Test runner: `coverage run --omit gmailsorter/_version.py -m unittest discover tests` (see `.github/workflows/unittest.yml`) — every new test file must be discoverable by `unittest discover tests` (class extends `unittest.TestCase`, file name starts with `test_`).
- IMAP auth is username/password only for this plan (no OAuth2/XOAUTH2). Passwords must never be accepted as a literal CLI argument.
- Webapp (`gmailsorter/webapp/`) and daemon (`gmailsorter/daemon/`) are explicitly out of scope — do not modify them.

---

### Task 1: Shared HTML-to-text helper in `base/message.py`

**Files:**
- Modify: `gmailsorter/base/message.py`
- Modify: `gmailsorter/google/message.py`
- Test: `tests/test_message.py`

**Interfaces:**
- Produces: `gmailsorter.base.message.strip_html_tags(html: str) -> str`, used by both `gmailsorter/google/message.py` (Task 1) and `gmailsorter/imap/message.py` (Task 3).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_message.py` (append inside the existing `MessageTest` class, and add the import at the top):

```python
from gmailsorter.base.message import email_date_converter, strip_html_tags
```

```python
    def test_strip_html_tags(self):
        self.assertEqual(
            strip_html_tags("<p>Hello <b>World</b></p>"),
            "Hello World",
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_message -v`
Expected: FAIL with `ImportError: cannot import name 'strip_html_tags'`

- [ ] **Step 3: Move `MLStripper` into `base/message.py` as `strip_html_tags`**

In `gmailsorter/base/message.py`, add these imports at the top (alongside the existing `abc`/`datetime` imports):

```python
from html.parser import HTMLParser
from io import StringIO
```

Then add, after the `_DATE_HYPHEN_COUNT` constant and before `email_date_converter`:

```python
# https://stackoverflow.com/questions/753052/strip-html-from-strings-in-python
class _MLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = StringIO()

    def handle_data(self, d):
        self.text.write(d)

    def get_data(self):
        return self.text.getvalue()


def strip_html_tags(html):
    stripper = _MLStripper()
    stripper.feed(html)
    return stripper.get_data()
```

- [ ] **Step 4: Update `gmailsorter/google/message.py` to use the shared helper**

Replace the top of `gmailsorter/google/message.py` — delete the `MLStripper` class and its imports, and import `strip_html_tags` instead:

```python
import base64

from gmailsorter.base.message import AbstractMessage, email_date_converter, strip_html_tags
```

(This replaces the old `import base64` / `from html.parser import HTMLParser` / `from io import StringIO` / `from gmailsorter.base.message import ...` block, and removes the `MLStripper` class definition that followed it.)

In the `Message` class, change `_get_parts_content` to call the shared function instead of `self._strip_tags`:

```python
    def _get_parts_content(self, message_parts):
        content_types = [p["mimeType"] for p in message_parts if "mimeType" in p]
        if "text/plain" in content_types:
            return self._get_email_body(
                message_parts=message_parts[content_types.index("text/plain")]
            )
        elif "text/html" in content_types:
            return strip_html_tags(
                html=self._get_email_body(
                    message_parts=message_parts[content_types.index("text/html")]
                )
            )
        elif "multipart/alternative" in content_types:
            multi_part_content = message_parts[
                content_types.index("multipart/alternative")
            ]
            if "parts" in multi_part_content:
                return self._get_parts_content(
                    message_parts=multi_part_content["parts"]
                )
            else:
                return None
        else:
            return None
```

Delete the now-unused `_strip_tags` staticmethod entirely (it was right after `_get_email_body`).

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m unittest tests.test_message -v`
Expected: PASS

- [ ] **Step 6: Run the full existing suite to confirm no regression**

Run: `python -m unittest discover tests -v`
Expected: All tests PASS (in particular `tests/test_google_message.py`, unaffected since `Message._get_parts_content`'s observable behavior is unchanged).

- [ ] **Step 7: Commit**

```bash
git add gmailsorter/base/message.py gmailsorter/google/message.py tests/test_message.py
git commit -m "refactor: move HTML-to-text stripping into base/message.py so it can be reused by imap/message.py"
```

---

### Task 2: Extract `AbstractMailBox` shared loop; refactor `GoogleMailBase`

**Files:**
- Create: `gmailsorter/base/mail.py`
- Modify: `gmailsorter/google/mail.py` (full rewrite)
- Modify: `tests/test_google_integration_units.py` (patch targets only)
- Test: `tests/test_mail_base.py`

**Interfaces:**
- Produces: `gmailsorter.base.mail.AbstractMailBox(ABC)` with constructor
  `__init__(self, mail_service, database_email=None, database_ml=None, user_id="me", db_user_id=1, email_download_format="metadata")`,
  concrete methods `labels` (property), `download_emails_for_label(label)`,
  `filter_messages_from_server(label, recommendation_ratio=0.9)`,
  `fit_machine_learning_model_to_database(n_estimators=100, max_features=400, random_state=42, bootstrap=True, include_deleted=False)`,
  `get_all_emails_in_database(include_deleted=False)`,
  `update_database(quick=False, label_lst=None, email_format=None)`,
  and abstract hooks `_search_email_on_server(query_string="", label_lst=None, only_message_ids=False)`,
  `_get_message_detail(message_id, email_format=None, metadata_headers=None)`,
  `_get_label_translate_dict()`,
  `_modify_message_labels(message_id, label_id_remove_lst=None, label_id_add_lst=None)`,
  `_get_labels_for_email(message_id)`, `_parse_message(message)`.
- Consumed by: Task 5 (`ImapMailBase(AbstractMailBox)`).

This is a **behavior-preserving refactor** of already-tested code, not new functionality, so the TDD cycle here is: move the code, then prove the full existing test suite (plus a new isolation-focused test file) still passes — rather than writing a new failing test first.

- [ ] **Step 1: Create `gmailsorter/base/mail.py`**

```python
from abc import ABC, abstractmethod

import pandas
from tqdm import tqdm

from gmailsorter.ml import (
    encode_df_for_machine_learning,
    fit_machine_learning_models,
    get_predictions_from_machine_learning_models,
)


class AbstractMailBox(ABC):
    def __init__(
        self,
        mail_service,
        database_email=None,
        database_ml=None,
        user_id="me",
        db_user_id=1,
        email_download_format="metadata",
    ):
        """
        Shared fetch-store-train-predict-move loop for a mailbox backend, independent of
        whether the backend is the Gmail API or a plain IMAP connection.

        Args:
            mail_service: backend-specific connection object (Gmail API service resource,
                imaplib connection, ...)
            database_email (gmailsorter.base.database.DatabaseInterface): SQLalchemy interface for email database
            database_ml (gmailsorter.ml.database.DatabaseInterface): SQLalchemy interface for machine learning database
            user_id (str): backend-specific user identifier
            db_user_id (int): Default 1 - set a user id when sharing a database with multiple users
            email_download_format (str): backend-specific download format hint
        """
        self._service = mail_service
        self._db_email = database_email
        self._db_ml = database_ml
        self._db_user_id = db_user_id
        self._userid = user_id
        self._email_download_format = email_download_format
        self._label_dict = self._get_label_translate_dict()
        self._label_dict_inverse = {v: k for k, v in self._label_dict.items()}

    @property
    def labels(self):
        return list(self._label_dict.keys())

    def download_emails_for_label(self, label):
        """
        Download emails for a specific label

        Args:
            label (str): label to download emails for

        Returns:
            pandas.DataFrame: Email content for the downloaded emails
        """
        return self._download_messages_to_dataframe(
            message_id_lst=self._search_email_on_server(
                label_lst=[label], only_message_ids=True
            )
        )

    def filter_messages_from_server(
        self,
        label,
        recommendation_ratio=0.9,
    ):
        """
        Filter new emails based on machine learning model recommendations.

        Args:
            label (str): Email label to filter for
            recommendation_ratio (float): Only accept recommendation above this ratio (0<r<1)
        """
        df_partial = self.download_emails_for_label(label=label)
        if len(df_partial) > 0:
            model_reload_dict, feature_reload_lst = self._db_ml.load_models()
            df_partial_features = encode_df_for_machine_learning(
                df=df_partial,
                feature_lst=feature_reload_lst,
                label_lst=list(model_reload_dict.keys()),
                return_labels=False,
            )
            df_partial_features = df_partial_features.reindex(
                sorted(df_partial_features.columns), axis=1
            )
            model_recommendation_dict = get_predictions_from_machine_learning_models(
                df_features=df_partial_features,
                model_dict=model_reload_dict,
                recommendation_ratio=recommendation_ratio,
            )
            self._move_emails(
                move_email_dict=model_recommendation_dict, label_to_ignore=label
            )

    def fit_machine_learning_model_to_database(
        self,
        n_estimators=100,
        max_features=400,
        random_state=42,
        bootstrap=True,
        include_deleted=False,
    ):
        """
        Fit machine learning models to emails stored in database and afterwards store machine learning models in
        database.

        Args:
            n_estimators (int): Number of estimators
            max_features (int): Number of features
            random_state (int): Random state
            bootstrap (boolean): Whether bootstrap samples are used when building trees. If False, the whole dataset is
                                 used to build each tree. (default: true)
            include_deleted (bool): Flag to include deleted emails - default False
        """
        df_all = self.get_all_emails_in_database(include_deleted=include_deleted)
        df_all_features, df_all_labels = encode_df_for_machine_learning(
            df=df_all, feature_lst=[], label_lst=[], return_labels=True
        )
        df_all_features = df_all_features.loc[
            :, ~df_all_features.columns.duplicated()
        ].copy()
        df_all_features = df_all_features.reindex(
            sorted(df_all_features.columns), axis=1
        )
        model_dict = fit_machine_learning_models(
            df_all_features=df_all_features,
            df_all_labels=df_all_labels,
            n_estimators=n_estimators,
            max_features=max_features,
            random_state=random_state,
            bootstrap=bootstrap,
        )
        self._db_ml.store_models(
            model_dict=model_dict,
            feature_lst=df_all_features.columns.values.tolist(),
            user_id=self._db_user_id,
            commit=True,
        )

    def get_all_emails_in_database(self, include_deleted=False):
        """
        Get all emails stored in the local database

        Args:
            include_deleted (bool): Flag to include deleted emails - default False

        Returns:
            pandas.DataFrame: With all emails and the corresponding information
        """
        return self._db_email.get_all_emails(
            include_deleted=include_deleted, user_id=self._db_user_id
        )

    def update_database(self, quick=False, label_lst=None, email_format=None):
        """
        Update local email database

        Args:
            quick (boolean): Only add new emails, do not update existing labels - by default: False
            label_lst (list): list of labels to be searched
            email_format (str/None): Email format to download
        """
        if label_lst is None:
            label_lst = []
        if self._db_email is not None:
            message_id_lst = self._search_email_on_server(
                label_lst=label_lst, only_message_ids=True
            )
            (
                new_messages_lst,
                message_label_updates_lst,
                deleted_messages_lst,
            ) = self._db_email.get_labels_to_update(
                message_id_lst=message_id_lst, user_id=self._db_user_id
            )
            if not quick:
                self._db_email.mark_emails_as_deleted(
                    message_id_lst=deleted_messages_lst, user_id=self._db_user_id
                )
                self._db_email.update_labels(
                    message_id_lst=message_label_updates_lst,
                    message_meta_lst=self._get_labels_for_emails(
                        message_id_lst=message_label_updates_lst
                    ),
                    user_id=self._db_user_id,
                )
            self._store_emails_in_database(
                message_id_lst=new_messages_lst, email_format=email_format
            )

    def _download_messages_to_dataframe(self, message_id_lst, email_format=None):
        """
        Download a list of messages based on their email IDs and store the content in a pandas.DataFrame.

        Args:
            message_id_lst (list): list of emails IDs
            email_format (str): Email format to download - default: "full"

        Returns:
            pandas.DataFrame: pandas.DataFrame which contains the rendered emails
        """
        return pandas.DataFrame(
            [
                message
                for message in [
                    self._parse_message(
                        message=self._get_message_detail(
                            message_id=message_id,
                            email_format=email_format,
                            metadata_headers=[],
                        )
                    )
                    for message_id in tqdm(
                        iterable=message_id_lst, desc="Download messages to DataFrame"
                    )
                ]
                if message is not None
            ]
        )

    def _get_labels_for_emails(self, message_id_lst):
        """
        Get labels for a list of emails

        Args:
            message_id_lst (list): list of emails IDs

        Returns:
            list: Nested list of email labels for each email
        """
        return [
            self._get_labels_for_email(message_id=message_id)
            for message_id in tqdm(
                iterable=message_id_lst, desc="Get labels for emails"
            )
        ]

    def _move_emails(self, move_email_dict, label_to_ignore):
        label_existing = self._label_dict[label_to_ignore]
        for message_id, label_add in tqdm(
            iterable=move_email_dict.items(), desc="Move emails"
        ):
            if label_add is not None and label_add != label_existing:
                self._modify_message_labels(
                    message_id=message_id,
                    label_id_remove_lst=[label_existing],
                    label_id_add_lst=[label_add],
                )

    def _store_emails_in_database(self, message_id_lst, email_format=None):
        df = self._download_messages_to_dataframe(
            message_id_lst=message_id_lst, email_format=email_format
        )
        if len(df) > 0:
            self._db_email.store_dataframe(df=df, user_id=self._db_user_id)

    @abstractmethod
    def _search_email_on_server(
        self, query_string="", label_lst=None, only_message_ids=False
    ):
        """
        Search emails either by a specific query or optionally limit your search to a list of labels

        Args:
            query_string (str): query string to search for
            label_lst (list): list of labels to be searched
            only_message_ids (bool): return only the email IDs not the thread IDs - default: false

        Returns:
            list: list of message ids (or backend-specific list items) matching the search
        """

    @abstractmethod
    def _get_message_detail(self, message_id, email_format=None, metadata_headers=None):
        """
        Get the raw, backend-specific representation of a single email message.

        Args:
            message_id (str): id used by this backend to uniquely identify the email
            email_format (str/None): backend-specific format hint
            metadata_headers (list): backend-specific list of metadata headers

        Returns:
            The backend-specific raw message representation, passed on to `_parse_message`.
        """

    @abstractmethod
    def _get_label_translate_dict(self):
        """
        Returns:
            dict: mapping of label/folder display name to the backend-specific label/folder id
        """

    @abstractmethod
    def _modify_message_labels(
        self, message_id, label_id_remove_lst=None, label_id_add_lst=None
    ):
        """
        Apply a label/folder change to a single email message.
        """

    @abstractmethod
    def _get_labels_for_email(self, message_id):
        """
        Args:
            message_id (str): id used by this backend to uniquely identify the email

        Returns:
            list: list of labels/folders currently assigned to the email
        """

    @abstractmethod
    def _parse_message(self, message):
        """
        Args:
            message: the backend-specific raw message representation returned by `_get_message_detail`

        Returns:
            dict/None: the common gmailsorter email dict (see `gmailsorter.base.message.AbstractMessage.to_dict`),
                       or None if the message could not be parsed
        """
```

- [ ] **Step 2: Rewrite `gmailsorter/google/mail.py`**

Replace the entire file content with:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gmailsorter.base import get_email_database
from gmailsorter.base.mail import AbstractMailBox
from gmailsorter.google.database import get_token_database
from gmailsorter.google.message import get_email_dict
from gmailsorter.ml import get_machine_learning_database


class GoogleMailBase(AbstractMailBox):
    def __init__(
        self,
        google_mail_service,
        database_email=None,
        database_ml=None,
        database_token=None,
        user_id="me",
        db_user_id=1,
        email_download_format="metadata",
    ):
        """
        Gmail class to manage Emails via the Gmail API directly from Python

        Args:
            google_mail_service: A Resource object with methods for interacting with the service.
            database_email (gmailsorter.base.database.DatabaseInterface): SQLalchemy interface for email database
            database_ml (gmailsorter.ml.database.DatabaseInterface): SQLalchemy interface for machine learning database
            database_token (gmailsorter.google.database.DatabaseInterface): SQLalchemy interface for google database
            user_id (str): in most cases this should be simply "me"
            db_user_id (int): Default 1 - set a user id when sharing a database with multiple users
            email_download_format (str): API response format [full, metadata]
        """
        self._db_token = database_token
        super().__init__(
            mail_service=google_mail_service,
            database_email=database_email,
            database_ml=database_ml,
            user_id=user_id,
            db_user_id=db_user_id,
            email_download_format=email_download_format,
        )

    def _get_label_translate_dict(self):
        results = self._service.users().labels().list(userId=self._userid).execute()
        labels = results.get("labels", [])
        return {label["name"]: label["id"] for label in labels}

    def _get_message_detail(self, message_id, email_format=None, metadata_headers=None):
        """
        Get details of a specific email message based on its email ID

        Args:
            message_id (str): email IDs used by Google Mail to uniquely identify emails
            email_format (str/None): API response format [raw, minimal, full, metadata]
            metadata_headers (list): list of meta data headers

        Returns:
            dict: details of the email as python dictionary
        """
        if email_format is None:
            email_format = self._email_download_format
        if metadata_headers is None:
            metadata_headers = []
        return (
            self._service.users()
            .messages()
            .get(
                userId=self._userid,
                id=message_id,
                format=email_format,
                metadataHeaders=metadata_headers,
            )
            .execute()
        )

    def _get_messages_page(self, label_ids, query_string, next_page_token=None):
        message_list_response = (
            self._service.users()
            .messages()
            .list(
                userId=self._userid,
                labelIds=label_ids,
                q=query_string,
                pageToken=next_page_token,
            )
            .execute()
        )

        return [
            message_list_response.get("messages", []),
            message_list_response.get("nextPageToken"),
        ]

    def _get_messages(self, query_string="", label_ids=None):
        if label_ids is None:
            label_ids = []
        message_items_lst, next_page_token = self._get_messages_page(
            label_ids=label_ids, query_string=query_string, next_page_token=None
        )

        while next_page_token:
            message_items, next_page_token = self._get_messages_page(
                label_ids=label_ids,
                query_string=query_string,
                next_page_token=next_page_token,
            )
            message_items_lst.extend(message_items)

        return message_items_lst

    def _modify_message_labels(
        self, message_id, label_id_remove_lst=None, label_id_add_lst=None
    ):
        if label_id_remove_lst is None:
            label_id_remove_lst = []
        if label_id_add_lst is None:
            label_id_add_lst = []
        body_dict = {}
        if len(label_id_remove_lst) > 0:
            body_dict["removeLabelIds"] = label_id_remove_lst
        if len(label_id_add_lst) > 0:
            body_dict["addLabelIds"] = label_id_add_lst
        if len(body_dict) > 0:
            self._service.users().messages().modify(
                userId=self._userid, id=message_id, body=body_dict
            ).execute()

    def _search_email_on_server(
        self, query_string="", label_lst=None, only_message_ids=False
    ):
        """
        Search emails either by a specific query or optionally limit your search to a list of labels

        Args:
            query_string (str): query string to search for
            label_lst (list): list of labels to be searched
            only_message_ids (bool): return only the email IDs not the thread IDs - default: false

        Returns:
            list: list with email IDs and thread IDs of the messages which match the search
        """
        if label_lst is None:
            label_lst = []
        label_ids = [self._label_dict[label] for label in label_lst]
        message_id_lst = self._get_messages(
            query_string=query_string, label_ids=label_ids
        )
        if not only_message_ids:
            return message_id_lst
        else:
            return [d["id"] for d in message_id_lst]

    def _get_labels_for_email(self, message_id):
        """
        Get labels for email

        Args:
            message_id (str): email ID

        Returns:
            list: List of email labels
        """
        message_dict = self._get_message_detail(
            message_id=message_id,
            email_format="metadata",
            metadata_headers=["labelIds"],
        )
        if "labelIds" in message_dict:
            return message_dict["labelIds"]
        else:
            return []

    def _parse_message(self, message):
        return get_email_dict(message=message)

    @staticmethod
    def _create_databases(connection_str):
        engine = create_engine(connection_str)
        session = sessionmaker(bind=engine)()
        db_email = get_email_database(engine=engine, session=session)
        db_ml = get_machine_learning_database(engine=engine, session=session)
        db_token = get_token_database(engine=engine, session=session)
        return db_email, db_ml, db_token

    @staticmethod
    def _get_message_ids(message_lst):
        return [d["id"] for d in message_lst]
```

- [ ] **Step 3: Update patch targets in `tests/test_google_integration_units.py`**

`encode_df_for_machine_learning`, `fit_machine_learning_models`, and `get_predictions_from_machine_learning_models` now execute from `gmailsorter.base.mail`, not `gmailsorter.google.mail`, so the two tests that patch them must point at the new location. In the `test_filter_messages_from_server` method:

```python
    @patch("gmailsorter.base.mail.get_predictions_from_machine_learning_models")
    @patch("gmailsorter.base.mail.encode_df_for_machine_learning")
    def test_filter_messages_from_server(self, encode_mock, predict_mock):
```

(was `@patch("gmailsorter.google.mail.get_predictions_from_machine_learning_models")` / `@patch("gmailsorter.google.mail.encode_df_for_machine_learning")`)

In the `test_fit_machine_learning_model_to_database` method:

```python
    @patch("gmailsorter.base.mail.fit_machine_learning_models")
    @patch("gmailsorter.base.mail.encode_df_for_machine_learning")
    def test_fit_machine_learning_model_to_database(self, encode_mock, fit_mock):
```

(was `@patch("gmailsorter.google.mail.fit_machine_learning_models")` / `@patch("gmailsorter.google.mail.encode_df_for_machine_learning")`)

No other lines in this file change — every assertion stays exactly as-is.

- [ ] **Step 4: Run the full existing suite to confirm no regression**

Run: `python -m unittest discover tests -v`
Expected: All tests PASS, including every test in `tests/test_google_integration_units.py` with unchanged assertions.

- [ ] **Step 5: Create `tests/test_mail_base.py` to test the extracted loop in isolation**

```python
from unittest import TestCase
from unittest.mock import MagicMock, patch

import pandas as pd

from gmailsorter.base.mail import AbstractMailBox


class _StubMailBox(AbstractMailBox):
    """Minimal concrete AbstractMailBox used to test the shared loop in isolation."""

    def __init__(self, label_dict_fixture=None, **kwargs):
        self.label_dict_fixture = label_dict_fixture or {"Inbox": "Inbox", "Spam": "Spam"}
        self.search_result = []
        self.message_detail_dict = {}
        self.modify_calls = []
        self.labels_for_email_dict = {}
        super().__init__(mail_service=MagicMock(), **kwargs)

    def _search_email_on_server(self, query_string="", label_lst=None, only_message_ids=False):
        return self.search_result

    def _get_message_detail(self, message_id, email_format=None, metadata_headers=None):
        return self.message_detail_dict.get(message_id)

    def _get_label_translate_dict(self):
        return self.label_dict_fixture

    def _modify_message_labels(self, message_id, label_id_remove_lst=None, label_id_add_lst=None):
        self.modify_calls.append((message_id, label_id_remove_lst, label_id_add_lst))

    def _get_labels_for_email(self, message_id):
        return self.labels_for_email_dict.get(message_id, [])

    def _parse_message(self, message):
        return message


class AbstractMailBoxTest(TestCase):
    def test_labels_property(self):
        mailbox = _StubMailBox()
        self.assertEqual(sorted(mailbox.labels), ["Inbox", "Spam"])

    def test_download_emails_for_label(self):
        mailbox = _StubMailBox()
        mailbox.search_result = ["id1", "id2"]
        mailbox.message_detail_dict = {
            "id1": {
                "id": "id1",
                "threads": "t1",
                "labels": [],
                "to": [],
                "from": None,
                "cc": [],
                "subject": "s1",
                "content": "c1",
                "date": None,
            },
            "id2": None,
        }

        df = mailbox.download_emails_for_label(label="Inbox")

        self.assertEqual(df["id"].tolist(), ["id1"])

    def test_move_emails_skips_matching_or_none_labels(self):
        mailbox = _StubMailBox()

        mailbox._move_emails(
            move_email_dict={"id1": None, "id2": "Inbox", "id3": "Spam"},
            label_to_ignore="Inbox",
        )

        self.assertEqual(mailbox.modify_calls, [("id3", ["Inbox"], ["Spam"])])

    def test_update_database_marks_missing_as_deleted(self):
        db_email = MagicMock()
        db_email.get_labels_to_update.return_value = (["new"], [], ["deleted"])
        mailbox = _StubMailBox(database_email=db_email)
        mailbox.search_result = ["new"]
        mailbox.message_detail_dict = {
            "new": {
                "id": "new",
                "threads": "t",
                "labels": [],
                "to": [],
                "from": None,
                "cc": [],
                "subject": "s",
                "content": "c",
                "date": None,
            }
        }

        mailbox.update_database(quick=False)

        db_email.mark_emails_as_deleted.assert_called_once_with(
            message_id_lst=["deleted"], user_id=1
        )
        db_email.store_dataframe.assert_called_once()

    @patch("gmailsorter.base.mail.fit_machine_learning_models")
    @patch("gmailsorter.base.mail.encode_df_for_machine_learning")
    def test_fit_machine_learning_model_to_database(self, encode_mock, fit_mock):
        db_email = MagicMock()
        db_email.get_all_emails.return_value = pd.DataFrame(
            [{"id": "x", "from": "a@b.com", "to": [], "cc": [], "labels": [], "threads": "t"}]
        )
        db_ml = MagicMock()
        mailbox = _StubMailBox(database_email=db_email, database_ml=db_ml)
        features = pd.DataFrame([{"email_id": "x", "f1": 1}])
        labels = pd.DataFrame([{"labels_Inbox": 1}])
        encode_mock.return_value = (features, labels)
        fit_mock.return_value = {"Inbox": MagicMock()}

        mailbox.fit_machine_learning_model_to_database(n_estimators=5, max_features=2)

        db_ml.store_models.assert_called_once()
```

- [ ] **Step 6: Run the new test to verify it passes**

Run: `python -m unittest tests.test_mail_base -v`
Expected: PASS (5 tests)

- [ ] **Step 7: Commit**

```bash
git add gmailsorter/base/mail.py gmailsorter/google/mail.py tests/test_google_integration_units.py tests/test_mail_base.py
git commit -m "refactor: extract AbstractMailBox loop from GoogleMailBase into base/mail.py"
```

---

### Task 3: `gmailsorter/imap/message.py`

**Files:**
- Create: `gmailsorter/imap/__init__.py` (empty package marker for now — populated in Task 6)
- Create: `gmailsorter/imap/message.py`
- Test: `tests/test_imap_message.py`

**Interfaces:**
- Consumes: `gmailsorter.base.message.AbstractMessage`, `gmailsorter.base.message.strip_html_tags` (Task 1).
- Produces: `gmailsorter.imap.message.Message(AbstractMessage)` with constructor `Message(message, folder, uid)`, and `gmailsorter.imap.message.get_email_dict(message, folder, uid) -> dict | None`. Consumed by Task 5 (`ImapMailBase._parse_message`).

- [ ] **Step 1: Create the package marker**

Create `gmailsorter/imap/__init__.py` with just:

```python
```

(empty file — populated with real exports in Task 6, once `authentication.py` and `mail.py` exist)

- [ ] **Step 2: Write the failing test**

Create `tests/test_imap_message.py`:

```python
from datetime import datetime
from email.message import EmailMessage
from unittest import TestCase

from gmailsorter.imap.message import Message, get_email_dict


class MessageTest(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        msg = EmailMessage()
        msg["Subject"] = "Test Email Subject"
        msg["From"] = "sender@server.net"
        msg["To"] = "me@mail.com, friend@provider.org"
        msg["Date"] = "Fri, 11 Feb 2022 18:08:46 +0100"
        msg["Message-ID"] = "<abc123@server.net>"
        msg.set_content("Hello world")
        cls._message = msg
        cls.message = Message(message=msg, folder="INBOX", uid="42")

    def test_subject(self):
        self.assertEqual(self.message.get_subject(), "Test Email Subject")

    def test_from(self):
        self.assertEqual(self.message.get_from(), "sender@server.net")

    def test_to(self):
        self.assertEqual(
            self.message.get_to(), ["me@mail.com", "friend@provider.org"]
        )

    def test_cc_empty(self):
        self.assertEqual(self.message.get_cc(), [])

    def test_email_id(self):
        self.assertEqual(self.message.get_email_id(), "INBOX\x1f42")

    def test_thread_id_falls_back_to_message_id(self):
        self.assertEqual(self.message.get_thread_id(), "<abc123@server.net>")

    def test_label_ids(self):
        self.assertEqual(self.message.get_label_ids(), ["INBOX"])

    def test_get_date(self):
        self.assertEqual(
            self.message.get_date(),
            datetime.strptime(
                "Fri, 11 Feb 2022 18:08:46 +0100", "%a, %d %b %Y %H:%M:%S %z"
            ),
        )

    def test_get_content(self):
        self.assertEqual(self.message.get_content().strip(), "Hello world")

    def test_get_content_html_fallback(self):
        html_msg = EmailMessage()
        html_msg["Subject"] = "HTML"
        html_msg["From"] = "sender@server.net"
        html_msg["To"] = "me@mail.com"
        html_msg["Date"] = "Fri, 11 Feb 2022 18:08:46 +0100"
        html_msg.set_content("<p>Hello <b>World</b></p>", subtype="html")
        message = Message(message=html_msg, folder="INBOX", uid="43")

        self.assertEqual(message.get_content().strip(), "Hello World")

    def test_thread_id_uses_references_header(self):
        msg = EmailMessage()
        msg["Subject"] = "Re: Test"
        msg["References"] = "<root@server.net> <mid@server.net>"
        msg["Message-ID"] = "<mid@server.net>"
        message = Message(message=msg, folder="INBOX", uid="44")

        self.assertEqual(message.get_thread_id(), "<root@server.net>")

    def test_from_with_multiple_addresses_is_none(self):
        msg = EmailMessage()
        msg["From"] = "a@server.net, b@server.net"
        message = Message(message=msg, folder="INBOX", uid="45")

        self.assertIsNone(message.get_from())

    def test_get_email_dict(self):
        result = get_email_dict(self._message, folder="INBOX", uid="42")
        content = result.pop("content")

        self.assertEqual(content.strip(), "Hello world")
        self.assertEqual(
            result,
            {
                "cc": [],
                "date": datetime.strptime(
                    "Fri, 11 Feb 2022 18:08:46 +0100", "%a, %d %b %Y %H:%M:%S %z"
                ),
                "from": "sender@server.net",
                "id": "INBOX\x1f42",
                "labels": ["INBOX"],
                "subject": "Test Email Subject",
                "threads": "<abc123@server.net>",
                "to": ["me@mail.com", "friend@provider.org"],
            },
        )
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m unittest tests.test_imap_message -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gmailsorter.imap.message'`

- [ ] **Step 4: Implement `gmailsorter/imap/message.py`**

```python
import email.utils

from gmailsorter.base.message import AbstractMessage, strip_html_tags


def get_email_dict(message, folder, uid):
    try:
        return Message(message=message, folder=folder, uid=uid).to_dict()
    except (ValueError, KeyError) as e:
        print(message, str(e))
        return None


class Message(AbstractMessage):
    def __init__(self, message, folder, uid):
        """
        Message class to parse a raw email.message.Message (as produced by
        email.message_from_bytes() after an IMAP FETCH) into the common gmailsorter
        email representation.

        Args:
            message (email.message.Message): parsed RFC822 message
            folder (str): IMAP mailbox/folder the message was fetched from
            uid (str): IMAP UID of the message within `folder`
        """
        self._message = message
        self._folder = folder
        self._uid = str(uid)

    def get_from(self):
        from_header = self._message.get("From")
        if from_header is None:
            return None
        addresses = [
            address
            for _, address in email.utils.getaddresses([from_header])
            if address
        ]
        if len(addresses) == 1:
            return addresses[0].lower()
        return None

    def get_to(self):
        return self._split_addresses(self._message.get_all("To"))

    def get_cc(self):
        return self._split_addresses(self._message.get_all("Cc"))

    def get_label_ids(self):
        return [self._folder]

    def get_subject(self):
        return self._message.get("Subject")

    def get_date(self):
        date_header = self._message.get("Date")
        if date_header is None:
            return None
        return email.utils.parsedate_to_datetime(date_header)

    def get_content(self):
        text_plain, text_html = None, None
        if self._message.is_multipart():
            for part in self._message.walk():
                if part.get_content_maintype() == "multipart":
                    continue
                if part.get_content_type() == "text/plain" and text_plain is None:
                    text_plain = self._decode_part(part)
                elif part.get_content_type() == "text/html" and text_html is None:
                    text_html = self._decode_part(part)
        elif self._message.get_content_type() == "text/plain":
            text_plain = self._decode_part(self._message)
        elif self._message.get_content_type() == "text/html":
            text_html = self._decode_part(self._message)
        if text_plain is not None:
            return text_plain
        elif text_html is not None:
            return strip_html_tags(text_html)
        else:
            return None

    def get_thread_id(self):
        references = self._message.get("References")
        if references:
            return references.split()[0]
        in_reply_to = self._message.get("In-Reply-To")
        if in_reply_to:
            return in_reply_to.strip()
        message_id = self._message.get("Message-ID")
        if message_id:
            return message_id.strip()
        return self.get_email_id()

    def get_email_id(self):
        return f"{self._folder}\x1f{self._uid}"

    @staticmethod
    def _decode_part(part):
        payload = part.get_payload(decode=True)
        if payload is None:
            return ""
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")

    @staticmethod
    def _split_addresses(header_values):
        if not header_values:
            return []
        return [
            address.lower()
            for _, address in email.utils.getaddresses(header_values)
            if address
        ]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m unittest tests.test_imap_message -v`
Expected: PASS (13 tests)

- [ ] **Step 6: Commit**

```bash
git add gmailsorter/imap/__init__.py gmailsorter/imap/message.py tests/test_imap_message.py
git commit -m "feat: add IMAP message parsing (gmailsorter.imap.message)"
```

---

### Task 4: `gmailsorter/imap/authentication.py`

**Files:**
- Create: `gmailsorter/imap/authentication.py`
- Test: `tests/test_imap_integration_units.py` (new file — also extended in Tasks 5 and 6)

**Interfaces:**
- Produces: `gmailsorter.imap.authentication.create_service(host, port, username, password, use_ssl=True) -> imaplib.IMAP4`. Consumed by Task 6 (`Imap.__init__`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_imap_integration_units.py`:

```python
from unittest import TestCase
from unittest.mock import patch

from gmailsorter.imap.authentication import create_service


class TestImapAuthentication(TestCase):
    @patch("gmailsorter.imap.authentication.IMAP4_SSL")
    def test_create_service_uses_ssl_by_default(self, imap_ssl_cls):
        connection = imap_ssl_cls.return_value

        result = create_service(
            host="localhost", port=993, username="user", password="secret"
        )

        imap_ssl_cls.assert_called_once_with("localhost", 993)
        connection.login.assert_called_once_with("user", "secret")
        self.assertIs(result, connection)

    @patch("gmailsorter.imap.authentication.IMAP4")
    def test_create_service_without_ssl(self, imap_cls):
        connection = imap_cls.return_value

        result = create_service(
            host="localhost",
            port=143,
            username="user",
            password="secret",
            use_ssl=False,
        )

        imap_cls.assert_called_once_with("localhost", 143)
        connection.login.assert_called_once_with("user", "secret")
        self.assertIs(result, connection)


if __name__ == "__main__":
    import unittest

    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_imap_integration_units -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gmailsorter.imap.authentication'`

- [ ] **Step 3: Implement `gmailsorter/imap/authentication.py`**

```python
from imaplib import IMAP4, IMAP4_SSL


def create_service(host, port, username, password, use_ssl=True):
    """
    Open and log in to an IMAP connection.

    Args:
        host (str): IMAP server hostname
        port (int): IMAP server port
        username (str): IMAP account username
        password (str): IMAP account password
        use_ssl (bool): connect via IMAP4_SSL (default) or plain IMAP4

    Returns:
        imaplib.IMAP4: logged-in IMAP connection
    """
    connection_cls = IMAP4_SSL if use_ssl else IMAP4
    connection = connection_cls(host, port)
    connection.login(username, password)
    return connection
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_imap_integration_units -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add gmailsorter/imap/authentication.py tests/test_imap_integration_units.py
git commit -m "feat: add IMAP username/password authentication (gmailsorter.imap.authentication)"
```

---

### Task 5: `gmailsorter/imap/mail.py`

**Files:**
- Create: `gmailsorter/imap/mail.py`
- Modify: `tests/test_imap_integration_units.py` (append)

**Interfaces:**
- Consumes: `gmailsorter.base.mail.AbstractMailBox` (Task 2), `gmailsorter.imap.message.get_email_dict` (Task 3).
- Produces: `gmailsorter.imap.mail.ImapMailBase(AbstractMailBox)` (no custom `__init__` — inherits `AbstractMailBox.__init__`), plus `ImapMailBase._create_databases(connection_str) -> (database_email, database_ml)`. Consumed by Task 6 (`Imap` class, `gmailsorter/imap/__init__.py`).
- Composite message id format: `f"{folder}\x1f{uid}"` (matches `gmailsorter.imap.message.Message.get_email_id`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_imap_integration_units.py` (add these imports at the top, alongside the existing ones):

```python
from unittest.mock import MagicMock
```

```python
from gmailsorter.imap.mail import ImapMailBase
```

Then add this test class at the end of the file (before the `if __name__ == "__main__":` block):

```python
class TestImapMailBase(TestCase):
    def _create_mock_service_with_folders(self, folders=None):
        service = MagicMock()
        service.capabilities = ["IMAP4rev1", "MOVE"]
        service.list.return_value = (
            "OK",
            folders
            if folders is not None
            else [
                b'(\\HasNoChildren) "/" "INBOX"',
                b'(\\HasNoChildren) "/" "MailSortInbox"',
                b'(\\Noselect \\HasChildren) "/" "[Gmail]"',
            ],
        )
        return service

    def test_get_label_translate_dict_skips_noselect(self):
        service = self._create_mock_service_with_folders()
        mail = ImapMailBase(mail_service=service)

        self.assertEqual(sorted(mail.labels), ["INBOX", "MailSortInbox"])

    def test_search_email_on_server_single_folder(self):
        service = self._create_mock_service_with_folders()
        service.select.return_value = ("OK", [b"1"])
        service.uid.return_value = ("OK", [b"1 2"])
        mail = ImapMailBase(mail_service=service)

        ids = mail._search_email_on_server(label_lst=["INBOX"], only_message_ids=True)

        service.select.assert_called_once_with('"INBOX"')
        service.uid.assert_called_once_with("search", None, "ALL")
        self.assertEqual(ids, ["INBOX\x1f1", "INBOX\x1f2"])

    def test_search_email_on_server_all_folders_when_no_label(self):
        service = self._create_mock_service_with_folders()
        service.select.return_value = ("OK", [b"1"])
        service.uid.return_value = ("OK", [b"5"])
        mail = ImapMailBase(mail_service=service)

        ids = mail._search_email_on_server(only_message_ids=True)

        self.assertEqual(
            service.select.call_args_list,
            [(('"INBOX"',),), (('"MailSortInbox"',),)],
        )
        self.assertEqual(ids, ["INBOX\x1f5", "MailSortInbox\x1f5"])

    def test_search_email_on_server_rejects_query_string(self):
        service = self._create_mock_service_with_folders()
        mail = ImapMailBase(mail_service=service)

        with self.assertRaises(NotImplementedError):
            mail._search_email_on_server(query_string="SUBJECT foo")

    def test_get_message_detail_selects_and_fetches(self):
        service = self._create_mock_service_with_folders()
        raw_message = b"Subject: hi\r\nFrom: a@b.com\r\nTo: c@d.com\r\n\r\nbody"
        service.select.return_value = ("OK", [b"1"])
        service.uid.return_value = ("OK", [(b"1 (RFC822 {10}", raw_message)])
        mail = ImapMailBase(mail_service=service)

        folder, uid, message = mail._get_message_detail(message_id="INBOX\x1f7")

        service.select.assert_called_once_with('"INBOX"')
        service.uid.assert_called_once_with("fetch", "7", "(RFC822)")
        self.assertEqual(folder, "INBOX")
        self.assertEqual(uid, "7")
        self.assertEqual(message["Subject"], "hi")

    def test_get_labels_for_email_from_composite_id(self):
        service = self._create_mock_service_with_folders()
        mail = ImapMailBase(mail_service=service)

        self.assertEqual(mail._get_labels_for_email("INBOX\x1f7"), ["INBOX"])

    def test_modify_message_labels_uses_move_when_supported(self):
        service = self._create_mock_service_with_folders()
        service.select.return_value = ("OK", [b"1"])
        service.uid.return_value = ("OK", [b"1"])
        mail = ImapMailBase(mail_service=service)

        mail._modify_message_labels(
            message_id="INBOX\x1f7",
            label_id_remove_lst=["INBOX"],
            label_id_add_lst=["MailSortInbox"],
        )

        service.select.assert_called_once_with('"INBOX"')
        service.uid.assert_called_once_with("move", "7", '"MailSortInbox"')
        service.expunge.assert_not_called()

    def test_modify_message_labels_falls_back_to_copy_delete(self):
        service = self._create_mock_service_with_folders()
        service.capabilities = ["IMAP4rev1"]
        service.select.return_value = ("OK", [b"1"])
        service.uid.return_value = ("OK", [b"1"])
        mail = ImapMailBase(mail_service=service)

        mail._modify_message_labels(
            message_id="INBOX\x1f7",
            label_id_remove_lst=["INBOX"],
            label_id_add_lst=["MailSortInbox"],
        )

        self.assertEqual(
            service.uid.call_args_list,
            [
                (("copy", "7", '"MailSortInbox"'),),
                (("store", "7", "+FLAGS", r"(\Deleted)"),),
            ],
        )
        service.expunge.assert_called_once()

    def test_modify_message_labels_noop_without_target(self):
        service = self._create_mock_service_with_folders()
        mail = ImapMailBase(mail_service=service)

        mail._modify_message_labels(message_id="INBOX\x1f7")

        service.select.assert_not_called()

    @patch("gmailsorter.imap.mail.get_email_dict")
    def test_parse_message_delegates_to_get_email_dict(self, get_email_dict_mock):
        service = self._create_mock_service_with_folders()
        mail = ImapMailBase(mail_service=service)
        get_email_dict_mock.return_value = {"id": "INBOX\x1f7"}

        result = mail._parse_message(("INBOX", "7", "raw"))

        get_email_dict_mock.assert_called_once_with(
            message="raw", folder="INBOX", uid="7"
        )
        self.assertEqual(result, {"id": "INBOX\x1f7"})

    def test_create_databases(self):
        with (
            patch("gmailsorter.imap.mail.create_engine") as create_engine_mock,
            patch("gmailsorter.imap.mail.sessionmaker") as sessionmaker_mock,
            patch("gmailsorter.imap.mail.get_email_database") as get_email_db_mock,
            patch(
                "gmailsorter.imap.mail.get_machine_learning_database"
            ) as get_ml_db_mock,
        ):
            engine = MagicMock()
            session = MagicMock()
            create_engine_mock.return_value = engine
            sessionmaker_mock.return_value.return_value = session
            get_email_db_mock.return_value = "EMAIL_DB"
            get_ml_db_mock.return_value = "ML_DB"

            dbs = ImapMailBase._create_databases("sqlite:///file.db")

        self.assertEqual(dbs, ("EMAIL_DB", "ML_DB"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_imap_integration_units -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gmailsorter.imap.mail'`

- [ ] **Step 3: Implement `gmailsorter/imap/mail.py`**

```python
import email
import re

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gmailsorter.base import get_email_database
from gmailsorter.base.mail import AbstractMailBox
from gmailsorter.imap.message import get_email_dict
from gmailsorter.ml import get_machine_learning_database

_LIST_ENTRY_PATTERN = re.compile(
    r'\((?P<flags>[^)]*)\)\s+"(?P<delimiter>.*)"\s+(?P<name>.+)'
)


class ImapMailBase(AbstractMailBox):
    def _get_label_translate_dict(self):
        status, mailbox_lst = self._service.list()
        if status != "OK" or mailbox_lst is None:
            return {}
        label_dict = {}
        for entry in mailbox_lst:
            flags, _delimiter, name = self._parse_list_entry(entry)
            if "\\Noselect" in flags:
                continue
            label_dict[name] = name
        return label_dict

    def _search_email_on_server(
        self, query_string="", label_lst=None, only_message_ids=False
    ):
        """
        Search emails either by a specific query or optionally limit your search to a list of labels

        Args:
            query_string (str): not supported yet - must be empty
            label_lst (list): list of IMAP folders to search; if empty, every folder is searched
            only_message_ids (bool): return only the composite email IDs - default: false

        Returns:
            list: list of composite "{folder}\\x1f{uid}" ids matching the search
        """
        if query_string:
            raise NotImplementedError(
                "Custom IMAP search queries are not supported yet, only label_lst filtering."
            )
        if label_lst is None:
            label_lst = []
        folder_lst = label_lst if len(label_lst) > 0 else list(self._label_dict.keys())
        message_id_lst = [
            f"{folder}\x1f{uid}"
            for folder in folder_lst
            for uid in self._search_folder(folder=folder)
        ]
        if only_message_ids:
            return message_id_lst
        else:
            return [{"id": message_id} for message_id in message_id_lst]

    def _search_folder(self, folder):
        status, _ = self._service.select(f'"{folder}"')
        if status != "OK":
            return []
        status, data = self._service.uid("search", None, "ALL")
        if status != "OK" or data[0] is None:
            return []
        return [
            uid.decode() if isinstance(uid, bytes) else uid for uid in data[0].split()
        ]

    def _get_message_detail(self, message_id, email_format=None, metadata_headers=None):
        """
        Fetch the raw RFC822 message for a composite "{folder}\\x1f{uid}" id.

        Returns:
            tuple: (folder, uid, email.message.Message)
        """
        folder, uid = message_id.split("\x1f", 1)
        status, _ = self._service.select(f'"{folder}"')
        if status != "OK":
            raise RuntimeError(f"Could not select IMAP folder {folder!r}")
        status, data = self._service.uid("fetch", uid, "(RFC822)")
        if status != "OK" or not data or data[0] is None:
            raise RuntimeError(f"Could not fetch IMAP message {message_id!r}")
        raw_message = data[0][1]
        parsed_message = email.message_from_bytes(raw_message)
        return folder, uid, parsed_message

    def _modify_message_labels(
        self, message_id, label_id_remove_lst=None, label_id_add_lst=None
    ):
        if not label_id_add_lst:
            return
        folder, uid = message_id.split("\x1f", 1)
        target_folder = label_id_add_lst[0]
        status, _ = self._service.select(f'"{folder}"')
        if status != "OK":
            raise RuntimeError(f"Could not select IMAP folder {folder!r}")
        if "MOVE" in self._service.capabilities:
            status, _ = self._service.uid("move", uid, f'"{target_folder}"')
            if status != "OK":
                raise RuntimeError(
                    f"Could not move IMAP message {message_id!r} to {target_folder!r}"
                )
        else:
            status, _ = self._service.uid("copy", uid, f'"{target_folder}"')
            if status != "OK":
                raise RuntimeError(
                    f"Could not copy IMAP message {message_id!r} to {target_folder!r}"
                )
            self._service.uid("store", uid, "+FLAGS", r"(\Deleted)")
            self._service.expunge()

    def _get_labels_for_email(self, message_id):
        folder, _uid = message_id.split("\x1f", 1)
        return [folder]

    def _parse_message(self, message):
        folder, uid, parsed_message = message
        return get_email_dict(message=parsed_message, folder=folder, uid=uid)

    @staticmethod
    def _parse_list_entry(entry):
        decoded = entry.decode() if isinstance(entry, bytes) else entry
        match = _LIST_ENTRY_PATTERN.match(decoded)
        flags = match.group("flags").split()
        delimiter = match.group("delimiter")
        name = match.group("name").strip('"')
        return flags, delimiter, name

    @staticmethod
    def _create_databases(connection_str):
        engine = create_engine(connection_str)
        session = sessionmaker(bind=engine)()
        db_email = get_email_database(engine=engine, session=session)
        db_ml = get_machine_learning_database(engine=engine, session=session)
        return db_email, db_ml
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_imap_integration_units -v`
Expected: PASS (all tests in the file, including the `TestImapAuthentication` tests from Task 4)

- [ ] **Step 5: Commit**

```bash
git add gmailsorter/imap/mail.py tests/test_imap_integration_units.py
git commit -m "feat: add ImapMailBase (folders-as-labels, MOVE/COPY+EXPUNGE)"
```

---

### Task 6: `Imap` class in `local.py`, IMAP package exports, top-level export

**Files:**
- Modify: `gmailsorter/imap/__init__.py`
- Modify: `gmailsorter/local.py`
- Modify: `gmailsorter/__init__.py`
- Modify: `tests/test_imap_integration_units.py` (append)

**Interfaces:**
- Produces: `gmailsorter.imap.create_service`, `gmailsorter.imap.ImapMailBase` (re-exports), `gmailsorter.local.Imap(host, port, username, password, connection_str, db_user_id=1, use_ssl=True, email_download_format="metadata")`, `gmailsorter.Imap`. Consumed by Task 7 (CLI).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_imap_integration_units.py` (add these imports at the top, alongside the existing ones):

```python
from gmailsorter.local import Imap
```

Then add this test class at the end of the file (before the `if __name__ == "__main__":` block):

```python
class TestImapLocalHelpers(TestCase):
    @patch("gmailsorter.local.ImapMailBase.__init__", return_value=None)
    @patch("gmailsorter.local.create_imap_service")
    @patch("gmailsorter.local.Imap._create_databases")
    def test_imap_initialization_wiring(
        self, create_databases_mock, create_service_mock, base_init_mock
    ):
        db_email, db_ml = MagicMock(), MagicMock()
        create_databases_mock.return_value = (db_email, db_ml)
        connection = MagicMock()
        create_service_mock.return_value = connection

        Imap(
            host="localhost",
            port=993,
            username="user",
            password="secret",
            connection_str="sqlite:///:memory:",
            db_user_id=4,
        )

        create_databases_mock.assert_called_once_with(
            connection_str="sqlite:///:memory:"
        )
        create_service_mock.assert_called_once_with(
            host="localhost",
            port=993,
            username="user",
            password="secret",
            use_ssl=True,
        )
        base_init_mock.assert_called_once_with(
            mail_service=connection,
            database_email=db_email,
            database_ml=db_ml,
            user_id="user",
            db_user_id=4,
            email_download_format="metadata",
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_imap_integration_units -v`
Expected: FAIL with `ImportError: cannot import name 'Imap' from 'gmailsorter.local'`

- [ ] **Step 3: Populate `gmailsorter/imap/__init__.py`**

```python
from gmailsorter.imap.authentication import create_service
from gmailsorter.imap.mail import ImapMailBase

__all__ = ["create_service", "ImapMailBase"]
```

- [ ] **Step 4: Add `Imap` to `gmailsorter/local.py`**

Add these imports at the top of `gmailsorter/local.py` (alongside the existing ones):

```python
from gmailsorter.imap import ImapMailBase
from gmailsorter.imap import create_service as create_imap_service
```

Then append the `Imap` class at the end of the file, after `load_client_secrets_file`:

```python
class Imap(ImapMailBase):
    def __init__(
        self,
        host,
        port,
        username,
        password,
        connection_str,
        db_user_id=1,
        use_ssl=True,
        email_download_format="metadata",
    ):
        """
        Imap class to manage Emails via a plain IMAP connection directly from Python

        Args:
            host (str): IMAP server hostname
            port (int): IMAP server port, typically 993 for IMAP4_SSL or 143 for IMAP4
            username (str): IMAP account username
            password (str): IMAP account password
            connection_str (str): SQLalchemy compatible connection string to connect to the SQL database
            db_user_id (int): Default 1 - set a user id when sharing a database with multiple users
            use_ssl (bool): connect via IMAP4_SSL (default) or plain IMAP4
            email_download_format (str): unused for IMAP, kept for interface parity with Gmail
        """
        self._connection_str = connection_str

        database_email, database_ml = self._create_databases(
            connection_str=self._connection_str
        )

        imap_connection = create_imap_service(
            host=host,
            port=port,
            username=username,
            password=password,
            use_ssl=use_ssl,
        )

        super().__init__(
            mail_service=imap_connection,
            database_email=database_email,
            database_ml=database_ml,
            user_id=username,
            db_user_id=db_user_id,
            email_download_format=email_download_format,
        )
```

- [ ] **Step 5: Export `Imap` from `gmailsorter/__init__.py`**

Replace the file content with:

```python
from gmailsorter.local import Gmail, Imap, load_client_secrets_file

from . import _version

__version__: str = _version.__version__
__all__ = ["Gmail", "Imap", "load_client_secrets_file"]
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m unittest tests.test_imap_integration_units -v`
Expected: PASS (all tests)

- [ ] **Step 7: Run the full suite**

Run: `python -m unittest discover tests -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add gmailsorter/imap/__init__.py gmailsorter/local.py gmailsorter/__init__.py tests/test_imap_integration_units.py
git commit -m "feat: add Imap convenience class and gmailsorter.Imap export"
```

---

### Task 7: `gmailsorter-imap` CLI

**Files:**
- Create: `gmailsorter/imap/__main__.py`
- Modify: `pyproject.toml`
- Test: `tests/test_imap_cli.py`

**Interfaces:**
- Consumes: `gmailsorter.Imap` (Task 6).
- Produces: `gmailsorter.imap.__main__.command_line_parser()`, console script `gmailsorter-imap`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_imap_cli.py`:

```python
import os
from unittest import TestCase
from unittest.mock import patch

from gmailsorter.imap.__main__ import command_line_parser


class ImapCliTest(TestCase):
    @patch("gmailsorter.imap.__main__.Imap")
    def test_update_wires_imap_and_triggers_update(self, imap_cls):
        imap_instance = imap_cls.return_value
        os.environ["IMAP_PASSWORD"] = "secret"
        try:
            with patch(
                "sys.argv",
                [
                    "gmailsorter-imap",
                    "--host",
                    "localhost",
                    "--port",
                    "993",
                    "--username",
                    "user",
                    "-d",
                    "sqlite:///:memory:",
                    "-u",
                ],
            ):
                command_line_parser()
        finally:
            del os.environ["IMAP_PASSWORD"]

        imap_cls.assert_called_once_with(
            host="localhost",
            port=993,
            username="user",
            password="secret",
            connection_str="sqlite:///:memory:",
            db_user_id=1,
            use_ssl=True,
            email_download_format="metadata",
        )
        imap_instance.update_database.assert_called_once_with(quick=False)
        imap_instance.fit_machine_learning_model_to_database.assert_called_once_with(
            n_estimators=100,
            max_features=400,
            random_state=42,
            bootstrap=True,
            include_deleted=False,
        )

    @patch("gmailsorter.imap.__main__.Imap")
    def test_label_wires_imap_and_triggers_filter(self, imap_cls):
        imap_instance = imap_cls.return_value
        os.environ["IMAP_PASSWORD"] = "secret"
        try:
            with patch(
                "sys.argv",
                [
                    "gmailsorter-imap",
                    "--host",
                    "localhost",
                    "--username",
                    "user",
                    "-d",
                    "sqlite:///:memory:",
                    "-l",
                    "MailSortInbox",
                ],
            ):
                command_line_parser()
        finally:
            del os.environ["IMAP_PASSWORD"]

        imap_instance.filter_messages_from_server.assert_called_once_with(
            label="MailSortInbox", recommendation_ratio=0.9
        )

    @patch("gmailsorter.imap.__main__.Imap")
    def test_missing_password_env_skips_wiring(self, imap_cls):
        os.environ.pop("IMAP_PASSWORD", None)
        with patch(
            "sys.argv",
            ["gmailsorter-imap", "--host", "localhost", "--username", "user"],
        ):
            command_line_parser()

        imap_cls.assert_not_called()

    @patch("gmailsorter.imap.__main__.Imap")
    def test_missing_host_skips_wiring(self, imap_cls):
        with patch("sys.argv", ["gmailsorter-imap", "--username", "user"]):
            command_line_parser()

        imap_cls.assert_not_called()


if __name__ == "__main__":
    import unittest

    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_imap_cli -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gmailsorter.imap.__main__'`

- [ ] **Step 3: Implement `gmailsorter/imap/__main__.py`**

```python
import argparse
import os

from gmailsorter import Imap


def command_line_parser():
    """
    Main function primarily used for the command line interface of the IMAP backend
    """
    parser = argparse.ArgumentParser(prog="gmailsorter-imap")
    parser.add_argument(
        "--host",
        help="IMAP server hostname e.g. imap.example.com .",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=993,
        help="IMAP server port - default: 993 .",
    )
    parser.add_argument(
        "--username",
        help="IMAP account username.",
    )
    parser.add_argument(
        "--password-env",
        default="IMAP_PASSWORD",
        help=(
            "Name of the environment variable holding the IMAP account password - "
            "default: IMAP_PASSWORD ."
        ),
    )
    parser.add_argument(
        "--no-ssl",
        action="store_true",
        help="Connect without SSL (IMAP4 instead of IMAP4_SSL).",
    )
    parser.add_argument(
        "-d",
        "--database",
        help="Connection string to connect to database e.g. sqlite:///email.db .",
    )
    parser.add_argument(
        "-u",
        "--update",
        action="store_true",
        help="Update local database and retrain machine learning model.",
    )
    parser.add_argument(
        "-i",
        "--identification",
        help="User ID of the database user e.g. 1 .",
    )
    parser.add_argument(
        "-l",
        "--label",
        help="Email label (IMAP folder) to be filtered with machine learning.",
    )
    args = parser.parse_args()
    db_user_id = int(args.identification) if args.identification else 1
    password = os.environ.get(args.password_env)
    if not args.host or not args.username:
        print("Please provide --host and --username.")
    elif not password:
        print(
            f"Please set the {args.password_env} environment variable to your IMAP password."
        )
    else:
        database = args.database or "sqlite:///email.db"
        imap = Imap(
            host=args.host,
            port=args.port,
            username=args.username,
            password=password,
            connection_str=database,
            db_user_id=db_user_id,
            use_ssl=not args.no_ssl,
            email_download_format="metadata",
        )
        if args.update:
            imap.update_database(quick=False)
            imap.fit_machine_learning_model_to_database(
                n_estimators=100,
                max_features=400,
                random_state=42,
                bootstrap=True,
                include_deleted=False,
            )
        elif args.label:
            imap.filter_messages_from_server(label=args.label, recommendation_ratio=0.9)
        else:
            parser.print_help()


if __name__ == "__main__":
    command_line_parser()
```

- [ ] **Step 4: Register the console script in `pyproject.toml`**

In the `[project.scripts]` section, add a fourth line:

```toml
[project.scripts]
gmailsorter = "gmailsorter.__main__:command_line_parser"
gmailsorter-daemon = "gmailsorter.daemon.__main__:command_line_parser"
gmailsorter-app = "gmailsorter.webapp.app:run_app"
gmailsorter-imap = "gmailsorter.imap.__main__:command_line_parser"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m unittest tests.test_imap_cli -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Run the full suite**

Run: `python -m unittest discover tests -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add gmailsorter/imap/__main__.py pyproject.toml tests/test_imap_cli.py
git commit -m "feat: add gmailsorter-imap CLI entry point"
```

---

### Task 8: GreenMail integration test + CI job

**Files:**
- Create: `tests/test_imap_service_integration.py`
- Modify: `.github/workflows/unittest.yml`

**Interfaces:**
- Consumes: `gmailsorter.local.Imap` (Task 6).
- Environment variables (matching the [testing-imap](https://github.com/jan-janssen/testing-imap) convention): `TEST_SMTP_HOST`, `TEST_SMTP_PORT`, `TEST_IMAP_HOST`, `TEST_IMAP_PORT`, `TEST_IMAP_USERNAME`, `TEST_EMAIL`, `TEST_EMAIL_PASSWORD`.

This test talks to a **real** GreenMail server, so it cannot be driven through a plain RED/GREEN cycle without one running. It's written to skip cleanly (not fail) when no server is reachable, so `python -m unittest discover tests` stays green for contributors without Docker; CI (Step 4 below) is what proves it actually passes.

- [ ] **Step 1: Create `tests/test_imap_service_integration.py`**

```python
import os
import smtplib
import time
import unittest
import uuid
from email.message import EmailMessage
from imaplib import IMAP4

from gmailsorter.local import Imap


class TestImapServiceIntegration(unittest.TestCase):
    smtp_host = os.environ.get("TEST_SMTP_HOST", "localhost")
    smtp_port = int(os.environ.get("TEST_SMTP_PORT", "3025"))
    imap_host = os.environ.get("TEST_IMAP_HOST", "localhost")
    imap_port = int(os.environ.get("TEST_IMAP_PORT", "3143"))
    username = os.environ.get("TEST_IMAP_USERNAME", "testuser")
    recipient = os.environ.get("TEST_EMAIL", "testuser@example.test")
    password = os.environ.get("TEST_EMAIL_PASSWORD", "secret")

    @classmethod
    def setUpClass(cls):
        if not cls._imap_server_available():
            raise unittest.SkipTest(
                "No IMAP test server reachable at "
                f"{cls.imap_host}:{cls.imap_port} - start the greenmail container "
                "described in https://github.com/jan-janssen/testing-imap to run this test."
            )

    @classmethod
    def _imap_server_available(cls, timeout=2.0):
        try:
            with IMAP4(cls.imap_host, cls.imap_port, timeout=timeout) as client:
                status, _ = client.noop()
                return status == "OK"
        except OSError:
            return False

    def setUp(self):
        with IMAP4(self.imap_host, self.imap_port, timeout=10) as client:
            client.login(self.username, self.password)
            client.select("INBOX")
            status, data = client.search(None, "ALL")
            for message_id in data[0].split():
                client.store(message_id, "+FLAGS", r"(\Deleted)")
            client.expunge()
            for folder in ("MailSortInbox", "Sorted"):
                client.create(folder)

    def _send_message(self, subject, body):
        message_id = f"<{uuid.uuid4()}@example.test>"
        message = EmailMessage()
        message["From"] = "sender@example.test"
        message["To"] = self.recipient
        message["Subject"] = subject
        message["Message-ID"] = message_id
        message.set_content(body)
        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as smtp:
            smtp.send_message(message)
        return message_id

    def _wait_for_message_in_inbox(self, message_id, timeout=10.0):
        deadline = time.monotonic() + timeout
        with IMAP4(self.imap_host, self.imap_port, timeout=10) as client:
            client.login(self.username, self.password)
            client.select("INBOX")
            while time.monotonic() < deadline:
                status, data = client.search(
                    None, "HEADER", "Message-ID", f'"{message_id}"'
                )
                self.assertEqual(status, "OK")
                if data[0].split():
                    return
                time.sleep(0.2)
        self.fail(f"Message {message_id!r} was not delivered to INBOX")

    def test_update_database_and_move_round_trip(self):
        message_id = self._send_message(
            subject="Integration test message",
            body="Body from gmailsorter IMAP test.",
        )
        self._wait_for_message_in_inbox(message_id)

        imap = Imap(
            host=self.imap_host,
            port=self.imap_port,
            username=self.username,
            password=self.password,
            connection_str="sqlite:///:memory:",
            use_ssl=False,
        )

        imap.update_database(quick=False)
        df = imap.get_all_emails_in_database()

        self.assertIn("Integration test message", df["subject"].tolist())
        stored_id = df.loc[
            df["subject"] == "Integration test message", "id"
        ].iloc[0]
        self.assertTrue(stored_id.startswith("INBOX\x1f"))

        imap._modify_message_labels(
            message_id=stored_id,
            label_id_remove_lst=["INBOX"],
            label_id_add_lst=["MailSortInbox"],
        )

        imap.update_database(quick=False)
        df_after_move = imap.get_all_emails_in_database()
        moved_row = df_after_move.loc[
            df_after_move["subject"] == "Integration test message"
        ]
        self.assertEqual(len(moved_row), 1)
        self.assertTrue(moved_row.iloc[0]["id"].startswith("MailSortInbox\x1f"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it locally (expected to skip without Docker)**

Run: `python -m unittest tests.test_imap_service_integration -v`
Expected: `skipped 'No IMAP test server reachable at localhost:3143 - ...'`

- [ ] **Step 3: (Optional local verification) Run it against a real GreenMail container**

If Docker is available locally:

```bash
docker run -d --rm --name greenmail-test \
  -p 3025:3025 -p 3143:3143 \
  -e GREENMAIL_OPTS='-Dgreenmail.setup.test.smtp -Dgreenmail.setup.test.imap -Dgreenmail.hostname=0.0.0.0 -Dgreenmail.users=testuser:secret@example.test' \
  greenmail/standalone:2.1.11
python -m unittest tests.test_imap_service_integration -v
docker stop greenmail-test
```

Expected: PASS (1 test). Skip this step if Docker isn't available — Step 4 (CI) is the authoritative check.

- [ ] **Step 4: Add a `imap-integration` job to `.github/workflows/unittest.yml`**

Append a second top-level job under `jobs:` (as a sibling of the existing `build` job), so the full file reads:

```yaml
# This workflow is used to run the unittest of pyiron

name: Unittests

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  build:

    runs-on: ${{ matrix.operating-system }}
    strategy:
      matrix:
        operating-system: [ubuntu-latest, windows-latest, macos-latest]
        python-version: ['3.14']
        include:
        - operating-system: ubuntu-latest
          python-version: '3.11'
        - operating-system: ubuntu-latest
          python-version: '3.12'
        - operating-system: ubuntu-latest
          python-version: '3.13'

    steps:
    - uses: actions/checkout@v4
    - name: Conda config
      shell: bash -l {0}
      run: echo -e "channels:\n  - conda-forge\n" > .condarc
    - uses: conda-incubator/setup-miniconda@v3
      with:
        python-version: ${{ matrix.python-version }}
        miniforge-version: latest
        condarc-file: .condarc
        environment-file: .ci_support/environment.yml
    - name: Test
      shell: bash -l {0}
      timeout-minutes: 30
      run: |
        pip install --no-deps .
        coverage run --omit gmailsorter/_version.py -m unittest discover tests

  imap-integration:
    runs-on: ubuntu-latest

    services:
      greenmail:
        image: greenmail/standalone:2.1.11
        env:
          GREENMAIL_OPTS: >-
            -Dgreenmail.setup.test.smtp
            -Dgreenmail.setup.test.imap
            -Dgreenmail.hostname=0.0.0.0
            -Dgreenmail.users=testuser:secret@example.test
        ports:
          - 3025:3025
          - 3143:3143

    env:
      TEST_SMTP_HOST: localhost
      TEST_SMTP_PORT: "3025"
      TEST_IMAP_HOST: localhost
      TEST_IMAP_PORT: "3143"
      TEST_IMAP_USERNAME: testuser
      TEST_EMAIL: testuser@example.test
      TEST_EMAIL_PASSWORD: secret

    steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: '3.12'
    - name: Install package
      run: pip install .
    - name: Run IMAP integration test
      run: python -m unittest tests.test_imap_service_integration -v
```

(Note: this is a separate job, not an extra step in `build` — GitHub Actions `services:` containers only run on Linux-hosted runners, and `build` mixes `ubuntu-latest`/`windows-latest`/`macos-latest` in one matrix, so the GreenMail-backed test needs its own Linux-only job.)

- [ ] **Step 5: Commit**

```bash
git add tests/test_imap_service_integration.py .github/workflows/unittest.yml
git commit -m "test: add GreenMail-backed IMAP integration test and CI job"
```

---

### Task 9: Documentation

**Files:**
- Modify: `docs/source/developer.md`
- Modify: `docs/source/architecture.md`

**Interfaces:** None (documentation only).

- [ ] **Step 1: Add an IMAP section to `docs/source/developer.md`**

After the existing `### Filter emails using machine learning` subsection and before `## Future directions`, insert:

```markdown
## IMAP accounts
`gmailsorter` also supports plain IMAP accounts (username and password, e.g. an app
password), for mail servers other than Google Mail. Import the `Imap` class instead of
`Gmail`:
```
from gmailsorter import Imap
```
```
imap = Imap(
    host="imap.example.com",
    port=993,
    username="user@example.com",
    password="app-password",
    connection_str="sqlite:////absolute/path/to/email.db",
)
```
`Imap` exposes the exact same `update_database()`, `get_all_emails_in_database()` and
`filter_messages_from_server()` methods as `Gmail` - the only difference is that IMAP
folders play the role Gmail labels play elsewhere in this document: each folder is
treated as one label, and moving an email means moving it from one IMAP folder to
another. A command line interface is also available as `gmailsorter-imap`, reading the
account password from an environment variable (`IMAP_PASSWORD` by default) rather than
accepting it as a command line argument:
```
export IMAP_PASSWORD=app-password
gmailsorter-imap --host imap.example.com --username user@example.com -d sqlite:///email.db -u
```
```

- [ ] **Step 2: Mention IMAP in `docs/source/architecture.md`**

In the "The big picture" section, change:

```markdown
* **Your Google Mail account** - the source of truth for your emails and labels, accessed exclusively through the
  official [Gmail API](https://developers.google.com/gmail/api/guides). `gmailsorter` never reads your mailbox
  through any other channel and never stores your Google password.
```

to:

```markdown
* **Your email account** - the source of truth for your emails and labels, accessed either through the official
  [Gmail API](https://developers.google.com/gmail/api/guides) or, for any other IMAP-capable provider, through a
  plain IMAP connection. `gmailsorter` never stores your Google password, and for IMAP accounts the password you
  provide is used only to log in - it is not persisted anywhere. When talking to a plain IMAP server, each mailbox
  folder plays the role a Gmail label plays throughout the rest of this page - "moving" an email between labels
  means moving it between IMAP folders.
```

- [ ] **Step 3: Commit**

```bash
git add docs/source/developer.md docs/source/architecture.md
git commit -m "docs: document the Imap class and CLI"
```

---

## Final verification (after all tasks)

- [ ] Run the full suite one more time: `coverage run --omit gmailsorter/_version.py -m unittest discover tests -v` — expect all tests PASS (GreenMail test SKIPPED unless Docker is running locally).
- [ ] Run `ruff check gmailsorter/` and `ruff format --check gmailsorter/` (or `pre-commit run --all-files` if available) — expect no lint errors.
- [ ] Push the branch and confirm both the `build` matrix and the new `imap-integration` job go green in GitHub Actions before opening the PR.
