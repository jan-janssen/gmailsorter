import os
from gmailsorter.daemon import load_config_file, get_database_engine

# Get environment
environment = os.environ

# Configuration
if "MAILSORT_ENV_CREDENTIALS_FILE" in environment:
    CLIENT_SECRETS_CONFIG = load_config_file(
        file_name=environment["MAILSORT_ENV_CREDENTIALS_FILE"]
    )
else:
    CLIENT_SECRETS_CONFIG = load_config_file(file_name="credentials.json")

# Database connection
if "MAILSORT_ENV_DATABASE_URL" in environment:
    ENGINE = get_database_engine(
        connection_str=environment["MAILSORT_ENV_DATABASE_URL"]
    )
else:
    ENGINE = get_database_engine(connection_str="sqlite:///email.db")

# Secret key for cookie
if "MAILSORT_ENV_SECRET_KEY" in environment:
    SECRET_KEY = environment["MAILSORT_ENV_SECRET_KEY"]
else:
    raise ValueError("The MAILSORT_ENV_SECRET_KEY environment variable is not set.")
