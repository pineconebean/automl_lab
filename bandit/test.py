import time

import framework.sk_models as sk
from framework.random_search import random_search
import utils.data_loader as data_loader
from bandit.model_selection import BanditModelSelection, RandomOptimization
from utils.logging_ import get_logger
import sys
import multiprocessing as mp
import pandas as pd
import pickle

BUDGET = 2
GROUND_TRUTH_PKL = 'log/ground_truth.pkl'

logger = get_logger('lab', 'bandit_test.log')

model_generators = [
    sk.DecisionTree(),
    sk.AdaBoost(),
    sk.QuadraticDiscriminantAnalysis(),
    sk.GaussianNB(),
    sk.LinearSVC(),
    sk.KNeighbors(),
    sk.BernoulliNB(),
    sk.ExtraTree(),
    sk.MultinomialNB(),
    sk.PassiveAggressive(),
    sk.RandomForest(),
    sk.SGD()
]


def find_ground_truth(data, model_generator, budget=BUDGET):
    """Find the ground truth model for each dataset

    Parameters
    ----------

    data: utils.data_loader.DataSet
        training data

    model_generator: framework.base.ModelGenerator
        generator for the target model

    budget: int
        number of samples

    Returns
    -------

    evaluation_result: (float, float, float)
        best evaluation result, mean and standard deviation

    """
    train_x, train_y = data.train_data()
    # begin sampling
    result = random_search(model_generator, train_x, train_y, search_times=budget)
    acc_column = result['Accuracy']
    return type(model_generator).__name__, acc_column.max(), acc_column.mean(), acc_column.std()


def ground_truth_lab():
    cores = mp.cpu_count()
    statistics = []
    ground_truth_model = {}
    for data in data_loader.all_data():
        # adult cost too much time so we ignore it
        if data.name == 'adult':
            continue

        start = time.time()
        with mp.Pool(processes=cores) as pool:
            result = pool.starmap(find_ground_truth, [(data, generator) for generator in model_generators])
            data_frame = pd.DataFrame(data=result, columns=['name', 'max', 'mean', 'std'])
            data_frame = data_frame.set_index(data_frame['name']).drop(['name'], axis=1)

            statistics.append((data.name, data_frame))

            best_model = data_frame['max'].idxmax()
            ground_truth_model[data.name] = best_model

            # save to csv
            with open('log/gt_{}.csv'.format(data.name), 'a') as f:
                f.write('best is {}\n'.format(best_model))
                data_frame.to_csv(f, mode='a')

        elapsed = time.time() - start
        logger.info('g-test --- Spend {}s on {}'.format(elapsed, data.name))

    with open(GROUND_TRUTH_PKL, 'wb') as f:
        pickle.dump(ground_truth_model, f)


def ucb_lab(data):
    """Do model selection by traditional ucb method

    Parameters
    ----------

    data: utils.data_loader.DataSet
        training data

    """
    import logging
    log = get_logger('ucb', 'ucb.log', level=logging.DEBUG)

    optimizations = _get_optimizations()
    model_selection = BanditModelSelection(optimizations, 'ucb')

    train_x, train_y = data.train_data()

    log.info('Begin fit on {}'.format(data.name))
    start = time.time()

    best_optimization = model_selection.fit(train_x, train_y, budget=1000)

    log.info('Done! Spend {}s'.format(time.time() - start))

    # save statistics to csv
    statistics = model_selection.statistics()
    statistics.to_csv('ucb_log/ucb_{}.csv'.format(data.name))
    # save to pickle file for calculating exploitation rate
    statistics.to_pickle('ucb_log/ucb_{}.pkl'.format(data.name))

    # record best_v, best_model, budget
    best_v = best_optimization.best_evaluation['Accuracy'][0]
    best_model = best_optimization.name
    test_v = _evaluate_test_v(data, best_optimization.best_model)

    return best_v, best_model, test_v


def proposed_lab():
    pass


