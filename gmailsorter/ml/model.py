import numpy as np
import pandas
from sklearn.ensemble import RandomForestClassifier


def train_random_forest(
    n_estimators: int,
    random_state: int,
    bootstrap: bool,
    max_features: int | float | str | None,
    X: pandas.DataFrame,
    y: pandas.DataFrame,
    max_depth: int | None = 20,
    min_samples_leaf: int = 2,
    n_jobs: int | None = None,
) -> RandomForestClassifier:
    """
    Train a single random forest classifier over all labels at once. RandomForestClassifier natively supports a
    2D binary-indicator y (one column per label), so one shared forest can predict every label instead of
    training a separate 100-tree forest per label - this is both far cheaper in memory (one set of trees instead
    of N) and tends to generalize better since correlated labels (e.g. same-domain senders) share split
    structure. bootstrap defaults to sparse-friendly settings and to bounded tree growth to avoid the previous
    unbounded-depth trees overfitting on near-unique columns.

    Args:
        n_estimators (int): number of estimators of the machine learning model
        max_features (int, float, str): maximum number of features considered per split
        random_state (int): random state for initialization of the machine learning model
        bootstrap (boolean): bootstrap of the machine learning model
        X (pandas.DataFrame or scipy.sparse matrix): binary encoded features
        y (pandas.DataFrame): binary encoded labels, one column per label
        max_depth (int): maximum tree depth, bounds memory and reduces overfitting on rare/high-cardinality columns
        min_samples_leaf (int): minimum number of samples required at a leaf node
        n_jobs (int): number of parallel jobs used internally by scikit-learn to build the trees

    Return:
        RandomForestClassifier: trained multi-output model, one column of predictions per label
    """
    return RandomForestClassifier(
        n_estimators=n_estimators,
        random_state=random_state,
        bootstrap=bootstrap,
        max_features=max_features,
        max_depth=max_depth,
        min_samples_leaf=min_samples_leaf,
        class_weight="balanced",
        n_jobs=n_jobs,
    ).fit(X=X, y=y)


def fit_machine_learning_models(
    df_all_features: pandas.DataFrame,
    df_all_labels: pandas.DataFrame,
    n_estimators: int = 100,
    max_features: int | float | str | None = "sqrt",
    random_state: int = 42,
    bootstrap: bool = True,
    max_depth: int | None = 20,
    min_samples_leaf: int = 2,
    max_workers: int | None = None,
) -> tuple[RandomForestClassifier, list[str]]:
    """
    Train a single multi-output machine learning model covering all labels at once.

    Args:
        df_all_features (pandas.DataFrame): binary encoded features stored in a pandas dataframe
        df_all_labels (pandas.DataFrame): binary encoded labels stored in a pandas dataframe
        n_estimators (int): number of estimators of the machine learning model
        max_features (int, float, str): maximum number of features considered per split
        random_state (int): random state for initialization of the machine learning model
        bootstrap (boolean): bootstrap of the machine learning model
        max_depth (int): maximum tree depth
        min_samples_leaf (int): minimum number of samples required at a leaf node
        max_workers (int): maximum number of parallel jobs used internally to build the trees (maps to
                           RandomForestClassifier's n_jobs)

    Returns:
        tuple: the trained model and the ordered list of label columns it predicts
    """
    df_training = df_all_features.drop(["email_id"], axis=1)
    X = _to_sparse_matrix(df=df_training)
    label_lst = df_all_labels.columns.tolist()
    model = train_random_forest(
        n_estimators=n_estimators,
        random_state=random_state,
        bootstrap=bootstrap,
        max_features=max_features,
        max_depth=max_depth,
        min_samples_leaf=min_samples_leaf,
        n_jobs=max_workers,
        X=X,
        y=df_all_labels.to_numpy(),
    )
    return model, label_lst


def get_predictions_from_machine_learning_models(
    df_features: pandas.DataFrame,
    model: RandomForestClassifier,
    label_lst: list[str],
    recommendation_ratio: float = 0.9,
) -> dict[str, str | None]:
    """
    Get recommendations from the machine learning model

    Args:
        df_features (pandas.DataFrame): binary encoded features stored in a pandas dataframe
        model (RandomForestClassifier): multi-output model trained with fit_machine_learning_models()
        label_lst (list): ordered list of label columns the model predicts, as returned by
                          fit_machine_learning_models()
        recommendation_ratio (float): recommendation cutoff ratio

    Returns:
        dict: email id as keys and the corresponding newly assigned label as value
    """
    df_predict = df_features.drop(["email_id"], axis=1)
    X = _to_sparse_matrix(df=df_predict)
    proba_per_label = model.predict_proba(X)
    classes_per_label = model.classes_
    if model.n_outputs_ == 1:
        # scikit-learn squeezes a single-column y back to single-output classification, so classes_/
        # predict_proba() return one array instead of a length-1 list - normalize back to the list form.
        proba_per_label = [proba_per_label]
        classes_per_label = [classes_per_label]
    prob_columns = []
    for classes, proba in zip(classes_per_label, proba_per_label, strict=True):
        classes_lst = list(classes)
        prob_columns.append(
            proba[:, classes_lst.index(1)]
            if 1 in classes_lst
            else np.zeros(proba.shape[0])
        )
    prediction_array = np.array(prob_columns).T
    clean_label_lst = [label.split("labels_")[-1] for label in label_lst]
    argmax_indices = np.argmax(prediction_array, axis=1)
    max_values = prediction_array[np.arange(len(prediction_array)), argmax_indices]
    new_label_lst = [
        clean_label_lst[idx] if max_val > recommendation_ratio else None
        for idx, max_val in zip(argmax_indices, max_values, strict=False)
    ]
    return dict(zip(df_features.email_id.values, new_label_lst, strict=False))


def _to_sparse_matrix(df: pandas.DataFrame):
    """
    Materialize the sparse-dtype feature DataFrame produced by gmailsorter.ml.encoding into a scipy sparse
    matrix right before handing it to scikit-learn, so the memory-heavy dense conversion never happens.
    """
    if hasattr(df, "sparse"):
        return df.sparse.to_coo().tocsr()
    return df.to_numpy()
