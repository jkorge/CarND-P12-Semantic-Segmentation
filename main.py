#!/usr/bin/env python3
import os.path
import tensorflow as tf
import helper
import warnings
from distutils.version import LooseVersion
import project_tests as tests


# Check TensorFlow Version
assert LooseVersion(tf.__version__) >= LooseVersion('1.0'), 'Please use TensorFlow version 1.0 or newer.  You are using {}'.format(tf.__version__)
print('TensorFlow Version: {}'.format(tf.__version__))

# Check for a GPU
if not tf.test.gpu_device_name():
    warnings.warn('No GPU found. Please use a GPU to train your neural network.')
else:
    print('Default GPU Device: {}'.format(tf.test.gpu_device_name()))


def load_vgg(sess, vgg_path):
    """
    Load Pretrained VGG Model into TensorFlow.
    :param sess: TensorFlow Session
    :param vgg_path: Path to vgg folder, containing "variables/" and "saved_model.pb"
    :return: Tuple of Tensors from VGG model (image_input, keep_prob, layer3_out, layer4_out, layer7_out)
    """
    vgg_tag = 'vgg16'
    vgg_input_tensor_name = 'image_input:0'
    vgg_keep_prob_tensor_name = 'keep_prob:0'
    vgg_layer3_out_tensor_name = 'layer3_out:0'
    vgg_layer4_out_tensor_name = 'layer4_out:0'
    vgg_layer7_out_tensor_name = 'layer7_out:0'

    # Load vgg model
    tf.saved_model.loader.load(sess, [vgg_tag], vgg_path)
    graph = tf.get_default_graph()

    # Get tensors by names vgg_*
    w_in = graph.get_tensor_by_name(vgg_input_tensor_name)
    keep_prob = graph.get_tensor_by_name(vgg_keep_prob_tensor_name)
    w_3 = graph.get_tensor_by_name(vgg_layer3_out_tensor_name)
    w_4 = graph.get_tensor_by_name(vgg_layer4_out_tensor_name)
    w_7 = graph.get_tensor_by_name(vgg_layer7_out_tensor_name)
    
    return w_in, keep_prob, w_3, w_4, w_7

# tests.test_load_vgg(load_vgg, tf)


def layers(vgg_layer3_out, vgg_layer4_out, vgg_layer7_out, num_classes):
    """
    Create the layers for a fully convolutional network.  Build skip-layers using the vgg layers.
    :param vgg_layer3_out: TF Tensor for VGG Layer 3 output
    :param vgg_layer4_out: TF Tensor for VGG Layer 4 output
    :param vgg_layer7_out: TF Tensor for VGG Layer 7 output
    :param num_classes: Number of classes to classify
    :return: The Tensor for the last layer of output
    """
    
    # 1x1 Convolution
    layer7_conv11 = tf.layers.conv2d(vgg_layer7_out, num_classes, 1, padding='SAME',
    	kernel_initializer=tf.initializers.random_normal(stddev=0.01),
    	kernel_regularizer=tf.contrib.layers.l2_regularizer(1e-3))

    # 2x2 Upsample
    layer7_deconv = tf.layers.conv2d_transpose(layer7_conv11, num_classes, 4, 2, padding='SAME',
    	kernel_initializer=tf.initializers.random_normal(stddev=0.01),
    	kernel_regularizer=tf.contrib.layers.l2_regularizer(1e-3))

    # Add skip layer (output of 1x1 conv applied to pooling at layer 4)
    layer4_conv11 = tf.layers.conv2d(vgg_layer4_out, num_classes, 1, padding='SAME',
    	kernel_initializer=tf.initializers.random_normal(stddev=0.01),
    	kernel_regularizer=tf.contrib.layers.l2_regularizer(1e-3))
    layer47_add = tf.add(layer7_deconv, layer4_conv11)

    # 2x2 Upsample
    layer47_deconv = tf.layers.conv2d_transpose(layer47_add, num_classes, 4, 2, padding='SAME',
    	kernel_initializer=tf.initializers.random_normal(stddev=0.01),
    	kernel_regularizer=tf.contrib.layers.l2_regularizer(1e-3))

    # Add skip layer (output of 1x1 conv applied to pooling at layer 3)
    layer3_conv11 = tf.layers.conv2d(vgg_layer3_out, num_classes, 1, padding='SAME',
    	kernel_initializer=tf.initializers.random_normal(stddev=0.01),
    	kernel_regularizer=tf.contrib.layers.l2_regularizer(1e-3))
    layer347_add = tf.add(layer47_deconv, layer3_conv11)

    # 8x8 Upsample
    nn_last_layer = tf.layers.conv2d_transpose(layer3_conv11, num_classes, 16, 8, padding='SAME',
    	kernel_initializer=tf.initializers.random_normal(stddev=0.01),
    	kernel_regularizer=tf.contrib.layers.l2_regularizer(1e-3))

    return nn_last_layer


