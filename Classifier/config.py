# -*- coding: utf-8 -*-
"""
Created on Thu Feb 13 07:50:30 2025

@author: stann
"""

from dataclasses import dataclass, field
from datetime import datetime
import torch
import os
import logging

@dataclass
class ConfigClassifier():
    NB_CLASSES: int = 5
    DIR_MODEL: str ="" 
    MODEL: str = "model50.pth"
    INPUT_SIGNAL_TYPE: str = "Signal" # Signal - przebieg czasowy, FFT - widmo czestotliwosciowe
    SIGNAL_LENGTH: int = 7500
    IN_FREQ: int = 256000
    IF_FFT: bool = False
    DEVICE: str = ""
    NETWORK: str = "CNN1"
    BATCH_SIZE: int = 2028
    #logger: logging.Logger = field(init=False, repr=False) 
    
    def __post_init__(self):
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        current_folder = os.path.dirname(os.path.abspath(__file__))
        dir_model = os.path.join(current_folder,"Models")
        assert os.path.exists(dir_model) == True, "Model path does not exist"       
        self.DIR_MODEL = dir_model
        self.DEVICE = device
            
    def __str__(self):
        return f"""
    NB_CLASSES: {self.NB_CLASSES}
    DIR_MODEL: {self.DIR_MODEL}
    MODEL: {self.MODEL}
    INPUT_SIGNAL_TYPE: {self.INPUT_SIGNAL_TYPE}
    SIGNAL_LENGTH: {self.SIGNAL_LENGTH}
    IN_FREQ: {self.IN_FREQ}
    IF_FFT: {self.IF_FFT}
    DEVICE: {self.DEVICE}
    NETWORK: {self.NETWORK}
    BATCH_SIZE: {self.BATCH_SIZE}
    """

configClassifier = ConfigClassifier()












    
    
    
