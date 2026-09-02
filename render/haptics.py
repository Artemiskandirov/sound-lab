"""
Хаптик выводится ИЗ ЗВУКА, а не пишется константой.

Три ограничения, из-за которых длинные паттерны не доходили до устройства:

1. ДЛИНА ПАТТЕРНА. Практический предел — около 10 элементов; всё сверх этого
   браузер обрезает или отклоняет. Формулировка MDN «max length depends on
   implementation» звучит мягко, но на деле у сцены из 43 элементов до мотора
   доезжают первые несколько — отсюда «вибро работает только в начале».
   Поэтому паттерн строится не из всех атак подряд, а из НЕСКОЛЬКИХ САМЫХ
   ЗНАЧИМЫХ: первая (сама атака) плюс сильнейшие остальные.

2. ЛИДИРУЮЩИЙ НОЛЬ. Спецификация его допускает, но это лишний элемент из
   дефицитного бюджета и известный источник расхождений между реализациями.
   Паттерн всегда начинается с настоящей вибрации: задержка в 16 мс на слух
   и на ощупь неразличима, а элемент экономит.

3. ПОРОГ ПО ГРОМКОСТИ. Порог, взятый как доля от максимума потока, съедал все
   тихие события у сцен с большим динамическим диапазоном: у победы в марафоне
   первая атака находилась только на 3163 мс, потому что гонг в середине на
   порядок громче тиков в начале. Теперь порог адаптивный — считается от
   локальной медианы, а не от глобального максимума.

Физические ограничения вибромотора:
  * у ERM/LRA есть время раскрутки и остановки ~20-30 мс, поэтому импульсы
    ближе ~55 мс сливаются в один;
  * импульс короче 8-10 мс большинство моторов не отрабатывает вовсе;
  * у Vibration API нет амплитуды, сила выражается только длительностью.
"""
import numpy as np
from scipy import signal

from dsp import SR

MIN_GAP_MS = 55
MIN_PULSE_MS = 10
MAX_PULSE_MS = 60
MAX_PULSES = 5          # 5 импульсов = 9 элементов паттерна, внутри лимита
MAX_ENTRIES = 9
MAX_TOTAL_MS = 8000


def onsets(y, sr=SR, hop=256, win=1024):
    """
    Атаки по спектральному потоку с адаптивным порогом.

    Порог считается от скользящей медианы, поэтому тихое событие в начале
    сцены находится так же уверенно, как громкое в кульминации.
    """
    mono = y.mean(axis=1) if y.ndim == 2 else y
    if len(mono) < win * 2:
        return np.array([0.0]), np.array([1.0])
    # Перед сигналом добавляется настоящая тишина. Без неё самый первый кадр
    # STFT уже содержит атаку целиком, прироста спектра нет и удар просто не
    # находится — детектировалась только вторая нота, а сама атака терялась.
    lead = int(0.040 * sr)
    padded_signal = np.concatenate([np.zeros(lead), mono])
    _, t, S = signal.stft(padded_signal, sr, nperseg=win, noverlap=win - hop, padded=False)
    mag = np.abs(S)
    flux = np.maximum(0.0, np.diff(mag, axis=1)).sum(axis=0)
    if flux.max() <= 0:
        return np.array([0.0]), np.array([1.0])
    times = t[1:] - lead / sr

    # скользящая медиана как локальный уровень фона
    span = max(3, int(0.35 * sr / hop))
    pad = np.pad(flux, (span, span), mode='edge')
    local = np.array([np.median(pad[i:i + 2 * span + 1]) for i in range(len(flux))])
    thresh = local + 0.22 * np.maximum(local, flux.max() * 0.015)

    distance = max(1, int((MIN_GAP_MS / 1000) * sr / hop))
    # find_peaks не умеет возвращать краевые индексы: пику нужны соседи с обеих
    # сторон. У перкуссии максимум потока приходится ровно на первый кадр, и
    # сама атака терялась — детектировалась только вторая нота. Обкладываем
    # массив нулями, чтобы край мог стать пиком, и возвращаем индексы обратно.
    padded = np.concatenate([[0.0], flux, [0.0]])
    thr_pad = np.concatenate([[np.inf], thresh, [np.inf]])
    peaks, _ = signal.find_peaks(padded, height=thr_pad, distance=distance)
    peaks = np.clip(peaks - 1, 0, len(flux) - 1)
    peaks = np.unique(peaks)
    if not len(peaks):
        peaks = np.array([int(np.argmax(flux))])
    # сила события — превышение над локальным фоном, а не абсолютная величина
    strength = np.maximum(flux[peaks] - local[peaks], 1e-9)
    found = times[peaks]
    keep = found >= -0.005          # отбрасываем то, что попало в добавленную тишину
    return np.maximum(found[keep], 0.0), strength[keep]


