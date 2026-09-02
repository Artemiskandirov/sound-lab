"""Пересборка паттернов под формат и движок web-haptics."""
import json

import haptics_dense as HD

BASE = '../cuelab-production-v13/'
man = json.load(open(BASE + 'sounds.json', encoding='utf-8'))

web = {}
segs = clicks = calls = 0
for s in man['sounds']:
    pattern = HD.segments(s['env'], s['envStepMs'])
    flat = HD.to_flat_web(pattern, 0.7)
    chunks = HD.to_chunks_web(flat)
    ct = HD.click_times(pattern, 0.7)
    s['pattern'] = pattern
    s['webHaptics'] = pattern
    s['chunks'] = chunks
    s['clicks'] = len(ct)
    s['clickTimes'] = ct
    segs += len(pattern)
    clicks += len(ct)
    calls += len(chunks)
    web[s['id']] = {'pattern': pattern, 'chunks': chunks, 'clicks': len(ct)}

json.dump(man, open(BASE + 'sounds.json', 'w', encoding='utf-8'),
          ensure_ascii=False, separators=(',', ':'))
json.dump(web, open(BASE + 'export/web/cuelab-haptics.json', 'w', encoding='utf-8'),
          ensure_ascii=False, separators=(',', ':'))
over = [s['id'] for s in man['sounds'] if any(len(c['pattern']) > 10 for c in s['chunks'])]
print(f'отрезков {segs}, щелчков {clicks}, вызовов vibrate {calls}, сверх лимита {len(over)}')
