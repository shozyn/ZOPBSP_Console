# -*- coding: utf-8 -*-
"""
Created on Sun May 11 11:14:21 2025

@author: stann
"""
from Classifier.classifier1 import Classifier
        
def AKA1A(s_i_cut, fs_i):
    if not hasattr(AKA1A, "fs_i"):
        AKA1A.fs_i = fs_i  # initialize static variable
        AKA1A.classifier = Classifier(fs_i)
    
    if AKA1A.fs_i != fs_i:
        AKA1A.classifier = Classifier(fs_i)
        AKA1A.fs_i = fs_i
          
    return AKA1A.classifier.predict(input_signal=s_i_cut)        
        
        
    
    
    