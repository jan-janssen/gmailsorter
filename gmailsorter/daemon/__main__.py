import argparse
import os
from gmailsorter.daemon.daemon import update
from gmailsorter.daemon.shared import get_database_engine, load_config_file


def command_line_parser():
    """
    Main function primarily used for the command line interface
    """
    parser = argparse.ArgumentParser(prog="gmailsortdaemon")
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
        "-f",
        "--filter",
        action="store_true",
        help="Filter emails using machine learning.",
    )
    parser.add_argument(
        "-u",
        "--update",
        action="store_true",
        help="Update local database and retrain machine learning model.",
    )
    parser.add_argument(
        "-s",
        "--scheduled",
        action="store_true",
        help="Filter emails using machine learning and initialize empty databases.",
    )
    args = parser.parse_args()
    if args.credentials:
        client_secrets_config = load_config_file(file_name=args.credentials)
    elif "credentials.json" in os.listdir("."):
        client_secrets_config = load_config_file(
            file_name=os.path.abspath("credentials.json")
        )
    else:
        raise ValueError("Cannot find Google API credentials file: credentials.json .")
    if args.database:
        engine = get_database_engine(connection_str=args.database)
    elif "email.db" in os.listdir("."):
        engine = get_database_engine(connection_str="sqlite:///email.db")
    else:
        raise ValueError(
            "Provide a connection string to connect to the database e.g. sqlite:///email.db ."
        )
    if args.update or args.filter or args.scheduled:
        if args.update and args.filter:
            mode = "all"
        elif args.update:
            mode = "update"
        elif args.scheduled:
            mode = "select"
        elif args.filter:
            mode = "fetch"
        else:
            raise ValueError("Mode of execution undefined.")
        update(
            engine=engine,
            client_secrets_config=client_secrets_config,
            mode=mode,
            n_estimators=100,
            max_features=400,
            random_state=42,
            bootstrap=True,
            include_deleted=False,
            recommendation_ratio=0.9,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    command_line_parser()
