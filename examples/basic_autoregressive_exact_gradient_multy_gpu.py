import tensorflow
from tensorflow.keras.layers import Input
from tensorflow.keras.models import Model
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.utils import multi_gpu_model

from pyket.callbacks import TensorBoard
from pyket.callbacks.exact import default_wave_function_callbacks_factory
from pyket.machines import SimpleConvNetAutoregressive1D
from pyket.operators import Ising
from pyket.optimizers import convert_to_accumulate_gradient_optimizer
from pyket.optimization import ExactVariational, energy_gradient_loss

# with tensorflow.device('/cpu:0'):
inputs = Input(shape=(16,), dtype='int8')
convnet = SimpleConvNetAutoregressive1D(inputs, depth=7, num_of_channels=32, weights_normalization=False)
orig_model = Model(inputs=inputs, outputs=convnet.predictions)
num_of_gpu = 4
model = multi_gpu_model(orig_model, gpus=num_of_gpu)
model = orig_model
batch_size = 2 ** 12
steps_per_epoch = 500 * (2 ** 16) / batch_size

hilbert_state_shape = [16, ]
operator = Ising(h=3.0, hilbert_state_shape=hilbert_state_shape, pbc=False)
exact_generator = ExactVariational(model, operator, batch_size)

optimizer = Adam(lr=0.001, beta_1=0.9, beta_2=0.999)
convert_to_accumulate_gradient_optimizer(optimizer,
                                         update_params_frequency=exact_generator.num_of_batch_until_full_cycle,
                                         accumulate_sum_or_mean=True)
model.compile(optimizer=optimizer, loss=energy_gradient_loss)
model.summary()

# still can use monte carlo generator for estimating histograms
# tensorboard = TensorBoardWithGeneratorValidationData(log_dir='tensorboard_logs/exact_run_0', generator=monte_carlo_generator, update_freq=1, histogram_freq=1, 
#                                                      batch_size=batch_size, write_output=False)
tensorboard = TensorBoard(log_dir='tensorboard_logs/exact_run_2')

callbacks = default_wave_function_callbacks_factory(exact_generator,
                                                    true_ground_state_energy=-49.257706531889006) + [tensorboard]
model.fit_generator(exact_generator, steps_per_epoch=steps_per_epoch, epochs=80, callbacks=callbacks, max_queue_size=0,
                    workers=0)
orig_model.save_weights('exact_multy.h5')