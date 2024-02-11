import pandas
import numpy as np
from tqdm import tqdm
from sklearn.ensemble import RandomForestClassifier
from concurrent.futures import ProcessPoolExecutor


def train_random_forest(n_estimators, random_state, bootstrap, max_features, X, y):
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
    df_all_features,
    df_all_labels,
    n_estimators=100,
    max_features=400,
    random_state=42,
    bootstrap=True,
    max_workers=None,
):
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
    df_features, model_dict, recommendation_ratio=0.9
):
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
    new_label_lst = [
        label_lst[email] if np.max(values) > float(recommendation_ratio) else None
        for email, values in zip(
            np.argsort(prediction_array, axis=1)[:, -1], prediction_array
        )
    ]
    return {
        email_id: label
        for email_id, label in zip(df_features.email_id.values, new_label_lst)
    }
