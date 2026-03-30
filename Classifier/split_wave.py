# -*- coding: utf-8 -*-
"""
Created on Wed Jan 28 18:09:07 2026

@author: stann
"""

import os
import wave


def split_wav(in_wav, out_dir, chunk_seconds):
    os.makedirs(out_dir, exist_ok=True)

    with wave.open(in_wav, "rb") as w:
        n_channels = w.getnchannels()
        sampwidth = w.getsampwidth()
        framerate = w.getframerate()
        n_frames = w.getnframes()

        frames_per_chunk = int(chunk_seconds * framerate)
        n_chunks = (n_frames + frames_per_chunk - 1) // frames_per_chunk  # ceil

        for i in range(n_chunks):
            w.setpos(i * frames_per_chunk)
            frames = w.readframes(frames_per_chunk)
            if not frames:
                break

            out_path = os.path.join(out_dir, f"chunk_{120}.wav")
            with wave.open(out_path, "wb") as out:
                out.setnchannels(n_channels)
                out.setsampwidth(sampwidth)
                out.setframerate(framerate)
                out.writeframes(frames)
                
            break


# Example:
split_wav('C:\\Code\\ZOPBSP_25_05_11\\UAV1_stream_20251016_124658.wav', 'C:\\Code\\ZOPBSP_25_05_11', chunk_seconds=120.0)