# -*- coding: utf-8 -*-
# @Author: lidong
# @Date:   2018-03-18 13:41:34
# @Last Modified by:   yulidong
# @Last Modified time: 2018-11-17 02:56:15
import sys
import torch
import visdom
import argparse
import numpy as np
import time
import torch.nn as nn
import torch.nn.functional as F
import torchvision.models as models

from torch.autograd import Variable
from torch.utils import data
from tqdm import tqdm
import torch.nn.functional as F
from cmf.models import get_model
from cmf.loader import get_loader, get_data_path
from cmf.loss import *
import os
import cv2
def train(args):
    torch.backends.cudnn.benchmark=True
    # Setup Augmentations

    loss_rec=[0]
    best_error=2
    # Setup Dataloader
    data_loader = get_loader(args.dataset)
    data_path = get_data_path(args.dataset)
    t_loader = data_loader(data_path, is_transform=True,
                           split='test', img_size=(args.img_rows, args.img_cols))
    v_loader = data_loader(data_path, is_transform=True,
                           split='test', img_size=(args.img_rows, args.img_cols))
    valloader = data.DataLoader(
        v_loader, batch_size=args.batch_size, num_workers=1, shuffle=False)
    train_length=t_loader.length//2
    test_length=v_loader.length//2
    trainloader = data.DataLoader(
        t_loader, batch_size=args.batch_size, num_workers=1, shuffle=True)
    valloader = data.DataLoader(
        v_loader, batch_size=args.batch_size, num_workers=1, shuffle=False)



    # Setup Model
    model = get_model(args.arch)
    # parameters=model.named_parameters()
    # for name,param in parameters:
    #     print(name)
    #     print(param.grad)
    # exit()

    model = torch.nn.DataParallel(
        model, device_ids=[0])
    #model = torch.nn.DataParallel(model, device_ids=[0])
    model.cuda(0)

    # Check if model has custom optimizer / loss
    # modify to adam, modify the learning rate
    # optimizer = torch.optim.Adam(
    #     model.parameters(), lr=args.l_rate,betas=(0.9,0.999))
    optimizer = torch.optim.SGD(
        model.parameters(), lr=args.l_rate,momentum=0.90, weight_decay=5e-5)
    # optimizer = torch.optim.Adam(
    #     model.parameters(), lr=args.l_rate,weight_decay=5e-4,betas=(0.9,0.999),amsgrad=True)
    loss_fn = l1
    trained=0
    scale=100

    if args.resume is not None:
        if os.path.isfile(args.resume):
            print("Loading model and optimizer from checkpoint '{}'".format(args.resume))
            checkpoint = torch.load(args.resume)
            #model_dict=model.state_dict()  
            #opt=torch.load('/home/lidong/Documents/cmf/cmf/exp1/l2/sgd/log/83/rsnet_nyu_best_model.pkl')
            model.load_state_dict(checkpoint['model_state'])
            optimizer.load_state_dict(checkpoint['optimizer_state'])
            #opt=None
            print("Loaded checkpoint '{}' (epoch {})"
                  .format(args.resume, checkpoint['epoch']))
            trained=checkpoint['epoch']
            trained=0
            best_error=5
            # loss_rec=np.load('/home/lidong/Documents/CMF/loss_8.npy')
            # loss_rec=list(loss_rec)
            # print(train_length)
            # loss_rec=loss_rec[:train_length*trained]
            
    else:
        print("No checkpoint found at '{}'".format(args.resume))
        print('Initialize from resnet34!')
        resnet34=torch.load('/home/lidong/Documents/CMF/9_cm_sub_4_flying3d_best_model.pkl')
        #optimizer.load_state_dict(resnet34['optimizer_state'])
        #model
        #model.load_state_dict(resnet34['state_dict'])
        model_dict=model.state_dict()            
        pre_dict={k: v for k, v in resnet34['model_state'].items() if k in model_dict}
        key=[]
        for k,v in pre_dict.items():
            if v.shape!=model_dict[k].shape:
                key.append(k)
        for k in key:
            pre_dict.pop(k)
        model_dict.update(pre_dict)
        model.load_state_dict(model_dict)
        #optimizer
        # opti_dict=optimizer.state_dict()
        # pre_dict={k: v for k, v in resnet34['optimizer_state'].items() if k in opti_dict}
        # # for k,v in pre_dict.items():
        # #     print(k)
        # #     if k=='state':
        # #         for a,b in v.items():
        # #             print(a)
        # #             for c,d in b.items():
        # #                 print(c,d)            
        # exit()
        # #pre_dict=resnet34['optimizer_state']
        # opti_dict.update(pre_dict)
        # optimizer.load_state_dict(opti_dict)
        print('load success!')
        trained=0



    #best_error=5
    # it should be range(checkpoint[''epoch],args.n_epoch)

    print('training!')
    model.eval()
    loss_3_rec=[]
    ones=torch.ones(1).cuda(0)
    zeros=torch.zeros(1).cuda(0)
    for i, (left, right,disparity,image,index) in enumerate(trainloader):
        #break
        with torch.no_grad():

            start_time=time.time()
            left = left.cuda(0)
            right = right.cuda(0)
            disparity = disparity.cuda(0)
            image=image.cuda(0)
            mask = (disparity < 192) & (disparity >0)
            mask.detach_()
            optimizer.zero_grad()
            #print(P.shape)
            output1, output2, output3 = model(left,right)
            #print(output3.shape)
            # output1 = torch.squeeze(output1, 1)

            output1 = torch.squeeze(output1, 1)
            output2 = torch.squeeze(output2, 1)
            output3 = torch.squeeze(output3, 1)
            loss = F.l1_loss(output3[mask], disparity[mask],reduction='elementwise_mean')
            pre = disparity.data.cpu().numpy().astype('uint8')[0,...][:,:-36]
            print(pre.shape)
            cv2.imwrite(os.path.join('/home/lidong/Documents/datasets/flying3d/visual',str(index.item())+':'+str(loss.item())+'.png'),pre)
            image=image.data.cpu().numpy().astype('uint8')[0,...][:,:-36,:]
            image=np.transpose(image,[1,2,0])
            print(image.shape)
            cv2.imwrite(os.path.join('/home/lidong/Documents/datasets/flying3d/visual',str(index.item())+':'+str(loss.item())+'rgb.png'),image)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Hyperparams')
    parser.add_argument('--arch', nargs='?', type=str, default='cmfsm_sub_16',
                        help='Architecture to use [\'region support network\']')
    parser.add_argument('--dataset', nargs='?', type=str, default='flying3d',
                        help='Dataset to use [\'sceneflow and kitti etc\']')
    parser.add_argument('--img_rows', nargs='?', type=int, default=480,
                        help='Height of the input image')
    parser.add_argument('--img_cols', nargs='?', type=int, default=640,
                        help='Width of the input image')
    parser.add_argument('--n_epoch', nargs='?', type=int, default=4000,
                        help='# of the epochs')
    parser.add_argument('--batch_size', nargs='?', type=int, default=1,
                        help='Batch Size')
    parser.add_argument('--l_rate', nargs='?', type=float, default=1e-4,
                        help='Learning Rate')
    parser.add_argument('--feature_scale', nargs='?', type=int, default=1,
                        help='Divider for # of features to use')
    parser.add_argument('--resume', nargs='?', type=str, default='/home/lidong/Documents/CMF/15_cmfsm_sub_16_flying3d_best_model.pkl',
                        help='Path to previous saved model to restart from /home/lidong/Documents/CMF/9_cm_sub_4_flying3d_best_model.pkl')
    parser.add_argument('--visdom', nargs='?', type=bool, default=True,
                        help='Show visualization(s) on visdom | False by  default')
    args = parser.parse_args()
    train(args)
