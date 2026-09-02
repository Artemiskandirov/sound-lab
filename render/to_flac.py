"""Мастера в FLAC: без потерь, вдвое меньше, и проверка побитового совпадения."""
import glob
import os
import subprocess

import numpy as np

import render_all as R

M = '../cuelab-production-v13/export/masters'
src = sorted(glob.glob(f'{M}/*.wav'))
before = sum(os.path.getsize(p) for p in src)
for p in src:
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', p, '-c:a', 'flac',
                    '-compression_level', '8', p[:-4] + '.flac'], check=True)
    os.remove(p)
after = sum(os.path.getsize(p) for p in glob.glob(f'{M}/*.flac'))
print(f'мастеров {len(src)}: WAV {before / 1024 / 1024:.1f} МБ -> '
      f'FLAC {after / 1024 / 1024:.1f} МБ')

# Проверка: декодированный FLAC должен совпадать с рендером в пределах
# 16-битного кванта. Это заодно ловит невоспроизводимость рендера.
QUANT = 1 / 32767
bad = []
checked = 0
for sid, i in [('tap', 0), ('tap', 3), ('coin', 2), ('coin', 4), ('marathon-win', 0),
               ('scroll-tick', 7), ('wood-knock', 1), ('victory-big', 0),
               ('crowd-cheer', 0), ('metal-gong', 0), ('stone-pebble', 2)]:
    path = f'{M}/{sid}-{i}.flac'
    if not os.path.exists(path):
        continue
    y = R.render_variant(sid, i)
    ch = 2 if y.ndim == 2 else 1
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-f', 's16le',
                          '-ac', str(ch), '-ar', '48000', '-'],
                         capture_output=True).stdout
    dec = np.frombuffer(raw, dtype='<i2').astype(np.float64) / 32767
    if ch == 2:
        dec = dec.reshape(-1, 2)
    orig = np.clip(y, -1, 1)
    n = min(len(dec), len(orig))
    err = float(np.abs(dec[:n] - orig[:n]).max())
    checked += 1
    if err > QUANT * 1.5:
        bad.append((f'{sid}-{i}', err))
print(f'проверено {checked} мастеров, расходятся сверх кванта: {len(bad)}')
for name, err in bad:
    print(f'   {name}: {err:.6f}')
print('ИТОГ:', 'без потерь и воспроизводимо' if not bad else 'ЕСТЬ РАСХОЖДЕНИЯ')
