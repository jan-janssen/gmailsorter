import pickle

from sklearn.ensemble import RandomForestClassifier
from sqlalchemy import Column, Engine, Integer, String
from sqlalchemy.orm import Session, declarative_base

from gmailsorter.base.database import DatabaseTemplate

Base = declarative_base()


class MachineLearningModel(Base):
    __tablename__ = "ml_model"
    id = Column(Integer, primary_key=True)
    model = Column(String)
    labels = Column(String)
    user_id = Column(Integer)


class MachineLearningFeatures(Base):
    __tablename__ = "ml_features"
    id = Column(Integer, primary_key=True)
    feature = Column(String)
    user_id = Column(Integer)


class MachineLearningDatabase(DatabaseTemplate):
    def store_model(
        self,
        model: RandomForestClassifier,
        label_lst: list[str],
        feature_lst: list[str],
        user_id: int = 1,
        commit: bool = True,
    ) -> None:
        """
        Store the machine learning model in the database. Unlike the previous one-row-per-label layout, a single
        multi-output model covering every label is stored per user, so training no longer multiplies memory and
        storage by the number of labels.

        Args:
            model (RandomForestClassifier): the trained multi-output machine learning model
            label_lst (list): ordered list of label columns the model predicts
            feature_lst (list): list of features the machine learning model was trained on
            user_id (int): database user id
            commit (boolean): boolean flag to write to the database
        """
        feature_filtered_lst = [
            feature for feature in feature_lst if feature != "email_id"
        ]
        feature_stored_lst = self.get_features(user_id=user_id)
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
        model_obj = (
            self._session.query(MachineLearningModel)
            .filter(MachineLearningModel.user_id == user_id)
            .first()
        )
        if model_obj is None:
            self._session.add(
                MachineLearningModel(
                    model=pickle.dumps(model),
                    labels=pickle.dumps(label_lst),
                    user_id=user_id,
                )
            )
        else:
            model_obj.model = pickle.dumps(model)
            model_obj.labels = pickle.dumps(label_lst)
        if len(feature_new_lst) > 0:
            self._session.add_all(
                [
                    MachineLearningFeatures(feature=feature, user_id=user_id)
                    for feature in feature_new_lst
                ]
            )
        if len(feature_remove_lst) > 0:
            self._session.query(MachineLearningFeatures).filter(
                MachineLearningFeatures.user_id == user_id
            ).filter(MachineLearningFeatures.feature.in_(feature_remove_lst)).delete()
        if commit:
            self._session.commit()

    def load_model(
        self, user_id: int = 1
    ) -> tuple[RandomForestClassifier | None, list[str], list[str]]:
        """
        Load the machine learning model from the database

        Args:
            user_id (int): database user id

        Returns:
            RandomForestClassifier, list, list: machine learning model (or None if it was never trained), the
            ordered list of label columns it predicts and the list of features it was trained on
        """
        model_obj = (
            self._session.query(MachineLearningModel)
            .filter(MachineLearningModel.user_id == user_id)
            .first()
        )
        feature_lst = self.get_features(user_id=user_id)
        if model_obj is None:
            return None, [], feature_lst
        return pickle.loads(model_obj.model), pickle.loads(model_obj.labels), feature_lst

    def get_features(self, user_id: int = 1) -> list[str]:
        return [
            feature_obj.feature
            for feature_obj in (
                self._session.query(MachineLearningFeatures)
                .filter(MachineLearningFeatures.user_id == user_id)
                .all()
            )
        ]


def get_machine_learning_database(
    engine: Engine, session: Session
) -> MachineLearningDatabase:
    Base.metadata.create_all(engine)
    return MachineLearningDatabase(session=session)
