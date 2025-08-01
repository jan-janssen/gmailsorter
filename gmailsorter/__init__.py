try:
    from importlib.metadata import version
except ImportError:
    from importlib_metadata import version

__version__ = version("gmailsorter")

from gmailsorter.local import Gmail, load_client_secrets_file
