"""Пересборка нативного хаптика: AHAP с кривыми и VibrationEffect с амплитудой."""
import json
import os
import subprocess

import numpy as np

import haptics
import native
import tactile as T
from dsp import SR

BASE = '../cuelab-production-v13/'
ROOT = BASE + 'export/'


def dec(path):
    raw = subprocess.run(['ffmpeg', '-v', 'quiet', '-i', path, '-f', 'f32le',
                          '-ac', '1', '-ar', str(SR), '-'],
                         check=True, stdout=subprocess.PIPE).stdout
    return np.frombuffer(raw, dtype='<f4').astype(np.float64)


man = json.load(open(BASE + 'sounds.json', encoding='utf-8'))
android_map = {}
os.makedirs(f'{ROOT}ios/haptics', exist_ok=True)

stats = {'events': 0, 'points': 0, 'transients': 0, 'primitives': 0, 'waveform': 0}
for s in man['sounds']:
    y = dec(f"{ROOT}masters/{s['id']}-0.flac")
    level = T.loudness_env(y, SR)
    bright = T.brightness(y, SR)
    times, flux = haptics.onsets(y, SR)
    onsets = []
    if len(times):
        norm = flux / (flux.max() + 1e-9)
        for t, w in zip(times, norm):
            k = min(len(level) - 1, int(round(t * 1000 / T.FRAME_MS)))
            strength = float(np.clip(max(level[k], 0.35 + 0.65 * w ** 0.55), 0.05, 1.0))
            onsets.append((t * 1000, strength, float(bright[k])))

    ap = native.ahap(level, bright, onsets, s['id'])
    ad = native.android(level, bright, onsets)
    with open(f"{ROOT}ios/haptics/{s['id']}.ahap", 'w', encoding='utf-8') as f:
        json.dump(ap, f, ensure_ascii=False, indent=1)
    android_map[s['id']] = {**ad, 'variants': len(s['variants'])}

    s['ahap'] = ap
    s['android'] = ad
    s['hapticEvents'] = [
        {'time': round(t / 1000, 4), 'intensity': round(st, 3), 'sharpness': round(sh, 3)}
        for t, st, sh in onsets
    ]
    stats['events'] += sum(1 for p in ap['Pattern'] if 'Event' in p)
    stats['transients'] += len(onsets)
    stats['points'] += sum(len(p['ParameterCurve']['ParameterCurveControlPoints'])
                           for p in ap['Pattern'] if 'ParameterCurve' in p)
    stats['primitives'] += len(ad['composition'])
    stats['waveform'] += len(ad['timings'])

json.dump(man, open(BASE + 'sounds.json', 'w', encoding='utf-8'),
          ensure_ascii=False, separators=(',', ':'))
os.makedirs(f'{ROOT}android/assets', exist_ok=True)
json.dump(android_map, open(f'{ROOT}android/assets/haptics.json', 'w', encoding='utf-8'),
          ensure_ascii=False, separators=(',', ':'))
print(stats)