def _select(times, strength, limit=MAX_PULSES):
    """
    Оставить не больше limit событий, РАВНОМЕРНО ПО ВРЕМЕНИ.

    Отбор просто по силе давал дыры: в победе марафона самые громкие атаки
    сидят в кульминации, и после первого импульса вибрация замолкала на
    4.4 секунды. Поэтому сцена делится на limit отрезков и из каждого берётся
    сильнейшее событие — так хаптик повторяет форму сцены, а не только её пик.
    """
    if len(times) <= limit:
        return times, strength
    span = times[-1] - times[0]
    if span <= 0:
        return times[:limit], strength[:limit]
    keep = {0}
    edges = np.linspace(times[0], times[-1], limit + 1)
    for i in range(limit):
        lo, hi = edges[i], edges[i + 1]
        seg = np.where((times >= lo) & (times <= hi))[0]
        if len(seg):
            keep.add(int(seg[np.argmax(strength[seg])]))
    # если в каких-то отрезках событий не было, добираем сильнейшими
    if len(keep) < limit:
        for i in np.argsort(strength)[::-1]:
            if len(keep) >= limit:
                break
            keep.add(int(i))
    idx = np.array(sorted(keep))[:limit]
    return times[idx], strength[idx]


def pattern(y, sr=SR, intensity=1.0):
    """Массив для navigator.vibrate: [вибрация, пауза, вибрация, ...]."""
    times, strength = onsets(y, sr)
    order = np.argsort(times)
    times, strength = times[order], strength[order]
    times, strength = _select(times, strength)

    weights = strength / (strength.max() + 1e-9)

    mono = y.mean(axis=1) if y.ndim == 2 else y
    env = np.abs(mono)
    live = np.where(env > env.max() * 0.01)[0]
    sound_ms = (live[-1] - live[0]) / sr * 1000 if len(live) else 1000.0
    cap = float(np.clip(sound_ms * 1.15, MIN_PULSE_MS, MAX_PULSE_MS))

    # Паттерн начинается с настоящей вибрации: первая атака переносится в ноль.
    base = times[0]
    events = []
    for t0, w in zip(times, weights):
        span = cap - MIN_PULSE_MS
        ms = int(round(np.clip(MIN_PULSE_MS + span * (w ** 0.6) * intensity,
                               MIN_PULSE_MS, cap)))
        start = int(round((t0 - base) * 1000))
        if events and start - events[-1][0] < MIN_GAP_MS:
            events[-1][1] = int(min(cap, events[-1][1] + ms // 2))
            continue
        events.append([start, ms])

    out, cursor = [], 0
    for start, ms in events:
        gap = start - cursor
        if out:
            if gap <= 0:
                out[-1] = int(min(cap, out[-1] + ms))
                continue
            out.append(int(gap))
        out.append(ms)
        cursor = start + ms

    total, trimmed = 0, []
    for value in out:
        if len(trimmed) >= MAX_ENTRIES or total + value > MAX_TOTAL_MS:
            break
        trimmed.append(int(value))
        total += value
    if trimmed and len(trimmed) % 2 == 0:
        trimmed.pop()
    return trimmed or [20]


def pulses(pat):
    """Сколько в паттерне реальных вибраций (нули не считаются)."""
    return sum(1 for i, v in enumerate(pat) if i % 2 == 0 and v > 0)


def coverage(y, pat, sr=SR):
    mono = y.mean(axis=1) if y.ndim == 2 else y
    env = np.abs(mono)
    live = np.where(env > env.max() * 0.01)[0]
    sound_ms = (live[-1] - live[0]) / sr * 1000 if len(live) else 0.0
    return sum(pat), sound_ms
