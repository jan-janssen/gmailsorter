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
