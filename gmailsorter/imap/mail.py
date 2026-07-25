import email
import re

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gmailsorter.base import get_email_database
from gmailsorter.base.mail import AbstractMailBox
from gmailsorter.imap.message import get_email_dict
from gmailsorter.ml import get_machine_learning_database

_LIST_ENTRY_PATTERN = re.compile(
    r'\((?P<flags>[^)]*)\)\s+(?:"(?P<delimiter>[^"]*)"|NIL)\s*(?P<name>.*)'
)

# Folder attributes which mark a folder as not usable as a sorting target: \Noselect
# (RFC 3501) plus the special-use attributes of RFC 6154. Without this the machine
# learning model can be trained on - and therefore recommend moving mail into -
# Trash, Spam, Sent or Drafts.
_SKIP_FOLDER_ATTRIBUTES = frozenset(
    {
        "\\noselect",
        "\\all",
        "\\archive",
        "\\drafts",
        "\\flagged",
        "\\junk",
        "\\sent",
        "\\trash",
    }
)

# Many servers (GreenMail among them) do not advertise the RFC 6154 special-use
# attributes at all, so a deliberately short list of unambiguous special folder names
# is used as a fallback. Only exact (case-insensitive) matches are excluded, so a
# custom sorting folder such as "Sorted" or "MailSortInbox" is unaffected.
_SKIP_FOLDER_NAMES = frozenset(
    {
        "all mail",
        "archive",
        "deleted items",
        "deleted messages",
        "drafts",
        "junk",
        "junk e-mail",
        "junk email",
        "sent",
        "sent items",
        "sent messages",
        "spam",
        "trash",
    }
)


def _decode_imap_bytes(value):
    """
    Decode a bytes/str fragment of an IMAP response, returning None for anything else.

    Mailbox names are usually pure ASCII (modified UTF-7), but servers may send raw
    UTF-8 literals - latin-1 is used as a lossless fallback so that a surprising
    encoding never raises out of the LIST parser.
    """
    if isinstance(value, str):
        return value
    if not isinstance(value, bytes):
        return None
    try:
        return value.decode()
    except UnicodeDecodeError:
        return value.decode("latin-1")


class ImapMailBase(AbstractMailBox):
    def _get_label_translate_dict(self):
        status, mailbox_lst = self._service.list()
        if status != "OK" or not mailbox_lst:
            return {}
        label_dict = {}
        for entry in mailbox_lst:
            parsed_entry = self._parse_list_entry(entry)
            if parsed_entry is None:
                continue
            flags, delimiter, name = parsed_entry
            if self._is_special_folder(flags=flags, delimiter=delimiter, name=name):
                continue
            label_dict[name] = name
        return label_dict

    @staticmethod
    def _is_special_folder(flags, delimiter, name):
        """
        Check whether an IMAP folder is a special-purpose folder rather than a folder
        emails may be sorted into.

        Args:
            flags (list): folder attributes from the LIST response
            delimiter (str/None): hierarchy delimiter from the LIST response
            name (str): full folder name

        Returns:
            bool: True if the folder must not be offered as a sorting label
        """
        if any(flag.lower() in _SKIP_FOLDER_ATTRIBUTES for flag in flags):
            return True
        name_lst = [name.strip().lower()]
        if delimiter:
            # also check the leaf of a nested name such as "[Gmail]/Trash"
            name_lst.append(name.rsplit(delimiter, 1)[-1].strip().lower())
        return any(candidate in _SKIP_FOLDER_NAMES for candidate in name_lst)

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
        Fetch the raw message for a composite "{folder}\\x1f{uid}" id.

        BODY.PEEK[] is used rather than RFC822/BODY[] because the latter implicitly
        set the \\Seen flag (RFC 3501), which would mark the whole mailbox as read
        on every update_database() run.

        Returns:
            tuple: (folder, uid, email.message.Message)
        """
        folder, uid = message_id.split("\x1f", 1)
        status, _ = self._service.select(f'"{folder}"')
        if status != "OK":
            raise RuntimeError(f"Could not select IMAP folder {folder!r}")
        status, data = self._service.uid("fetch", uid, "(BODY.PEEK[])")
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
        """
        Parse a single entry of an IMAP LIST response.

        Handles the plain bytes/str form, the ``(header, literal_name)`` tuple form
        imaplib returns when the server encodes the mailbox name as an IMAP literal,
        and the unquoted ``NIL`` hierarchy delimiter which is legal per RFC 3501 for
        servers without a folder hierarchy.

        Args:
            entry (bytes/str/tuple/None): one element of ``imaplib.IMAP4.list()`` data

        Returns:
            tuple/None: (flags, delimiter, name) or None if the entry is unparseable.
                        Unparseable entries are skipped rather than raised on, because
                        this runs from ``AbstractMailBox.__init__``.
        """
        literal_name = None
        if isinstance(entry, tuple):
            try:
                entry, literal_name = entry[0], _decode_imap_bytes(entry[1])
            except IndexError:
                return None
            if literal_name is None:
                return None
        decoded = _decode_imap_bytes(entry)
        if decoded is None:
            return None
        match = _LIST_ENTRY_PATTERN.match(decoded)
        if match is None:
            return None
        flags = match.group("flags").split()
        delimiter = match.group("delimiter")
        if literal_name is not None:
            name = literal_name
        else:
            name = match.group("name").strip().strip('"')
        if not name:
            return None
        return flags, delimiter, name

    @staticmethod
    def _create_databases(connection_str):
        engine = create_engine(connection_str)
        session = sessionmaker(bind=engine)()
        db_email = get_email_database(engine=engine, session=session)
        db_ml = get_machine_learning_database(engine=engine, session=session)
        return db_email, db_ml
