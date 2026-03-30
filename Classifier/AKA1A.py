# -*- coding: utf-8 -*-
"""
AKA1A.py

Project ABI:
pred_class, class_prob = AKA1A(s_i_cut, fs_i)

- s_i_cut: np.array int32 (mono), arbitrary length
- fs_i   : int

AKA1A keeps the historical design:
- cache one classifier instance
- if sampling rate changes -> rebuild classifier instance
"""

from Classifier.classifier1 import Classifier


def AKA1A(s_i_cut, fs_i):
    # Initialize static variables on first call
    if not hasattr(AKA1A, "fs_i"):
        AKA1A.fs_i = int(fs_i)
        AKA1A.classifier = Classifier(AKA1A.fs_i)

    # If sampling frequency changes, rebuild classifier (legacy behavior)
    if AKA1A.fs_i != int(fs_i):
        AKA1A.fs_i = int(fs_i)
        AKA1A.classifier = Classifier(AKA1A.fs_i)

    # Legacy call style: classifier uses its stored fs_i
    return AKA1A.classifier.predict(input_signal=s_i_cut)
 
        
        
    
    
    