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
