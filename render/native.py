"""
Хаптик для нативных приложений: настоящая амплитуда, без обходов.

В вебе единственный рычаг — частота щелчков, и вибрация там ИМИТИРУЕТСЯ. В
Core Haptics и в VibrationEffect амплитуда настоящая и меняется непрерывно,
поэтому нативная версия строится иначе: не «россыпь событий», а непрерывное
событие с кривыми параметров, идущими за звуком кадр в кадр.

iOS:
  * HapticContinuous на каждый звучащий участок;
  * ParameterCurve HapticIntensityControl — множитель силы 0..1 по огибающей;
  * ParameterCurve HapticSharpnessControl — СДВИГ резкости −1..1 по яркости
    (это именно сдвиг, а не множитель, поэтому базовая резкость события 0,5,
    а кривая несёт отклонение);
  * HapticTransient на каждой атаке со своей силой и резкостью.

Android:
  * waveform с амплитудами 0..255 по огибающей, шаг 16 мс;
  * composition из примитивов (CLICK/TICK/THUD) на атаках для устройств,
    которые их поддерживают, — примитивы ощущаются чище, чем прямоугольные
    импульсы waveform.
"""
import numpy as np

FRAME_MS = 32.0
ANDROID_STEP_MS = 16
MAX_CURVE_POINTS = 96      # больше Core Haptics принимать не обязан
CURVE_EPS = 0.03           # порог, ниже которого точку кривой можно выбросить
MAX_GAP_MS = 200.0         # дальше этого точку ставим принудительно
SILENCE = 0.06             # ниже этого уровня — тишина, событие обрывается
MIN_REGION_MS = 48.0


def regions(level, step_ms=FRAME_MS):
    """Звучащие участки: (начало_мс, конец_мс) — между ними настоящая тишина."""
    out = []
    start = None
    for i, v in enumerate(level):
        if v >= SILENCE and start is None:
            start = i
        elif v < SILENCE and start is not None:
            if (i - start) * step_ms >= MIN_REGION_MS:
                out.append((start * step_ms, i * step_ms))
            start = None
    if start is not None:
        out.append((start * step_ms, len(level) * step_ms))
    return out


def thin(points, eps=CURVE_EPS, max_gap=MAX_GAP_MS, limit=MAX_CURVE_POINTS):
    """
    Прореживание кривой: точка нужна, если значение заметно изменилось, если
    после прошлой прошло больше max_gap, или если это локальный экстремум.
    Концы сохраняются всегда.
    """
    if len(points) <= 2:
        return list(points)
    keep = [points[0]]
    for i in range(1, len(points) - 1):
        t, v = points[i]
        pv = keep[-1][1]
        nv = points[i + 1][1]
        extremum = (v - pv) * (nv - v) < 0
        if abs(v - pv) >= eps or t - keep[-1][0] >= max_gap or extremum:
            keep.append((t, v))
    keep.append(points[-1])
    if len(keep) > limit:
        idx = np.linspace(0, len(keep) - 1, limit).round().astype(int)
        keep = [keep[i] for i in sorted(set(idx))]
    return keep


def ahap(level, bright, onsets, name='CueLab', step_ms=FRAME_MS):
    """
    AHAP для Core Haptics.

    Каждый элемент Pattern обёрнут в ключ Event или ParameterCurve — так
    устроены образцы Apple. HapticIntensity и HapticSharpness лежат в 0..1,
    значения кривой HapticSharpnessControl — в −1..1, потому что это сдвиг.
    """
    pattern = []
    for a, b in regions(level, step_ms):
        i0, i1 = int(a / step_ms), int(b / step_ms)
        pattern.append({'Event': {
            'Time': round(a / 1000, 4),
            'EventType': 'HapticContinuous',
            'EventDuration': round((b - a) / 1000, 4),
            'EventParameters': [
                {'ParameterID': 'HapticIntensity', 'ParameterValue': 1.0},
                # базовая резкость посередине: кривая ниже сдвигает её в обе
                # стороны, а сдвинуть вверх от 1.0 было бы некуда
                {'ParameterID': 'HapticSharpness', 'ParameterValue': 0.5},
            ],
        }})

    for t, strength, sharp in onsets:
        pattern.append({'Event': {
            'Time': round(t / 1000, 4),
            'EventType': 'HapticTransient',
            'EventParameters': [
                {'ParameterID': 'HapticIntensity', 'ParameterValue': round(float(strength), 3)},
                {'ParameterID': 'HapticSharpness', 'ParameterValue': round(float(sharp), 3)},
            ],
        }})

    inten = thin([(i * step_ms, float(v)) for i, v in enumerate(level)])
    sharpc = thin([(i * step_ms, float(b) - 0.5) for i, b in enumerate(bright)])
    for pid, pts in (('HapticIntensityControl', inten), ('HapticSharpnessControl', sharpc)):
        # Кривая из одной точки недопустима, да и не нужна: звук короче двух
        # кадров — это чистый транзиент, у него нет огибающей, которую можно
        # вести. Такие сцены остаются одним HapticTransient, как и положено.
        if len(pts) < 2:
            continue
        pattern.append({'ParameterCurve': {
            'ParameterID': pid,
            'Time': 0,
            'ParameterCurveControlPoints': [
                {'Time': round(t / 1000, 4), 'ParameterValue': round(v, 3)} for t, v in pts
            ],
        }})

    pattern.sort(key=lambda p: p.get('Event', p.get('ParameterCurve'))['Time'])
    return {
        'Version': 1,
        'Metadata': {
            'Project': 'CueLab', 'Pattern': name,
            'Description': 'Огибающая громкости по кривой A, резкость по спектральному центроиду',
        },
        'Pattern': pattern,
    }


def android(level, bright, onsets, step_ms=FRAME_MS, out_step=ANDROID_STEP_MS):
    """
    waveform + composition для VibrationEffect.

    waveform: амплитуды 0..255 по огибающей с шагом 16 мс, соседние равные
    отрезки слиты — так массив короче, а форма не меняется.
    composition: примитив на каждую атаку. TICK для звонкого, CLICK для
    среднего, THUD для глухого; масштаб равен силе атаки.
    """
    total_ms = len(level) * step_ms
    steps = max(1, int(round(total_ms / out_step)))
    amps = []
    for k in range(steps):
        idx = min(len(level) - 1, int(k * out_step / step_ms))
        amps.append(int(np.clip(round(level[idx] * 255), 0, 255)))
    # атаки поднимаем: у прямоугольного импульса нет собственного транзиента
    for t, strength, _ in onsets:
        k = int(round(t / out_step))
        for d in (0, 1):
            if 0 <= k + d < len(amps):
                amps[k + d] = int(np.clip(max(amps[k + d], round(strength * 255)), 0, 255))

    timings, amplitudes = [], []
    for a in amps:
        if amplitudes and amplitudes[-1] == a:
            timings[-1] += out_step
        else:
            timings.append(out_step)
            amplitudes.append(a)
    while amplitudes and amplitudes[-1] == 0:
        amplitudes.pop()
        timings.pop()
    if not timings:
        timings, amplitudes = [20], [180]

    comp = []
    prev = 0.0
    for t, strength, sharp in onsets:
        primitive = 'TICK' if sharp > 0.66 else ('CLICK' if sharp > 0.33 else 'THUD')
        comp.append({'primitive': primitive,
                     'scale': round(float(np.clip(strength, 0.05, 1.0)), 3),
                     'delayMs': int(round(t - prev))})
        prev = t
    return {'timings': timings, 'amplitudes': amplitudes, 'repeat': -1,
            'composition': comp[:32], 'stepMs': out_step}
