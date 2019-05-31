import pytest
import numpy as np
import tensorflow as tf
from tensorflow.keras.optimizers import Adam

from pyket.callbacks.exact import ExactLocalEnergy
from pyket.callbacks.monte_carlo import LocalEnergyStats
from pyket.evaluation import evaluate, exact_evaluate
from pyket.operators import Heisenberg, NetketOperatorWrapper
from pyket.optimization import ExactVariational, VariationalMonteCarlo, loss_for_energy_minimization
from pyket.samplers import ExactSampler
from .simple_models import complex_values_linear_1d_model, real_values_1d_model

DEFAULT_TF_GRAPH = tf.get_default_graph()
ONE_DIM_OPERATOR = Heisenberg(hilbert_state_shape=[7], pbc=True)


@pytest.mark.parametrize('model_builder, operator, batch_size, num_of_mc_iterations', [
    (real_values_1d_model, ONE_DIM_OPERATOR, 2 ** 10, 1000),
    (complex_values_linear_1d_model, ONE_DIM_OPERATOR, 2 ** 10, 1000),
])
def test_exact_and_monte_carlo_agree(model_builder, operator, batch_size, num_of_mc_iterations):
    with DEFAULT_TF_GRAPH.as_default():
        model = model_builder()
        exact_variational = ExactVariational(model, operator, batch_size)
        reduce_variance(exact_variational, model)
        sampler = ExactSampler(exact_variational, batch_size)
        variational_monte_carlo = VariationalMonteCarlo(model, operator, sampler)
        exact_logs = exact_evaluate(exact_variational,
                                    [ExactLocalEnergy(exact_variational)])
        exact_energy = exact_logs['energy/energy']
        monte_carlo_energy = evaluate(variational_monte_carlo, num_of_mc_iterations,
                                      [LocalEnergyStats(variational_monte_carlo)])['energy/energy']
        monte_carlo_std = np.sqrt(exact_logs['energy/local_energy_variance'] / (batch_size * num_of_mc_iterations))
        assert monte_carlo_energy == pytest.approx(exact_energy, monte_carlo_std)


def reduce_variance(exact_variational, model):
    optimizer = Adam(lr=0.01, beta_1=0.9, beta_2=0.999)
    model.compile(optimizer=optimizer, loss=loss_for_energy_minimization)
    model.fit_generator(exact_variational.to_generator(),
                        steps_per_epoch=1000, epochs=1, max_queue_size=0,
                        workers=0)


def test_monte_carlo_and_netket_agree(netket):
    input_size = 7
    batch_size = 1000
    num_of_mc_iterations = 1000
    g = netket.graph.Hypercube(length=input_size, n_dim=1)
    hi = netket.hilbert.Spin(s=0.5, graph=g)
    ha = netket.operator.Heisenberg(hilbert=hi)
    layers = (
        netket.layer.FullyConnected(
            input_size=input_size,
            output_size=1),
    )
    ma = netket.machine.FFNN(hi, layers)
    sa = netket.sampler.ExactSampler(machine=ma)
    op = netket.optimizer.Sgd(learning_rate=0.00)

    pyket_model = complex_values_linear_1d_model()
    exact_variational = ExactVariational(pyket_model,
                                         NetketOperatorWrapper(ha, (input_size,)), batch_size)
    exact_logs = exact_evaluate(exact_variational,
                                [ExactLocalEnergy(exact_variational)])
    real_weights, imag_weights = pyket_model.get_weights()
    ma.parameters = (real_weights + imag_weights * -1j).flatten()
    gs = netket.variational.Vmc(
        hamiltonian=ha,
        sampler=sa,
        optimizer=op,
        method='Gd',
        n_samples=batch_size,
        diag_shift=0.01)
    netket_energy = np.zeros((num_of_mc_iterations,))
    for i in range(num_of_mc_iterations):
        gs.advance(1)
        netket_energy[i] = gs.get_observable_stats()['Energy']['Mean']
    netket_energy_mean = np.mean(netket_energy)
    exact_energy = exact_logs['energy/energy']
    monte_carlo_std = np.sqrt(exact_logs['energy/local_energy_variance'] / (batch_size * num_of_mc_iterations))
    assert netket_energy_mean == pytest.approx(exact_energy, monte_carlo_std)
