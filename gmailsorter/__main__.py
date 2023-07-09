import argparse
import os
from gmailsorter import Gmail, load_client_secrets_file


def command_line_parser():
    """
    Main function primarily used for the command line interface
    """
    credentials, database = None, None
    parser = argparse.ArgumentParser(prog="gmailsorter")
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
        "-i",
        "--identification",
        help="User ID of the database user e.g. 1 .",
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
    if args.identification:
        db_user_id = int(args.identification)
    else:
        db_user_id = 1
    if args.credentials:
        credentials = args.credentials
    elif "credentials.json" in os.listdir("."):
        credentials = os.path.abspath("credentials.json")
    else:
        print("Please provide a credentials file, -c/--credentials credentials.json")
    if credentials:
        if args.database:
            database = args.database
        else:
            database = "sqlite:///email.db"
        gmail = Gmail(
            client_config=load_client_secrets_file(client_secrets_file=credentials),
            connection_str=database,
            user_id="me",
            db_user_id=db_user_id,
            port=port,
            email_download_format="metadata",
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
            gmail.filter_messages_from_server(
                label=args.label, recommendation_ratio=0.9
            )
        else:
            parser.print_help()


if __name__ == "__main__":
    command_line_parser()
