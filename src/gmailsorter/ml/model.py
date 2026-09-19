from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas
from sklearn.ensemble import RandomForestClassifier
from tqdm import tqdm


def train_random_forest(
    n_estimators: int,
    random_state: int,
    bootstrap: bool,
    max_features: int,
    X: pandas.DataFrame,
    y: pandas.Series,
) -> RandomForestClassifier:
    """
    Train a random forest classifier

    Args:
        n_estimators (int): number of estimators of the machine learning models
        max_features (int): maximum number of features of the machine learning models
        random_state (int): random state for initialization of the machine learning models
        bootstrap (boolean): bootstrap of the machine learning models
        X (pandas.DataFrame): binary encoded features stored in a pandas dataframe
        y (pandas.Series): boolean encoded label

    Return:
        RandomForestClassifier: trained model
    """
    return RandomForestClassifier(
        n_estimators=n_estimators,
        random_state=random_state,
        bootstrap=bootstrap,
        max_features=max_features,
    ).fit(X=X, y=y)


def fit_machine_learning_models(
    df_all_features: pandas.DataFrame,
    df_all_labels: pandas.DataFrame,
    n_estimators: int = 100,
    max_features: int = 400,
    random_state: int = 42,
    bootstrap: bool = True,
    max_workers: int | None = None,
) -> dict[str, RandomForestClassifier]:
    """
    Train machine learning models

    Args:
        df_all_features (pandas.DataFrame): binary encoded features stored in a pandas dataframe
        df_all_labels (pandas.DataFrame): binary encoded labels stored in a pandas dataframe
        n_estimators (int): number of estimators of the machine learning models
        max_features (int): maximum number of features of the machine learning models
        random_state (int): random state for initialization of the machine learning models
        bootstrap (boolean): bootstrap of the machine learning models
        max_workers (int): maximum number of workers for the machine learning models

    Returns:
        dict: dictionary with machine learning models with labels as keys
    """
    df_training = df_all_features.drop(["email_id"], axis=1)
    if max_workers == 1:
        return {
            to_learn.split("labels_")[-1]: train_random_forest(
                n_estimators=n_estimators,
                random_state=random_state,
                bootstrap=bootstrap,
                max_features=max_features,
                X=df_training,
                y=df_all_labels[to_learn],
            )
            for to_learn in tqdm(
                iterable=df_all_labels.columns.tolist(),
                desc="Train machinelearning models",
            )
        }
    else:
        with ProcessPoolExecutor(max_workers=max_workers) as exe:
            futures_dict = {
                to_learn.split("labels_")[-1]: exe.submit(
                    train_random_forest,
                    n_estimators=n_estimators,
                    random_state=random_state,
                    bootstrap=bootstrap,
                    max_features=max_features,
                    X=df_training,
                    y=df_all_labels[to_learn],
                )
                for to_learn in df_all_labels.columns.tolist()
            }
            return {
                k: v.result()
                for k, v in tqdm(
                    iterable=futures_dict.items(), desc="Train machinelearning models"
                )
            }


def get_predictions_from_machine_learning_models(
    df_features: pandas.DataFrame,
    model_dict: dict[str, RandomForestClassifier],
    recommendation_ratio: float = 0.9,
) -> dict[str, str | None]:
    """
    Get recommendations from machine learning models

    Args:
        df_features (pandas.DataFrame): binary encoded features stored in a pandas dataframe
        model_dict (dict): dictionary with machine learning models with labels as keys
        recommendation_ratio (float): recommendation cutoff ratio

    Returns:
        dict: email id as keys and the corresponding newly assigned label as value
    """
    df_predict = df_features.drop(["email_id"], axis=1)
    predictions = {k: v.predict(df_predict) for k, v in model_dict.items()}
    label_lst = list(predictions.keys())
    prediction_array = np.array(list(predictions.values())).T
    argmax_indices = np.argmax(prediction_array, axis=1)
    max_values = prediction_array[np.arange(len(prediction_array)), argmax_indices]
    new_label_lst = [
        label_lst[idx] if max_val > recommendation_ratio else None
        for idx, max_val in zip(argmax_indices, max_values, strict=False)
    ]
    return dict(zip(df_features.email_id.values, new_label_lst, strict=False))
