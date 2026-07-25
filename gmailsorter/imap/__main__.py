import argparse
import os

from gmailsorter import Imap


def command_line_parser():
    """
    Main function primarily used for the command line interface of the IMAP backend
    """
    parser = argparse.ArgumentParser(prog="gmailsorter-imap")
    parser.add_argument(
        "--host",
        help="IMAP server hostname e.g. imap.example.com .",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=993,
        help="IMAP server port - default: 993 .",
    )
    parser.add_argument(
        "--username",
        help="IMAP account username.",
    )
    parser.add_argument(
        "--password-env",
        default="IMAP_PASSWORD",
        help=(
            "Name of the environment variable holding the IMAP account password - "
            "default: IMAP_PASSWORD ."
        ),
    )
    parser.add_argument(
        "--no-ssl",
        action="store_true",
        help="Connect without SSL (IMAP4 instead of IMAP4_SSL).",
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
        "-i",
        "--identification",
        help="User ID of the database user e.g. 1 .",
    )
    parser.add_argument(
        "-l",
        "--label",
        help="Email label (IMAP folder) to be filtered with machine learning.",
    )
    args = parser.parse_args()
    db_user_id = int(args.identification) if args.identification else 1
    password = os.environ.get(args.password_env)
    if not args.host or not args.username:
        print("Please provide --host and --username.")
    elif not password:
        print(
            f"Please set the {args.password_env} environment variable to your IMAP password."
        )
    else:
        database = args.database or "sqlite:///email.db"
        imap = Imap(
            host=args.host,
            port=args.port,
            username=args.username,
            password=password,
            connection_str=database,
            db_user_id=db_user_id,
            use_ssl=not args.no_ssl,
            email_download_format="metadata",
        )
        if args.update:
            imap.update_database(quick=False)
            imap.fit_machine_learning_model_to_database(
                n_estimators=100,
                max_features=400,
                random_state=42,
                bootstrap=True,
                include_deleted=False,
            )
        elif args.label:
            imap.filter_messages_from_server(label=args.label, recommendation_ratio=0.9)
        else:
            parser.print_help()


if __name__ == "__main__":
    command_line_parser()
