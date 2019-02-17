import time

import framework.sk_models as sk
from framework.random_search import random_search
import utils.data_loader as data_loader
from bandit.model_selection import BanditModelSelection, RandomOptimization, EpsilonGreedySelection, SoftMaxSelection
from utils.logging_ import get_logger
import sys
import multiprocessing as mp
import pandas as pd
import pickle
from logging import INFO, DEBUG

BUDGET = 20
GROUND_TRUTH_PKL = 'log/ground_truth.pkl'
CORES = mp.cpu_count()

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
    model_name = type(model_generator).__name__
    start = time.time()
    log = get_logger('gt.model', '', level=INFO)
    log.info('{} --- {} start fitting'.format(data.name, model_name))

    # begin sampling
    result = random_search(model_generator, train_x, train_y, search_times=budget)

    log.info('{} --- {} end running, spend {}s'.format(data.name, model_name, time.time() - start))
    acc_column = result['Accuracy']
    return model_name, acc_column.max(), acc_column.mean(), acc_column.std()


def ground_truth_lab():
    statistics = []
    ground_truth_model = {}
    log = get_logger('gt', 'log/gt.log', level=INFO)
    for data in data_loader.all_data():
        # adult cost too much time so we ignore it
        if data.name == 'adult':
            continue

        start = time.time()
        log.info('Start finding ground truth model for data set {}'.format(data.name))

        with mp.Pool(processes=CORES) as pool:
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
        log.info('g-test --- Fitting on {} is over, spend {}s'.format(data.name, elapsed))

    with open(GROUND_TRUTH_PKL, 'wb') as f:
        pickle.dump(ground_truth_model, f)


def ucb_lab(method):
    all_data = data_loader.all_data()
    with mp.Pool(processes=CORES) as pool:
        result = pool.starmap(ucb_or_random_method, [(data, method) for data in all_data])
        df_result = pd.DataFrame(data=result, columns=['data set', 'best_v', 'best_model', 'test_v'])
        df_result.to_csv('log/{}_lab.csv'.format(method))
        df_result.to_pickle('log/{}_lab.pkl'.format(method))


def eg_or_sf_lab(method, record_file):
    all_data = data_loader.all_data()
    with mp.Pool(processes=CORES) as pool:
        result = pool.map(method, all_data)
        df_result = pd.DataFrame(data=result, columns=['data set', 'best_v', 'best_model', 'test_v'])
        df_result.to_csv('log/{}_lab.csv'.format(record_file))
        df_result.to_pickle('log/{}_lab.pkl'.format(record_file))


def ucb_or_random_method(data, method):
    """Do model selection by traditional ucb method

    Parameters
    ----------

    data: utils.data_loader.DataSet
        training data

    method: str
        model selection method (only ucb or random can be chosen)

    """
    log = get_logger(method, 'log/{}/{}.log'.format(method, method), level=DEBUG)

    optimizations = _get_optimizations()
    model_selection = BanditModelSelection(optimizations, method)

    log.info('Begin fit on {}'.format(data.name))
    train_x, train_y = data.train_data()

    start = time.time()

    best_optimization = model_selection.fit(train_x, train_y, budget=BUDGET)

    log.info('Fitting no {} is done! Spend {}s'.format(data.name, time.time() - start))

    csv_file = 'log/{}/{}_{}.csv'.format(method, method, data.name)
    pkl_file = 'log/{}/{}_{}.pkl'.format(method, method, data.name)
    return _get_test_result(best_optimization, data, model_selection.statistics(), csv_file, pkl_file, log)


def proposed_lab():
    theta = float(sys.argv[2])
    gamma = float(sys.argv[3])
    beta = float(sys.argv[4])

    all_data = data_loader.all_data()[0:2]
    with mp.Pool(processes=CORES) as pool:
        result = pool.starmap(proposed_method, [(data, theta, gamma, beta) for data in all_data])
        df_result = pd.DataFrame(data=result, columns=['data set', 'best_v', 'best_model', 'test_v'])
        df_result.to_csv('log/proposed/proposed_{}_{}_{}.csv'.format(theta, gamma, beta))
        df_result.to_pickle('log/proposed/proposed_{}_{}_{}.pkl'.format(theta, gamma, beta))


