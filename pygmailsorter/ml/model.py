import pandas
import numpy as np
from tqdm import tqdm
from sklearn.ensemble import RandomForestClassifier


def fit_machine_learning_models(
    df_all_features,
    df_all_labels,
    n_estimators=100,
    max_features=400,
    random_state=42,
    bootstrap=True,
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

    Returns:
        dict: dictionary with machine learning models with labels as keys
    """
    df_training = df_all_features.drop(["email_id"], axis=1)
    return {
        to_learn.split("labels_")[-1]: RandomForestClassifier(
            n_estimators=n_estimators,
            random_state=random_state,
            bootstrap=bootstrap,
            max_features=max_features,
        ).fit(df_training, df_all_labels[to_learn])
        for to_learn in tqdm(
            iterable=df_all_labels.columns.tolist(), desc="Train machinelearning models"
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
