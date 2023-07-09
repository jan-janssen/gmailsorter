import pickle
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base
from gmailsorter.base.database import DatabaseTemplate


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
        feature_filtered_lst = [
            feature for feature in feature_lst if "email_id" != feature
        ]
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
            feature
            for feature in feature_filtered_lst
            if feature not in feature_stored_lst
        ]
        feature_remove_lst = [
            feature
            for feature in feature_stored_lst
            if feature not in feature_filtered_lst
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


def get_machine_learning_database(engine, session):
    Base.metadata.create_all(engine)
    return MachineLearningDatabase(session=session)
