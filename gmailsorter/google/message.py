import base64
from typing import Any

from gmailsorter.base.message import (
    AbstractMessage,
    email_date_converter,
    strip_html_tags,
)


def get_email_dict(message: dict[str, Any]) -> dict[str, Any] | None:
    try:
        return Message(message_dict=message).to_dict()
    except ValueError as e:
        print(message, str(e))
        return None


class Message(AbstractMessage):
    def __init__(self, message_dict: dict[str, Any]) -> None:
        self._message_dict = message_dict

    def get_from(self) -> str | None:
        email_lst = self._split_emails(
            email_lst=self.get_header_field_from_message(field="From")
        )
        if len(email_lst) == 1:
            return email_lst[0]
        else:
            return None

    def get_to(self) -> list[str]:
        return self._split_emails(
            email_lst=self.get_header_field_from_message(field="To")
        )

    def get_cc(self) -> list[str]:
        return self._split_emails(
            email_lst=self.get_header_field_from_message(field="Cc")
        )

    def get_label_ids(self) -> list[str]:
        if "labelIds" in self._message_dict:
            return self._message_dict["labelIds"]
        else:
            return []

    def get_subject(self) -> str | None:
        return self.get_header_field_from_message(field="Subject")

    def get_date(self) -> datetime | None:
        return email_date_converter(
            email_date=self.get_header_field_from_message(field="Date")
        )

    def get_content(self) -> str | None:
        if "parts" in self._message_dict["payload"]:
            return self._get_parts_content(
                message_parts=self._message_dict["payload"]["parts"]
            )
        else:
            return self._get_parts_content(
                message_parts=[self._message_dict["payload"]]
            )

    def get_thread_id(self) -> str:
        return self._message_dict["threadId"]

    def get_email_id(self) -> str:
        return self._message_dict["id"]

    def get_header_field_from_message(self, field: str) -> str | None:
        lst = [
            entry["value"]
            for entry in self._message_dict["payload"]["headers"]
            if entry["name"] == field
        ]
        if len(lst) > 0:
            return lst[0]
        else:
            return None

    def _get_parts_content(self, message_parts: list[dict[str, Any]]) -> str | None:
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

    def _split_emails(self, email_lst: str | None) -> list[str]:
        if email_lst is not None:
            email_split_lst = email_lst.split(", ")
            return [
                self._get_email_address(email=email)
                for email in email_split_lst
                if "@" in email
            ]
        else:
            return []

    @staticmethod
    def _get_email_body(message_parts: dict[str, Any]) -> str:
        if "body" in message_parts and "data" in message_parts["body"]:
            return base64.urlsafe_b64decode(
                message_parts["body"]["data"].encode("UTF-8")
            ).decode("UTF-8")
        else:
            return ""

    @staticmethod
    def _get_email_address(email):
        email_split = email.split("<")
        if len(email_split) == 1:
            return email.lower()
        else:
            return email_split[1].split(">")[0].lower()
