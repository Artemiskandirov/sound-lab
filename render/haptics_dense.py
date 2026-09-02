"""
Плотный хаптик, повторяющий звук.

Прошлая версия давала пять импульсов на сцену — этого хватает, чтобы отметить
события, но не хватает, чтобы вибрация ОЩУЩАЛАСЬ как звук. Пять точек на шесть
секунд — это пунктир, а не форма.

Ограничение никуда не делось: спецификация Vibration API прямо задаёт
«Let max length have the value 10» и обрезает всё сверх десяти записей. Но
активация для vibrate() — sticky, а не transient: она держится всё время жизни
страницы после первого касания. Значит длинную дорожку можно нарезать на куски
по десять записей и выдавать их по таймеру встык. Каждый вызов отменяет
предыдущий — и это ровно то, что нужно, если следующий кусок стартует в момент
окончания предыдущего.

Здесь строится сама дорожка: транзиенты на атаках плюс серия импульсов,
плотность и длительность которых идут за огибающей.
"""
import numpy as np
from scipy import signal

import haptics
from dsp import SR

MIN_PULSE_MS = 10
MAX_PULSE_MS = 55
MIN_GAP_MS = 24          # ниже этого мотор не успевает остановиться
FRAME_MS = 32            # шаг сетки, по которой идёт огибающая
FLOOR_DB = -48.0         # ниже этого уровня относительно пика вибрации нет


