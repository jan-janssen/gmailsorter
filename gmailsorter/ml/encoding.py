from typing import Any

import numpy as np
import pandas
from scipy import sparse
from sklearn.preprocessing import MultiLabelBinarizer


def encode_df_for_machine_learning(
    df: pandas.DataFrame,
    feature_lst: list[str] | np.ndarray | None = None,
    label_lst: list[str] | np.ndarray | None = None,
    return_labels: bool = False,
    label_prefix: str = "labels_",
) -> pandas.DataFrame | tuple[pandas.DataFrame, pandas.DataFrame]:
    """
    Encode a given dataframe for machine learning. Either based on a list of existing features and labels or by
    generating the features and labels from the dataframe. By default, only the dataframe with features is returned
    optionally also the dataframe with labels can be returned.

    Args:
        df (pandas.DataFrame): DataFrame with emails
        feature_lst (list): list of features to encode, if no list is provided the features are generated from the
                            Dataframe
        label_lst (list): list of labels to encode, if no list is provided the labels are generated from the Dataframe
        return_labels (boolean): optional flag to return the dataframe with labels

    Returns:
        pandas.DataFrame/ list: Dataframe with features and optionally also the dataframe with labels
    """
    if feature_lst is None:
        feature_lst = []
    if label_lst is None:
        label_lst = []
    if isinstance(feature_lst, np.ndarray):
        feature_lst = feature_lst.tolist()
    if isinstance(label_lst, np.ndarray):
        label_lst = label_lst.tolist()
    combined_lst = [
        feature for feature in feature_lst + label_lst if feature != "email_id"
    ]
    df_all_encode = one_hot_encoding(df=df, feature_lst=combined_lst)
    if len(feature_lst) == 0:
        feature_lst = [
            feature
            for feature in df_all_encode.columns.values
            if "labels_" not in feature
        ]
    feature_lst += ["email_id"]
    df_all_features = df_all_encode[feature_lst]
    if not return_labels:
        return df_all_features
    else:
        if len(label_lst) == 0:
            label_lst = [
                label for label in df_all_encode.columns.values if label_prefix in label
            ]
        return df_all_features, df_all_encode[label_lst]


def one_hot_encoding(
    df: pandas.DataFrame, feature_lst: list[str] | None = None
) -> pandas.DataFrame:
    """
    Sparse binary one hot encoding of features in a pandas DataFrame.

    Note: the email thread is deliberately not one-hot encoded. Thread IDs are close to unique per email, so
    encoding them turns into a near-identity column that lets a random forest memorize training threads instead
    of generalizing - expensive in memory and harmful to accuracy on emails from new threads.

    Args:
        df (pandas.DataFrame): DataFrame with emails
        feature_lst (list): list of features to encode

    Returns:
        pandas.DataFrame: sparse hot encoding of features in a pandas DataFrame
    """
    if feature_lst is None:
        feature_lst = []
    all_binary_sparse, all_labels = _encoding_helper(df=df)
    if len(feature_lst) == 0:
        df_new = pandas.DataFrame.sparse.from_spmatrix(
            all_binary_sparse, columns=all_labels
        )
    else:
        labels_to_drop = [label for label in all_labels if label not in feature_lst]
        labels_to_add = [label for label in feature_lst if label not in all_labels]
        if len(labels_to_add) > 0:
            pad_sparse = sparse.csr_matrix(
                (len(df), len(labels_to_add)), dtype=np.uint8
            )
            data_stack = sparse.hstack(
                [all_binary_sparse, pad_sparse], format="csr", dtype=np.uint8
            )
        else:
            data_stack = all_binary_sparse
        columns = np.array(all_labels + labels_to_add)
        df_new = pandas.DataFrame.sparse.from_spmatrix(data_stack, columns=columns)
        df_new.drop(labels_to_drop, inplace=True, axis=1)
    df_new["email_id"] = df.id.values
    return df_new.sort_index(axis=1)


# Helper functions for one hot encoding
def _encoding_helper(df: pandas.DataFrame) -> tuple[sparse.csr_matrix, list[str]]:
    labels_red_lst = _build_red_lst(df_column=df.labels.values)
    cc_red_lst = _build_red_lst(df_column=df.cc.values)
    to_red_lst = _build_red_lst(df_column=df.to.values)
    from_red_lst = [email for email in df["from"].unique() if email is not None] + list(
        {
            "@" + email.split("@")[-1]
            for email in df["from"].unique()
            if email is not None and isinstance(email, str) and "@" in email
        }
    )
    labels_sp = _encode_multi_label(
        value_lst=df["labels"].values, red_lst=labels_red_lst, expand_domains=False
    )
    cc_sp = _encode_multi_label(
        value_lst=df["cc"].values, red_lst=cc_red_lst, expand_domains=True
    )
    from_sp = _encode_multi_label(
        value_lst=[[v] if isinstance(v, str) else [] for v in df["from"].values],
        red_lst=from_red_lst,
        expand_domains=True,
    )
    to_sp = _encode_multi_label(
        value_lst=df["to"].values, red_lst=to_red_lst, expand_domains=True
    )
    all_binary_sparse = sparse.hstack(
        [labels_sp, cc_sp, from_sp, to_sp], format="csr", dtype=np.uint8
    )
    all_labels = (
        _get_lst_without_none(lst=labels_red_lst, column="labels")
        + _get_lst_without_none(lst=cc_red_lst, column="cc")
        + _get_lst_without_none(lst=from_red_lst, column="from")
        + _get_lst_without_none(lst=to_red_lst, column="to")
    )
    return all_binary_sparse, all_labels


def _build_red_lst(df_column: np.ndarray) -> list[str]:
    collect_lst = []
    for lst in df_column:
        for entry in lst:
            collect_lst.append(entry)

        # For email addresses add an additional column with the domain
        for entry in lst:
            if "@" in entry:
                collect_lst.append("@" + entry.split("@")[-1])
    return list(set(collect_lst))


def _get_lst_without_none(lst: list[Any], column: str) -> list[str]:
    return [
        column + "_" + entry
        for entry in lst
        if entry is not None and isinstance(entry, str)
    ]


def _encode_multi_label(
    value_lst: np.ndarray, red_lst: list[str], expand_domains: bool
) -> sparse.csr_matrix:
    """
    Vectorized replacement for the previous per-cell python-loop one hot encoding. Builds a sparse binary
    indicator matrix of shape (len(value_lst), len(red_lst)) marking which of the vocabulary entries in red_lst
    are present in each row - optionally also matching an address' domain (e.g. "@example.com") against the
    corresponding domain vocabulary entry, mirroring the previous substring-matching behaviour.

    Args:
        value_lst (np.ndarray): per row list of raw string entries (e.g. cc addresses, label names)
        red_lst (list): vocabulary of columns to encode, as produced by _build_red_lst
        expand_domains (boolean): also match each entry's "@domain" fragment against the vocabulary

    Returns:
        scipy.sparse.csr_matrix: sparse binary indicator matrix
    """
    if len(red_lst) == 0:
        return sparse.csr_matrix((len(value_lst), 0), dtype=np.uint8)
    if expand_domains:
        rows = [_expand_with_domains(entries=entries) for entries in value_lst]
    else:
        rows = list(value_lst)
    binarizer = MultiLabelBinarizer(classes=red_lst, sparse_output=True)
    return binarizer.fit_transform(rows).astype(np.uint8)


def _expand_with_domains(entries: list[str]) -> list[str]:
    expanded = list(entries)
    for entry in entries:
        if isinstance(entry, str) and "@" in entry:
            expanded.append("@" + entry.split("@")[-1])
    return expanded
