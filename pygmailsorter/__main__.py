import argparse
from pygmailsorter.interface import Gmail


def command_line_parser():
    """
    Main function primarily used for the command line interface
    """
    parser = argparse.ArgumentParser(prog="pygmailsorter")
    parser.add_argument(
        "-c",
        "--config",
        help="Configuration Folder e.g. ~/.pygmailsorter .",
    )
    parser.add_argument(
        "-u",
        "--update",
        action="store_true",
        help="Update local database and retrain machine learning model.",
    )
    parser.add_argument(
        "-l",
        "--label",
        help="Email label to be filtered with machine learning.",
    )
    args = parser.parse_args()
    if args.config:
        gmail = Gmail(config_folder=args.config)
    else:
        gmail = Gmail()
    if args.update:
        gmail.update_database(quick=False)
        gmail.fit_machine_learning_model_to_database(
            n_estimators=100,
            max_features=400,
            random_state=42,
            bootstrap=True,
            include_deleted=False
        )
    elif args.label:
        gmail.filter_messages_from_server(
            label=args.label,
            recommendation_ratio=0.9
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    command_line_parser()
