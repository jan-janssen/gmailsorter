import argparse
from pygmailsorter.interface import Gmail


def command_line_parser():
    """
    Main function primarly used for the command line interface
    """
    parser = argparse.ArgumentParser(prog="pygmailsorter")
    parser.add_argument(
        "-d",
        "--database",
        action="store_true",
        help="Update local database.",
    )
    parser.add_argument(
        "-c",
        "--config",
        help="Configuration Folder e.g. ~/.pygmailsorter",
    )
    parser.add_argument(
        "-m",
        "--machinelearning",
        help="Email label to be filtered with machine learning.",
    )
    parser.add_argument(
        "-n",
        "--gmailfilterlabel",
        help="Email label to be filtered with machine learning from Gmail.",
    )
    args = parser.parse_args()
    if args.config:
        gmail = Gmail(config_folder=args.config)
    else:
        gmail = Gmail()
    if args.database:
        gmail.update_database(quick=False)
    elif args.machinelearning:
        gmail.update_database(quick=True, label_lst=[args.machinelearning])
        gmail.filter_label_by_machine_learning(
            label=args.machinelearning, recalculate=True
        )
    elif args.gmailfilterlabel:
        gmail.update_database(quick=True, label_lst=[args.gmailfilterlabel])
        gmail.filter_only_new_messages(label=args.gmailfilterlabel, recalculate=True)
    else:
        parser.print_help()


if __name__ == "__main__":
    command_line_parser()
