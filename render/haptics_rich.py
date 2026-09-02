"""
Богатый хаптик для нативных платформ.

Веб-версия (haptics.py) умеет только длительности: у Vibration API нет
амплитуды, и силу приходится кодировать длиной импульса. У iOS Core Haptics и
у Android VibrationEffect амплитуда есть, поэтому для приложений хаптик должен
нести настоящие силу и резкость — иначе мы искусственно обедняем платформу,
которая умеет больше.

  intensity — из превышения спектрального потока над локальным фоном;
  sharpness — из спектрального центроида в момент атаки: удар по металлу
              ощущается «острее» удара по дереву, и это измеримо;
  continuous — события длиннее 140 мс, у которых энергия держится, а не падает.
"""
import numpy as np
from scipy import signal

import haptics
from dsp import SR

# Границы, в которых центроид отображается в резкость 0..1. Ниже 500 Гц
# ощущение тупое, выше 5 кГц — предельно резкое; между ними логарифм.
SHARP_LO, SHARP_HI = 500.0, 5000.0
CONTINUOUS_MS = 140


def _centroid_at(mono, t0, sr=SR, win=2048):
    """Спектральный центроид в окне сразу после атаки."""
    start = int(t0 * sr)
    seg = mono[start:start + win]
    if len(seg) < 64:
        return 1500.0
    # Окно Ханна зануляет НАЧАЛО сегмента, а у перкуссии вся яркость именно
    # в атаке: у нажатия центроид падал с 1650 до 556 Гц, и удар по дереву
    # получался «мягче» удара по вате. Окно должно только гасить хвост.
    taper = np.ones(len(seg))
    half = len(seg) // 2
    taper[half:] = np.cos(np.linspace(0, np.pi / 2, len(seg) - half)) ** 2
    seg = seg * taper
    sp = np.abs(np.fft.rfft(seg)) ** 2
    fr = np.fft.rfftfreq(len(seg), 1 / sr)
    total = sp.sum()
    return float((fr * sp).sum() / total) if total > 0 else 1500.0


def _sustain_after(mono, t0, sr=SR, span_ms=CONTINUOUS_MS):
    """Держится ли энергия после атаки — признак continuous-события."""
    a = int(t0 * sr)
    b = a + int(span_ms / 1000 * sr)
    if b >= len(mono):
        return 0.0
    head = np.abs(mono[a:a + int(0.02 * sr)]).mean() + 1e-9
    tail = np.abs(mono[b - int(0.02 * sr):b]).mean()
    return float(np.clip(tail / head, 0, 1))


def events(y, sr=SR, max_events=48):
    """
    Полный список событий: время, сила, резкость, тип, длительность.
    Ограничение здесь мягче веб-версии: Core Haptics и VibrationEffect
    спокойно принимают десятки событий.
    """
    mono = y.mean(axis=1) if y.ndim == 2 else y
    times, strength = haptics.onsets(y, sr)
    if not len(times):
        return []
    order = np.argsort(times)
    times, strength = times[order], strength[order]
    if len(times) > max_events:
        keep = np.argsort(strength)[::-1][:max_events]
        keep = np.sort(keep)
        times, strength = times[keep], strength[keep]

    weights = strength / (strength.max() + 1e-9)
    out = []
    for i, (t0, w) in enumerate(zip(times, weights)):
        centroid = _centroid_at(mono, t0, sr)
        sharp = float(np.clip(
            np.log(max(centroid, 1.0) / SHARP_LO) / np.log(SHARP_HI / SHARP_LO), 0.0, 1.0))
        intensity = float(np.clip(0.25 + 0.75 * (w ** 0.55), 0.05, 1.0))
        nxt = times[i + 1] if i + 1 < len(times) else t0 + 0.4
        gap = nxt - t0
        sustain = _sustain_after(mono, t0, sr)
        if gap * 1000 > CONTINUOUS_MS and sustain > 0.35:
            out.append({
                'time': round(float(t0), 4),
                'type': 'continuous',
                'duration': round(float(min(gap * 0.85, 1.5)), 4),
                'intensity': round(intensity * 0.8, 3),
                'sharpness': round(sharp, 3),
            })
        else:
            out.append({
                'time': round(float(t0), 4),
                'type': 'transient',
                'duration': 0.0,
                'intensity': round(intensity, 3),
                'sharpness': round(sharp, 3),
            })
    return out


def to_ahap(evs, name='CueLab'):
    """
    AHAP для iOS Core Haptics.

    Каждый элемент массива Pattern обёрнут в ключ "Event" — так устроены
    образцы Apple. Значения HapticIntensity и HapticSharpness в диапазоне 0..1.
    """
    pattern = []
    for e in evs:
        event = {
            'Time': e['time'],
            'EventType': 'HapticContinuous' if e['type'] == 'continuous' else 'HapticTransient',
            'EventParameters': [
                {'ParameterID': 'HapticIntensity', 'ParameterValue': e['intensity']},
                {'ParameterID': 'HapticSharpness', 'ParameterValue': e['sharpness']},
            ],
        }
        if e['type'] == 'continuous':
            event['EventDuration'] = e['duration']
        pattern.append({'Event': event})
    return {
        'Version': 1,
        'Metadata': {'Project': 'CueLab', 'Pattern': name,
                     'Description': 'Выведено из формы волны звука'},
        'Pattern': pattern,
    }


def to_android(evs, min_pulse_ms=12):
    """
    Данные для VibrationEffect.createWaveform(timings, amplitudes, -1).

    Массивы идут парами «пауза, вибрация»: у Android амплитуда 0..255 задаётся
    на каждый отрезок отдельно, поэтому силу можно передать честно, а не
    кодировать длительностью, как в вебе.
    """
    timings, amps = [], []
    cursor = 0.0
    for e in evs:
        start_ms = e['time'] * 1000
        gap = int(round(start_ms - cursor))
        if gap > 0:
            timings.append(gap)
            amps.append(0)
        if e['type'] == 'continuous':
            dur = max(min_pulse_ms, int(round(e['duration'] * 1000)))
        else:
            # у transient длительности нет — даём короткий отрезок,
            # силу несёт амплитуда
            dur = max(min_pulse_ms, int(round(14 + 26 * e['intensity'])))
        timings.append(dur)
        amps.append(int(np.clip(round(e['intensity'] * 255), 1, 255)))
        cursor = start_ms + dur
    if not timings:
        timings, amps = [20], [180]
    return {'timings': timings, 'amplitudes': amps, 'repeat': -1}
