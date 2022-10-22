import pandas
import pickle
import numpy as np
from tqdm import tqdm
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base
from pygmailsorter.base.database import DatabaseTemplate
from sklearn.ensemble import RandomForestClassifier


Base = declarative_base()


class MachineLearningLabels(Base):
    __tablename__ = "ml_labels"
    id = Column(Integer, primary_key=True)
    label_id = Column(String)
    random_forest = Column(String)
    user_id = Column(Integer)


class MachineLearningFeatures(Base):
    __tablename__ = "ml_features"
    id = Column(Integer, primary_key=True)
    feature = Column(String)
    user_id = Column(Integer)


class MachineLearningDatabase(DatabaseTemplate):
    def store_models(self, model_dict, feature_lst, user_id=1, commit=True):
        """
        Store machine learning models in database

        Args:
            model_dict (dict): dictionary containing the machine learning models
            feature_lst (list): list of features the machine learning models were trained on
            user_id (int): database user id
            commit (boolean): boolean flag to write to the database
        """
        label_stored_lst = self._get_labels(user_id=user_id)
        feature_stored_lst = self.get_features(user_id=user_id)
        model_dict_new = {
            k: v for k, v in model_dict.items() if k not in label_stored_lst
        }
        model_dict_update = {
            k: v for k, v in model_dict.items() if k in label_stored_lst
        }
        model_delete_lst = [
            label for label in label_stored_lst if label not in model_dict.keys()
        ]
        feature_new_lst = [
            feature for feature in feature_lst if feature not in feature_stored_lst
        ]
        feature_remove_lst = [
            feature for feature in feature_stored_lst if feature not in feature_lst
        ]
        if len(model_dict_new) > 0:
            self._session.add_all(
                [
                    MachineLearningLabels(
                        label_id=k, random_forest=pickle.dumps(v), user_id=user_id
                    )
                    for k, v in model_dict_new.items()
                ]
            )
        if len(feature_new_lst) > 0:
            self._session.add_all(
                [
                    MachineLearningFeatures(feature=feature, user_id=user_id)
                    for feature in feature_new_lst
                ]
            )
        if len(model_dict_update) > 0:
            label_obj_lst = (
                self._session.query(MachineLearningLabels)
                .filter(MachineLearningLabels.user_id == user_id)
                .filter(
                    MachineLearningLabels.label_id.in_(list(model_dict_update.keys()))
                )
                .all()
            )
            for label_obj in label_obj_lst:
                label_obj.random_forest = pickle.dumps(
                    model_dict_update[label_obj.label_id]
                )
        if len(model_delete_lst) > 0:
            self._session.query(MachineLearningLabels).filter(
                MachineLearningLabels.user_id == user_id
            ).filter(MachineLearningLabels.label_id.in_(model_delete_lst)).delete()
        if len(feature_remove_lst) > 0:
            self._session.query(MachineLearningFeatures).filter(
                MachineLearningFeatures.user_id == user_id
            ).filter(MachineLearningFeatures.feature.in_(feature_remove_lst)).delete()
        if commit:
            self._session.commit()

    def load_models(self, user_id=1):
        """
        Load models from database

        Args:
            user_id (int): database user id

        Returns:
            dict, list: machine learning model dictionary and feature list
        """
        label_obj_lst = (
            self._session.query(MachineLearningLabels)
            .filter(MachineLearningLabels.user_id == user_id)
            .all()
        )
        feature_lst = self.get_features(user_id=user_id)
        return {
            label_obj.label_id: pickle.loads(label_obj.random_forest)
            for label_obj in label_obj_lst
        }, feature_lst

    def get_models(
        self,
        df,
        user_id=1,
        n_estimators=100,
        max_features=400,
        random_state=42,
        bootstrap=True,
        recalculate=False,
    ):
        """
        Get machine learning models, either from database or by retraining them

        Args:
            df (pandas.DataFrame): binary encoded features stored in a pandas dataframe
            user_id (int): database user id
            n_estimators (int): number of estimators of the machine learning models
            max_features (int): maximum number of features of the machine learning models
            random_state (int): random state for initialization of the machine learning models
            bootstrap (boolean): bootstrap of the machine learning models
            recalculate (boolean): boolean flag to enforce retraining of machine learning models

        Returns:
            dict, list: machine learning model dictionary and feature list
        """
        labels_to_learn = [c for c in df.columns.values if "labels_Label_" in c]
        label_name_lst = [to_learn.split("labels_")[-1] for to_learn in labels_to_learn]
        if not recalculate and sorted(label_name_lst) == sorted(
            self._get_labels(user_id=user_id)
        ):
            return self.load_models(user_id=user_id)
        else:
            return self._train_model(
                df=df,
                labels_to_learn=labels_to_learn,
                user_id=user_id,
                n_estimators=n_estimators,
                max_features=max_features,
                random_state=random_state,
                bootstrap=bootstrap,
            )

    def _get_labels(self, user_id=1):
        return [
            label[0]
            for label in self._session.query(MachineLearningLabels.label_id)
            .filter(MachineLearningLabels.user_id == user_id)
            .all()
        ]

    def get_features(self, user_id=1):
        return [
            feature_obj.feature
            for feature_obj in (
                self._session.query(MachineLearningFeatures)
                .filter(MachineLearningFeatures.user_id == user_id)
                .all()
            )
        ]

    def _train_model(
        self,
        df,
        labels_to_learn=None,
        user_id=1,
        n_estimators=100,
        max_features=400,
        random_state=42,
        bootstrap=True,
    ):
        model_dict = train_model(
            df=df,
            labels_to_learn=labels_to_learn,
            n_estimators=n_estimators,
            max_features=max_features,
            random_state=random_state,
            bootstrap=bootstrap,
        )
        feature_lst = df.columns.values
        self.store_models(
            model_dict=model_dict, feature_lst=feature_lst, user_id=user_id
        )
        return model_dict, feature_lst


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


