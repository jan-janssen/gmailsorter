import argparse
import os
from pygmailsorter import GmailDatabase, load_client_secrets_file


def command_line_parser():
    """
    Main function primarily used for the command line interface
    """
    credentials, database = None, None
    parser = argparse.ArgumentParser(prog="pygmailsorter")
    parser.add_argument(
        "-c",
        "--credentials",
        help="Path to credentials file provided by Google e.g. credentials.json .",
    )
    parser.add_argument(
        "-d",
        "--database",
        help="Connection string to connect to database e.g. sqlite:///email.db .",
    )
    parser.add_argument(
        "-u",
        "--update",
        action="store_true",
        help="Update local database and retrain machine learning model.",
    )
    parser.add_argument(
        "-p",
        "--port",
        help="Port for authentication webserver to run e.g. 8080 .",
    )
    parser.add_argument(
        "-l",
        "--label",
        help="Email label to be filtered with machine learning.",
    )
    args = parser.parse_args()
    if args.port:
        port = args.port
    else:
        port = 8080
    if args.credentials:
        credentials = args.credentials
    elif "credentials.json" in os.listdir("."):
        credentials = os.path.abspath("credentials.json")
    else:
        print("Please provide a credentials file, -c/--credentials credentials.json")
    if args.database:
        database = args.database
    elif "email.db" in os.listdir("."):
        database = "sqlite:///email.db"
    else:
        print("Please provide a connection string for the SQL database, -d/--database \"sqlite:///email.db\"")
    if credentials and database:
        gmail = GmailDatabase(
            client_config=load_client_secrets_file(
                client_secrets_file=credentials
            ),
            connection_str=database,
            user_id="me",
            db_user_id=1,
            port=port
        )
        if args.update:
            gmail.update_database(quick=False)
            gmail.fit_machine_learning_model_to_database(
                n_estimators=100,
                max_features=400,
                random_state=42,
                bootstrap=True,
                include_deleted=False,
            )
        elif args.label:
            gmail.filter_messages_from_server(label=args.label, recommendation_ratio=0.9)
        else:
            parser.print_help()


if __name__ == "__main__":
    command_line_parser()
