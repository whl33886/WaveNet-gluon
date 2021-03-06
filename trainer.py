# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""
Module: WaveNet trainer modulep
"""
import sys
import numpy as np
import mxnet as mx
from mxnet import gluon, autograd, nd
from tqdm import trange

from models import WaveNet
from utils import decode_mu_law
from data_loader import load_wav, data_generation, data_generation_sample
# pylint: disable=invalid-name, too-many-arguments, too-many-instance-attributes, no-member, no-self-use
# set gpu count
def setting_ctx(use_gpu):
    """
    Description : setting cpu/gpu
    """
    if use_gpu:
        ctx = mx.gpu()
    else:
        ctx = mx.cpu()
    return ctx

class Train():
    """
    Description : Trainer for WaveNet
    """
    def __init__(self, config):
        ##setting hyper-parameters
        self.batch_size = config.batch_size
        self.epoches = config.epoches
        self.mu = config.mu
        self.n_residue = config.n_residue
        self.n_skip = config.n_skip
        self.dilation_depth = config.dilation_depth
        self.n_repeat = config.n_repeat
        self.seq_size = config.seq_size
        self.use_gpu = config.use_gpu
        self.ctx = setting_ctx(self.use_gpu)
        self.build_model()

    def build_model(self):
        """
        Description : module for building network
        """
        self.net = WaveNet(mu=self.mu, n_residue=self.n_residue, n_skip=self.n_skip,\
         dilation_depth=self.dilation_depth, n_repeat=self.n_repeat)
        #parameter initialization
        self.net.collect_params().initialize(ctx=self.ctx)
        #set optimizer
        self.trainer = gluon.Trainer(self.net.collect_params(), optimizer='adam',\
        optimizer_params={'learning_rate':0.01})
        self.loss_fn = gluon.loss.SoftmaxCrossEntropyLoss()

    def save_model(self, epoch, current_loss):
        """
        Description : module for saving network
        """
        filename = 'models/best_perf_epoch_'+str(epoch)+"_loss_"+str(current_loss)
        self.net.save_params(filename)

    def train(self):
        """
        Description : module for running train
        """
        fs, data = load_wav('parametric-2.wav')
        g = data_generation(data, fs, mu=self.mu, seq_size=self.seq_size, ctx=self.ctx)

        loss_save = []
        best_loss = sys.maxsize
        for epoch in trange(self.epoches):
            loss = 0.0
            for _ in range(self.batch_size):
                batch = next(g)
                x = batch[:-1]
                with autograd.record():
                    logits = self.net(x)
                    sz = logits.shape[0]
                    loss = loss + self.loss_fn(logits, batch[-sz:])
                loss.backward()
                self.trainer.step(1, ignore_stale_grad=True)
            loss_save.append(nd.sum(loss).asscalar()/self.batch_size)

            #save the best model
            current_loss = nd.sum(loss).asscalar()/self.batch_size
            if best_loss > current_loss:
                print('epoch {}, loss {}'.format(epoch, nd.sum(loss).asscalar()/self.batch_size))
                self.save_model(epoch, current_loss)
                best_loss = current_loss

    def generate_slow(self, x, models, dilation_depth, n_repeat, ctx, n=100):
        """
        Description : module for generation core
        """
        dilations = [2**i for i in range(dilation_depth)] * n_repeat
        res = list(x.asnumpy())
        for _ in trange(n):
            x = nd.array(res[-sum(dilations)-1:], ctx=ctx)
            y = models(x)
            res.append(y.argmax(1).asnumpy()[-1])
        return res

    def generation(self):
        """
        Description : module for generation
        """
        fs, data = load_wav('parametric-2.wav')
        initial_data = data_generation_sample(data, fs, mu=self.mu, seq_size=3000, ctx=self.ctx)
        gen_rst = self.generate_slow(initial_data[0:3000], self.net, dilation_depth=10,\
         n_repeat=2, n=2000, ctx=self.ctx)
        gen_wav = np.array(gen_rst)
        gen_wav = decode_mu_law(gen_wav, 128)
        np.save("wav.npy", gen_wav)
