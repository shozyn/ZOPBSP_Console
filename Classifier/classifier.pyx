# -*- coding: utf-8 -*-
"""
Created on Fri Apr 18 13:43:33 2025

@author: stann
"""

# cython: language_level=3
from model import create_model
from config import configClassifier as cc
import logging
import torch
import numpy as np
import os

cdef class Classifier:
    cdef object model_path
    cdef object model
    cdef object input_signal_type
    cdef object device
    cdef object fs_i
    cdef object logger

    def __cinit__(self):
        pass  # Initialization logic moved to __init__

    def __init__(self, fs_i):
        self.model = os.path.join(cc.DIR_MODEL, cc.MODEL)  # Build model path from config
        self.input_signal_type = cc.INPUT_SIGNAL_TYPE
        self.device = cc.DEVICE
        self.fs_i = fs_i  # Assign sampling frequency or similar input value

        # Create and load the model
        self.model, _, _, _, _ = create_model(num_classes=cc.NB_CLASSES)
        self.model.to(cc.DEVICE)
        model_path = os.path.join(cc.DIR_MODEL, cc.MODEL)
        self.model.load_state_dict(torch.load(model_path, cc.DEVICE, weights_only=False))
        self.model.eval()  # Set the model to evaluation mode

        # Set up logging
        self.logger = logging.getLogger(__name__)
        self.logger.addHandler(logging.NullHandler())
        self.logger.propagate = False
        self.logger.info("Model initialized")

    cpdef bint test_signal(self, input_signal):
        # Validate signal length for raw signals
        if cc.INPUT_SIGNAL_TYPE == "Signal" and input_signal.numel() < cc.SIGNAL_LENGTH:
            self.logger.debug("Signal is too short")
            return False

        # Validate signal length for FFT input
        if cc.INPUT_SIGNAL_TYPE == "FFT" and input_signal.numel() < 101:
            self.logger.debug("FFT is too short")
            return False

        return True

    cpdef predict(self, input_signal):
        with torch.inference_mode():  # Disable gradient calculations
            # Convert input to torch tensor if it's a NumPy array
            if isinstance(input_signal, np.ndarray):
                input_signal = torch.from_numpy(input_signal).float().to(cc.DEVICE)
            elif isinstance(input_signal, torch.Tensor):
                input_signal = input_signal.to(cc.DEVICE)
            else:
                self.logger.error("Signal is not tensor or ndarray")
                return -1, np.zeros((1, 5), dtype=np.float32)

            # Optional: Validate signal
            # if not self.test_signal(input_signal):
            #     return {-1: "Signal error"}

            # Reshape the signal into rows of fixed length
            matrix_rows = input_signal.numel() // cc.SIGNAL_LENGTH
            input_signal = input_signal[:cc.SIGNAL_LENGTH * matrix_rows]
            input_signal = input_signal.view(matrix_rows, cc.SIGNAL_LENGTH)

            # Optional: random sampling if batch size is limited
            # if cc.BATCH_SIZE < 2028:
            #     indices = torch.randperm(input_signal.size(0))[:cc.BATCH_SIZE]
            #     input_signal = input_signal[indices]

            # Apply FFT and slice to first 101 coefficients (real part only)
            input_signal = torch.fft.rfft(input_signal, n=None, dim=-1, norm=None)[:, :101].real
            y = self.model(torch.unsqueeze(input_signal, dim=1).to(cc.DEVICE))  # Add channel dim and run prediction
            predicts = torch.softmax(y, dim=1)  # Convert logits to probabilities

            # Find the predicted class indices
            class_nbs = torch.argmax(predicts, dim=1)
            counts = torch.bincount(class_nbs, minlength=cc.NB_CLASSES).cpu()
            counts = torch.cat((torch.tensor([0]), counts), dim=0)  # Padding to match class index if needed

            # Normalize to get probability distribution
            prob = counts / torch.sum(counts)
            _, most_class = counts.max(0)  # Get class with max count

            return int(most_class.item()), prob.numpy().astype(np.float32)