# tests.test_layers(layers)


def optimize(nn_last_layer, correct_label, learning_rate, num_classes):
    """
    Build the TensorFLow loss and optimizer operations.
    :param nn_last_layer: TF Tensor of the last layer in the neural network
    :param correct_label: TF Placeholder for the correct label image
    :param learning_rate: TF Placeholder for the learning rate
    :param num_classes: Number of classes to classify
    :return: Tuple of (logits, train_op, cross_entropy_loss)
    """

    # Reshape logits & labels
    logits = tf.reshape(nn_last_layer, (-1, num_classes))
    correct_label = tf.reshape(correct_label, (-1, num_classes))

    # Compute cross entropy loss
    cross_entropy_loss = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits_v2(logits=logits, labels=correct_label))

    # Add loss from regularizers
    reg_loss = tf.get_collection(tf.GraphKeys.REGULARIZATION_LOSSES)
    total_loss = cross_entropy_loss + sum(reg_loss)

    # Optimize w/ AdamOptimizer
    optimizer = tf.train.AdamOptimizer(learning_rate=learning_rate)
    train_op = optimizer.minimize(total_loss)

    return logits, cross_entropy_loss, train_op

# tests.test_optimize(optimize)


def train_nn(sess, epochs, batch_size, get_batches_fn, train_op, cross_entropy_loss, input_image,
             correct_label, keep_prob, learning_rate):
    """
    Train neural network and print out the loss during training.
    :param sess: TF Session
    :param epochs: Number of epochs
    :param batch_size: Batch size
    :param get_batches_fn: Function to get batches of training data.  Call using get_batches_fn(batch_size)
    :param train_op: TF Operation to train the neural network
    :param cross_entropy_loss: TF Tensor for the amount of loss
    :param input_image: TF Placeholder for input images
    :param correct_label: TF Placeholder for label images
    :param keep_prob: TF Placeholder for dropout keep probability
    :param learning_rate: TF Placeholder for learning rate
    """
    
    # Initializer varaibles
    sess.run(tf.global_variables_initializer())

    print("Training...\n")

    for epoch in range(epochs):
    	print("EPOCH {}\n".format(epoch+1))
    	for image, label in get_batches_fn(batch_size):
    		_, loss = sess.run([train_op, cross_entropy_loss],feed_dict={input_image:image, correct_label:label,keep_prob:0.5, learning_rate:0.0001})
    	print("Loss = {:.3f}\n".format(loss))
    return

# tests.test_train_nn(train_nn)


def run():
    num_classes = 2
    image_shape = (160, 576)
    data_dir = './data'
    runs_dir = './runs'
    tests.test_for_kitti_dataset(data_dir)

    # Download pretrained vgg model
    helper.maybe_download_pretrained_vgg(data_dir)

    # OPTIONAL: Train and Inference on the cityscapes dataset instead of the Kitti dataset.
    # You'll need a GPU with at least 10 teraFLOPS to train on.
    #  https://www.cityscapes-dataset.com/

    with tf.Session() as sess:
        # Path to vgg model
        vgg_path = os.path.join(data_dir, 'vgg')
        # Create function to get batches
        get_batches_fn = helper.gen_batch_function(os.path.join(data_dir, 'data_road/training'), image_shape)

        # OPTIONAL: Augment Images for better results
        #  https://datascience.stackexchange.com/questions/5224/how-to-prepare-augment-images-for-neural-network

        # Build NN using load_vgg, layers, and optimize function
        epochs = 50
        batch_size = 3

        correct_label = tf.placeholder(tf.int32, [None, None, None, num_classes], name='correct_label')
        learning_rate = tf.placeholder(tf.float32, name='learning_rate')


        input_image, keep_prob, vgg_layer3_out, vgg_layer4_out, vgg_layer7_out = load_vgg(sess, vgg_path)

        nn_last_layer = layers(vgg_layer3_out, vgg_layer4_out, vgg_layer7_out, num_classes)

        logits, cross_entropy_loss, train_op = optimize(nn_last_layer, correct_label, learning_rate, num_classes)

        # Train NN using the train_nn function
        train_nn(sess, epochs, batch_size, get_batches_fn, train_op, cross_entropy_loss, input_image, correct_label, keep_prob, learning_rate)

        # TODO: Save inference data using helper.save_inference_samples
        helper.save_inference_samples(runs_dir, data_dir, sess, image_shape, logits, keep_prob, input_image)

        # OPTIONAL: Apply the trained model to a video


if __name__ == '__main__':
    run()
