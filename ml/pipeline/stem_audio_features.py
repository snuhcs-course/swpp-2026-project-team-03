"""Four spatial/harmonic scores from a BS-RoFormer guitar stem.

Samples four 12-second clips and takes each score's median.
"""

from __future__ import annotations

from math import gcd
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.ndimage import maximum_filter1d
from scipy.signal import resample_poly, stft


SAMPLE_RATE = 11025
CLIP_SEC = 12
FRACTIONS = (0.15, 0.35, 0.55, 0.75)
NFFT = 2048
HOP = 512
NAMES = ("pan_spread", "pan_two_sides", "pitch_polyphony", "pitch_lr_distance")


def pitch_salience(mag: np.ndarray, freqs: np.ndarray) -> np.ndarray:
    midi = np.arange(40, 86)
    fundamental = 440.0 * (2.0 ** ((midi - 69.0) / 12.0))
    result = np.zeros((len(midi), mag.shape[1]), dtype=np.float64)
    for harmonic, weight in ((1, 1.0), (2, 0.6), (3, 0.4)):
        bins = np.clip(np.rint(fundamental * harmonic / (freqs[1] - freqs[0])).astype(int),
                       1, mag.shape[0] - 2)
        result += weight * np.maximum.reduce((mag[bins - 1], mag[bins], mag[bins + 1]))
    return result


def summarize_clip(audio: np.ndarray) -> np.ndarray:
    freqs, _, left = stft(audio[:, 0], fs=SAMPLE_RATE, nperseg=NFFT,
                          noverlap=NFFT - HOP, boundary=None, padded=False)
    _, _, right = stft(audio[:, 1], fs=SAMPLE_RATE, nperseg=NFFT,
                       noverlap=NFFT - HOP, boundary=None, padded=False)
    lm, rm = np.abs(left), np.abs(right)
    total = lm * lm + rm * rm
    band = (freqs >= 120) & (freqs <= 2200)
    band_power = total[band]
    active = band_power.sum(axis=0) > np.quantile(band_power.sum(axis=0), 0.25)
    if not active.any():
        return np.zeros(4)
    pan = (lm[band] ** 2 - rm[band] ** 2) / (band_power + 1e-12)
    cutoff = np.quantile(band_power[:, active], 0.70)
    weights = np.where((band_power > cutoff) & active[None, :], band_power, 0.0)
    normalizer = weights.sum() + 1e-12
    mean_pan = float((weights * pan).sum() / normalizer)
    pan_spread = float(np.sqrt((weights * (pan - mean_pan) ** 2).sum() / normalizer))
    left_mass = float(weights[pan > 0.25].sum())
    right_mass = float(weights[pan < -0.25].sum())
    pan_two_sides = 2 * min(left_mass, right_mass) / (normalizer + 1e-12)
    sal_left = pitch_salience(lm, freqs)
    sal_right = pitch_salience(rm, freqs)
    sal_mid = sal_left + sal_right
    local_peak = sal_mid >= maximum_filter1d(sal_mid, size=3, axis=0)
    strong = sal_mid >= 0.55 * np.max(sal_mid, axis=0, keepdims=True)
    count = (local_peak & strong).sum(axis=0)
    polyphony = float(np.quantile(count[active], 0.75))
    cosine = (sal_left * sal_right).sum(axis=0) / (
        np.linalg.norm(sal_left, axis=0) * np.linalg.norm(sal_right, axis=0) + 1e-12)
    lr_distance = float(np.median((1 - cosine)[active]))
    return np.array([pan_spread, pan_two_sides, polyphony, lr_distance])


def extract(path: Path) -> np.ndarray:
    samples = []
    with sf.SoundFile(str(path)) as stream:
        duration = len(stream) / stream.samplerate
        if duration < CLIP_SEC:
            raise ValueError("guitar stem too short")
        for fraction in FRACTIONS:
            start = min(max(0, int(duration * fraction * stream.samplerate)),
                        len(stream) - int(CLIP_SEC * stream.samplerate))
            stream.seek(start)
            segment = stream.read(int(CLIP_SEC * stream.samplerate), dtype="float32", always_2d=True)
            if segment.shape[1] == 1:
                segment = np.repeat(segment, 2, axis=1)
            elif segment.shape[1] != 2:
                segment = segment[:, :2]
            factor = gcd(stream.samplerate, SAMPLE_RATE)
            segment = resample_poly(segment, SAMPLE_RATE // factor,
                                    stream.samplerate // factor, axis=0)
            samples.append(summarize_clip(segment))
    result = np.median(np.stack(samples), axis=0)
    if result.shape != (4,) or not np.isfinite(result).all():
        raise ValueError("Invalid guitar-stem feature")
    return result
