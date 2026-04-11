import unittest
import pickle
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sklearn.ensemble import RandomForestClassifier

from gmailsorter.ml.encoding import (
    encode_df_for_machine_learning,
    one_hot_encoding,
    _build_red_lst,
    _get_lst_without_none,
    _single_entry_df,
    _single_entry_email_df,
    _list_entry_df,
    _list_entry_email_df,
)
from gmailsorter.ml.model import (
    train_random_forest,
    fit_machine_learning_models,
    get_predictions_from_machine_learning_models,
)
from gmailsorter.ml.database import (
    MachineLearningDatabase,
    MachineLearningLabels,
    MachineLearningFeatures,
    get_machine_learning_database,
    Base,
)

class TestMlDatabase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
        self.db = MachineLearningDatabase(session=self.session)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.session.close()

    def test_get_machine_learning_database(self):
        db_instance = get_machine_learning_database(self.engine, self.session)
        self.assertIsInstance(db_instance, MachineLearningDatabase)
        self.assertEqual(self.session.query(MachineLearningLabels).count(), 0)
        self.assertEqual(self.session.query(MachineLearningFeatures).count(), 0)

    def test_store_and_load_models_new(self):
        models = {"label1": RandomForestClassifier(), "label2": RandomForestClassifier()}
        features = ["feature1", "feature2", "email_id"]
        self.db.store_models(models, features)

        self.assertEqual(self.session.query(MachineLearningLabels).count(), 2)
        self.assertEqual(self.session.query(MachineLearningFeatures).count(), 2)
        self.assertEqual(len(self.db.get_features()), 2)
        self.assertNotIn("email_id", self.db.get_features())

        loaded_models, loaded_features = self.db.load_models()
        self.assertEqual(len(loaded_models), 2)
        self.assertEqual(set(loaded_models.keys()), {"label1", "label2"})
        self.assertIsInstance(loaded_models["label1"], RandomForestClassifier)
        self.assertEqual(set(loaded_features), {"feature1", "feature2"})

    def test_store_models_update(self):
        models = {"label1": RandomForestClassifier(n_estimators=10)}
        features = ["feature1"]
        self.db.store_models(models, features)

        updated_models = {"label1": RandomForestClassifier(n_estimators=20)}
        self.db.store_models(updated_models, features)

        loaded_models, _ = self.db.load_models()
        self.assertEqual(loaded_models["label1"].n_estimators, 20)
        self.assertEqual(self.session.query(MachineLearningLabels).count(), 1)

    def test_store_models_delete(self):
        models = {"label1": "model1", "label2": "model2"}
        features = ["feature1", "feature2"]
        self.db.store_models(models, features)

        new_models = {"label1": "model1_updated"}
        self.db.store_models(new_models, features)

        loaded_models, _ = self.db.load_models()
        self.assertEqual(set(loaded_models.keys()), {"label1"})
        self.assertEqual(self.session.query(MachineLearningLabels).count(), 1)

    def test_store_features_add_and_remove(self):
        models = {"label1": "model1"}
        features = ["feature1", "feature2"]
        self.db.store_models(models, features)
        self.assertEqual(set(self.db.get_features()), {"feature1", "feature2"})

        new_features = ["feature2", "feature3"]
        self.db.store_models(models, new_features)
        self.assertEqual(set(self.db.get_features()), {"feature2", "feature3"})
        self.assertEqual(self.session.query(MachineLearningFeatures).count(), 2)

    def test_store_models_no_commit(self):
        models = {"label1": "model1"}
        features = ["feature1"]
        self.db.store_models(models, features, commit=False)
        self.session.rollback()

        self.assertEqual(self.session.query(MachineLearningLabels).count(), 0)
        self.assertEqual(self.session.query(MachineLearningFeatures).count(), 0)

    def test_get_labels(self):
        labels = [
            MachineLearningLabels(label_id="label1", random_forest=pickle.dumps("test"), user_id=1),
            MachineLearningLabels(label_id="label2", random_forest=pickle.dumps("test"), user_id=1),
            MachineLearningLabels(label_id="label3", random_forest=pickle.dumps("test"), user_id=2),
        ]
        self.session.add_all(labels)
        self.session.commit()

        retrieved_labels = self.db._get_labels(user_id=1)
        self.assertEqual(set(retrieved_labels), {"label1", "label2"})

    def test_get_features(self):
        features = [
            MachineLearningFeatures(feature="feature1", user_id=1),
            MachineLearningFeatures(feature="feature2", user_id=1),
            MachineLearningFeatures(feature="feature3", user_id=2),
        ]
        self.session.add_all(features)
        self.session.commit()

        retrieved_features = self.db.get_features(user_id=1)
        self.assertEqual(set(retrieved_features), {"feature1", "feature2"})


