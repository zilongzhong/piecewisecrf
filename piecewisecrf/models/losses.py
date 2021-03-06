import tensorflow as tf

from piecewisecrf.slim import slim
import piecewisecrf.datasets.helpers.pairwise_label_generator as indices
import piecewisecrf.config.prefs as prefs

FLAGS = prefs.flags.FLAGS


def add_loss_summaries(total_loss):
    '''

    Add summaries for losses in model.

    Generates moving average for all losses and associated summaries for
    visualizing the performance of the network.

    Parameters
    ----------
    total_loss : float
        Total loss from loss()

    Returns
    -------
    loss_averages_op: tensorflow operation
        Operation for generating moving averages of losses


    '''
    # Compute the moving average of all individual losses and the total loss.
    loss_averages = tf.train.ExponentialMovingAverage(0.9, name='avg')
    losses = tf.get_collection('losses')
    loss_averages_op = loss_averages.apply(losses + [total_loss])

    # Attach a scalar summary to all individual losses and the total loss; do the
    # same for the averaged version of the losses.
    for l in losses + [total_loss]:
        # Name each loss as '(raw)' and name the moving average version of the loss
        # as the original loss name.
        tf.scalar_summary(l.op.name + ' (raw)', l)
        tf.scalar_summary(l.op.name, loss_averages.average(l))

    return loss_averages_op


def total_loss_sum(losses):
    '''

    Adds L2 regularization loss to the given list of losses

    Parameters
    ----------
    losses : list
        List of losses

    Returns
    -------
    total_loss: float
        L2 regularized loss


    '''
    # Assemble all of the losses for the current tower only.
    # Calculate the total loss for the current tower.
    regularization_losses = tf.get_collection(tf.GraphKeys.REGULARIZATION_LOSSES)
    total_loss = tf.add_n(losses + regularization_losses, name='total_loss')
    return total_loss


def neg_log_likelihood(out_unary, out_binary, out_binary_ab, labels_unary, labels_binary, labels_binary_ab,
                       batch_size, weights, weights_surr, weights_ab):
    '''

    Negative log likelihood

    Parameters
    ----------
    out_unary: tensor
        Unary scores

    out_binary: tensor
        Pairwise (surrounding neighbourhood) scores

    out_binary_ab: tensor
        Pairwise (above/below neighbourhood) scores

    labels_unary: bool
        Unary labels

    labels_binary: tensor
        Binary labels for surrounding neighbourhood

    labels_binary_ab: tensor
        Binary labels for above/below neighbourhood

    batch_size: int
        Batch size

    weights: tensor
        Class balancing weights for unary potentials

    weights_surr: tensor
        Class balancing weights for binary potentials (surrounding neighbourhood)

    weights_ab: tensor
        Class balancing weights for binary potentials (above/below neighbourhood)

    Returns
    -------
    loss_val: float
        Negative log likelihood


    '''
    print('Loss: Negative Log Likelihood Loss')
    num_examples = (batch_size * FLAGS.img_height * FLAGS.img_width //
                    FLAGS.subsample_factor // FLAGS.subsample_factor)
    num_neighbours = batch_size * indices.NUMBER_OF_NEIGHBOURS_SURR
    num_neighbours_ab = batch_size * indices.NUMBER_OF_NEIGHBOURS_AB

    with tf.op_scope([out_unary, out_binary, out_binary_ab,
                      labels_unary, labels_binary, labels_binary_ab], None, 'NegativeLogLikelyhood'):
        one_hot_labels_unary = tf.one_hot(tf.to_int64(labels_unary), FLAGS.num_classes, 1, 0)
        one_hot_labels_unary = tf.reshape(one_hot_labels_unary, [num_examples, FLAGS.num_classes])
        one_hot_labels_binary = tf.one_hot(tf.to_int64(labels_binary), FLAGS.num_classes * FLAGS.num_classes, 1, 0)
        one_hot_labels_binary = tf.reshape(one_hot_labels_binary, [num_neighbours,
                                           FLAGS.num_classes * FLAGS.num_classes])
        one_hot_labels_binary_ab = tf.one_hot(tf.to_int64(labels_binary_ab),
                                              FLAGS.num_classes * FLAGS.num_classes, 1, 0)
        one_hot_labels_binary_ab = tf.reshape(one_hot_labels_binary_ab, [num_neighbours_ab,
                                              FLAGS.num_classes * FLAGS.num_classes])

        out_unary_1d = tf.reshape(out_unary, [num_examples, FLAGS.num_classes])
        out_binary_1d = tf.reshape(out_binary, [num_neighbours, FLAGS.num_classes * FLAGS.num_classes])
        out_binary_ab_1d = tf.reshape(out_binary_ab, [num_neighbours_ab, FLAGS.num_classes * FLAGS.num_classes])

        log_softmax_unary = tf.log(tf.clip_by_value(tf.nn.softmax(out_unary_1d), 1.0e-6, 1.0))
        log_softmax_binary = tf.log(tf.clip_by_value(tf.nn.softmax(out_binary_1d), 1.0e-6, 1.0))
        log_softmax_binary_ab = tf.log(tf.clip_by_value(tf.nn.softmax(out_binary_ab_1d), 1.0e-6, 1.0))

        xent = tf.reduce_sum(tf.mul(tf.to_float(one_hot_labels_unary), log_softmax_unary), 1)
        pu = tf.mul(tf.minimum(tf.to_float(100), weights), xent)

        xent_bin = tf.reduce_sum(tf.mul(tf.to_float(one_hot_labels_binary), log_softmax_binary), 1)
        pb = tf.mul(tf.minimum(tf.to_float(100), weights_surr), xent_bin)

        xent_ab = tf.reduce_sum(tf.mul(tf.to_float(one_hot_labels_binary_ab), log_softmax_binary_ab), 1)
        pb_ab = tf.mul(tf.minimum(tf.to_float(100), weights_ab), xent_ab)

        loss_val = (tf.div(tf.reduce_sum(-pu), tf.to_float(num_examples)) +
                    tf.div(tf.reduce_sum(-pb), tf.to_float(num_neighbours)) +
                    tf.div(tf.reduce_sum(-pb_ab), tf.to_float(num_neighbours_ab)))

        tf.add_to_collection(slim.losses.LOSSES_COLLECTION, loss_val)
        return loss_val
