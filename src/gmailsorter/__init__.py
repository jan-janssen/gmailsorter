from gmailsorter.local import Gmail, load_client_secrets_file

from . import _version

__version__: str = _version.__version__
__all__ = ["Gmail", "load_client_secrets_file"]