class TestMlEncoding(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame(
            {
                "id": ["id1", "id2"],
                "labels": [["Label_1", "Label_2"], ["Label_2", "Label_3"]],
                "cc": [["cc1@test.com"], ["cc2@test.com", "cc3@another.com"]],
                "threads": ["thread1", "thread2"],
                "to": [["to1@test.com"], ["to2@test.com"]],
                "from": ["from1@test.com", "from2@another.com"],
            }
        )

    def test_encode_df_for_machine_learning_no_feature_list(self):
        df_features = encode_df_for_machine_learning(self.df, return_labels=False)
        self.assertIn("email_id", df_features.columns)
        self.assertEqual(len(df_features), 2)
        self.assertNotIn("labels_Label_1", df_features.columns)

    def test_encode_df_for_machine_learning_with_feature_list(self):
        features = ["cc_@test.com", "from_from1@test.com"]
        df_features = encode_df_for_machine_learning(
            self.df, feature_lst=features, return_labels=False
        )
        self.assertEqual(
            set(df_features.columns), {"cc_@test.com", "from_from1@test.com", "email_id"}
        )

    def test_encode_df_for_machine_learning_with_numpy_arrays(self):
        features = np.array(["cc_@test.com", "from_from1@test.com"])
        labels = np.array(["labels_Label_1"])
        df_features, df_labels = encode_df_for_machine_learning(
            self.df, feature_lst=features, label_lst=labels, return_labels=True
        )
        self.assertEqual(
            set(df_features.columns), {"cc_@test.com", "from_from1@test.com", "email_id"}
        )
        self.assertEqual(set(df_labels.columns), {"labels_Label_1"})

    def test_encode_df_for_machine_learning_return_labels(self):
        df_features, df_labels = encode_df_for_machine_learning(
            self.df, return_labels=True
        )
        self.assertIn("labels_Label_1", df_labels.columns)
        self.assertEqual(df_labels["labels_Label_1"].tolist(), [1, 0])

    def test_one_hot_encoding_no_feature_list(self):
        df_encoded = one_hot_encoding(self.df)
        self.assertIn("labels_Label_1", df_encoded.columns)
        self.assertIn("cc_@test.com", df_encoded.columns)
        self.assertEqual(df_encoded["from_@another.com"].sum(), 1)
        self.assertEqual(df_encoded["threads_thread1"].sum(), 1)
        self.assertEqual(df_encoded["to_to1@test.com"].sum(), 1)

    def test_one_hot_encoding_with_feature_list(self):
        features = ["labels_Label_1", "cc_@another.com", "from_@test.com"]
        df_encoded = one_hot_encoding(self.df, feature_lst=features)
        self.assertEqual(
            set(df_encoded.columns),
            {"labels_Label_1", "cc_@another.com", "from_@test.com", "email_id"},
        )
        self.assertEqual(df_encoded["labels_Label_1"].tolist(), [1, 0])
        self.assertEqual(df_encoded["from_@test.com"].tolist(), [1, 0])

    def test_build_red_lst(self):
        test_col = [["a@b.c", "d"], ["e@f.g", "d"]]
        red_lst = _build_red_lst(test_col)
        self.assertEqual(set(red_lst), {"a@b.c", "@b.c", "d", "e@f.g", "@f.g"})

    def test_get_lst_without_none(self):
        lst = ["a", None, "b"]
        result = _get_lst_without_none(lst, "col")
        self.assertEqual(result, ["col_a", "col_b"])

    def test_single_entry_df(self):
        red_lst = ["a", "b", None]
        value_lst = ["b", "a", "c"]
        result = _single_entry_df(red_lst, value_lst)
        np.testing.assert_array_equal(result, [[0, 1], [1, 0], [0, 0]])

    def test_single_entry_email_df(self):
        red_lst = ["a@b.c", "@b.c", None]
        value_lst = ["a@b.c", "d@e.f", None]
        result = _single_entry_email_df(red_lst, value_lst)
        np.testing.assert_array_equal(result, [[1, 1], [0, 0], [0, 0]])

    def test_list_entry_df(self):
        red_lst = ["a", "b", "c"]
        value_lst = [["a", "d"], ["b"], ["c", "a"]]
        result = _list_entry_df(red_lst, value_lst)
        np.testing.assert_array_equal(result, [[1, 0, 0], [0, 1, 0], [1, 0, 1]])

    def test_list_entry_email_df(self):
        red_lst = ["@b.c", "d@e.f"]
        value_lst = [["a@b.c"], ["x@y.z", "d@e.f"]]
        result = _list_entry_email_df(red_lst, value_lst)
        np.testing.assert_array_equal(result, [[1, 0], [0, 1]])


class TestMlModel(unittest.TestCase):
    def setUp(self):
        self.df_features = pd.DataFrame(
            {
                "email_id": ["id1", "id2", "id3"],
                "feature1": [1, 0, 1],
                "feature2": [0, 1, 0],
            }
        )
        self.df_labels = pd.DataFrame(
            {
                "labels_Label_1": [1, 0, 1],
                "labels_Label_2": [0, 1, 0],
            }
        )
        self.models = fit_machine_learning_models(
            self.df_features, self.df_labels, n_estimators=10, max_workers=1
        )

    def test_train_random_forest(self):
        X = self.df_features.drop("email_id", axis=1)
        y = self.df_labels["labels_Label_1"]
        model = train_random_forest(10, 42, True, 2, X, y)
        self.assertIsInstance(model, RandomForestClassifier)
        self.assertTrue(hasattr(model, "predict"))

    def test_fit_machine_learning_models(self):
        self.assertEqual(set(self.models.keys()), {"Label_1", "Label_2"})
        self.assertIsInstance(self.models["Label_1"], RandomForestClassifier)

    def test_get_predictions_from_machine_learning_models(self):
        predictions = get_predictions_from_machine_learning_models(
            self.df_features, self.models
        )
        self.assertEqual(set(predictions.keys()), {"id1", "id2", "id3"})
        self.assertEqual(predictions["id1"], "Label_1")
        self.assertEqual(predictions["id2"], "Label_2")
        self.assertEqual(predictions["id3"], "Label_1")

    def test_get_predictions_from_machine_learning_models_no_recommendation(self):
        predictions = get_predictions_from_machine_learning_models(
            self.df_features, self.models, recommendation_ratio=1.0
        )
        self.assertIsNone(predictions["id1"])
