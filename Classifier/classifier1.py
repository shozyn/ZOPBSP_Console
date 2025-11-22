#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Mar  2 17:41:39 2025

@author: linux
"""

from Classifier.config import configClassifier as cc
from Classifier.model import create_model
import logging
import torch
import numpy as np
import os

class Classifier:
    def __init__(self,fs_i):
        #Metoda do testowania sygnału wejsciowego
        self.model = os.path.join(cc.DIR_MODEL,cc.MODEL)
        self.input_signal_type = cc.INPUT_SIGNAL_TYPE
        self.device = cc.DEVICE
        self.fs_i = fs_i
        self.model, _, _, _, _ = create_model(num_classes=cc.NB_CLASSES)
        self.model.to(cc.DEVICE)
        model_path = os.path.join(cc.DIR_MODEL,cc.MODEL)
        self.model.load_state_dict(torch.load(model_path, cc.DEVICE,weights_only=False))
        self.model.eval() 
        self.logger = logging.getLogger(__name__)
        self.logger.addHandler(logging.NullHandler())
        self.logger.propagate = False
        self.logger.info("Model initialized")
        
    def test_signal(self,input_signal):
        if cc.INPUT_SIGNAL_TYPE == "Signal" and input_signal.numel() < cc.SIGNAL_LENGTH:
            logger.debug("Signal is too short")
            return False
            
        if cc.INPUT_SIGNAL_TYPE == "FFT" and input_signal.numel() < 101:
            logger.debug("FFT is too short")
            return False

    def predict(self,input_signal):
        with torch.inference_mode():
            if isinstance(input_signal, np.ndarray):
                input_signal = torch.from_numpy(input_signal).float().to(cc.DEVICE)
            elif isinstance(input_signal, torch.Tensor):
                input_signal.to(cc.DEVICE)
            else:
                logger.error("Signal is not tensor or ndarray")
                return -1, np.zeros((1, 5),dtype=np.float32)

            # if not self.test_signal(input_signal):
            #     return {-1: "Signal error"}

            matrix_rows = input_signal.numel() // cc.SIGNAL_LENGTH
            input_signal = input_signal[:cc.SIGNAL_LENGTH * matrix_rows]
            
            input_signal = input_signal.view(matrix_rows,cc.SIGNAL_LENGTH)
            # if cc.BATCH_SIZE < 2028:
            #     indices = torch.randperm(input_signal.size(0))[:cc.BATCH_SIZE]
            #     input_signal = input_signal[indices]
            
            
            input_signal = torch.fft.rfft(input_signal, n=None, dim=-1, norm=None)[:,:101].real 
            y = self.model(torch.unsqueeze(input_signal,dim=1).to(cc.DEVICE))            
            predicts = torch.softmax(y, dim=1)
            class_nbs = torch.argmax(predicts,dim=1)
            counts = torch.bincount(class_nbs,minlength=cc.NB_CLASSES).cpu()
            counts = torch.cat((torch.tensor([0]),counts),dim=0)           
            prob = counts / torch.sum(counts)
            _, most_class = counts.max(0)
            return int(most_class.item()),  prob.numpy().astype(np.float32)
    

            
        
       
        

        