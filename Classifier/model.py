# -*- coding: utf-8 -*-
"""
Created on Tue Mar  5 11:06:02 2024

@author: stann
"""
import config
import torch
from Classifier.config import configClassifier as cc
from torch import nn

if cc.NETWORK == 'CNN1':
    input_size = 1
    num_hidden = 1024
    num_layers = 1
    dense_layer_size = 256
if cc.NETWORK == 'CNN2':
    input_size = 1
    num_hidden = 64
    num_layers = 1
    dense_layer_size = 16
    
elif cc.NETWORK == 'CNN3':
    input_size = 1
    conv_out_1 = 16
    conv_kern_1 = 11
    maxp_kern_1 = 5
    maxp_str_1 = 2
    maxp_pad_1 = 2
    num_hidden = 0
    num_layers = 0
    dense_layer_size = 0
     
elif cc.NETWORK == 'GRU1':
    input_size = 1
    num_hidden = 32
    num_layers = 1
    dense_layer_size = 8       
    
def create_model(num_classes):   
    if cc.NETWORK == 'CNN1':
        class cnn_net(nn.Module):
            def __init__(self,input_size,num_hidden,num_layers):
                super().__init__()    
                self.conv1 = nn.Conv1d(1, 16, 11) #7500 -> 7490
                self.conv2 = nn.Conv1d(16, 32, 5) #7496
                self.linear1 = nn.Linear(32*87,num_classes)             
            def forward(self,X):
                x = self.conv1(X)
                x = torch.relu(x)
                x = self.conv2(x)
                x = torch.relu(x)
                x = torch.flatten(x,1)
                y = self.linear1(x)
                return y

    if cc.NETWORK == 'CNN2':
        class cnn_net(nn.Module):
            def __init__(self,input_size,num_hidden,num_layers):
                super().__init__()    
                self.conv1 = nn.Conv1d(1, 16, 11)
                self.conv2 = nn.Conv1d(16, 32, 5)
                self.linear1 = nn.Linear(239552,num_classes)    #32*7496         
            def forward(self,X):
                x = self.conv1(X)
                x = torch.relu(x)
                x = self.conv2(x)
                x = torch.relu(x)
                x = torch.flatten(x,1)
                y = self.linear1(x)
                return y     
            
    if cc.NETWORK == 'CNN3':
        class cnn_net(nn.Module):
            def __init__(self,input_size,num_hidden,num_layers):
                super().__init__()    
                self.conv1 = nn.Conv1d(input_size, conv_out_1, conv_kern_1)
                self.bn1 = nn.BatchNorm1d(conv_out_1)
                self.maxpool1 = nn.MaxPool1d(kernel_size=maxp_kern_1,stride=maxp_str_1,
                                             padding=maxp_pad_1)
                self.dropout1 = nn.Dropout(0.3)
                #self.conv2 = nn.Conv1d(16, 32, 5)
                dense_size = int((((7500 - (conv_kern_1 - 1))*conv_out_1 + 2*maxp_pad_1 - maxp_kern_1) / maxp_str_1) + 1)
                self.linear1 = nn.Linear(dense_size,num_classes)             
            def forward(self,X):
                x = self.conv1(X)
                x = self.bn1(x)
                x = torch.relu(x)
                x = self.maxpool1(x)
                x = self.dropout1(x)

                x = torch.flatten(x,1)
                y = self.linear1(x)
                return y 

    if cc.NETWORK == 'GRU1':    
        class rnn_net(nn.Module):
            def __init__(self,input_size,num_hidden,num_layers):
                super().__init__()        
                self.rnn = nn.GRU(input_size,num_hidden,num_layers,batch_first=True)
                self.linear1 = nn.Linear(num_hidden,dense_layer_size) #64 signal, 16 fft
                self.linear2 = nn.Linear(dense_layer_size,5)
                
            def forward(self,X):
                _ , hidden = self.rnn(X)
                x = self.linear1(hidden[-1])
                y = self.linear2(x)
                #y, hidden = self.rnn(x)
                return y, hidden
            
    model = cnn_net(input_size, num_hidden, num_layers)
    return model, input_size, num_hidden, num_layers, dense_layer_size