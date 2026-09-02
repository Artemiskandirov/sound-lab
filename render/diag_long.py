"""Насколько паттерн вибро повторяет события длинного звука."""
import json, subprocess
import numpy as np
import haptics, tactile as T
from dsp import SR

BASE = '../cuelab-production-v13/'

def dec(sid):
    raw = subprocess.run(['ffmpeg','-v','quiet','-i',f'{BASE}export/masters/{sid}-0.flac',
                          '-f','f32le','-ac','1','-ar',str(SR),'-'],
                         check=True, stdout=subprocess.PIPE).stdout
    return np.frombuffer(raw, dtype='<f4').astype(np.float64)

def articulation(pattern, onset_ms, tol=64):
    """Атака считается переданной, если рядом начинается отрезок или растёт сила."""
    marks = []
    t = 0.0
    prev = 0.0
    for v in pattern:
        t += v.get('delay', 0)
        if v.get('delay', 0) > 0 or v['intensity'] - prev > 0.12:
            marks.append(t)
        prev = v['intensity']
        t += v['duration']
    hit = sum(1 for o in onset_ms if any(abs(o - m) <= tol for m in marks))
    return hit, len(onset_ms), len(marks)

man = json.load(open(BASE + 'sounds.json', encoding='utf-8'))
longs = [s for s in man['sounds'] if s['durationMs'] >= 900]
print(f'длинных звуков (>=900 мс): {len(longs)}\n')
tot_hit = tot_on = 0
worst = []
for s in longs:
    y = dec(s['id'])
    ot, _ = haptics.onsets(y, SR)
    onset_ms = [t * 1000 for t in ot]
    hit, n, marks = articulation(s['pattern'], onset_ms)
    tot_hit += hit; tot_on += n
    # доля времени, проведённая в одном отрезке дольше 300 мс — «плита»
    slab = sum(v['duration'] for v in s['pattern'] if v['duration'] > 300)
    worst.append((hit / max(n,1), s['title'], hit, n, marks, len(s['pattern']),
                  round(slab / max(s['durationMs'],1), 2), s['durationMs']))
worst.sort()
print(f'{"звук":26s} {"атак":>5s} {"передано":>9s} {"отрезков":>9s} {"плиты":>6s}')
for w in worst[:12]:
    print(f'{w[1][:26]:26s} {w[3]:5d} {w[2]:9d} {w[5]:9d} {w[6]:6.0%}')
print(f'\nвсего атак {tot_on}, передано {tot_hit} = {tot_hit/max(tot_on,1):.0%}')
