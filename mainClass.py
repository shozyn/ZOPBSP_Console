#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from Classifier.classifier1 import Classifier, wav_to_si_cut, OUTPUT_CLASSES
from scipy.io import wavfile
import wave
from Classifier.AKA1A import AKA1A
import time
import torchaudio
import torch

WAV_PATH = r"C:\Databases\ZOP-BSP\Database\Raft\UAV2_stream_20251016_113235.wav"
#MODEL_DIR = r"C:\Users\stann\Pytorch\CNN\ZOPBSP\Results\FINAL_2026-02-15_13_10_51"  # folder with model_final.pth + scaler_final.pth





with wave.open(WAV_PATH, "rb") as wf:
    n_channels = wf.getnchannels()
    sample_rate = wf.getframerate()
    sampwidth_bytes = wf.getsampwidth()
    bits_per_sample = sampwidth_bytes * 8

print("channels:", n_channels)
print("sample_rate:", sample_rate)
print("sample_width_bytes:", sampwidth_bytes)
print("bits_per_sample:", bits_per_sample)

fs_i, s_i_cut = wav_to_si_cut(WAV_PATH)
print(f"wav_to_si_cut s_i_cut.min: {s_i_cut.min()}")
print(f"wav_to_si_cut s_i_cut.max: {s_i_cut.max()}")


# fs_i, s_i_cut = wavfile.read(WAV_PATH)
# print(f"wavfile s_i_cut.min: {s_i_cut.min()}")
# print(f"wavfile s_i_cut.max: {s_i_cut.max()}")

#wav, sr = torchaudio.load(WAV_PATH)

# print("dtype:", wav.dtype)
# print("shape:", wav.shape)
# print("min:", wav.min().item())
# print("max:", wav.max().item())
# print("sample rate:", sr)

start_time = time.perf_counter() 
pred_class, class_prob = AKA1A(s_i_cut, fs_i)
elapsed = time.perf_counter() - start_time

print("\n=== RESULT ===")
print(f"pred_class: {pred_class}\nclass_prob:")
for i, name in enumerate(OUTPUT_CLASSES):
    print(f"  {i:2d} {name:18s}: {float(class_prob[i]):.6f}")

print(f"\nElapsed time: {elapsed:.3f} seconds")