def bandit_test():
    # model_generators = [m for m in inspect.getmembers(sk, inspect.isclass) if m[1].__module__ == sk.__name__]
    # filtered_models = filter(lambda p: p[0] != 'SKLearnModelGenerator' and 'SVC' not in p[0], model_generators)

    optimizations = _get_optimizations()

    # get data sets
    data_sets = [
        ('adult', data_loader.adult_dataset()),
        ('cmc', data_loader.cmc_dataset()),
        ('car', data_loader.car_dataset()),
        ('banknote', data_loader.banknote_dataset())
    ]

    # choose selection method from commandline argument
    method = sys.argv[1]

    if method == 'proposed':
        # test with the new function
        logger.info('==================Proposed Method=====================')
        theta = float(sys.argv[2])
        gamma = float(sys.argv[3])
        beta = float(sys.argv[4])

        logger.info("Set theta = {}".format(theta))
        bandit_selection = BanditModelSelection(optimizations, update_func='new', theta=theta, gamma=gamma, beta=beta)
        _do_model_selection(data_sets, bandit_selection, 'model_new_{}_{}'.format(theta, gamma),
                            'selection_new_{}_{}'.format(theta, gamma))
        logger.info('==================Proposed Method Done=====================')
    elif method == 'ucb':
        # test with traditional ucb function
        logger.info('==================Traditional UCB=====================')
        ucb_bandit_selection = BanditModelSelection(optimizations, update_func='ucb')
        _do_model_selection(data_sets, ucb_bandit_selection, 'model_ucb', 'selection_ucb')
        logger.info('==================Traditional UCB Done=====================')


def calculate_exploitation_rate(data, budget_statistics):
    """Calculate exploitation rate

    Parameters
    ----------

    budget_statistics: pandas.DataFrame
        statistics of budget

    data: utils.data_loader.DataSet
        target data set

    Returns
    -------

    exploitation_rate: float
        exploitation rate of this method

    """
    # read ground truth model information
    with open(GROUND_TRUTH_PKL, 'rb') as f:
        ground_truth_models = pickle.load(f)

    assert isinstance(ground_truth_models, dict)
    gt_model = ground_truth_models[data.name]  # get ground truth model's name
    assert isinstance(gt_model, str)

    # get budget and calculate exploitation rate
    budget = budget_statistics['budget'][gt_model]

    return budget / BUDGET


def _get_optimizations():
    return [RandomOptimization(generator, type(generator).__name__) for generator in model_generators]


def _evaluate_test_v(data, model):
    """Use selected model to fit on the data

    Parameters
    ----------

    data: utils.data_loader.DataSet
        training and test data

    model: classifier
        selected model

    Returns
    -------

    test_v: float
        accuracy on test data
    """
    train_x, train_y = data.train_data()
    model.fit(train_x, train_y)

    test_x, test_y = data.test_data()
    return model.score(test_x, test_y)


def _do_model_selection(data, strategy, model_file, selection_file):
    assert isinstance(strategy, BanditModelSelection)

    for data_name, (train_x, train_y) in data:

        logger.info('Begin bandit selection on dataset {}'.format(data_name))
        start = time.time()

        result = strategy.fit(train_x, train_y, BUDGET)
        assert isinstance(result, RandomOptimization)

        elapsed_time = time.time() - start
        logger.info('Bandit selection done, spend {}s\n\n'.format(elapsed_time))

        logger.info('Selection result: \n{}\n\n'.format(result))
        logger.info('All models information:\n{}\n\n'.format(strategy.show_models()))

        strategy.statistics().to_csv('log/{}_{}.csv'.format(model_file, data_name), mode='a')
        with open('log/{}_{}.csv'.format(selection_file, data_name), 'a') as f:
            count = 13  # used to represent selection count
            for record in strategy.param_change_info:
                f.write('t = {}'.format(count))
                record.to_csv(f, mode='a')
                f.write('\n\n')

                count += 1


if __name__ == '__main__':
    ground_truth_lab()