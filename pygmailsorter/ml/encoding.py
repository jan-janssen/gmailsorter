import pandas
import numpy as np


def one_hot_encoding(df, feature_lst=[]):
    """
    Binary one hot encoding of features in a pandas DataFrame

    Args:
        df (pandas.DataFrame): DataFrame with emails
        feature_lst (list): list of features to encode

    Returns:
        pandas.DataFrame: hot encoding of features in a pandas DataFrame
    """
    labels_red_lst = _build_red_lst(df_column=df.labels.values)
    cc_red_lst = _build_red_lst(df_column=df.cc.values)
    thread_red_lst = df["threads"].unique()
    to_red_lst = _build_red_lst(df_column=df.to.values)
    from_red_lst = [email for email in df["from"].unique() if email is not None] + list(
        set(
            [
                "@" + email.split("@")[-1]
                for email in df["from"].unique()
                if email is not None and "@" in email
            ]
        )
    )
    dict_labels_lst = _list_entry_df(
        red_lst=labels_red_lst, value_lst=df["labels"].values
    )
    dict_cc_lst = _list_entry_email_df(red_lst=cc_red_lst, value_lst=df["cc"].values)
    dict_from_lst = _single_entry_email_df(
        red_lst=from_red_lst, value_lst=df["from"].values
    )
    dict_threads_lst = _single_entry_df(
        red_lst=thread_red_lst, value_lst=df["threads"].values
    )
    dict_to_lst = _list_entry_email_df(red_lst=to_red_lst, value_lst=df["to"].values)
    all_binary_values = np.hstack(
        (dict_labels_lst, dict_cc_lst, dict_from_lst, dict_threads_lst, dict_to_lst)
    )
    all_labels = (
        _get_lst_without_none(lst=labels_red_lst, column="labels")
        + _get_lst_without_none(lst=cc_red_lst, column="cc")
        + _get_lst_without_none(lst=from_red_lst, column="from")
        + _get_lst_without_none(lst=thread_red_lst, column="threads")
        + _get_lst_without_none(lst=to_red_lst, column="to")
    )
    if len(feature_lst) == 0:
        df_new = pandas.DataFrame(all_binary_values, columns=all_labels)
    else:
        labels_to_drop = [label for label in all_labels if label not in feature_lst]
        labels_to_add = [label for label in feature_lst if label not in all_labels]
        data_stack = np.hstack(
            (all_binary_values, np.zeros((len(df), len(labels_to_add))))
        )
        columns = np.array(all_labels + labels_to_add)
        df_new = pandas.DataFrame(
            data_stack,
            columns=columns,
        )
        df_new.drop(labels_to_drop, inplace=True, axis=1)
    df_new["email_id"] = df.id.values
    return df_new.sort_index(axis=1)


# Helper functions for one hot encoding
def _build_red_lst(df_column):
    collect_lst = []
    for lst in df_column:
        for entry in lst:
            collect_lst.append(entry)

        # For email addresses add an additional column with the domain
        for entry in lst:
            if "@" in entry:
                collect_lst.append("@" + entry.split("@")[-1])
    return list(set(collect_lst))


def _get_lst_without_none(lst, column):
    return [column + "_" + entry for entry in lst if entry is not None]


def _single_entry_df(red_lst, value_lst):
    return np.array(
        [
            [
                1 if email == red_entry else 0
                for red_entry in red_lst
                if red_entry is not None
            ]
            for email in value_lst
        ]
    ).astype("float64")


def _single_entry_email_df(red_lst, value_lst):
    return np.array(
        [
            [
                1 if email is not None and red_entry in email else 0
                for red_entry in red_lst
                if red_entry is not None
            ]
            for email in value_lst
        ]
    ).astype("float64")


def _list_entry_df(red_lst, value_lst):
    return np.array(
        [
            [1 if red_entry in email else 0 for red_entry in red_lst]
            for email in value_lst
        ]
    ).astype("float64")


def _list_entry_email_df(red_lst, value_lst):
    return np.array(
        [
            [1 if any([red_entry in e for e in email]) else 0 for red_entry in red_lst]
            for email in value_lst
        ]
    ).astype("float64")
