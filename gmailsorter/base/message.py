from abc import ABC, abstractmethod
from datetime import datetime

_MAX_DATE_COMMAS = 2
_DATE_HYPHEN_COUNT = 2


def email_date_converter(email_date):
    if not isinstance(email_date, str):
        return None
    if email_date[:1] == "\xa0":
        email_date = email_date.replace("\xa0", "")
    if email_date.count(",") >= _MAX_DATE_COMMAS:
        email_date = ", ".join(email_date.split(", ")[-2:])
    if email_date[-3:-2].isalpha():
        email_date = " ".join(email_date.split()[:-1])
    if email_date[-1].isalpha():
        email_date = email_date[:-1]
    if email_date[:3].isalpha() and email_date[-3] != ":" and email_date[-6] == "_":
        email_date, date_format = email_date.split(".")[0], "%a, %d %b %Y %H:%M:%S %z"
    elif email_date[:3].isalpha() and email_date[-3] != ":" and "(" in email_date:
        email_date, date_format = (
            email_date.split(" (")[0],
            "%a, %d %b %Y %H:%M:%S %z",
        )
    elif email_date[:3].isalpha() and email_date[-3] != ":":
        date_format = "%a, %d %b %Y %H:%M:%S %z"
    elif email_date[-3] == ":":
        date_format = "%a, %d %b %Y %H:%M:%S"
    elif email_date.count("-") == _DATE_HYPHEN_COUNT:
        date_format = "%d-%m-%Y"
    else:
        date_format = "%d %b %Y %H:%M:%S %z"
    return datetime.strptime(email_date, date_format)


class AbstractMessage(ABC):
    def __init__(self, message_dict):
        self._message_dict = message_dict

    @abstractmethod
    def get_from(self):
        pass

    @abstractmethod
    def get_to(self):
        pass

    @abstractmethod
    def get_cc(self):
        pass

    @abstractmethod
    def get_label_ids(self):
        pass

    @abstractmethod
    def get_subject(self):
        pass

    @abstractmethod
    def get_date(self):
        pass

    @abstractmethod
    def get_content(self):
        pass

    @abstractmethod
    def get_thread_id(self):
        pass

    @abstractmethod
    def get_email_id(self):
        pass

    def to_dict(self):
        return {
            "id": self.get_email_id(),
            "threads": self.get_thread_id(),
            "labels": self.get_label_ids(),
            "to": self.get_to(),
            "from": self.get_from(),
            "cc": self.get_cc(),
            "subject": self.get_subject(),
            "content": self.get_content(),
            "date": self.get_date(),
        }
