# -*- coding: utf-8 -*-
"""
Model definitions for propeller-noise classification.

Key change vs old version:
- Linear layer input sizes are computed from N_BINS (derived from WINDOW_MS/F_MAX_HZ),
  not hard-coded constants tied to a legacy FFT length.
"""

import torch
from torch import nn

from config import configClassifier as cc


def create_model(num_classes):
    """
    Create a model defined by cc.NETWORK.

    CNN1:
      - no padding, length shrinks by (11-1) + (5-1) = 14 bins
    CNN2:
      - padding preserves length for odd kernels ("same" convolution)
    """

    if cc.NETWORK == "CNN1":
        class CNN1(nn.Module):
            def __init__(self):
                super().__init__()
                self.conv1 = nn.Conv1d(1, 16, kernel_size=11, padding=0)
                self.conv2 = nn.Conv1d(16, 32, kernel_size=5, padding=0)

                L0 = int(cc.N_BINS)
                L2 = L0 - (11 - 1) - (5 - 1)  # L0 - 14
                if L2 <= 0:
                    raise ValueError(
                        f"N_BINS={L0} too small for CNN1 kernels. "
                        "Increase F_MAX_HZ/WINDOW_MS or use CNN2."
                    )

                self.linear1 = nn.Linear(32 * L2, num_classes)

            def forward(self, X):
                x = self.conv1(X)
                x = torch.relu(x)
                x = self.conv2(x)
                x = torch.relu(x)
                x = torch.flatten(x, 1)
                y = self.linear1(x)
                return y

        model = CNN1()
        return model, 1, 0, 0, 0  # legacy placeholders

    if cc.NETWORK == "CNN2":
        class CNN2(nn.Module):
            def __init__(self):
                super().__init__()
                # padding=(k-1)/2 preserves length for odd kernels
                self.conv1 = nn.Conv1d(1, 16, kernel_size=11, padding=5)
                self.conv2 = nn.Conv1d(16, 32, kernel_size=5, padding=2)

                L0 = int(cc.N_BINS)
                L2 = L0
                self.linear1 = nn.Linear(32 * L2, num_classes)

            def forward(self, X):
                x = self.conv1(X)
                x = torch.relu(x)
                x = self.conv2(x)
                x = torch.relu(x)
                x = torch.flatten(x, 1)
                y = self.linear1(x)
                return y

        model = CNN2()
        return model, 1, 0, 0, 0  # legacy placeholders

    raise ValueError(f"Unsupported NETWORK={cc.NETWORK}. Use CNN1 or CNN2.")
