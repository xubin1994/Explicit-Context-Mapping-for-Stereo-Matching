# -*- coding: utf-8 -*-
# @Author: yulidong
# @Date:   2018-03-19 13:33:07
# @Last Modified by:   yulidong
# @Last Modified time: 2018-10-22 15:51:46

import os
import torch
import numpy as np
from torch.utils import data
import torchvision.transforms as transforms
import random
class Flying3d(data.Dataset):


    def __init__(self, root, split="train", is_transform=True, img_size=(540,960)):
        """__init__

        :param root:
        :param split:
        :param is_transform:
        :param img_size:
        """
        self.is_transform = is_transform
        self.img_size = img_size if isinstance(img_size, tuple) else (540, 960)
        self.stats={'mean': [0.485, 0.456, 0.406],
                   'std': [0.229, 0.224, 0.225]}
        self.files = {}
        self.datapath=root
        self.files=os.listdir(os.path.join(self.datapath,split))
        self.files.sort()          
        self.split=split
        if len(self.files)<1:
            raise Exception("No files for ld=[%s] found in %s" % (split, self.ld))

        print("Found %d in %s data" % (len(self.files), self.datapath))

    def __len__(self):
        """__len__"""
        return len(self.files)

    def __getitem__(self, index):
        """__getitem__

        :param index:
        """
        #index=58

        data=np.load(os.path.join(self.datapath,self.split,self.files[index]))
        #print(os.path.join(self.datapath,self.split,self.files[index]))
        if self.split=='train':
            h,w = data.shape[0],data.shape[1]
            th, tw = 540, 960
            x1 = random.randint(0, h - th)
            y1 = random.randint(0, w - tw)
            data=data[x1:x1+th,y1:y1+tw,:]
        else:
            h,w = data.shape[0],data.shape[1]
            padding=np.zeros([4,data.shape[1],data.shape[2]])
            th, tw = 540, 960
            x1 = 0
            y1 = 0
            data=data[x1:th,y1:tw,:]
            data=np.concatenate([data,padding],0)
        #data=data[:540,:960,:]
        left=data[...,0:3]/255
        #
        image=data[...,0:3]
        image=transforms.ToTensor()(image)
        #print(torch.max(image),torch.min(image))
        right=data[...,3:6]/255
        disparity=data[...,6]

        if self.is_transform:
            left, right,disparity = self.transform(left, right,disparity)
        #print(torch.max(left),torch.min(left))
        return left, right,disparity,image
    def transform(self, left, right,disparity):
        """transform
        """
        trans=transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize(**self.stats),
        ])
     
        left=trans(left).float()
        right=trans(right).float()

        disparity=torch.from_numpy(disparity).float()

        return left,right,disparity
