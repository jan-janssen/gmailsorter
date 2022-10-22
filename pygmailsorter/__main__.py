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
        help="Configuration Folder e.g. ~/.pygmailsorter",
    )
    parser.add_argument(
        "-d",
        "--database",
        action="store_true",
        help="Update local database.",
    )
    parser.add_argument(
        "-l",
        "--label",
        help="Email label to be filtered with machine learning",
    )
    parser.add_argument(
        "-m",
        "--machinelearning",
        action="store_true",
        help="Train machine learning models. (requires -l/ --label)",
    )
    parser.add_argument(
        "-p",
        "--prediction",
        action="store_true",
        help="Sort emails based on prediction of machine learning models. (requires -l/ --label)",
    )
    args = parser.parse_args()
    if args.config:
        gmail = Gmail(config_folder=args.config)
    else:
        gmail = Gmail()
    if args.database:
        gmail.update_database(quick=False)
    if args.label:
        if args.machinelearning:
            _ = gmail.train_machine_learning_models(label=args.label, recalculate=True)
        elif args.prediction:
            gmail.filter_only_new_messages(label=args.label, recalculate=False)
        else:
            parser.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    command_line_parser()