def proposed_method(data, theta, gamma, beta):
    """Do model selection with proposed method

    Parameters
    ----------
    data: utils.data_loader.DataSet
        training data

    theta: float

    gamma: float

    beta: float
    """
    log_name = 'proposed-{}-{}-{}'.format(theta, gamma, beta)
    log = get_logger(log_name, 'log/proposed/' + log_name + '.log', level=DEBUG)

    optimizations = _get_optimizations()
    model_selection = BanditModelSelection(optimizations, 'new', theta=theta, gamma=gamma, beta=beta)

    log.info('Begin fit on {}'.format(data.name))
    train_x, train_y = data.train_data()

    start = time.time()
    best_optimization = model_selection.fit(train_x, train_y, budget=BUDGET)

    log.info('Fitting on {} is over, spend {}s'.format(data.name, time.time() - start))

    csv_file = 'log/proposed/proposed_{}_{}_{}_{}.csv'.format(theta, gamma, beta, data.name)
    pkl_file = 'log/proposed/proposed_{}_{}_{}_{}.pkl'.format(theta, gamma, beta, data.name)

    return _get_test_result(best_optimization, data, model_selection.statistics(), csv_file, pkl_file, log)


def eg_method(data):
    """Do model selection with epsilon-greedy method

    Parameters
    ----------
    data: utils.data_loader.DataSet
        training data

    """

    log = get_logger('epsilon-greedy', 'log/eg/epsilon-greedy.log', level=DEBUG)

    optimizations = _get_optimizations()
    model_selection = EpsilonGreedySelection(optimizations)

    log.info('Begin fitting on {}'.format(data.name))
    train_x, train_y = data.train_data()

    start = time.time()
    best_optimization = model_selection.fit(train_x, train_y, budget=BUDGET)
    elapsed = time.time() - start

    log.info('Fitting on {} is over, spend {}s'.format(data.name, elapsed))

    csv_file = 'log/eg/eg_{}.csv'.format(data.name)
    pkl_file = 'log/eg/eg_{}.pkl'.format(data.name)

    return _get_test_result(best_optimization, data, model_selection.statistics(), csv_file, pkl_file, log)


def softmax_method(data):
    """Do model selection with softmax method

    Parameters
    ----------
    data: utils.data_loader.DataSet
        training data

    """

    log = get_logger('softmax', 'log/sf/softmax.log', level=DEBUG)

    optimizations = _get_optimizations()
    model_selection = SoftMaxSelection(optimizations)

    log.info('Begin fitting on {}'.format(data.name))
    train_x, train_y = data.train_data()

    start = time.time()
    best_optimization = model_selection.fit(train_x, train_y, temperature=0.5, budget=BUDGET)
    elapsed = time.time() - start

    log.info('Fitting on {} is over, spend {}s'.format(data.name, elapsed))

    csv_file = 'log/sf/sf_{}.csv'.format(data.name)
    pkl_file = 'log/sf/sf_{}.pkl'.format(data.name)

    return _get_test_result(best_optimization, data, model_selection.statistics(), csv_file, pkl_file, log)


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


def _get_test_result(best_optimization, data, statistics, csv_file, pkl_file, log):
    # save statistics to csv
    statistics.to_csv(csv_file)
    # save to pickle file for calculating exploitation rate
    statistics.to_pickle(pkl_file)

    # return best_v, best_model, budget
    print(best_optimization.best_evaluation)
    best_v = best_optimization.best_evaluation['Accuracy']
    best_model = best_optimization.name
    test_v = _evaluate_test_v(data, best_optimization.best_model)

    log.info('\n===========================\n'
             'Result of fitting on {}\n'
             'best v: {}\n'
             'best model: {}\n'
             'test v: {}\n'
             '======================'
             .format(data.name, best_v, best_model, test_v))

    return data.name, best_v, best_model, test_v


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


if __name__ == '__main__':
    method_choice = sys.argv[1]
    if method_choice == 'ground':
        ground_truth_lab()
    elif method_choice == 'ucb':
        ucb_lab('ucb')
    elif method_choice == 'sf':
        eg_or_sf_lab(softmax_method, 'sf')
    elif method_choice == 'eg':
        eg_or_sf_lab(eg_method, 'eg')
    elif method_choice == 'random':
        ucb_lab('random')
    elif method_choice == 'proposed':
        proposed_lab()
