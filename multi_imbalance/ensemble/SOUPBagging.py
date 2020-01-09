import multiprocessing
from collections import Counter
from copy import deepcopy

import numpy as np
from sklearn.ensemble import BaggingClassifier
from sklearn.neighbors import KNeighborsClassifier
from sklearn.utils import resample
from multi_imbalance.resampling.SOUP import SOUP
from multi_imbalance.utils.array_util import setdiff
from cvxpy import *

np.random.seed(0)


def fit_clf(args):
    return SOUPBagging.fit_classifier(args)


class SOUPBagging(BaggingClassifier):
    def __init__(self, classifier=None, n_classifiers=5):
        super().__init__()
        self.classifiers = list()
        self.num_core = multiprocessing.cpu_count()
        self.n_classifiers = n_classifiers
        self.classes = None
        for _ in range(n_classifiers):
            if classifier is not None:
                self.classifiers.append(deepcopy(classifier))
            else:
                self.classifiers.append(KNeighborsClassifier())

    @staticmethod
    def fit_classifier(args):
        clf, X, y = args
        x_sampled, y_sampled = resample(X, y, stratify=y)
        print(X.shape, y.shape)
        # print(np.hstack((X,[y])))
        # out_of_bag = setdiff(np.hstack((X,y)), np.hstack((x_sampled, y_sampled)))

        x_resampled, y_resampled = SOUP().fit_transform(x_sampled, y_sampled)
        clf.fit(x_resampled, y_resampled)
        return clf

    def fit(self, X, y):
        """

        :param X: {array-like, sparse matrix} of shape = [n_samples, n_features] The training input samples.
        :param y: array-like, shape = [n_samples]. The target values (class labels).
        :return: self object
        """
        self.classes = np.unique(y)

        clf = self.classifiers[0]
        x_sampled, y_sampled = resample(X, y, stratify=y)
        out_of_bag = setdiff(np.hstack((X, y[:, np.newaxis])), np.hstack((x_sampled, y_sampled[:, np.newaxis])))
        x_out, y_out = out_of_bag[:, :-1], out_of_bag[:, -1].astype(int)
        class_quantities = Counter(y_out)

        x_resampled, y_resampled = SOUP().fit_transform(x_sampled, y_sampled)
        clf.fit(x_resampled, y_resampled)

        result = clf.predict_proba(x_out)

        class_sum_prob = np.sum(result, axis=0) + 0.001
        expected_sum_prob = np.array([class_quantities[i] for i in range(len(class_quantities))])
        global_weights = expected_sum_prob / class_sum_prob

        result = clf.predict_proba(x_out)

        cls_var = [Variable(name=f'w_{str(i)}', nonneg=True) for i in range(len(class_quantities))]
        epsilons, constraints = list(), list()
        constraints.append(sum(cls_var) == 1)

        for i in range(result.shape[0]):
            expected = y_out[i]
            for class_id in range(result.shape[1]):
                if class_id != expected:
                    if result[i, class_id] != 0:
                        eps = Variable(name=f'eps_{str(i)}_{str(class_id)}', nonneg=True)
                        constraints.append(result[i, expected] * cls_var[expected] - result[i, class_id] * cls_var[class_id] + eps >= 0)
                        # epsilons.append((1 - class_quantities[expected] / len(y_out)) * eps)
                        epsilons.append((class_quantities[expected] / len(y_out)) * eps)
                        # epsilons.append(eps)

        obj = Minimize(sum(epsilons))
        problem = Problem(obj, constraints)
        problem.solve(verbose=True)
        if problem.status not in ["infeasible", "unbounded"]:
            # Otherwise, problem.value is inf or -inf, respectively.
            print("Optimal value: %s" % problem.value)
        for variable in problem.variables():
            print("Variable %s: value %s" % (variable.name(), variable.value))

        # pool = multiprocessing.Pool(self.num_core)
        # self.classifiers = pool.map(fit_clf, [(clf, X, y) for clf in self.classifiers])
        # pool.close()
        # pool.join()

    def predict(self, X, strategy: str = 'average', maj_int_min: dict = None):
        """
        Predict class for X. The predicted class of an input sample is computed as the class with the highest
        sum of predicted probability.

        :param X: {array-like, sparse matrix} of shape = [n_samples, n_features]. The training input samples.
        :param strategy:
            'average' - takes max from average values in prediction
            'optimistic' - takes always best value of probability
            'pessimistic' - takes always the worst value of probability
            'mixed' - for minority classes takes optimistic strategy, and pessimistic for others. It requires maj_int_min
        :param maj_int_min: dict. It keeps indices of minority classes under 'min' key.
        :return: y : array of shape = [n_samples]. The predicted classes.
        """
        weights_sum = self.predict_proba(X)
        if strategy == 'average':
            p = np.sum(weights_sum, axis=0)
        elif strategy == 'optimistic':
            p = np.max(weights_sum, axis=0)
        elif strategy == 'pessimistic':
            p = np.min(weights_sum, axis=0)
        elif strategy == 'mixed':
            n_samples = X.shape[0]
            n_classes = self.classes.shape[0]
            p = np.zeros(shape=(n_samples, n_classes)) - 1

            for i in range(n_classes):
                two_dim_class_vector = weights_sum[:, :, i]  # [:,:,1] -> [classifiers x samples]
                if i in maj_int_min['min']:
                    squeeze_with_strategy = np.max(two_dim_class_vector, axis=0)
                else:
                    squeeze_with_strategy = np.min(two_dim_class_vector, axis=0)  # [1, n_samples, 1] -> [n_samples]
                p[:, i] = squeeze_with_strategy
            assert -1 not in p
        else:
            raise KeyError(f'Incorrect strategy param: ${strategy}')

        y_result = np.argmax(p, axis=1)
        return y_result

    def predict_proba(self, X):
        """
        Predict class probabilities for X.

        :param X:{array-like, sparse matrix} of shape = [n_samples, n_features]. The training input samples.
        :return: array of shape = [n_classifiers, n_samples, n_classes]. The class probabilities of the input samples.
        """
        n_samples = X.shape[0]
        n_classes = self.classes.shape[0]

        results = np.zeros(shape=(self.n_classifiers, n_samples, n_classes))

        for i, clf in enumerate(self.classifiers):
            results[i] = clf.predict_proba(X)

        return results


if __name__ == '__main__':
    from imblearn.metrics import geometric_mean_score
    from sklearn.model_selection import train_test_split
    from sklearn.neighbors import KNeighborsClassifier
    from multi_imbalance.datasets import load_datasets

    dataset = load_datasets()['new_ecoli']

    X, y = dataset.data, dataset.target

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25)
    clf = KNeighborsClassifier()
    vote_classifier = SOUPBagging(clf, n_classifiers=1)
    vote_classifier.fit(X_train, y_train)
    y_pred = vote_classifier.predict(X_test)
    print(geometric_mean_score(y_test, y_pred, correction=0.001))
