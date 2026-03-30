#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
classifier1.py

"""

import os
import numpy as np
import torch
from torch import nn

from Classifier.config import configClassifier as cc

def create_model(num_classes):
    """
    Create a model defined by cc.NETWORK.

    CNN1:
      - no padding, length shrinks by (11-1) + (5-1) = 14 bins
    CNN2:
      - padding preserves length for odd kernels ("same" convolution)
    """

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
# ===========================
# External output class space
# ===========================

OUTPUT_CLASSES = [
    "Cisza",
    "Cargo_47",
    "LAUV",
    "Otter",
    "Passengership_109",
    "Ponton_2",
    "Ponton_3",
    "INNE",
]
OUTPUT_INNE_ID = OUTPUT_CLASSES.index("INNE")

# Internal model class ids (training order):
# 0: LAUV, 1: Raft, 2: Otter, 3: Salience
INTERNAL_TO_OUTPUT_ID = {
    0: OUTPUT_CLASSES.index("LAUV"),
    1: OUTPUT_CLASSES.index("Ponton_2"),
    2: OUTPUT_CLASSES.index("Otter"),
    3: OUTPUT_CLASSES.index("Cisza"),
}


# =========================================================
# WAV -> (s_i_cut:int32, fs_i:int)  [TEST HARNESS ONLY]
# =========================================================

def wav_to_si_cut(wav_path):
    """
    Convert a WAV file into the project-wide input format:
      fs_i   : int
      s_i_cut: np.ndarray int32 mono

    Preferred: torchaudio.load() (float waveform) -> int32
    Fallback : scipy.io.wavfile.read() -> normalise -> int32
    """
    # Preferred: torchaudio
    try:
        import torchaudio
        wav, sr = torchaudio.load(wav_path)  # (ch, n), float32/float64
        if wav.shape[0] > 1:
            wav = wav.mean(dim=0, keepdim=True)
        x = wav.squeeze(0).cpu().numpy().astype(np.float32)   # ~[-1,1]
        x = np.clip(x, -1.0, 1.0)
        s_i_cut = (x * (2**31 - 1)).astype(np.int32)
        return int(sr), s_i_cut
    except Exception:
        pass

    # Fallback: scipy
    from scipy.io import wavfile
    sr, x = wavfile.read(wav_path)  # x can be int16/int32/float/etc.
    x = np.asarray(x)

    # Mono
    if x.ndim == 2:
        # scipy commonly returns (n_samples, n_channels)
        x = x.mean(axis=1)

    # Convert to float in [-1,1]
    if x.dtype.kind == "f":
        xf = np.clip(x.astype(np.float32), -1.0, 1.0)
    elif x.dtype.kind == "i":
        info = np.iinfo(x.dtype)
        scale = float(max(abs(info.min), info.max))
        xf = np.clip(x.astype(np.float32) / scale, -1.0, 1.0)
    elif x.dtype.kind == "u":
        if x.dtype == np.uint8:
            xf = (x.astype(np.float32) - 128.0) / 128.0
        else:
            info = np.iinfo(x.dtype)
            xf = (x.astype(np.float32) / float(info.max)) * 2.0 - 1.0
        xf = np.clip(xf, -1.0, 1.0)
    else:
        xf = x.astype(np.float32)
        mx = float(np.max(np.abs(xf))) if xf.size else 1.0
        if mx > 0:
            xf = xf / mx
        xf = np.clip(xf, -1.0, 1.0)

    s_i_cut = (xf * (2**31 - 1)).astype(np.int32)
    return int(sr), s_i_cut


# ===========================
# Small internal utilities
# ===========================

def _getattr_default(obj, name, default):
    return getattr(obj, name) if hasattr(obj, name) else default


def _int32_to_float_pm1(x_int32):
    """
    int32 PCM-like -> float32 in [-1,1]
    """
    x = np.asarray(x_int32)
    if x.dtype != np.int32:
        x = x.astype(np.int32, copy=False)
    y = x.astype(np.float32) / float(2**31 - 1)
    return np.clip(y, -1.0, 1.0).astype(np.float32, copy=False)


def _resample_float_1d(x, sr_in, sr_out):
    """
    Resample float32 mono waveform x from sr_in to sr_out.
    Preference:
      1) torchaudio
      2) scipy.signal.resample_poly
      3) numpy interp
    """
    sr_in = int(sr_in)
    sr_out = int(sr_out)
    if sr_in == sr_out:
        return x

    # 1) torchaudio
    try:
        import torchaudio
        xt = torch.from_numpy(x).to(torch.float32).unsqueeze(0)  # (1, N)
        res = torchaudio.transforms.Resample(orig_freq=sr_in, new_freq=sr_out)
        y = res(xt).squeeze(0).cpu().numpy().astype(np.float32)
        return y
    except Exception:
        pass

    # 2) scipy resample_poly
    try:
        from scipy.signal import resample_poly
        import math
        g = math.gcd(sr_in, sr_out)
        up = sr_out // g
        down = sr_in // g
        y = resample_poly(x, up, down).astype(np.float32)
        return y
    except Exception:
        pass

    # 3) numpy interp fallback
    n_in = int(x.size)
    n_out = int(round(n_in * (float(sr_out) / float(sr_in))))
    if n_out <= 1:
        return np.zeros((0,), dtype=np.float32)

    t_in = np.linspace(0.0, 1.0, num=n_in, endpoint=False, dtype=np.float32)
    t_out = np.linspace(0.0, 1.0, num=n_out, endpoint=False, dtype=np.float32)
    return np.interp(t_out, t_in, x).astype(np.float32)


def _map_internal_meanprob_to_output(mean_prob_internal):
    """
    mean_prob_internal: np.ndarray (4,) in internal order [LAUV, Raft, Otter, Salience]
    returns: output_prob (8,) aligned to OUTPUT_CLASSES
    """
    out = np.zeros((len(OUTPUT_CLASSES),), dtype=np.float32)
    out[OUTPUT_CLASSES.index("LAUV")] = float(mean_prob_internal[0])
    out[OUTPUT_CLASSES.index("Ponton_2")] = float(mean_prob_internal[1])
    out[OUTPUT_CLASSES.index("Otter")] = float(mean_prob_internal[2])
    out[OUTPUT_CLASSES.index("Cisza")] = float(mean_prob_internal[3])
    # remaining classes stay 0.0
    return out


# ===========================
# Classifier
# ===========================

class Classifier:
    def __init__(self, fs_i):
        """
        Legacy design:
        - fs_i is stored in the classifier object,
        - AKA1A rebuilds the classifier if fs_i changes.

        Current approach:
        - we resample to model sample rate internally, so one model is enough,
          but we keep the ABI unchanged.
        """
        self.fs_i = int(fs_i)

        # Device
        dev = _getattr_default(cc, "DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
        self.device = torch.device(dev) if isinstance(dev, str) else dev

        # Model/scaler locations
        self.dir_model = _getattr_default(cc, "DIR_MODEL", os.path.join(os.path.dirname(__file__), "Models"))
        self.model_name = _getattr_default(cc, "MODEL", "model_final.pth")
        self.scaler_name = _getattr_default(cc, "SCALER", "scaler_final.pth")

        self.model_path = os.path.join(self.dir_model, self.model_name)
        self.scaler_path = os.path.join(self.dir_model, self.scaler_name)

        if not os.path.exists(self.model_path):
            raise FileNotFoundError(self.model_path)
        if not os.path.exists(self.scaler_path):
            raise FileNotFoundError(self.scaler_path)

        # Feature extraction parameters (defaults match your final training config)
        self.model_sr = int(_getattr_default(cc, "SAMPLE_RATE", 64000))
        self.window_ms = float(_getattr_default(cc, "WINDOW_MS", 250))
        self.hop_ms = float(_getattr_default(cc, "HOP_MS", 250))
        self.f_max_hz = float(_getattr_default(cc, "F_MAX_HZ", 8000))

        self.frame_len = int(round(self.model_sr * self.window_ms / 1000.0))
        self.hop_len = int(round(self.model_sr * self.hop_ms / 1000.0))
        self.k_max = int(np.floor(self.f_max_hz * self.frame_len / float(self.model_sr)))
        self.n_bins = int(self.k_max)  # DC excluded => bins 1..k_max

        if self.n_bins <= 0 or self.frame_len <= 0:
            raise RuntimeError("Invalid feature parameters. Check SAMPLE_RATE/WINDOW_MS/F_MAX_HZ.")

        self.hann = np.hanning(self.frame_len).astype(np.float32)

        # Model (internal classes fixed to 4)
        self.model, _, _, _, _ = create_model(num_classes=4)
        self.model = self.model.to(self.device)
        self.model.load_state_dict(torch.load(self.model_path, map_location=self.device))
        self.model.eval()

        # Scaler: {"min": (n_bins,1), "den": (n_bins,1)}
        scaler = torch.load(self.scaler_path, map_location="cpu")
        if not (isinstance(scaler, dict) and "min" in scaler and "den" in scaler):
            raise ValueError("Scaler must be a dict with keys {'min','den'}.")

        self.tr_min = scaler["min"].to(torch.float32).view(-1, 1)
        self.tr_den = scaler["den"].to(torch.float32).view(-1, 1)

        if int(self.tr_min.shape[0]) != int(self.n_bins):
            raise RuntimeError(
                f"Scaler bins={int(self.tr_min.shape[0])} != feature bins={int(self.n_bins)}. "
                "Your config (window/fmax/sr) does not match the trained model."
            )

        self.infer_batch = int(_getattr_default(cc, "INFER_BATCH", 256))

    def _features(self, x_float_modelsr):
        """
        x_float_modelsr: float32 mono at model_sr
        returns: np.ndarray float32 (n_windows, n_bins)
        """
        feats = []
        N = int(x_float_modelsr.size)

        for start in range(0, N - self.frame_len + 1, self.hop_len):
            frame = x_float_modelsr[start:start + self.frame_len]
            frame = frame - float(frame.mean())
            frame = frame * self.hann

            mag = np.abs(np.fft.rfft(frame)).astype(np.float32)
            mag = mag[1:self.k_max + 1]   # bins 1..K_MAX (DC excluded)
            mag = np.log1p(mag)           # log compression
            feats.append(mag)

        if len(feats) == 0:
            return np.zeros((0, self.n_bins), dtype=np.float32)

        return np.stack(feats, axis=0).astype(np.float32)

    def predict(self, input_signal):
        """
        Returns:
          pred_class: int (index in OUTPUT_CLASSES)
          class_prob: np.ndarray float32, shape (8,)
        """
        # Accept numpy or torch; project input is numpy int32
        if isinstance(input_signal, torch.Tensor):
            input_signal = input_signal.detach().cpu().numpy()

        x = np.asarray(input_signal)

        # Ensure mono if a 2D array slips in
        if x.ndim == 2:
            if x.shape[0] < x.shape[1]:
                x = x.mean(axis=0)
            else:
                x = x.mean(axis=1)

        # Contract expects int32; convert if needed (best effort)
        if x.dtype != np.int32:
            x = x.astype(np.int32, copy=False)

        # int32 -> float [-1,1]
        xf = _int32_to_float_pm1(x)

        # resample from fs_i to model_sr
        xf = _resample_float_1d(xf, self.fs_i, self.model_sr)

        # extract features
        X = self._features(xf)

        # too short => INNE one-hot
        if X.shape[0] == 0:
            class_prob = np.zeros((len(OUTPUT_CLASSES),), dtype=np.float32)
            class_prob[OUTPUT_INNE_ID] = 1.0
            return int(OUTPUT_INNE_ID), class_prob

        # scale like training: transpose to (n_bins, n_windows)
        Xt = torch.tensor(X, dtype=torch.float32).t()
        Xt = (Xt - self.tr_min) / self.tr_den
        Xt = torch.clamp(Xt, 0.0, 1.0)

        # model input (n_windows, 1, n_bins)
        X_model = Xt.t().unsqueeze(1)

        probs_all = []
        preds_all = []

        with torch.inference_mode():
            for i in range(0, X_model.shape[0], self.infer_batch):
                xb = X_model[i:i + self.infer_batch].to(self.device)
                logits = self.model(xb)
                pb = torch.softmax(logits, dim=1)        # (B, 4)
                yb = torch.argmax(pb, dim=1)             # (B,)
                probs_all.append(pb.cpu().numpy())
                preds_all.append(yb.cpu().numpy())

        probs = np.concatenate(probs_all, axis=0).astype(np.float32)  # (n_windows, 4)
        preds = np.concatenate(preds_all, axis=0).astype(np.int64)    # (n_windows,)

        # majority vote in internal space
        counts = np.bincount(preds, minlength=4)
        pred_internal = int(np.argmax(counts))

        # output pred_class (external index)
        pred_class = int(INTERNAL_TO_OUTPUT_ID.get(pred_internal, OUTPUT_INNE_ID))

        # output probability vector from mean internal probabilities
        mean_prob_internal = probs.mean(axis=0)  # (4,)
        class_prob = _map_internal_meanprob_to_output(mean_prob_internal)

        return pred_class, class_prob
