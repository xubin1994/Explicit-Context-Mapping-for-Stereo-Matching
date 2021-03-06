# -*- coding: utf-8 -*-
# @Author: lidong
# @Date:   2018-03-18 13:41:34
# @Last Modified by:   yulidong
# @Last Modified time: 2019-02-28 22:04:43
import sys
import torch
import visdom
import argparse
import numpy as np
import time
import torch.nn as nn
import torch.nn.functional as F
import torchvision.models as models
import cv2
from torch.autograd import Variable
from torch.utils import data
from tqdm import tqdm
import torch.nn.functional as F
from cmf.models import get_model
from cmf.loader import get_loader, get_data_path
from cmf.loss import *
import os

def train(args):
    torch.backends.cudnn.benchmark=True
    # Setup Augmentations

    loss_rec=[0]
    best_error=5
    # Setup Dataloader
    data_loader = get_loader(args.dataset)
    data_path = get_data_path(args.dataset)
    t_loader = data_loader(data_path, is_transform=True,
                           split='train', img_size=(args.img_rows, args.img_cols))
    v_loader = data_loader(data_path, is_transform=True,
                           split='eval', img_size=(args.img_rows, args.img_cols))

    train_length=t_loader.length//args.batch_size
    test_length=v_loader.length//args.batch_size
    trainloader = data.DataLoader(
        t_loader, batch_size=args.batch_size, num_workers=args.batch_size, shuffle=True)
    evalloader = data.DataLoader(
        v_loader, batch_size=args.batch_size, num_workers=args.batch_size, shuffle=False)

    train_length=len(trainloader)
    test_length=len(evalloader)
    # Setup visdom for visualization
    if args.visdom:
        vis = visdom.Visdom(env='kitti_sub_4')
        error_window = vis.line(X=torch.zeros((1,)).cpu(),
                               Y=torch.zeros((1)).cpu(),
                               opts=dict(xlabel='minibatches',
                                         ylabel='error',
                                         title='test error',
                                         legend=['Error']))
        loss_window = vis.line(X=torch.zeros((1,)).cpu(),
                               Y=torch.zeros((1)).cpu(),
                               opts=dict(xlabel='minibatches',
                                         ylabel='Loss',
                                         title='Training Loss',
                                         legend=['Loss']))
        pre_window = vis.image(
            np.random.rand(256, 512),
            opts=dict(title='predict!', caption='predict.'),
        )
        ground_window = vis.image(
            np.random.rand(256, 512),
            opts=dict(title='ground!', caption='ground.'),
        )
        image_window = vis.image(
            np.random.rand(256, 512),
            opts=dict(title='image!', caption='image.'),
        )
        error3_window = vis.image(
            np.random.rand(256, 512),
            opts=dict(title='error!', caption='error.'),
        )
    # Setup Model
    model = get_model(args.arch)
    # parameters=model.named_parameters()
    # for name,param in parameters:
    #     print(name)
    #     print(param.grad)
    # exit()

    model = torch.nn.DataParallel(
        model, device_ids=[0,1,2,3])
    #model = torch.nn.DataParallel(model, device_ids=[0])
    model.cuda(0)

    # Check if model has custom optimizer / loss
    # modify to adam, modify the learning rate
    optimizer = torch.optim.Adam(
        model.parameters(), lr=args.l_rate,betas=(0.9,0.999))
    # optimizer = torch.optim.SGD(
    #     model.parameters(), lr=args.l_rate,momentum=0.90, weight_decay=5e-5)
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
            #optimizer.load_state_dict(checkpoint['optimizer_state'])
            #opt=None
            print("Loaded checkpoint '{}' (epoch {})"
                  .format(args.resume, checkpoint['epoch']))
            trained=checkpoint['epoch']
            #best_error=checkpoint['error']+1
            #mean_loss=checkpoint['error']
            best_error=100
            mean_loss=100
            print(mean_loss)
            #trained=0
            # loss_rec=np.load('/home/lidong/Documents/CMF/loss_8.npy')
            # loss_rec=list(loss_rec)
            # print(train_length)
            # loss_rec=loss_rec[:train_length*trained]
            
    else:
        print("No checkpoint found at '{}'".format(args.resume))
        print('Initialize from resnet34!')
        resnet34=torch.load('/home/lidong/Documents/CMF/466_cmfsm_kitti_0.591322544373964_error3_1.8297886095548932_six_best_model.pkl')
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
    for epoch in range(trained, args.n_epoch):
        ones=torch.ones(1).cuda(0)
        zeros=torch.zeros(1).cuda(0)
        print('training!')
        model.train()
        epe_rec=[]
        loss_3_re =[]
        for i, (left, right,disparity,image) in enumerate(trainloader):
            # if epoch==trained:
            #     break
            #break
            #with torch.no_grad():
            #print(left.shape)
            #print(torch.max(image),torch.min(image))
            flag=1
            count=0
            start_time=time.time()
            left = left.cuda(0)
            right = right.cuda(0)
            disparity = disparity.cuda(0)
            mask = (disparity < 192) & (disparity >0)
            mask.detach_()
            iterative_count=0
            while(flag):
                optimizer.zero_grad()
                #print(P.shape)
                output1, output2, output3 = model(left,right)
                #print(output3.shape)
                # output1 = torch.squeeze(output1, 1)
                # loss = F.smooth_l1_loss(output1[mask], disparity[mask],reduction='mean')
                output1 = torch.squeeze(output1, 1)
                output2 = torch.squeeze(output2, 1)
                output3 = torch.squeeze(output3, 1)
                # #outputs=outputs
                #test the l2 loss to reduce the error3
                #increase the weight for the error more than 3.
                # loss = 0.5 * softl1loss(output1[mask], disparity[mask]) \
                #      + 0.7 * softl1loss(output2[mask], disparity[mask]) \
                #      + softl1loss(output3[mask], disparity[mask])
                loss = 0.5 * F.smooth_l1_loss(output1[mask], disparity[mask],reduction='mean') \
                     + 0.7 * F.smooth_l1_loss(output2[mask], disparity[mask], reduction='mean') \
                     + F.smooth_l1_loss(output3[mask], disparity[mask], reduction='mean')
                #loss=loss/2.2

                #output3 = model(left,right)
                #output1=output3+0
                output3 = torch.squeeze(output3, 1)
                epe=torch.mean(torch.abs(output3[mask]-disparity[mask]))
                error_map=torch.where((torch.abs(output3[mask] - disparity[mask])<3) | (torch.abs(output3[mask] - disparity[mask])<0.05*disparity[mask]),ones,zeros)
                #total=torch.where(disparity[mask]>0,ones,zeros)
                loss_3=100-torch.sum(error_map)/torch.sum(mask)*100
                #loss = F.smooth_l1_loss(output3[mask], disparity[mask], reduction='mean')
                #loss.backward()
                #parameters=model.named_parameters()
                #optimizer.step()
                if args.visdom:
                    if iterative_count>0:
                        error_map=torch.where((torch.abs(output3 - disparity)>=3) | (torch.abs(output3 - disparity)>=0.05*disparity),ones,zeros) * mask.float()
                        #print(output3.shape)
                        pre = output3.data.cpu().numpy().astype('float32')
                        pre = pre[0,:,:]
                        #print(np.max(pre))
                        #print(pre.shape)
                        pre = np.reshape(pre, [256,512]).astype('float32')
                        vis.image(
                            pre,
                            opts=dict(title='predict!', caption='predict.'),
                            win=pre_window,
                        )

                        error_map=error_map.data.cpu().numpy().astype('float32')
                        error_map = error_map[0,...]
                        #image=image[0,...]
                        #print(image.shape,np.min(image))
                        error_map = np.reshape(error_map, [256,512]).astype('float32')
                        vis.image(
                            error_map,
                            opts=dict(title='error!', caption='error.'),
                            win=error3_window,
                        )
                    else:
                        error_map=torch.where((torch.abs(output3 - disparity)>=3) | (torch.abs(output3 - disparity)>=0.05*disparity),ones,zeros) * mask.float()
                        #print(output3.shape)
                        pre = output3.data.cpu().numpy().astype('float32')
                        pre = pre[0,:,:]
                        #print(np.max(pre))
                        #print(pre.shape)
                        pre = np.reshape(pre, [256,512]).astype('float32')
                        vis.image(
                            pre,
                            opts=dict(title='predict!', caption='predict.'),
                            win=pre_window,
                        )

                        ground=disparity.data.cpu().numpy().astype('float32')
                        ground = ground[0, :, :]
                        ground = np.reshape(ground, [256,512]).astype('float32')
                        vis.image(
                            ground,
                            opts=dict(title='ground!', caption='ground.'),
                            win=ground_window,
                        )
                        image=image.data.cpu().numpy().astype('float32')
                        image = image[0,...]
                        #image=image[0,...]
                        #print(image.shape,np.min(image))
                        image = np.reshape(image, [3,256,512]).astype('float32')
                        vis.image(
                            image,
                            opts=dict(title='image!', caption='image.'),
                            win=image_window,
                        )      
                        error_map=error_map.data.cpu().numpy().astype('float32')
                        error_map = error_map[0,...]
                        #image=image[0,...]
                        #print(image.shape,np.min(image))
                        error_map = np.reshape(error_map, [256,512]).astype('float32')
                        vis.image(
                            error_map,
                            opts=dict(title='error!', caption='error.'),
                            win=error3_window,
                        )

                if iterative_count==0:
                    #min_loss3_t=epe
                    min_loss3_t=loss_3
                if epoch<=trained+1000:
                    loss_bp=loss
                    loss.backward()
                    epe_rec.append(epe.item())
                    optimizer.step()
                    break
                # else:
                #     loss_bp=0.1*loss
                #     loss.backward()
                #     epe_rec.append(epe.item())
                #     optimizer.step()
                #     break
                #if (epe<=1.25*mean_loss) :
                if (loss_3<=1.25) :
                    #loss_bp=loss*torch.pow(100,-(mean_loss-lin)/mean_loss)
                    #loss_bp=loss*zero
                    print('no back')
                    # if epe<=0.75*mean_loss:
                    #     loss_bp=0.1*loss
                    # else:
                    #     loss_bp=0.1*loss
                    #optimizer.step()
                    loss_bp.backward()
                    epe_rec.append(epe.item())
                    optimizer.step()
                    break
                else:
                    #print(torch.pow(10,torch.min(one,(lin-mean_loss)/mean_loss)).item())
                    print('back')
                    #loss=loss*torch.pow(10,torch.min(one,(lin-mean_loss)/mean_loss))
                    # if epe>1.5*mean_loss:
                    #     loss_bp=10*loss
                    # else:
                    #     loss_bp=loss
                    if loss_3>2:
                        loss_bp=loss
                    else:
                        loss_bp=loss
                    loss_bp.backward()
                    optimizer.step()
                #if epe<=mean_loss or iterative_count>5 :
                if loss_3<=1.25 or iterative_count>8 :

                    if loss_3<min_loss3_t:
                        epe_rec.append(epe.item())
                        # mean_loss=np.mean(epe_rec)
                        break
                    else:
                        min_loss3_t=torch.min(loss_3,min_loss3_t)
                        #if lin<1.5*mean_loss:
                        iterative_count+=1
                        print("repeat data [%d/%d/%d/%d] Loss: %.4f error_3: %.4f " % (i,train_length, epoch, args.n_epoch,epe.item(),loss_3.item()))
                else:
                    min_loss3_t=torch.min(loss_3,min_loss3_t)
                    #if lin<1.5*mean_loss:
                    iterative_count+=1
                    print("repeat data [%d/%d/%d/%d] Loss: %.4f error_3: %.4f " % (i,train_length, epoch, args.n_epoch,epe.item(),loss_3.item()))


            #torch.cuda.empty_cache()
            #print(loss.item)
            if args.visdom ==True:
                vis.line(
                    X=torch.ones(1).cpu() * i+torch.ones(1).cpu() *(epoch-trained)*train_length,
                    Y=epe.item()*torch.ones(1).cpu(),
                    win=loss_window,
                    update='append')
                #print(torch.max(output3).item(),torch.min(output3).item())
                # if i%1==0:
                #     error_map=torch.where((torch.abs(output3 - disparity)>=3) | (torch.abs(output3 - disparity)>=0.05*disparity),ones,zeros) * mask.float()
                #     #print(output3.shape)
                #     pre = output3.data.cpu().numpy().astype('float32')
                #     pre = pre[0,:,:]
                #     #print(np.max(pre))
                #     #print(pre.shape)
                #     pre = np.reshape(pre, [256,512]).astype('float32')
                #     vis.image(
                #         pre,
                #         opts=dict(title='predict!', caption='predict.'),
                #         win=pre_window,
                #     )

                #     ground=disparity.data.cpu().numpy().astype('float32')
                #     ground = ground[0, :, :]
                #     ground = np.reshape(ground, [256,512]).astype('float32')
                #     vis.image(
                #         ground,
                #         opts=dict(title='ground!', caption='ground.'),
                #         win=ground_window,
                #     )
                #     image=image.data.cpu().numpy().astype('float32')
                #     image = image[0,...]
                #     #image=image[0,...]
                #     #print(image.shape,np.min(image))
                #     image = np.reshape(image, [3,256,512]).astype('float32')
                #     vis.image(
                #         image,
                #         opts=dict(title='image!', caption='image.'),
                #         win=image_window,
                #     )      
                #     error_map=error_map.data.cpu().numpy().astype('float32')
                #     error_map = error_map[0,...]
                #     #image=image[0,...]
                #     #print(image.shape,np.min(image))
                #     error_map = np.reshape(error_map, [256,512]).astype('float32')
                #     vis.image(
                #         error_map,
                #         opts=dict(title='error!', caption='error.'),
                #         win=error3_window,
                #     )         
            loss_rec.append(loss.item())
            print(time.time()-start_time)
            print("data [%d/%d/%d/%d] Loss: %.4f, loss_3:%.4f" % (i,train_length, epoch, args.n_epoch,epe.item(),loss_3.item()))
            loss_3_re.append(loss_3.item())
        print('epe:',np.mean(epe_rec))
        print('loss_3:',np.mean(loss_3_re))
        mean_loss=np.mean(epe_rec)
        #eval
        print('testing!')
        model.eval()
        epe_rec=[]
        loss_3_re =[]
        for i, (left, right,disparity,image) in tqdm(enumerate(evalloader)):
            #break
            #with torch.no_grad():
            #print(left.shape)
            #print(torch.max(image),torch.min(image))
            with torch.no_grad():

                count=0
                start_time=time.time()
                left = left.cuda(0)
                right = right.cuda(0)
                disparity = disparity.cuda(0)
                mask = (disparity < 192) & (disparity >0)
                mask.detach_()
                iterative_count=0

                optimizer.zero_grad()
                #print(P.shape)
                output1, output2, output3 = model(left,right)
                #print(output3.shape)
                # output1 = torch.squeeze(output1, 1)
                # loss = F.smooth_l1_loss(output1[mask], disparity[mask],reduction='mean')
                # output1 = torch.squeeze(output1, 1)
                # output2 = torch.squeeze(output2, 1)
                # output3 = torch.squeeze(output3, 1)
                # # #outputs=outputs
                # loss = 0.5 * F.mse_loss(output1[mask], disparity[mask],reduction='mean') \
                #      + 0.7 * F.mse_loss(output2[mask], disparity[mask], reduction='mean') \
                #      + F.mse_loss(output3[mask], disparity[mask], reduction='mean')
                #loss=loss/2.2
                #output3 = model(left,right)
                #output1=output3
                output3 = torch.squeeze(output3, 1)
                error_map=torch.where((torch.abs(output3[mask] - disparity[mask])<3) | (torch.abs(output3[mask] - disparity[mask])<0.05*disparity[mask]),ones,zeros)
                #total=torch.where(disparity[mask]>0,ones,zeros)
                loss_3=100-torch.sum(error_map)/torch.sum(mask)*100
                epe=torch.mean(torch.abs(output3[mask]-disparity[mask]))
                epe_rec.append(epe.item())
                loss_3_re.append(loss_3.item())
            if args.visdom ==True:
                vis.line(
                    X=torch.ones(1).cpu() * i+torch.ones(1).cpu() *(epoch-trained)*test_length,
                    Y=loss_3.item()*torch.ones(1).cpu(),
                    win=error_window,
                    update='append')
                #print(torch.max(output3).item(),torch.min(output3).item())

            #loss_rec.append(loss.item())
            print(time.time()-start_time)
            print("data [%d/%d/%d/%d] Loss: %.4f, loss_3:%.4f" % (i,test_length, epoch, args.n_epoch,epe.item(),loss_3.item()))
            if loss_3.item()>10:
                pre = output3.data.cpu().numpy().astype('float32')
                pre = pre[0,:,:]
                cv2.imwrite(os.path.join('/home/lidong/Documents/CMF/visual/',str(i),'pre.png'),pre)
                ground=disparity.data.cpu().numpy().astype('float32')
                ground = ground[0, :, :]
                cv2.imwrite(os.path.join('/home/lidong/Documents/CMF/visual/',str(i),'ground.png'),ground)
                image=image.data.cpu().numpy().astype('uint8')
                image = image[0,...]
                print(image.shape)
                image=np.transpose(image,[1,2,0])[...,::-1]
                cv2.imwrite(os.path.join('/home/lidong/Documents/CMF/visual/',str(i),'image.png'),image)
                #exit()
        print('epe:',np.mean(epe_rec))
        print('loss_3:',np.mean(loss_3_re))
        error=np.mean(loss_3_re)
        # if epoch>400:
        #     optimizer = torch.optim.Adam(
        #     model.parameters(), lr=args.l_rate/10,betas=(0.9,0.999))
        if error<best_error:
            best_error=error
            state = {'epoch': epoch+1,
             'model_state': model.state_dict(),
             'optimizer_state': optimizer.state_dict(),
             'error':np.mean(epe_rec),
             'error3':np.mean(loss_3_re)}
            #np.save('loss_4.npy',loss_rec)
            torch.save(state, "{}_{}_{}_{}_error3_{}_four_disparity_model.pkl".format(epoch,args.arch,args.dataset,np.mean(epe_rec),np.mean(loss_3_re)))
        if epoch%50==0:
            state = {'epoch': epoch+1,
             'model_state': model.state_dict(),
             'optimizer_state': optimizer.state_dict(),
             'error':np.mean(epe_rec),
             'error3':np.mean(loss_3_re)}
            #np.save('loss_4.npy',loss_rec)
            torch.save(state, "{}_{}_{}_{}_error3_{}_four_disparity_model.pkl".format(epoch,args.arch,args.dataset,np.mean(epe_rec),np.mean(loss_3_re)))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Hyperparams')
    parser.add_argument('--arch', nargs='?', type=str, default='cmfsm',
                        help='Architecture to use [\'region support network\']')
    parser.add_argument('--dataset', nargs='?', type=str, default='kitti',
                        help='Dataset to use [\'sceneflow and kitti etc\']')
    parser.add_argument('--img_rows', nargs='?', type=int, default=480,
                        help='Height of the input image')
    parser.add_argument('--img_cols', nargs='?', type=int, default=640,
                        help='Width of the input image')
    parser.add_argument('--n_epoch', nargs='?', type=int, default=4000,
                        help='# of the epochs')
    parser.add_argument('--batch_size', nargs='?', type=int, default=4,
                        help='Batch Size')
    parser.add_argument('--l_rate', nargs='?', type=float, default=1e-3,
                        help='Learning Rate')
    parser.add_argument('--feature_scale', nargs='?', type=int, default=1,
                        help='Divider for # of features to use')
    parser.add_argument('--resume', nargs='?', type=str, default='/home/lidong/Documents/CMF/4_cmfsm_sceneflow_best_model.pkl',
                        help='Path to previous saved model to restart from /home/lidong/Documents/CMF/4_cmfsm_sceneflow_best_model.pkl')
    parser.add_argument('--visdom', nargs='?', type=bool, default=True,
                        help='Show visualization(s) on visdom | False by  default')
    args = parser.parse_args()
    train(args)
