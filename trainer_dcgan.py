# %% 
"""
Wasserstein Divergence for GANs
"""
import os 
import time
import torch
import datetime

import torch.nn as nn 
import torchvision

import numpy as np

from models.wgan_div import Generator, Discriminator
from utils.utils import *

# %%
class Trainer_dcgan(object):
    def __init__(self, data_loader, config):
        super(Trainer_dcgan, self).__init__()

        # data loader 
        self.data_loader = data_loader

        # exact model and loss 
        self.model = config.model

        # model hyper-parameters
        self.imsize = config.img_size 
        self.g_num = config.g_num
        self.z_dim = config.z_dim
        self.channels = config.channels
        self.g_conv_dim = config.g_conv_dim
        self.d_conv_dim = config.d_conv_dim

        self.epochs = config.epochs
        self.batch_size = config.batch_size
        self.num_workers = config.num_workers 

        self.g_lr = config.g_lr
        self.d_lr = config.d_lr 
        self.beta1 = config.beta1
        self.beta2 = config.beta2

        self.pretrained_model = config.pretrained_model

        self.dataset = config.dataset 
        self.use_tensorboard = config.use_tensorboard

        # path
        self.image_path = config.dataroot 
        self.log_path = config.log_path
        self.sample_path = config.sample_path
        self.version = config.version

        # step 
        self.log_step = config.log_step
        self.sample_step = config.sample_step
        self.model_save_step = config.model_save_step

        # path with version
        self.log_path = os.path.join(config.log_path, self.version)
        self.sample_path = os.path.join(config.sample_path, self.version)
        self.model_save_path = os.path.join(config.model_save_path, self.version)

        if self.use_tensorboard:
            self.build_tensorboard()

        self.build_model()

    def train(self):
        '''
        Training
        '''

        # fixed input for debugging
        # for the 10x10 output image
        fixed_z = tensor2var(torch.randn(100, self.z_dim)) # （*, 100）

        for epoch in range(self.epochs):
            # start time
            start_time = time.time()

            for i, (real_images, _) in enumerate(self.data_loader):
                # Requires grad, Generator requires_grad = False
                for p in self.D.parameters():
                    p.requires_grad = True

                # configure input 
                real_images = tensor2var(real_images, grad=True) # for wgan-div to compute grad
                
                self.D.train()
                self.G.train()
                # ==================== Train D ==================
                # train D more iterations than G

                self.D.zero_grad()

                # compute loss with real images 
                d_out_real = self.D(real_images)

                d_loss_real = - torch.mean(d_out_real)
        
                # noise z for generator
                z = tensor2var(torch.randn(real_images.size(0), self.z_dim)) # 64, 100

                fake_images = self.G(z) # (*, c, 64, 64)
                d_out_fake = self.D(fake_images) # (*,)

                d_loss_fake = torch.mean(d_out_fake)
               
                # total d loss
                d_loss = d_loss_real + d_loss_fake

                # for the wgan-div loss function
                grad = compute_gradient_penalty_div(d_out_real, d_out_fake, real_images, fake_images)
                d_loss = d_loss + grad

                d_loss.backward()
                # update D
                self.d_optimizer.step()

                # train the generator every 5 steps
                if i % self.g_num == 0:

                    # =================== Train G and gumbel =====================
                    for p in self.D.parameters():
                        p.requires_grad = False  # to avoid computation

                    self.G.zero_grad()
                    # create random noise 
                    fake_images = self.G(z)

                    # compute loss with fake images 
                    g_out_fake = self.D(fake_images) # batch x n

                    g_loss_fake = - torch.mean(g_out_fake)
                  
                    g_loss_fake.backward()
                    # update G
                    self.g_optimizer.step()

            # log to the tensorboard
            self.logger.add_scalar('d_loss', d_loss.data, epoch)
            self.logger.add_scalar('g_loss', g_loss_fake.data, epoch)
            # end one epoch

            # print out log info
            if (epoch) % self.log_step == 0:
                elapsed = time.time() - start_time
                elapsed = str(datetime.timedelta(seconds=elapsed))
                print("Elapsed [{}], G_step [{}/{}], D_step[{}/{}], d_loss: {:.4f}, g_loss: {:.4f}, "
                    .format(elapsed, epoch, self.epochs, epoch,
                            self.epochs, d_loss.item(), g_loss_fake.item()))

            # sample images 
            if (epoch) % self.sample_step == 0:
                self.G.eval()
                # save real image
                save_sample(self.sample_path + '/real_images/', real_images, epoch)
                
                with torch.no_grad():
                    fake_images = self.G(fixed_z)
                    # save fake image 
                    save_sample(self.sample_path + '/fake_images/', fake_images, epoch)
                    
                # sample sample one images
                # for the FID score
                # self.number = save_sample_one_image(self.sample_path, real_images, fake_images, epoch)

            if (epoch) % self.model_save_step == 0:
                torch.save({
                    'epoch': epoch, 
                    'G_state_dict': self.G.state_dict(),
                    'g_loss': g_loss_fake,
                    'D_state_dict': self.D.state_dict(),
                    'd_loss': d_loss,
                },
                os.path.join(self.model_save_path, '{}.pth.tar'.format(epoch))
                )



    def build_model(self):

        self.G = Generator(image_size = self.imsize, z_dim = self.z_dim, conv_dim = self.g_conv_dim, channels = self.channels).cuda()
        self.D = Discriminator(image_size = self.imsize, conv_dim = self.d_conv_dim, channels = self.channels).cuda()

        # apply the weights_init to randomly initialize all weights
        # to mean=0, stdev=0.2
        self.G.apply(weights_init)
        self.D.apply(weights_init)
        
        # optimizer 
        self.g_optimizer = torch.optim.Adam(self.G.parameters(), self.g_lr, [self.beta1, self.beta2])
        self.d_optimizer = torch.optim.Adam(self.D.parameters(), self.d_lr, [self.beta1, self.beta2])

        # print networks
        print(self.G)
        print(self.D)

    def build_tensorboard(self):
        from torch.utils.tensorboard import SummaryWriter
        self.logger = SummaryWriter(self.log_path)
