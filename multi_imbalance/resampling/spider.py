import numpy as np
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neighbors import NearestNeighbors
from sklearn.metrics import confusion_matrix
import warnings
#warnings.filterwarnings("ignore")
import pandas as pd
import seaborn as sns

class SPIDER3:
    """
    SPIDER3 algorithm implementation for selective preprocessing of multi-class imbalanced data sets.

    Reference:
    Wojciechowski, S., Wilk, S., Stefanowski, J.: An Algorithm for Selective Preprocessing
    of Multi-class Imbalanced Data. Proceedings of the 10th International Conference
    on Computer Recognition Systems CORES 2017

    Methods
    ----------
    fit_transform(X, y)
        Performs resampling of X.
    """

    def __init__(self, k, cost, majority_classes, intermediate_classes, minority_classes):
        """
        Parameters
        ----------
        :param k:
            Number of nearest neighbors considered while resampling.
        :param cost:
            The cost matrix. An element c[i, j] of this matrix represents the cost
            associated with misclassifying an example from class i as class one from class j.
        :param majority_classes:
            List of majority classes.
        :param intermediate_classes:
            List of intermediate classes.
        :param minority_classes:
            List of minority classes.
        """

        self.k = k
        self.neigh_clf = NearestNeighbors(n_neighbors=self.k)
        self.cost = cost
        self.majority_classes = majority_classes
        self.intermediate_classes = intermediate_classes
        self.minority_classes = minority_classes
        self.AS, self.RS = np.array([]), np.array([])  # RS - examples from majority class that can be safely relabeled

    def fit_transform(self, X, y):
        """

        :param X:
            Numpy array of examples that is the subject of resampling.
        :param y:
            Numpy array of labels corresponding to examples from X.
        :return:
            Resampled X along with accordingly modified labels.
        """

        self.DS = np.append(X, y.reshape(y.shape[0], 1), axis=1)
        self.calculate_weak_majority_examples()
        self.DS = self._setdiff(self.DS, self.RS)
        self.RS = np.array([])  # according to java SPIDER3 implementation (l. 121)

        for int_min_class in self.intermediate_classes + self.minority_classes:
            int_min_ds = self.DS[self.DS[:, -1] == int_min_class]
            for x in int_min_ds:
                self._relabel_nn(x)

            int_min_as = self.calc_int_min_as(int_min_class)
            for x in self._union(int_min_ds, int_min_as):
                self._clean_nn(x)

            for x in int_min_ds:
                self._amplify(x)

        self.DS = self._union(self.DS, self.AS)

        return self.DS[:, :-1], self.DS[:, -1]

    def calc_int_min_as(self, int_min_class):
        """
        Helper method to calculate examples form AS that belong to int_min_class parameter class.
        :param int_min_class:
            The class name (intermediate or minority).
        :return:
            Examples from AS that are belong to int_min_class.
        """

        if self.AS.size != 0:
            int_min_as = self.AS[self.AS[:, -1] == int_min_class]
        else:
            int_min_as = np.array([])
        return int_min_as

    def calculate_weak_majority_examples(self):
        """
        Calculates weak majority examples and appends them to the RS set.
        :return:
        """

        for majority_class in self.majority_classes:
            majority_examples = self.DS[self.DS[:, -1] == majority_class]
            for x in majority_examples:
                if majority_class not in self._min_cost_classes(x, self.DS):
                    self.RS = self._union(self.RS, np.array([x]))

    def _min_cost_classes(self, x, DS):
        """
        Utility function that aims to identify minimum-cost classes, i.e. classes leading
        to the minimum cost after being (mis)classified as classes appearing in the neighborhood of x.

        :param x:
            Single observation
        :param DS:
            DS
        :return:
            List of classes associated with minimal cost of misclassification.
        """

        C = self.majority_classes + self.intermediate_classes + self.minority_classes
        vals = []
        for cj in C:
            s = 0
            for ci in C:
                s += (self._knn(x, DS, ci).shape[0] / self.k) * self.cost[C.index(ci), C.index(cj)]
            vals.append(s)
        C = np.array(C)
        vals = np.array(vals)
        return C[vals == vals[
            np.argmin(vals)]]

    @staticmethod
    def _setdiff(arr1, arr2):
        """
        Performs the difference over two numpy arrays.

        :param arr1:
            Numpy array number 1.
        :param arr2:
            Numpy array number 2.
        :return:
            Result of the difference of arr1 and arr2.
        """

        for element in arr2.tolist():
            if element in arr1.tolist():
                arr1 = np.delete(arr1, arr1.tolist().index(element), 0)
        return arr1

    @staticmethod
    def _union(arr1, arr2):
        """
        Performs the union over two numpy arrays
        (not removing duplicates, as it's how the algorithm SPIDER3 actually works).

        :param arr1:
            Numpy array number 1.
        :param arr2:
            Numpy array number 2.
        :return:
            The union of arr1 and arr2.
        """

        if arr1.size == 0:
            return arr2
        elif arr2.size == 0:
            return arr1
        else:
            return np.append(arr1, arr2, axis=0)

    def _intersect(self, arr1, arr2):
        """
        Performs the intersection operation over two numpy arrays (not removing duplicates).

        :param arr1:
            Numpy array number 1.
        :param arr2:
            Numpy array number 2.
        :return:
            The intersection of arr1 and arr2.
        """

        if arr1.size == 0 or arr2.size == 0:
            return np.array([])

        result = np.array([])
        for x1 in arr1:
            for x2 in arr2:
                if all(x1 == x2):
                    result = self._union(result, np.array([x1]))
        return result

    def _relabel_nn(self, x):  # possibly differs from java implementation (l. 185)
        """
        Performs relabeling in the nearest neighborhood of x.

        :param x:
            An observation.
        :return:
        """
        nearest_neighbors = self._knn(x,
                                      self.ds_as_rs_union())  # do we actually need the union with DS and AS? We're taking intersect with RS in the next step anyway
        TS = self._intersect(self.RS,
                             nearest_neighbors)  # TS - neighbors from majority class that can be relabeled
        while TS.shape[0] > 0 and \
                any(majority_class in self._min_cost_classes(x, self.ds_as_rs_union())
                    for majority_class in self.majority_classes):
            y = self._nearest(x, TS)
            TS = self._setdiff(TS, np.array([y]))
            self.RS = self._setdiff(self.RS, np.array([y]))
            y[-1] = x[-1]
            self.AS = self._union(self.AS, np.array([y]))

    @staticmethod
    def _nearest(x, TS):
        """
        Returns nearest neighbor of x in TS.

        :param x:
            Single observation.
        :param TS:
            Temporal set.
        :return:
            Nearest neighbor of x in TS.
        """
        clf = NearestNeighbors(n_neighbors=1).fit(TS[:, :-1])
        indices = clf.kneighbors([x[:-1]], return_distance=False)
        return TS[indices[0]][0]

    def _clean_nn(self, x):
        """
        Performs cleaning in the nearest neighborhood of x.

        :param x:
            Single observation.
        :return:
        """

        for majority_class in self.majority_classes:
            TS = self._knn(x, self.ds_as_rs_union(), majority_class)
            while TS.shape[0] > 0 and \
                    majority_class in self._min_cost_classes(x, self.ds_as_rs_union()):
                y = self._nearest(x, TS)
                TS = self._setdiff(TS, np.array([y]))
                self.DS = self._setdiff(self.DS, np.array([y]))
                self.RS = self._setdiff(self.RS, np.array([y]))

    def _knn(self, x, DS, c=None):
        """
        Returns k nearest neighbors of x in DS that belong to c class if specified.

        :param x:
            Single observation
        :param DS:
            DS
        :param c:
            Class of neighbors that should be returned.
        :return:
            These neighbors from k nearest that belong to class c if specified. Otherwise all of them.
        """

        self.neigh_clf.fit(DS[:, :-1])
        indices = self.neigh_clf.kneighbors([x[:-1]], return_distance=False)[0]
        if c is not None:
            result = []
            for idx in indices:
                if self._class_of(DS[idx]) == c:
                    result.append(DS[idx])
            return np.array(result)
        else:
            return DS[indices]

    def _amplify(self, x):
        """
        Artificially amplifies example x by adding a copy of it to the AS.

        :param x:
            Single observation.
        :return:
        """

        while self._class_of(x) not in self._min_cost_classes(x, self.ds_as_rs_union()):
            y = x.copy()
            self.AS = self._union(self.AS, np.asarray([y]))

    @staticmethod
    def _class_of(example):
        return example[-1]

    def ds_as_rs_union(self):
        return self._union(self.DS, self._union(self.AS, self.RS))