def envelope(y, sr=SR, frame_ms=FRAME_MS):
    """Огибающая по кадрам: среднеквадратичное в окне, нормировано к пику."""
    mono = y.mean(axis=1) if y.ndim == 2 else y
    hop = max(1, int(frame_ms / 1000 * sr))
    n = max(1, len(mono) // hop)
    env = np.array([np.sqrt((mono[i * hop:(i + 1) * hop] ** 2).mean() + 1e-12)
                    for i in range(n)])
    peak = env.max()
    if peak <= 0:
        return env, hop / sr
    # Шкала логарифмическая: слух и осязание работают в децибелах, а по
    # линейной доле тихое начало сцены проваливается под порог. У победы в
    # марафоне гонг в середине настолько громче вступления, что вся первая
    # треть оставалась без вибрации.
    db = 20 * np.log10(env / peak + 1e-9)
    level = np.clip((db - FLOOR_DB) / (0.0 - FLOOR_DB), 0.0, 1.0)
    return level, hop / sr


def track(y, sr=SR, intensity=1.0, max_ms=6000):
    """
    Дорожка событий: [{'t': сек, 'ms': длительность, 'i': сила 0..1}, ...].

    Атаки дают сильные короткие импульсы, удерживаемая энергия — цепочку
    импульсов, у которых длительность растёт с громкостью. Пауза между
    импульсами тоже зависит от громкости: громче — чаще, и это ощущается
    как непрерывное усиление, а не как отдельные тычки.
    """
    env, step = envelope(y, sr)
    # Импульс не должен быть длиннее самого звука: у тика в 11 мс вибрация
    # на 55 мс ощущается отдельным событием, не связанным с тем, что слышно.
    mono = y.mean(axis=1) if y.ndim == 2 else y
    amp = np.abs(mono)
    live = np.where(amp > amp.max() * 0.01)[0]
    sound_ms = (live[-1] - live[0]) / sr * 1000 if len(live) else 1000.0
    cap = float(np.clip(sound_ms * 1.1, MIN_PULSE_MS, MAX_PULSE_MS))
    onset_times, onset_strength = haptics.onsets(y, sr)
    onset_set = set(int(round(t / step)) for t in onset_times)
    strength_at = {}
    if len(onset_times):
        norm = onset_strength / (onset_strength.max() + 1e-9)
        for t, w in zip(onset_times, norm):
            strength_at[int(round(t / step))] = float(w)

    events = []
    last_end = -1e9
    for i, level in enumerate(env):
        t = i * step
        if t * 1000 > max_ms:
            break
        if level <= 0.02:
            continue
        is_onset = i in onset_set
        # На атаке импульс всегда длиннее: транзиент должен читаться как удар.
        weight = max(level, strength_at.get(i, 0.0)) if is_onset else level
        ms = MIN_PULSE_MS + (cap - MIN_PULSE_MS) * (weight ** 0.7) * intensity
        if is_onset:
            ms = min(cap, ms * 1.35)
        ms = int(round(np.clip(ms, MIN_PULSE_MS, cap)))
        start_ms = t * 1000
        if start_ms - last_end < MIN_GAP_MS and not is_onset:
            continue
        if start_ms - last_end < MIN_GAP_MS * 0.5:
            continue
        events.append({'t': round(float(t), 4), 'ms': ms, 'i': round(float(weight), 3)})
        last_end = start_ms + ms
    if not events:
        events = [{'t': 0.0, 'ms': 20, 'i': 0.6}]
    return events


def to_flat(events):
    """
    Плоский массив [вибрация, пауза, ...] для navigator.vibrate.
    Может быть длиннее десяти — его нарезает плеер.
    """
    out = []
    cursor = 0.0
    for e in events:
        start = e['t'] * 1000
        gap = int(round(start - cursor))
        if out:
            out.append(max(0, gap))
        elif gap > 0:
            out += [0, gap]
        out.append(e['ms'])
        cursor = start + e['ms']
    return out


def to_web_haptics(events):
    """
    Формат в духе lochie/web-haptics: объекты с delay, duration и intensity.
    Читается глазами и переносится в чужой проект без расшифровки.
    """
    out = []
    cursor = 0.0
    for e in events:
        start = e['t'] * 1000
        delay = int(round(start - cursor))
        item = {'duration': e['ms'], 'intensity': round(e['i'], 2)}
        if delay > 0 and out:
            item['delay'] = delay
        elif delay > 0:
            item['delay'] = delay
        out.append(item)
        cursor = start + e['ms']
    return out


def chunks(flat, max_len=10):
    """
    Нарезка на куски по десять записей со временем старта каждого.

    Спецификация: «If the length of the pattern is greater than max length,
    truncate pattern, leaving only the first max length entries», где
    max length = 10. Поэтому длинная дорожка играется несколькими вызовами,
    каждый в момент окончания предыдущего.
    """
    out = []
    at = 0
    i = 0
    # Ведущая пара [0, пауза] появляется, когда первое событие не в нуле.
    # В паттерне она занимает две записи из десяти и при этом ничего не даёт —
    # переносим её в задержку старта чанка.
    if len(flat) >= 2 and flat[0] == 0:
        at += int(flat[1])
        i = 2
    while i < len(flat):
        piece = flat[i:i + max_len]
        # Кусок обязан заканчиваться вибрацией: иначе следующий кусок начнётся
        # с паузы, а vibrate() трактует ПЕРВЫЙ элемент как вибрацию — пауза
        # превратится в длинный гул не в том месте.
        if len(piece) % 2 == 0:
            piece = piece[:-1]
        if not piece:
            break
        out.append({'at': at, 'pattern': [int(v) for v in piece]})
        at += sum(piece)
        i += len(piece)
        # следующий элемент — пауза; она уходит в задержку старта, а не в паттерн
        if i < len(flat):
            at += int(flat[i])
            i += 1
    return out


def stats(events, y, sr=SR):
    mono = y.mean(axis=1) if y.ndim == 2 else y
    env = np.abs(mono)
    live = np.where(env > env.max() * 0.01)[0]
    sound_ms = (live[-1] - live[0]) / sr * 1000 if len(live) else 0.0
    span = (events[-1]['t'] * 1000 + events[-1]['ms']) if events else 0
    return {
        'events': len(events),
        'spanMs': int(span),
        'soundMs': int(sound_ms),
        'coverage': round(span / max(sound_ms, 1), 2),
        'vibratingMs': sum(e['ms'] for e in events),
    }


TICK_MIN_MS = 26.0    # чаще — щелчки переключателя склеиваются в один
TICK_MAX_MS = 90.0    # реже — распадаются на отдельные тычки
TICK_FLOOR = 0.06     # ниже этого уровня щелчков нет вообще
TICK_CURVE = 0.6      # уровень -> частота, с поджатием в сторону плотного
TRAIN_MAX_TICKS = 600


def switch_ticks(env, step_ms=FRAME_MS, intensity=1.0, max_ms=6000):
    """
    Расписание переключений <input type="checkbox" switch> — вибрация для iOS.

    В Safari на iOS navigator.vibrate отсутствует во всех версиях, а все
    браузеры на iPhone работают на WebKit. Единственный доступный вебу
    системный хаптик — тик переключателя, и он даёт один щелчок на одно
    переключение. Длительной вибрации как примитива там нет: её собирают,
    дёргая переключатель туда-сюда.

    Частота щелчков идёт за огибающей НЕПРЕРЫВНО, а не по импульсам дорожки:
    между импульсами по 200–300 мс пустоты, и по ним «длинной вибрации» не
    выходит. Ниже 26 мс щелчки склеиваются в один, выше 90 мс распадаются на
    отдельные тычки — между этими границами и живёт непрерывность.
    """
    out = []
    total = min(len(env) * step_ms, max_ms)
    t = 0.0
    while t < total and len(out) < TRAIN_MAX_TICKS:
        raw = env[int(t // step_ms)] / 100.0
        if raw < TICK_FLOOR:
            t += step_ms
            continue
        level = min(1.0, max(0.0, raw * intensity)) ** TICK_CURVE
        out.append(int(round(t)))
        t += TICK_MAX_MS - (TICK_MAX_MS - TICK_MIN_MS) * level
    return out


SEG_FLOOR = 0.06      # тише этого — пауза, а не вибрация
SEG_CURVE = 0.4       # уровень -> сила: тихое подтягивается вверх
SEG_QUANT = 0.2       # шаг квантования силы: соседние кадры сливаются в отрезок
SEG_SMOOTH = 3        # кадров скользящего максимума: убирает дрожь огибающей
SEG_MAX_MS = 1000     # предел одного импульса в web-haptics


def segments(env, step_ms=FRAME_MS, max_ms=6000):
    """
    Огибающая -> паттерн web-haptics: [{delay, duration, intensity}, ...].

    В этом формате duration — не короткий тычок, а отрезок, внутри которого
    вибрация ДЕРЖИТСЯ: движок щёлкает переключателем каждые
    16 + (1 - intensity) * 184 мс, пока отрезок не кончится. Поэтому сцена
    описывается сплошными отрезками с силой, а не россыпью импульсов —
    именно из-за этого у web-haptics вибрация ощущается непрерывной.

    Три вещи, без которых отрезки получаются бесполезными:

    * скользящий максимум по трём кадрам — сырая огибающая дрожит, и без
      сглаживания каждый кадр уходил бы в свой отрезок по 32 мс;
    * степень 0.4 на уровне — сила 0.2 даёт щелчок раз в 163 мс, то есть
      отдельные тычки; звук, который слышно, должен и ощущаться, поэтому
      тихое подтягивается вверх, а форма сохраняется;
    * квантование силы шагом 0.2 — иначе соседние кадры не сливаются.
    """
    env = [max(env[max(0, i - SEG_SMOOTH + 1):i + 1]) for i in range(len(env))]
    out = []
    pending_delay = 0.0
    i = 0
    n = len(env)
    while i < n and i * step_ms < max_ms:
        if env[i] / 100.0 < SEG_FLOOR:
            pending_delay += step_ms
            i += 1
            continue
        power = lambda v: (v / 100.0) ** SEG_CURVE
        q = round(power(env[i]) / SEG_QUANT)
        acc = []
        j = i
        while (j < n and env[j] / 100.0 >= SEG_FLOOR
               and round(power(env[j]) / SEG_QUANT) == q
               and (j - i) * step_ms < SEG_MAX_MS):
            acc.append(power(env[j]))
            j += 1
        item = {'duration': int((j - i) * step_ms),
                'intensity': round(min(1.0, max(0.2, sum(acc) / len(acc))), 2)}
        if pending_delay > 0:
            item['delay'] = int(pending_delay)
        out.append(item)
        pending_delay = 0.0
        i = j
    if not out:
        out = [{'duration': 25, 'intensity': 0.7}]
    return out


def click_times(vibrations, default_intensity=0.5):
    """
    Моменты щелчков переключателя: 16 + (1 - сила) * 184 мс.
    Отсчёт от последнего щелчка сквозной, а не с начала каждого отрезка —
    так же, как в самом движке.
    """
    out = []
    t = 0.0
    last = None
    for v in vibrations:
        t += v.get('delay', 0)
        intensity = min(1.0, max(0.0, v.get('intensity', default_intensity)))
        gap = 16.0 + (1.0 - intensity) * 184.0
        u = t
        while u < t + v['duration']:
            if last is None or u - last >= gap:
                out.append(int(round(u)))
                last = u
            u += 8.0
        t += v['duration']
    return out


PWM_FRAME_MS = 20        # окно широтно-импульсной модуляции
VIBRATE_MAX_ENTRIES = 10  # «Let max length have the value 10»


def _pwm(duration, intensity):
    """
    Импульс -> череда «включено/выключено» окнами по 20 мс.

    У Vibration API нет амплитуды. Доля включённого времени внутри окна равна
    силе — мотор успевает отработать, и слабое ощущается слабым, а не просто
    коротким. Приём взят из web-haptics.
    """
    if intensity >= 1:
        return [duration]
    if intensity <= 0:
        return []
    on = max(1, round(PWM_FRAME_MS * intensity))
    off = PWM_FRAME_MS - on
    out = []
    rest = duration
    while rest >= PWM_FRAME_MS:
        out += [on, off]
        rest -= PWM_FRAME_MS
    if rest > 0:
        tail = max(1, round(rest * intensity))
        out.append(tail)
        if rest - tail > 0:
            out.append(rest - tail)
    return out


def to_flat_web(vibrations, default_intensity=0.5):
    """Паттерн web-haptics -> плоский массив для navigator.vibrate."""
    out = []
    for v in vibrations:
        intensity = min(1.0, max(0.0, v.get('intensity', default_intensity)))
        delay = v.get('delay', 0)
        if delay > 0:
            if out and len(out) % 2 == 0:
                out[-1] += delay
            else:
                if not out:
                    out.append(0)
                out.append(delay)
        frames = _pwm(v['duration'], intensity)
        if not frames:
            if out and len(out) % 2 == 0:
                out[-1] += v['duration']
            elif v['duration'] > 0:
                out += [0, v['duration']]
            continue
        out += frames
    return [int(round(x)) for x in out]


def to_chunks_web(flat, max_len=VIBRATE_MAX_ENTRIES):
    """Нарезка на куски по десять записей; кусок заканчивается вибрацией."""
    out = []
    at = 0
    i = 0
    if len(flat) >= 2 and flat[0] == 0:
        at += flat[1]
        i = 2
    while i < len(flat):
        piece = flat[i:i + max_len]
        if len(piece) % 2 == 0:
            piece = piece[:-1]
        if not piece:
            break
        out.append({'at': int(at), 'pattern': [int(v) for v in piece]})
        at += sum(piece)
        i += len(piece)
        if i < len(flat):
            at += flat[i]
            i += 1
    return out
