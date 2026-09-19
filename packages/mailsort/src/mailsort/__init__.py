from mailsort.local import Imap, load_client_secrets_file

from . import _version

__version__: str = _version.__version__
__all__ = ["Imap", "load_client_secrets_file"]
