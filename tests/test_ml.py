import ast
import unittest

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gmailsorter.ml.database import (
    Base,
    MachineLearningDatabase,
    MachineLearningFeatures,
    MachineLearningModel,
    get_machine_learning_database,
)
from gmailsorter.ml.encoding import (
    _build_red_lst,
    _encode_multi_label,
    _expand_with_domains,
    _get_lst_without_none,
    encode_df_for_machine_learning,
    one_hot_encoding,
)
from gmailsorter.ml.model import (
    _to_sparse_matrix,
    fit_machine_learning_models,
    get_predictions_from_machine_learning_models,
    train_random_forest,
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
        self.assertEqual(self.session.query(MachineLearningModel).count(), 0)
        self.assertEqual(self.session.query(MachineLearningFeatures).count(), 0)

    def test_store_and_load_model_new(self):
        model = RandomForestClassifier()
        label_lst = ["labels_label1", "labels_label2"]
        features = ["feature1", "feature2", "email_id"]
        self.db.store_model(model, label_lst, features)

        self.assertEqual(self.session.query(MachineLearningModel).count(), 1)
        self.assertEqual(self.session.query(MachineLearningFeatures).count(), 2)
        self.assertEqual(len(self.db.get_features()), 2)
        self.assertNotIn("email_id", self.db.get_features())

        loaded_model, loaded_labels, loaded_features = self.db.load_model()
        self.assertIsInstance(loaded_model, RandomForestClassifier)
        self.assertEqual(loaded_labels, label_lst)
        self.assertEqual(set(loaded_features), {"feature1", "feature2"})

    def test_load_model_missing(self):
        loaded_model, loaded_labels, loaded_features = self.db.load_model()
        self.assertIsNone(loaded_model)
        self.assertEqual(loaded_labels, [])
        self.assertEqual(loaded_features, [])

    def test_store_model_update(self):
        model = RandomForestClassifier(n_estimators=10)
        features = ["feature1"]
        self.db.store_model(model, ["labels_label1"], features)

        updated_model = RandomForestClassifier(n_estimators=20)
        self.db.store_model(updated_model, ["labels_label1"], features)

        loaded_model, _, _ = self.db.load_model()
        self.assertEqual(loaded_model.n_estimators, 20)
        self.assertEqual(self.session.query(MachineLearningModel).count(), 1)

    def test_store_features_add_and_remove(self):
        model = "model1"
        features = ["feature1", "feature2"]
        self.db.store_model(model, ["labels_label1"], features)
        self.assertEqual(set(self.db.get_features()), {"feature1", "feature2"})

        new_features = ["feature2", "feature3"]
        self.db.store_model(model, ["labels_label1"], new_features)
        self.assertEqual(set(self.db.get_features()), {"feature2", "feature3"})
        self.assertEqual(self.session.query(MachineLearningFeatures).count(), 2)

    def test_store_model_no_commit(self):
        model = "model1"
        features = ["feature1"]
        self.db.store_model(model, ["labels_label1"], features, commit=False)
        self.session.rollback()

        self.assertEqual(self.session.query(MachineLearningModel).count(), 0)
        self.assertEqual(self.session.query(MachineLearningFeatures).count(), 0)

    def test_store_model_user_isolation(self):
        model1 = RandomForestClassifier(n_estimators=5)
        model2 = RandomForestClassifier(n_estimators=10)
        self.db.store_model(model1, ["labels_A"], ["f1"], user_id=1)
        self.db.store_model(model2, ["labels_B"], ["f2"], user_id=2)

        loaded1, labels1, features1 = self.db.load_model(user_id=1)
        loaded2, labels2, features2 = self.db.load_model(user_id=2)
        self.assertEqual(loaded1.n_estimators, 5)
        self.assertEqual(loaded2.n_estimators, 10)
        self.assertEqual(labels1, ["labels_A"])
        self.assertEqual(labels2, ["labels_B"])
        self.assertEqual(features1, ["f1"])
        self.assertEqual(features2, ["f2"])

    def test_load_model_missing_returns_empty_features_when_features_exist(self):
        self.session.add(MachineLearningFeatures(feature="f1", user_id=99))
        self.session.commit()

        loaded_model, loaded_labels, loaded_features = self.db.load_model(user_id=99)
        self.assertIsNone(loaded_model)
        self.assertEqual(loaded_labels, [])
        self.assertEqual(loaded_features, ["f1"])

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
        df_features = encode_df_for_machine_learning(
            self.df, return_labels=False, label_prefix="labels_Label_"
        )
        self.assertIn("email_id", df_features.columns)
        self.assertEqual(len(df_features), 2)
        self.assertNotIn("labels_Label_1", df_features.columns)

    def test_encode_df_for_machine_learning_with_feature_list(self):
        features = ["cc_@test.com", "from_from1@test.com"]
        df_features = encode_df_for_machine_learning(
            self.df,
            feature_lst=features,
            return_labels=False,
            label_prefix="labels_Label_",
        )
        self.assertEqual(
            set(df_features.columns),
            {"cc_@test.com", "from_from1@test.com", "email_id"},
        )

    def test_encode_df_for_machine_learning_with_numpy_arrays(self):
        features = np.array(["cc_@test.com", "from_from1@test.com"])
        labels = np.array(["labels_Label_1"])
        df_features, df_labels = encode_df_for_machine_learning(
            self.df,
            feature_lst=features,
            label_lst=labels,
            return_labels=True,
            label_prefix="labels_Label_",
        )
        self.assertEqual(
            set(df_features.columns),
            {"cc_@test.com", "from_from1@test.com", "email_id"},
        )
        self.assertEqual(set(df_labels.columns), {"labels_Label_1"})

    def test_encode_df_for_machine_learning_return_labels(self):
        df_features, df_labels = encode_df_for_machine_learning(
            self.df, return_labels=True, label_prefix="labels_Label_"
        )
        self.assertIn("labels_Label_1", df_labels.columns)
        self.assertEqual(df_labels["labels_Label_1"].tolist(), [1, 0])

    def test_one_hot_encoding_no_feature_list(self):
        df_encoded = one_hot_encoding(self.df)
        self.assertIn("labels_Label_1", df_encoded.columns)
        self.assertIn("cc_@test.com", df_encoded.columns)
        self.assertEqual(df_encoded["from_@another.com"].sum(), 1)
        self.assertEqual(df_encoded["to_to1@test.com"].sum(), 1)

    def test_one_hot_encoding_does_not_encode_threads(self):
        # Thread IDs are close to unique per email - one-hot encoding them would let the model memorize
        # training threads instead of generalizing, so they are deliberately excluded.
        df_encoded = one_hot_encoding(self.df)
        self.assertFalse(
            any(column.startswith("threads_") for column in df_encoded.columns)
        )

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

    def test_expand_with_domains(self):
        self.assertEqual(
            set(_expand_with_domains(["a@b.c", "d"])), {"a@b.c", "d", "@b.c"}
        )

    def test_encode_multi_label_exact_match(self):
        red_lst = ["a", "b", "c"]
        value_lst = [["a", "d"], ["b"], ["c", "a"]]
        result = _encode_multi_label(value_lst, red_lst, expand_domains=False).toarray()
        np.testing.assert_array_equal(result, [[1, 0, 0], [0, 1, 0], [1, 0, 1]])

    def test_encode_multi_label_with_domain_expansion(self):
        red_lst = ["@b.c", "d@e.f"]
        value_lst = [["a@b.c"], ["x@y.z", "d@e.f"]]
        result = _encode_multi_label(value_lst, red_lst, expand_domains=True).toarray()
        np.testing.assert_array_equal(result, [[1, 0], [0, 1]])

    def test_encode_multi_label_empty_vocabulary(self):
        result = _encode_multi_label([[], []], [], expand_domains=False)
        self.assertEqual(result.shape, (2, 0))


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
        self.model, self.label_lst = fit_machine_learning_models(
            self.df_features,
            self.df_labels,
            n_estimators=10,
            max_depth=None,
            min_samples_leaf=1,
            bootstrap=False,
        )

    def test_train_random_forest(self):
        X = self.df_features.drop("email_id", axis=1).to_numpy()
        y = self.df_labels.to_numpy()
        model = train_random_forest(
            10, 42, True, 2, X, y, max_depth=None, min_samples_leaf=1
        )
        self.assertIsInstance(model, RandomForestClassifier)
        self.assertTrue(hasattr(model, "predict"))

    def test_train_random_forest_respects_max_depth_and_min_samples_leaf(self):
        X = self.df_features.drop("email_id", axis=1).to_numpy()
        y = self.df_labels.to_numpy()
        model = train_random_forest(
            5, 0, False, "sqrt", X, y, max_depth=3, min_samples_leaf=2
        )
        self.assertEqual(model.max_depth, 3)
        self.assertEqual(model.min_samples_leaf, 2)

    def test_train_random_forest_with_n_jobs(self):
        X = self.df_features.drop("email_id", axis=1).to_numpy()
        y = self.df_labels.to_numpy()
        model = train_random_forest(
            5, 0, False, "sqrt", X, y, max_depth=None, min_samples_leaf=1, n_jobs=2
        )
        self.assertIsInstance(model, RandomForestClassifier)
        self.assertEqual(model.n_jobs, 2)

    def test_fit_machine_learning_models(self):
        self.assertEqual(set(self.label_lst), {"labels_Label_1", "labels_Label_2"})
        self.assertIsInstance(self.model, RandomForestClassifier)
        self.assertEqual(self.model.n_outputs_, 2)

    def test_fit_machine_learning_models_max_depth_and_min_samples_leaf(self):
        model, label_lst = fit_machine_learning_models(
            self.df_features,
            self.df_labels,
            n_estimators=5,
            max_depth=5,
            min_samples_leaf=2,
            bootstrap=False,
        )
        self.assertEqual(model.max_depth, 5)
        self.assertEqual(model.min_samples_leaf, 2)

    def test_fit_machine_learning_models_max_workers(self):
        model, _ = fit_machine_learning_models(
            self.df_features,
            self.df_labels,
            n_estimators=5,
            max_depth=None,
            min_samples_leaf=1,
            bootstrap=False,
            max_workers=2,
        )
        self.assertEqual(model.n_jobs, 2)

    def test_get_predictions_from_machine_learning_models(self):
        predictions = get_predictions_from_machine_learning_models(
            self.df_features, self.model, self.label_lst
        )
        self.assertEqual(set(predictions.keys()), {"id1", "id2", "id3"})
        self.assertEqual(predictions["id1"], "Label_1")
        self.assertEqual(predictions["id2"], "Label_2")
        self.assertEqual(predictions["id3"], "Label_1")

    def test_get_predictions_from_machine_learning_models_no_recommendation(self):
        predictions = get_predictions_from_machine_learning_models(
            self.df_features, self.model, self.label_lst, recommendation_ratio=1.0
        )
        self.assertIsNone(predictions["id1"])

    def test_get_predictions_single_output_label(self):
        # When only one label column is present, scikit-learn squeezes the output to single-output
        # classification. The implementation must normalise it back to the list form.
        df_labels_single = self.df_labels[["labels_Label_1"]]
        model, label_lst = fit_machine_learning_models(
            self.df_features,
            df_labels_single,
            n_estimators=10,
            max_depth=None,
            min_samples_leaf=1,
            bootstrap=False,
        )
        predictions = get_predictions_from_machine_learning_models(
            self.df_features, model, label_lst
        )
        self.assertEqual(set(predictions.keys()), {"id1", "id2", "id3"})
        for value in predictions.values():
            self.assertTrue(value is None or value == "Label_1")

    def test_to_sparse_matrix_dense(self):
        df = pd.DataFrame({"a": [1, 0], "b": [0, 1]})
        result = _to_sparse_matrix(df)
        np.testing.assert_array_equal(result, [[1, 0], [0, 1]])

    def test_to_sparse_matrix_sparse(self):
        from scipy.sparse import issparse

        df = pd.DataFrame(
            {
                "a": pd.arrays.SparseArray([1, 0]),
                "b": pd.arrays.SparseArray([0, 1]),
            }
        )
        result = _to_sparse_matrix(df)
        self.assertTrue(issparse(result))

    def test_spam_example_csv_pipeline(self):
        csv_data = """id,from,to,cc,date,threads,labels,subject,content
19d8718ecb472fdb,email@spam.net,['bill.gates@outlook.com'],[],2026-04-13 09:45:17,19d8718ecb472fdb,['Label_7891913576640435048'],"bill.gates¸Your Account Has been Blocked! Your Photos and Videos will be Removed Mon,13 Apr-2026. take action!!",
19da5e58f1ba213f,email@spam.net,['bill.gates@outlook.com'],[],2026-04-19 09:16:42,19da5e58f1ba213f,['Label_7891913576640435048'],"bill.gates, Your Cloud Account has been locked on Sun, 19 Apr 2026 09:16:42 -0400. Your photos and videos will be removed!",
19dbf294452d4b08,email@spam.net,['bill.gates@outlook.com'],[],2026-04-24 07:00:57,19dbf294452d4b08,['Label_7891913576640435048'],Last Alert Before Account Deactivation,
19dc1d19a0ea36c3,email@spam.net,['bill.gates@outlook.com'],[],2026-04-24 19:15:02,19dc1d19a0ea36c3,['Label_7891913576640435048'],"We've Blocked Your Account! Your photos and videos will be deleted Today Fri,24 Apr-2026",
19de42f704c33a07,email@spam.net,['bill.gates@outlook.com'],[],2026-05-01 11:24:15,19de42f704c33a07,['Label_7891913576640435048'],RE: Why Veterans Are Cashing In While Others Stay Broke—Don’t Be Left Behind.,
19de2daa08ea7433,email@spam.net,['bill.gates@outlook.com'],[],2026-05-01 05:24:27,19de2daa08ea7433,['Label_7891913576640435048'],bill.gates Tired of Dieting? Try This Instead,
19ddef585e04396a,email@spam.net,['bill.gates@outlook.com'],[],2026-04-30 11:14:54,19ddef585e04396a,['Label_7891913576640435048'],Get access to DirectMeds - No insurance Needed,
19ddbf843a81b143,email@spam.net,['bill.gates@outlook.com'],[],2026-04-29 20:56:32,19ddbf843a81b143,['Label_7891913576640435048'],Last Attempt For You! Claim your Lοwe's Kοbаlt Τοοlset Now,
19e0ed21b438238a,email@spam.net,['bill.gates@outlook.com'],[],2026-05-09 18:14:58,19e0ed21b438238a,['Label_7891913576640435048'],Payment Failed: Subscription Terminated,
19e08746fec1990d,email@spam.net,['bill.gates@outlook.com'],[],2026-05-08 12:37:36,19e08746fec1990d,['Label_7891913576640435048'],"We’re sorry: bill.gates from today onward, we will not take any responsibility! Fri,08 May-2026",
19df9b3bb020c477,email@spam.net,['bill.gates@outlook.com'],[],2026-05-05 15:52:40,19df9b3bb020c477,['Label_7891913576640435048'],2026 Benefit List Shows 12 Programs Many Seniors Miss ...,
19e13b7e2ff2f9c3,email@spam.net,['bill.gates@outlook.com'],[],2026-05-10 17:05:42,19e13b7e2ff2f9c3,['Label_7891913576640435048'],Your Protection Has Been Disabled,
"""
        rows = []
        for line in csv_data.strip().splitlines()[1:]:
            entry = line.split(",", 7)
            subject_content = entry[7]
            subject, content = subject_content.rsplit(",", 1)
            rows.append(
                {
                    "id": entry[0],
                    "from": entry[1],
                    "to": entry[2],
                    "cc": entry[3],
                    "date": entry[4],
                    "threads": entry[5],
                    "labels": entry[6],
                    "subject": subject.strip('"'),
                    "content": content if content else None,
                }
            )
        df = pd.DataFrame(rows)
        for col in ["to", "cc", "labels"]:
            df[col] = df[col].apply(ast.literal_eval)

        df_features, df_labels = encode_df_for_machine_learning(
            df, return_labels=True, label_prefix="labels_Label_"
        )
        df_features = df_features.loc[:, ~df_features.columns.duplicated()]
        self.assertEqual(len(df_features), 12)
        self.assertIn("email_id", df_features.columns)
        self.assertEqual(set(df_labels.columns), {"labels_Label_7891913576640435048"})

        model, label_lst = fit_machine_learning_models(
            df_features, df_labels, n_estimators=10, max_features=2
        )
        predictions = get_predictions_from_machine_learning_models(
            df_features, model, label_lst
        )
        self.assertEqual(set(predictions.values()), {"Label_7891913576640435048"})

    def test_spam_example_csv_pipeline_parallel(self):
        csv_data = """id,from,to,cc,date,threads,labels,subject,content
19d8718ecb472fdb,email@spam.net,['bill.gates@outlook.com'],[],2026-04-13 09:45:17,19d8718ecb472fdb,['Label_7891913576640435048'],"bill.gates¸Your Account Has been Blocked! Your Photos and Videos will be Removed Mon,13 Apr-2026. take action!!",
19da5e58f1ba213f,email@spam.net,['bill.gates@outlook.com'],[],2026-04-19 09:16:42,19da5e58f1ba213f,['Label_7891913576640435048'],"bill.gates, Your Cloud Account has been locked on Sun, 19 Apr 2026 09:16:42 -0400. Your photos and videos will be removed!",
19dbf294452d4b08,email@spam.net,['bill.gates@outlook.com'],[],2026-04-24 07:00:57,19dbf294452d4b08,['Label_7891913576640435048'],Last Alert Before Account Deactivation,
19dc1d19a0ea36c3,email@spam.net,['bill.gates@outlook.com'],[],2026-04-24 19:15:02,19dc1d19a0ea36c3,['Label_7891913576640435048'],"We've Blocked Your Account! Your photos and videos will be deleted Today Fri,24 Apr-2026",
19de42f704c33a07,email@spam.net,['bill.gates@outlook.com'],[],2026-05-01 11:24:15,19de42f704c33a07,['Label_7891913576640435048'],RE: Why Veterans Are Cashing In While Others Stay Broke—Don’t Be Left Behind.,
19de2daa08ea7433,email@spam.net,['bill.gates@outlook.com'],[],2026-05-01 05:24:27,19de2daa08ea7433,['Label_7891913576640435048'],bill.gates Tired of Dieting? Try This Instead,
19ddef585e04396a,email@spam.net,['bill.gates@outlook.com'],[],2026-04-30 11:14:54,19ddef585e04396a,['Label_7891913576640435048'],Get access to DirectMeds - No insurance Needed,
19ddbf843a81b143,email@spam.net,['bill.gates@outlook.com'],[],2026-04-29 20:56:32,19ddbf843a81b143,['Label_7891913576640435048'],Last Attempt For You! Claim your Lοwe's Kοbаlt Τοοlset Now,
19e0ed21b438238a,email@spam.net,['bill.gates@outlook.com'],[],2026-05-09 18:14:58,19e0ed21b438238a,['Label_7891913576640435048'],Payment Failed: Subscription Terminated,
19e08746fec1990d,email@spam.net,['bill.gates@outlook.com'],[],2026-05-08 12:37:36,19e08746fec1990d,['Label_7891913576640435048'],"We’re sorry: bill.gates from today onward, we will not take any responsibility! Fri,08 May-2026",
19df9b3bb020c477,email@spam.net,['bill.gates@outlook.com'],[],2026-05-05 15:52:40,19df9b3bb020c477,['Label_7891913576640435048'],2026 Benefit List Shows 12 Programs Many Seniors Miss ...,
19e13b7e2ff2f9c3,email@spam.net,['bill.gates@outlook.com'],[],2026-05-10 17:05:42,19e13b7e2ff2f9c3,['Label_7891913576640435048'],Your Protection Has Been Disabled,
"""
        rows = []
        for line in csv_data.strip().splitlines()[1:]:
            entry = line.split(",", 7)
            subject_content = entry[7]
            subject, content = subject_content.rsplit(",", 1)
            rows.append(
                {
                    "id": entry[0],
                    "from": entry[1],
                    "to": entry[2],
                    "cc": entry[3],
                    "date": entry[4],
                    "threads": entry[5],
                    "labels": entry[6],
                    "subject": subject.strip('"'),
                    "content": content if content else None,
                }
            )
        df = pd.DataFrame(rows)
        for col in ["to", "cc", "labels"]:
            df[col] = df[col].apply(ast.literal_eval)

        df_features, df_labels = encode_df_for_machine_learning(
            df, return_labels=True, label_prefix="labels_Label_"
        )
        df_features = df_features.loc[:, ~df_features.columns.duplicated()]
        self.assertEqual(len(df_features), 12)
        self.assertIn("email_id", df_features.columns)
        self.assertEqual(set(df_labels.columns), {"labels_Label_7891913576640435048"})

        models, label_lst = fit_machine_learning_models(
            df_features, df_labels, n_estimators=10, max_features=2, max_workers=2
        )
        predictions = get_predictions_from_machine_learning_models(
            df_features, models, label_lst
        )
        self.assertEqual(set(predictions.values()), {"Label_7891913576640435048"})
