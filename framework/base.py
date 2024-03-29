"""
Author: Yi-Qi Hu
this is a template for model evaluation
"""
import abc

import numpy as np
from sklearn.metrics import accuracy_score
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold

from utils.logging_ import LoggerManager

FLOAT = 0
INTEGER = 1
CATEGORICAL = 2
_PENALTY = 0


def data_collector(index_list, features, labels):
    """
    re-collect data according to index
    :param index_list: the data index
    :param features: original features
    :param labels: original labels
    :return: the features and labels collected by index_list
    """

    assert len(features.shape) == 2
    assert len(labels.shape) == 1

    feature_dim = features.shape[1]

    trans_features = np.zeros((len(index_list), feature_dim))
    trans_labels = np.zeros(len(index_list))

    for i in range(len(index_list)):
        trans_features[i, :] = features[index_list[i], :]
        trans_labels[i] = labels[index_list[i]]

    return trans_features, trans_labels


class ModelEvaluator:

    def __init__(self, model_generator=None, train_x=None, train_y=None, criterion='accuracy', valid_k=5):
        """
        :param model_generator: an instantiation son class of ModelGenerator
        :param train_x: train feature, type -- array
        :param train_y: train label, type -- array
        :param criterion: evaluation metric, type -- string
        :param valid_k: k-validation, type -- int
        """
        self.model_generator = model_generator
        self.train_x = train_x
        self.train_y = train_y
        self.criterion = criterion
        self.validation_kf = StratifiedKFold(n_splits=valid_k, shuffle=False)
        return

    def evaluate(self, x):
        """
        evaluate the hyperparameter x by k-fold validation
        :param x: the hyperparameter list, type -- list
        :return: the evaluation value according to the metric, type -- float
        """

        this_model = self.model_generator.generate_model(x)

        eval_values = []
        for train_index, valid_index in self.validation_kf.split(self.train_x, self.train_y):
            x, y = data_collector(train_index, self.train_x, self.train_y)
            valid_x, valid_y = data_collector(valid_index, self.train_x, self.train_y)

            try:
                this_model = this_model.fit(x, y)
            except ValueError as e:  # temporally just catch ValueError
                logger = LoggerManager.get_logger('model_evaluator')
                logger.info("Parameter wrong, return 0, error message: {}".format(e))
                return _PENALTY

            predictions = this_model.predict(valid_x)

            if self.criterion == 'accuracy':
                eval_value = accuracy_score(valid_y, predictions)
            elif self.criterion == 'auc':
                eval_value = roc_auc_score(valid_y, predictions)
            else:
                eval_value = 0.0
            eval_values.append(eval_value)

        eval_mean = np.mean(np.array(eval_values))

        return eval_mean


class ModelGenerator:
    """
    This is the father class of each model implementation. Each specific model implementation should overwrite the two
    basic functions: set_hyper-parameter and generate_model.
    """

    def __init__(self, hp_space, model_initializer):
        self.hp_space = hp_space
        self._model_initializer = model_initializer

    @property
    def raw_dimension(self):
        return [param.retrieve_raw_param() for param in self.hp_space]

    @abc.abstractmethod
    def generate_model(self, param_values):
        return

    def retrieve_actual_params(self, raw_params):
        actual_params = []
        for hp, raw_param in zip(self.hp_space, raw_params):
            actual_params.append(hp.convert_raw_param(raw_param))
        return actual_params


class HyperParameter:

    def __init__(self, name, param_range, param_type):
        self.name = name
        self._param_range = param_range
        self.param_type = param_type

    @classmethod
    def int_param(cls, name, param_range):
        return cls(name, param_range, INTEGER)

    @classmethod
    def float_param(cls, name, param_range):
        return cls(name, param_range, FLOAT)

    @classmethod
    def categorical_param(cls, name, param_range):
        return cls(name, param_range, CATEGORICAL)

    @property
    def param_bound(self):
        """Get lower bound and upper bound for a parameter

        Returns
        -------
        bound: tuple of int or tuple of float
            lower_bound and higher_bound are both inclusive if
            parameter's type is int or float
        """
        if self.param_type == CATEGORICAL:
            return 0, len(self._param_range) - 1
        else:
            return self._param_range

    def in_range(self, value):
        """Test whether the parameter's value is in a legal range

        Parameters
        ---------
        value : str or int or float
            value of parameter

        Returns
        -------
        is_in_range: bool
            True if value is in range
        """
        if self.param_type == CATEGORICAL:
            return 0 <= int(value) < len(self._param_range)
        else:
            assert len(self._param_range) == 2
            return self._param_range[0] <= value <= self._param_range[1]

    def convert_raw_param(self, raw_param):
        """Cast raw parameter value to certain type

        Parameters
        ----------
        raw_param : str or int or float
            value which can be any type

        Returns
        -------
        param : str or int or float
            casted value
        """
        if self.param_type == INTEGER:
            return int(raw_param)
        elif self.param_type == FLOAT:
            return float(raw_param)
        elif self.param_type == CATEGORICAL:
            return self._param_range[int(raw_param)]
        else:
            assert False

    def retrieve_raw_param(self):
        if self.param_type == CATEGORICAL:
            return [0, 0, CATEGORICAL, list(range(len(self._param_range)))]
        else:
            lower_bound, upper_bound = self.param_bound
            return [lower_bound, upper_bound, self.param_type, None]

    def is_int_type(self):
        return self.param_type == INTEGER

    def is_float_type(self):
        return self.param_type == FLOAT

    def is_categorical_type(self):
        return self.param_type == CATEGORICAL
