"""Строгая проверка нативных выгрузок."""
import glob
import json

problems = []
files = sorted(glob.glob('../cuelab-production-v13/export/ios/haptics/*.ahap'))
ev = tr = cont = pts = 0
maxpts = maxdur = 0
for path in files:
    d = json.load(open(path, encoding='utf-8'))
    name = path.split('/')[-1]
    if d.get('Version') != 1:
        problems.append(f'{name}: Version != 1')
    last = -1e9
    for item in d['Pattern']:
        if len(item) != 1:
            problems.append(f'{name}: у элемента Pattern больше одного ключа')
        if 'Event' in item:
            e = item['Event']
            ev += 1
            if e['EventType'] == 'HapticTransient':
                tr += 1
                if 'EventDuration' in e:
                    problems.append(f'{name}: у transient задан EventDuration')
            elif e['EventType'] == 'HapticContinuous':
                cont += 1
                if not (0 < e.get('EventDuration', 0) <= 30):
                    problems.append(f'{name}: EventDuration вне (0, 30]')
                maxdur = max(maxdur, e['EventDuration'])
            else:
                problems.append(f'{name}: неизвестный EventType {e["EventType"]}')
            ids = set()
            for p in e['EventParameters']:
                ids.add(p['ParameterID'])
                if not (0.0 <= p['ParameterValue'] <= 1.0):
                    problems.append(f'{name}: {p["ParameterID"]}={p["ParameterValue"]} вне 0..1')
            if ids != {'HapticIntensity', 'HapticSharpness'}:
                problems.append(f'{name}: параметры события {ids}')
            t = e['Time']
        else:
            c = item['ParameterCurve']
            if c['ParameterID'] not in ('HapticIntensityControl', 'HapticSharpnessControl'):
                problems.append(f'{name}: неизвестный ParameterID {c["ParameterID"]}')
            lo, hi = (0.0, 1.0) if c['ParameterID'].startswith('HapticIntensity') else (-1.0, 1.0)
            cp = c['ParameterCurveControlPoints']
            pts += len(cp)
            maxpts = max(maxpts, len(cp))
            if len(cp) < 2:
                problems.append(f'{name}: в кривой меньше двух точек')
            pt = -1e9
            for p in cp:
                if not (lo <= p['ParameterValue'] <= hi):
                    problems.append(f'{name}: точка {p["ParameterValue"]} вне {lo}..{hi}')
                if p['Time'] < pt:
                    problems.append(f'{name}: время точек не по возрастанию')
                pt = p['Time']
            t = c['Time']
        if t < last:
            problems.append(f'{name}: элементы Pattern не по времени')
        last = t

andr = json.load(open('../cuelab-production-v13/export/android/assets/haptics.json', encoding='utf-8'))
wf = comp = 0
for sid, a in andr.items():
    if len(a['timings']) != len(a['amplitudes']):
        problems.append(f'{sid}: длины timings и amplitudes не совпадают')
    if any(t <= 0 for t in a['timings']):
        problems.append(f'{sid}: неположительная длительность в timings')
    if any(not (0 <= v <= 255) for v in a['amplitudes']):
        problems.append(f'{sid}: амплитуда вне 0..255')
    if a['amplitudes'] and a['amplitudes'][-1] == 0:
        problems.append(f'{sid}: waveform заканчивается тишиной')
    for c in a['composition']:
        if not (0 < c['scale'] <= 1):
            problems.append(f'{sid}: scale примитива вне (0,1]')
        if c['delayMs'] < 0:
            problems.append(f'{sid}: отрицательная задержка примитива')
        if c['primitive'] not in ('TICK', 'CLICK', 'THUD'):
            problems.append(f'{sid}: неизвестный примитив {c["primitive"]}')
    wf += len(a['timings'])
    comp += len(a['composition'])

print(f'AHAP файлов {len(files)}: событий {ev} (continuous {cont}, transient {tr}), '
      f'точек кривых {pts}, максимум точек в кривой {maxpts}, '
      f'самое длинное continuous {maxdur:.2f} с')
print(f'Android: звуков {len(andr)}, отрезков waveform {wf}, примитивов {comp}')
print(f'ПРОБЛЕМ: {len(problems)}')
for p in problems[:12]:
    print(' ', p)
