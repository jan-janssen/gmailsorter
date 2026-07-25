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
            address for _, address in email.utils.getaddresses([from_header]) if address
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
