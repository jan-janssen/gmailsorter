# IMAP support for gmailsorter

## Problem

`gmailsorter` currently only talks to Gmail through the Gmail API. This limits it to
Google Mail accounts and means the machine-learned sorting logic can never be exercised
in CI without live Google credentials. We want to add a second backend that speaks IMAP
(username + password auth), so that:

* Users with any IMAP-capable mailbox (self-hosted, Dovecot, etc.) can use gmailsorter.
* CI can run a real, end-to-end integration test against a disposable IMAP server
  (GreenMail), the way [jan-janssen/testing-imap](https://github.com/jan-janssen/testing-imap)
  demonstrates.

## Scope

In scope:

* A new `gmailsorter/imap/` package (`authentication.py`, `message.py`, `mail.py`)
  parallel to `gmailsorter/google/`.
* A new `Imap` class in `gmailsorter/local.py`, parallel to `Gmail`.
* A new `gmailsorter-imap` CLI entry point, parallel to `gmailsorter`/`gmailsorter-daemon`.
* Refactoring the fetch-store-train-predict-move loop currently living in
  `GoogleMailBase` into a shared abstract base class, so both backends reuse it instead
  of duplicating it.
* Unit tests (mocked `imaplib`) and a real integration test against a `greenmail`
  container in GitHub Actions.

Out of scope (explicitly deferred):

* The Flask webapp / gmailsorter.com login flow — stays Gmail-OAuth-only.
* `gmailsorter-daemon` — stays Gmail-only for now.
* OAuth2/XOAUTH2 for IMAP (e.g. Outlook, Gmail-via-IMAP) — only plain username/password
  login (`IMAP4_SSL`/`IMAP4` `LOGIN`) is implemented. The authentication module should
  not need reworking to add this later, but implementing it is not part of this change.
* Custom IMAP `SEARCH` queries (the `query_string` parameter that already exists but is
  never actually used anywhere in the current codebase) — the IMAP backend only needs to
  support `SEARCH ALL` for v1.

## Architecture

### Extracting the shared loop

`GoogleMailBase` (`gmailsorter/google/mail.py`) currently mixes two concerns: the
backend-agnostic fetch→store→train→predict→move loop, and Gmail-API-specific calls
(`service.users().messages()...`). Adding IMAP as a second backend without extracting
the shared part would mean copy-pasting roughly 150 lines of loop/business logic
(`download_emails_for_label`, `filter_messages_from_server`,
`fit_machine_learning_model_to_database`, `get_all_emails_in_database`,
`update_database`, `_download_messages_to_dataframe`, `_store_emails_in_database`,
`_get_labels_for_email(s)`, `_move_emails`) into a new `imap/mail.py`. Instead, this
logic moves into a new class:

```
gmailsorter/base/mail.py
    class AbstractMailBox(ABC):
        # concrete, shared:
        labels (property)
        download_emails_for_label(label)
        filter_messages_from_server(label, recommendation_ratio=0.9)
        fit_machine_learning_model_to_database(...)
        get_all_emails_in_database(include_deleted=False)
        update_database(quick=False, label_lst=None, email_format=None)
        _download_messages_to_dataframe(message_id_lst, email_format=None)
        _get_labels_for_email(message_id)
        _get_labels_for_emails(message_id_lst)
        _move_emails(move_email_dict, label_to_ignore)
        _store_emails_in_database(message_id_lst, email_format=None)

        # abstract, backend-specific:
        _search_email_on_server(query_string="", label_lst=None, only_message_ids=False)
        _get_message_detail(message_id, email_format=None, metadata_headers=None)
        _get_label_translate_dict()
        _modify_message_labels(message_id, label_id_remove_lst=None, label_id_add_lst=None)
        _parse_message(message) -> dict   # via each backend's AbstractMessage subclass
```

This mirrors the existing `base/` vs `google/` split already used for `message.py`
(`AbstractMessage`) and `database.py` (`DatabaseTemplate`/`DatabaseInterface`).

`GoogleMailBase(AbstractMailBox)` keeps its **exact current public constructor
signature** (`google_mail_service`, `database_email`, `database_ml`, `database_token`,
`user_id`, `db_user_id`, `email_download_format`) so existing callers and tests
(`tests/test_google_integration_units.py`) are unaffected. `database_token` is confirmed
unused outside of `__init__` (grepped the codebase — it's stored on `self` but never
read again), so it stays a `GoogleMailBase`-only attribute rather than being threaded
into the shared base class.

The small `MLStripper` HTML-to-text helper currently in `gmailsorter/google/message.py`
is generic (not Gmail-specific), so it moves to `gmailsorter/base/message.py` and both
`google/message.py` and the new `imap/message.py` reuse it from there.

### `gmailsorter/imap/authentication.py`

```python
def create_service(host, port, username, password, use_ssl=True):
    """Open and log in to an IMAP4_SSL/IMAP4 connection. Raises on failure."""
```

No token database, no refresh flow — the password is supplied directly each time a
connection is created (matches how `Gmail`'s `client_config` is supplied directly, just
without the OAuth indirection). If the connection drops, callers reconnect by calling
`create_service` again.

### `gmailsorter/imap/message.py`

`Message(AbstractMessage)` parses a raw `email.message.Message` (as returned by
`email.message_from_bytes` after an IMAP `FETCH ... (RFC822)`), plus the folder name it
was fetched from:

* `get_email_id()` → composite `f"{folder}\x1f{uid}"`. IMAP UIDs are only unique/stable
  *within one mailbox* (a `MOVE` to another folder assigns a new UID at the
  destination), so the folder is baked into the id used as the primary key in the local
  database.
* `get_thread_id()` → first `References` header entry, else `In-Reply-To`, else the
  message's own `Message-ID` (so a thread-starting message is its own thread root).
* `get_label_ids()` → `[folder]` — a single-item list, since one IMAP mailbox = one
  label. This fits the existing multi-label list contract in `ml/encoding.py` unchanged.
* `get_from`/`get_to`/`get_cc`/`get_subject`/`get_date` → parsed from the standard email
  headers (`email.utils.parseaddr`/`getaddresses`, `email.utils.parsedate_to_datetime`).
* `get_content()` → walks MIME parts for `text/plain`, falling back to `text/html`
  stripped via the shared `MLStripper`.

### `gmailsorter/imap/mail.py`

`ImapMailBase(AbstractMailBox)` implements the abstract hooks:

* `_get_label_translate_dict()` — `IMAP LIST` all mailboxes, skipping ones flagged
  `\Noselect`, returned as `{name: name}` (IMAP has no separate id vs. display name).
* `_search_email_on_server(query_string="", label_lst=None, only_message_ids=False)` —
  * If `label_lst` is non-empty: `SELECT` each named folder and `UID SEARCH ALL`.
  * If `label_lst` is empty (the case `update_database()` always uses in practice —
    verified `__main__.py` and `daemon/daemon.py` both call it with no `label_lst`,
    exactly mirroring how Gmail's own `label_ids=[]` means "no filter, whole account"):
    iterate over **every** folder from `_get_label_translate_dict()` and aggregate.
  * A non-empty `query_string` raises `NotImplementedError` (not silently ignored),
    since custom IMAP `SEARCH` syntax isn't implemented in v1 and it's better to fail
    loudly than search the wrong thing.
* `_get_message_detail(message_id, ...)` — splits the composite id into
  `(folder, uid)`, `SELECT`s the folder, `UID FETCH ... (RFC822)`.
* `_modify_message_labels(message_id, label_id_remove_lst, label_id_add_lst)` — treated
  as "move `message_id` from `label_id_remove_lst[0]` to `label_id_add_lst[0]`" (IMAP
  only has one folder per message, unlike Gmail's multi-label add/remove). Issues IMAP
  `MOVE` if the server advertises the `MOVE` capability, otherwise falls back to `COPY` +
  `STORE +FLAGS (\Deleted)` + `EXPUNGE`.
* `_create_databases(connection_str)` — creates only `database_email` and `database_ml`
  (no token database, since there's no OAuth token to persist).

### `gmailsorter/local.py`

```python
class Imap(ImapMailBase):
    def __init__(self, host, port, username, password, connection_str,
                 db_user_id=1, use_ssl=True, email_download_format="metadata"):
        ...
```

Parallel to the existing `Gmail` class: builds the two databases, opens the IMAP
connection via `imap.authentication.create_service`, and calls `super().__init__(...)`.

### CLI: `gmailsorter-imap`

A new console-script entry point in `pyproject.toml`
(`gmailsorter-imap = "gmailsorter.imap.__main__:command_line_parser"`), parallel to the
existing `gmailsorter`/`gmailsorter-daemon`/`gmailsorter-app` scripts (a new top-level
CLI rather than overloading the existing `gmailsorter` parser with two unrelated
credential schemes). Flags:

* `--host`, `--port` (default `993`), `--username`
* `--password-env` (name of an environment variable holding the password; default
  `IMAP_PASSWORD`) — the password is never accepted as a literal CLI argument, so it
  never ends up in shell history or `ps` output.
* `--database`, `--update`, `--label`, `--identification` — same meaning as the
  existing `gmailsorter` CLI.

## Testing

* `tests/test_imap_message.py` — mirrors `tests/test_google_message.py`: constructs a
  raw `email.message.Message`, asserts each `get_*` method and `to_dict()`.
* `tests/test_imap_integration_units.py` — mirrors
  `tests/test_google_integration_units.py`: mocks `imaplib.IMAP4_SSL` and asserts
  `ImapMailBase`'s hook methods issue the right IMAP commands (`SELECT`, `UID SEARCH`,
  `UID FETCH`, `MOVE`/`COPY`+`STORE`+`EXPUNGE`), plus `Imap` wiring in `local.py`.
* `tests/test_mail_base.py` — new tests for the extracted `AbstractMailBox` loop logic
  itself (currently only exercised indirectly through `GoogleMailBase` in
  `test_google_integration_units.py`), using a minimal concrete stub subclass.
* Existing `tests/test_google_integration_units.py` continues to pass unmodified,
  proving the refactor didn't change `GoogleMailBase`'s observable behavior.
* `tests/test_imap_service_integration.py` — a real end-to-end test (not mocked) that:
  1. Connects to a live `greenmail/standalone` container via `smtplib` (send) and
     `imaplib` (fetch), following the pattern in
     [jan-janssen/testing-imap](https://github.com/jan-janssen/testing-imap)'s
     `tests/test_imap_service.py`.
  2. Drives it through `gmailsorter.local.Imap` — updates a SQLite database from the
     live GreenMail mailbox, verifies stored content, and exercises a folder move.
  3. Reads connection details from environment variables
     (`TEST_IMAP_HOST`/`TEST_IMAP_PORT`/`TEST_IMAP_USERNAME`/`TEST_EMAIL_PASSWORD`/
     `TEST_SMTP_HOST`/`TEST_SMTP_PORT`), matching the testing-imap repo's convention, so
     the exact same environment variable names configure both.
* `.github/workflows/unittest.yml` gets a `greenmail` entry under `services:` (image
  `greenmail/standalone:2.1.11`, same `GREENMAIL_OPTS`/ports as the testing-imap repo)
  and the matching env vars, so `tests/test_imap_service_integration.py` runs on every
  push/PR alongside the rest of the unit test suite. Mocked tests keep running on all
  three OSes/Python versions in the existing matrix; the GreenMail-backed integration
  test only needs to run once (GitHub Actions service containers are Linux-only), so it
  runs as an additional step gated to the `ubuntu-latest` job.

## Documentation

* `docs/source/developer.md` — add an "IMAP" section parallel to the existing Python
  Interface section, showing `Imap(...)` construction and noting it shares the exact
  same `update_database`/`get_all_emails_in_database`/`filter_messages_from_server` API
  as `Gmail`.
* `docs/source/architecture.md` — update "the source of truth" bullet to mention IMAP as
  an alternative to the Gmail API, and note that IMAP folders play the role Gmail labels
  play elsewhere in the document.
* `README.md` — mention IMAP support alongside the existing Gmail description, if it
  currently states Gmail-only.

## Non-goals / known limitations carried into v1

* No OAuth2/XOAUTH2 (Outlook, Gmail-via-IMAP) — plain `LOGIN` only.
* No custom IMAP `SEARCH` query support.
* A message's database identity changes when it's moved between folders (old id is
  marked deleted, a new id is created at the destination) — this is a direct, accepted
  consequence of IMAP's per-mailbox UID model, not a bug to fix here.
* Webapp and daemon remain Gmail-only.