# if __name__ == "__main__":
#     rc = {'text.color': 'white', 'axes.labelcolor': 'white', 'xtick.color': 'white', 'ytick.color': 'white'}
#     sns.set_style('darkgrid', rc=rc)
#
#     # TODO replace it by correct file in repository
#     ecoli_url = 'https://archive.ics.uci.edu/ml/machine-learning-databases/ecoli/ecoli.data'
#     df = pd.read_csv(ecoli_url, delim_whitespace=True, header=None,
#                      names=['name', '1', '2', '3', '4', '5', '6', '7', 'class'])
#
#     X, y = df.iloc[:, 1:8].to_numpy(), df['class'].to_numpy()
#     print(X[:5])
#     print(y[:5])
#     cost = np.random.rand(64).reshape((8, 8))  # np.ones((8, 8))
#     for i in range(8):
#         cost[i][i] = 0
#
#     clf = SPIDER3(k=3, cost=cost, majority_classes=['cp', 'im'],
#                   intermediate_classes=['pp', 'imU', 'om'], minority_classes=['imS', 'imL', 'omL'])
#     transformed = clf.fit_transform(X.astype(np.float64), y)
#
#     print("Done")

def read_train_and_test_data(overlap, imbalance_ratio):
    for i in range(1, 11):
        with open(f"../../../3class-ho/3class-{imbalance_ratio}-overlap-{overlap}-learn-{i}.arff") as f:
            content = f.readlines()
        content = [x.strip().split(",") for x in content][5:]
        data = np.array(content)
        if i == 1:
            X_train, y_train = data[:, :-1].astype(float), data[:, -1].astype(object)
        else:
            X_train = np.append(X_train, data[:, :-1].astype(float), axis=0)
            y_train = np.append(y_train, data[:, -1].astype(object), axis=0)
    for i in range(1, 11):
        with open(f"../../../3class-ho/3class-{imbalance_ratio}-overlap-{overlap}-test-{i}.arff") as f:
            content = f.readlines()
        content = [x.strip().split(",") for x in content][5:]
        data = np.array(content)
        if i == 1:
            X_test, y_test = data[:, :-1].astype(float), data[:, -1].astype(object)
        else:
            X_test = np.append(X_test, data[:, :-1].astype(float), axis=0)
            y_test = np.append(y_test, data[:, -1].astype(object), axis=0)
    return X_train, y_train, X_test, y_test


def train_and_test():
    neigh = KNeighborsClassifier(n_neighbors=1)
    neigh.fit(X_train, y_train)
    y_pred = neigh.predict(X_test)
    labels = ['MIN', 'INT', 'MAJ']
    for i, label in enumerate(labels):
        print(
            f"{label} TPR: {confusion_matrix(y_test, y_pred, labels=labels)[i, i] / confusion_matrix(y_test, y_pred, labels=labels)[:, i].sum()}")


if __name__ == "__main__":
    for imbalance_ratio in ["70-30-0-0", "40-50-10-0", "30-40-15-15"]:
        print(f"Imbalance ratio: {imbalance_ratio}")
        for overlap in range(0, 3):
            print(f"Overlap: {overlap}")
            X_train, y_train, X_test, y_test = read_train_and_test_data(overlap, imbalance_ratio)
            cost = np.ones((3, 3))
            for i in range(3):
                cost[i][i] = 0

            clf = SPIDER3(k=3, cost=cost, majority_classes=['MAJ'],
                          intermediate_classes=['INT'], minority_classes=['MIN'])
            X_train, y_train = clf.fit_transform(X_train.astype(np.float64), y_train)
            train_and_test()
