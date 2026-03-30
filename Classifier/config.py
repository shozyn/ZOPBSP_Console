# -*- coding: utf-8 -*-
"""
Created on Feb 22 11:26:32 2026

@author: s.hozyn

Config file for Classfier script

"""

from dataclasses import dataclass
import os

import numpy as np
import torch


@dataclass
class ConfigClassifier:
    DIR_MODEL: str = ""
    MODEL: str = "model_final.pth"
    SCALER: str = "scaler_final.pth"

    #  Feature extraction parameters
    SAMPLE_RATE: int = 64000
    WINDOW_MS: int = 250
    HOP_MS: int = 250
    F_MAX_HZ: int = 8000

    # Calculated in __post_init__
    FRAME_LEN: int = 0
    HOP_LEN: int = 0
    K_MAX: int = 0
    N_BINS: int = 0

    # ------------------------- Runtime -------------------------
    DEVICE: str = ""

    def __post_init__(self):
        # Device selection
        self.DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Device: {self.DEVICE}")

        # Default model directory: ./Models
        current_folder = os.path.dirname(os.path.abspath(__file__))
        self.DIR_MODEL = os.path.join(current_folder, "Models")

        # Derived feature parameters
        self.FRAME_LEN = int(self.SAMPLE_RATE * self.WINDOW_MS / 1000.0)
        self.HOP_LEN = int(self.SAMPLE_RATE * self.HOP_MS / 1000.0)

        # Highest rFFT bin index whose center frequency <= F_MAX_HZ
        self.K_MAX = int(np.floor(self.F_MAX_HZ * self.FRAME_LEN / self.SAMPLE_RATE))

        # DC excluded => keep bins 1..K_MAX inclusive => N_BINS = K_MAX
        self.N_BINS = int(self.K_MAX)

        assert self.N_BINS > 0, "N_BINS must be positive. Check WINDOW_MS/F_MAX_HZ."

    # @property
    # def CLASS_TO_ID(self):
    #     return {name: i for i, name in enumerate(self.CLASSES)}

    # @property
    # def ID_TO_CLASS(self):
    #     return {i: name for i, name in enumerate(self.CLASSES)}


configClassifier = ConfigClassifier()













    
    
    
