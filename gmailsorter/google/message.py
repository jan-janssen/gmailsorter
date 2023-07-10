import base64
from html.parser import HTMLParser
from io import StringIO
from gmailsorter.base.message import AbstractMessage, email_date_converter


# https://stackoverflow.com/questions/753052/strip-html-from-strings-in-python
class MLStripper(HTMLParser):
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


def get_email_dict(message):
    try:
        return Message(message_dict=message).to_dict()
    except ValueError as e:
        print(message, str(e))
        return None


class Message(AbstractMessage):
    def __init__(self, message_dict):
        self._message_dict = message_dict

    def get_from(self):
        email_lst = self._split_emails(
            email_lst=self.get_header_field_from_message(field="From")
        )
        if len(email_lst) == 1:
            return email_lst[0]
        else:
            return None

    def get_to(self):
        return self._split_emails(
            email_lst=self.get_header_field_from_message(field="To")
        )

    def get_cc(self):
        return self._split_emails(
            email_lst=self.get_header_field_from_message(field="Cc")
        )

    def get_label_ids(self):
        if "labelIds" in self._message_dict.keys():
            return self._message_dict["labelIds"]
        else:
            return []

    def get_subject(self):
        return self.get_header_field_from_message(field="Subject")

    def get_date(self):
        return email_date_converter(
            email_date=self.get_header_field_from_message(field="Date")
        )

    def get_content(self):
        if "parts" in self._message_dict["payload"].keys():
            return self._get_parts_content(
                message_parts=self._message_dict["payload"]["parts"]
            )
        else:
            return self._get_parts_content(
                message_parts=[self._message_dict["payload"]]
            )

    def get_thread_id(self):
        return self._message_dict["threadId"]

    def get_email_id(self):
        return self._message_dict["id"]

    def get_header_field_from_message(self, field):
        lst = [
            entry["value"]
            for entry in self._message_dict["payload"]["headers"]
            if entry["name"] == field
        ]
        if len(lst) > 0:
            return lst[0]
        else:
            return None

    def _get_parts_content(self, message_parts):
        content_types = [p["mimeType"] for p in message_parts if "mimeType" in p.keys()]
        if "text/plain" in content_types:
            return self._get_email_body(
                message_parts=message_parts[content_types.index("text/plain")]
            )
        elif "text/html" in content_types:
            return self._strip_tags(
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

    def _split_emails(self, email_lst):
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
    def _get_email_body(message_parts):
        if "body" in message_parts.keys() and "data" in message_parts["body"].keys():
            return base64.urlsafe_b64decode(
                message_parts["body"]["data"].encode("UTF-8")
            ).decode("UTF-8")
        else:
            return ""

    @staticmethod
    def _strip_tags(html):
        s = MLStripper()
        s.feed(html)
        return s.get_data()

    @staticmethod
    def _get_email_address(email):
        email_split = email.split("<")
        if len(email_split) == 1:
            return email.lower()
        else:
            return email_split[1].split(">")[0].lower()
