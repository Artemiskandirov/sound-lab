"""Пересборка паттернов вибро: громкость по кривой A, зерно по яркости."""
import json
import subprocess

import numpy as np

import haptics
import haptics_dense as HD
import tactile as T
from dsp import SR

BASE = '../cuelab-production-v13/'


def decode(path):
    raw = subprocess.run(
        ['ffmpeg', '-v', 'quiet', '-i', path, '-f', 'f32le', '-ac', '1',
         '-ar', str(SR), '-'], check=True, stdout=subprocess.PIPE).stdout
    return np.frombuffer(raw, dtype='<f4').astype(np.float64)


man = json.load(open(BASE + 'sounds.json', encoding='utf-8'))
web = {}
segs = clicks = calls = 0
rows = []
for s in man['sounds']:
    y = decode(f"{BASE}export/masters/{s['id']}-0.flac")
    level = T.loudness_env(y, SR)
    bright = T.brightness(y, SR)
    # Атаки берём из самой волны спектральным потоком, а не из огибающей:
    # после сглаживания скользящим максимумом удары в ней уже смазаны.
    onset_t, _ = haptics.onsets(y, SR)
    pattern = T.segments(level, bright, onset_ms=[t * 1000 for t in onset_t])
    flat = HD.to_flat_web(pattern, 0.7)
    chunks = HD.to_chunks_web(flat)
    ct = HD.click_times(pattern, 0.7)
    gaps = sorted(ct[i + 1] - ct[i] for i in range(len(ct) - 1)) or [0]
    # Средняя яркость — взвешенная по громкости: тихий хвост не должен
    # перевешивать удар, который и определяет характер звука.
    wsum = float(level.sum())
    mean_bright = float((bright * level).sum() / wsum) if wsum > 0 else 0.5

    s['env'] = [int(round(v * 100)) for v in level]
    s['bright'] = [int(round(v * 100)) for v in bright]
    s['envStepMs'] = int(T.FRAME_MS)
    s['brightness'] = round(mean_bright, 2)
    s['pattern'] = pattern
    s['webHaptics'] = pattern
    s['chunks'] = chunks
    s['clicks'] = len(ct)
    s['clickGapMs'] = int(gaps[len(gaps) // 2])
    segs += len(pattern)
    clicks += len(ct)
    calls += len(chunks)
    web[s['id']] = {'pattern': pattern, 'chunks': chunks, 'clicks': len(ct),
                    'brightness': round(mean_bright, 2)}
    rows.append((s['id'], s['title'], mean_bright, gaps[len(gaps) // 2], len(ct)))

json.dump(man, open(BASE + 'sounds.json', 'w', encoding='utf-8'),
          ensure_ascii=False, separators=(',', ':'))
json.dump(web, open(BASE + 'export/web/cuelab-haptics.json', 'w', encoding='utf-8'),
          ensure_ascii=False, separators=(',', ':'))

rows.sort(key=lambda r: r[2])
print(f'отрезков {segs}, щелчков {clicks}, вызовов vibrate {calls}')
print('\nсамые глухие (крупное зерно):')
for r in rows[:6]:
    print(f'  {r[1][:26]:26s} яркость {r[2]:.2f}  интервал {r[3]:3d} мс  щелчков {r[4]:3d}')
print('самые звонкие (мелкое зерно):')
for r in rows[-6:]:
    print(f'  {r[1][:26]:26s} яркость {r[2]:.2f}  интервал {r[3]:3d} мс  щелчков {r[4]:3d}')
over = [s['id'] for s in man['sounds'] if any(len(c['pattern']) > 10 for c in s['chunks'])]
print('\nчанков сверх лимита 10:', len(over))