def _get_training_input(df):
    return df.drop(
        [c for c in df.columns.values if "labels_" in c] + ["email_id"], axis=1
    )


def _get_lst_without_none(lst, column):
    return [column + "_" + entry for entry in lst if entry is not None]


def train_model(
    df,
    labels_to_learn,
    n_estimators=100,
    max_features=400,
    random_state=42,
    bootstrap=True,
):
    """
    Train machine learning models

    Args:
        df (pandas.DataFrame): binary encoded features stored in a pandas dataframe
        labels_to_learn (None/list): list of labels to train on, resulting in keys for the machine learning
                                     model dictionary.
        n_estimators (int): number of estimators of the machine learning models
        max_features (int): maximum number of features of the machine learning models
        random_state (int): random state for initialization of the machine learning models
        bootstrap (boolean): bootstrap of the machine learning models

    Returns:
        dict: dictionary with machine learning models with labels as keys
    """
    if labels_to_learn is None:
        labels_to_learn = [c for c in df.columns.values if "labels_Label_" in c]
    df_in = _get_training_input(df=df)
    return {
        to_learn.split("labels_")[-1]: RandomForestClassifier(
            n_estimators=n_estimators,
            random_state=random_state,
            bootstrap=bootstrap,
            max_features=max_features,
        ).fit(df_in, df[to_learn])
        for to_learn in tqdm(
            iterable=labels_to_learn, desc="Train machinelearning models"
        )
    }


def get_machine_learning_recommendations(
    models, df_select, df_all_encode, feature_lst, recommendation_ratio=0.9
):
    """
    Get recommendations from machine learning models

    Args:
        models (dict): dictionary with machine learning models with labels as keys
        df_select (pandas.DataFrame): dataframe of emails to be sorted
        df_all_encode (pandas.DataFrame): binary encoded features in a pandas dataframe
        feature_lst (list): list of features the machine learning models were trained on
        recommendation_ratio (float): recommendation cutoff ratio

    Returns:
        dict: email id as keys and the corresponding newly assigned label as value
    """
    df_select_hot = one_hot_encoding(
        df=df_select, label_lst=df_all_encode.columns.values, feature_lst=feature_lst
    )
    df_select_red = _get_training_input(df=df_select_hot)

    predictions = {k: v.predict(df_select_red) for k, v in models.items()}
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
        for email_id, label in zip(df_select_hot.email_id.values, new_label_lst)
    }


def gather_data_for_machine_learning(
    df_all, labels_dict, feature_lst, labels_to_exclude_lst=[]
):
    """
    Internal function to gather dataframe for training machine learning models

    Args:
        df_all (pandas.DataFrame): Dataframe with all emails
        labels_dict (dict): Dictionary with translation for labels
        feature_lst (list): list of features to train machine learning models on
        labels_to_exclude_lst (list): list of email labels which are excluded from the fitting process

    Returns:
        pandas.DataFrame: With all emails and their encoded labels
    """
    df_all_encode = one_hot_encoding(df=df_all, feature_lst=feature_lst)
    df_columns_to_drop_lst = [
        "labels_" + labels_dict[label]
        for label in labels_to_exclude_lst
        if label in list(labels_dict.keys())
    ]
    df_columns_to_drop_lst = [
        c for c in df_columns_to_drop_lst if c in df_all_encode.columns
    ]
    if len(df_columns_to_drop_lst) > 0:
        array_bool = np.any(
            [(df_all_encode[c] == 1).values for c in df_columns_to_drop_lst], axis=0
        )
        if isinstance(array_bool, np.ndarray) and len(array_bool) == len(df_all_encode):
            df_all_encode = df_all_encode[~array_bool]
        return df_all_encode.drop(labels=df_columns_to_drop_lst, axis=1)
    else:
        return df_all_encode


def one_hot_encoding(df, feature_lst, label_lst=[]):
    """
    Binary one hot encoding of features in a pandas DataFrame

    Args:
        df (pandas.DataFrame): DataFrame with emails
        feature_lst (list): list of features the machine learning models were trained on
        label_lst (list): list of labels

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
    if len(label_lst) == 0:
        df_new = pandas.DataFrame(all_binary_values, columns=all_labels)
    else:
        labels_to_drop = [label for label in all_labels if label not in label_lst]
        labels_to_add = [label for label in label_lst if label not in all_labels]
        data_stack = np.hstack(
            (all_binary_values, np.zeros((len(df), len(labels_to_add))))
        )
        columns = np.array(all_labels + labels_to_add)
        if len(feature_lst) > 0:
            ind = np.isin(columns, feature_lst)
            df_new = pandas.DataFrame(
                data_stack[:, ind],
                columns=columns[ind],
            )
        else:
            df_new = pandas.DataFrame(
                data_stack,
                columns=columns,
            )
        df_new.drop(labels_to_drop, inplace=True, axis=1)
    df_new["email_id"] = df.id.values
    return df_new.sort_index(axis=1)


def get_machine_learning_database(engine, session):
    Base.metadata.create_all(engine)
    return MachineLearningDatabase(session=session)
