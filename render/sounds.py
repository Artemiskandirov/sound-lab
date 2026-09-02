"""
CueLab v13 — определения звуков.

Главное правило, выведенное измерением: UI-звук обязан жить в полосе
400 Гц – 6 кГц. Динамик телефона и ноутбука почти ничего не отдаёт ниже
400 Гц, поэтому звук, у которого 76% энергии в суббасе, доходит до
пользователя огрызком. В v12 этим грешили почти все события — отсюда
ощущение глухого барабана.

Каждый звук собран послойно: транзиент контакта, тело инструмента, хвост.
"""
import numpy as np
from scipy import signal
from dsp import *

N = lambda m: 440.0 * 2 ** ((m - 69) / 12.0)


# --------------------------------------------------------------- инструменты

def bar(f0, dur, ratios, t60, mallet=3.0, velocity=1.0, pos=0.28,
        beta=1.2, gamma=0.62, seed=1, tube=None, tube_q=14.0, tube_mix=0.0,
        roughness=0.35):
    """Настроенный стержень: маримба, ксилофон, глокеншпиль, вудблок, диск."""
    force = hertz_contact(velocity, mallet, roughness=roughness)
    freqs = np.asarray(ratios, dtype=float) * f0
    t60s = damping_curve(freqs, f0, t60, beta, gamma)
    gains = strike_gains(ratios, pos, 'bar')
    y = pad_to(modal(force, freqs, t60s, gains, seed=seed, detune=0.4), dur)
    if tube_mix > 0:
        y = y * (1 - tube_mix * 0.5) + resonator(y, tube or f0, tube_q) * tube_mix
    return y


# Твёрдость киянки задана в тех же единицах, что и калибровка контакта:
# 1.0 -> 3.5 мс (мягкая шерсть), 3.5 -> 1 мс (резина), 7 -> 0.5 мс (металл).
MARIMBA   = dict(ratios=[1, 3.99, 9.2, 15.4, 22.8], t60=0.52, beta=1.5, gamma=0.72, mallet=3.2)
GLOCK     = dict(ratios=[1, 2.756, 5.404, 8.933, 13.34], t60=1.7, beta=0.9, gamma=0.5, mallet=8.0)
WOODBLOCK = dict(ratios=[1, 2.41, 3.72, 5.06, 6.8], t60=0.135, beta=1.05, gamma=0.68, mallet=3.2)
DISC      = dict(ratios=[1, 1.73, 2.33, 3.91, 4.11, 5.95, 7.24], t60=0.8, beta=0.85, gamma=0.45, mallet=6.0)
MEMBRANE  = dict(ratios=[1, 1.593, 2.135, 2.295, 2.653], t60=0.28, beta=1.35, gamma=0.72, mallet=2.2)


def tick_noise(dur_ms, freq, q, gain, seed, decay=3.0):
    n = max(8, int(dur_ms * SR / 1000))
    x = noise_burst(dur_ms / 1000 * 1.8, seed)[:n] * np.exp(-np.linspace(0, decay, n))
    x = resonator(x, freq, q)
    return x / (np.abs(x).max() + 1e-12) * gain


def finish(y, hp=240, mud=(330, -3.0), presence=(3000, -2.5), air=None,
           drive=1.3, room=0.12, size=0.20, damp=0.65, peak=0.85, tail_ms=10,
           seed=7):
    """
    Общая доводка. Убирает суббас, который динамик всё равно не отдаст,
    снимает «мутную» полосу и резкость, добавляет короткую комнату.
    """
    y = highpass(y, hp, 2)
    if mud:
        y = biquad(y, 'peak', mud[0], q=1.0, gain_db=mud[1])
    if presence:
        y = biquad(y, 'peak', presence[0], q=1.2, gain_db=presence[1])
    if air:
        y = biquad(y, 'highshelf', air[0], q=0.7, gain_db=air[1])
    if drive and drive != 1.0:
        y = saturate(y * drive, 1.4)
    y = space(y, room, size=size, damp=damp, seed=seed)
    return fade_out(normalize(y, peak), tail_ms)


# ------------------------------------------------------------------ ЗВУКИ

def tap(velocity=1.0, seed=11, tone=1.0, level=0.85):
    """
    Основное нажатие: подушечка пальца по маленькому бруску твёрдого дерева.
    Тело подняли до 1.2 кГц — там, где динамик телефона реально играет.
    """
    dur = 0.22
    body = bar(1240 * tone, dur, velocity=velocity, pos=0.31, seed=seed, **WOODBLOCK)
    warm = bar(455 * tone, dur, ratios=[1, 2.7, 4.4], t60=0.11, beta=1.2, gamma=0.75,
               mallet=2.6, velocity=velocity * 0.85, seed=seed + 1)
    click = pad_to(tick_noise(2.5, 3600 * tone, 2.2, 0.6, seed + 2), dur)
    y = body * 1.0 + warm * 0.55 + click * 0.09
    return finish(y, hp=250, mud=(360, -2.5), presence=(3100, -3.0),
                  air=(9000, +1.5), room=0.09, size=0.15, damp=0.72, peak=level, tail_ms=8, seed=101)


def tap_soft(seed=21):
    y = tap(velocity=0.5, seed=seed, tone=1.15, level=0.55)
    return normalize(lowpass(y, 6500, 2), 0.52)


def tap_heavy(seed=31):
    """Тяжёлое нажатие: больше тела, но низ по-прежнему под контролем."""
    dur = 0.28
    body = bar(690, dur, velocity=1.9, pos=0.27, seed=seed, **WOODBLOCK)
    drum = bar(305, dur, ratios=MEMBRANE['ratios'], t60=0.20, beta=1.4, gamma=0.75,
               mallet=2.2, velocity=1.8, seed=seed + 1)
    click = pad_to(tick_noise(3.0, 2500, 2.0, 0.65, seed + 2), dur)
    y = body * 1.0 + drum * 0.60 + click * 0.10
    return finish(y, hp=225, mud=(320, -3.5), presence=(3200, -3.5),
                  air=(9000, +1.0), drive=1.45, room=0.11, size=0.19, peak=0.92, tail_ms=10, seed=113)


def key_press(seed=41):
    """Механическая клавиша: щелчок нажатия + приземление."""
    dur = 0.16
    down = pad_to(tick_noise(2.0, 3300 + (seed % 5) * 150, 2.4, 1.0, seed), dur)
    shell = bar(1420 + (seed % 7) * 30, dur, ratios=[1, 2.2, 3.4, 4.9], t60=0.085,
                beta=1.05, gamma=0.66, mallet=2.9, velocity=1.0, seed=seed + 1)
    bottom = at(bar(520, 0.09, ratios=[1, 2.6, 4.2], t60=0.055, beta=1.3, gamma=0.8,
                    mallet=2.8, velocity=1.1, seed=seed + 2), 0.008, dur)
    y = down * 0.06 + shell * 1.0 + bottom * 0.60
    return finish(y, hp=300, mud=(480, -2.0), presence=(4300, -3.0),
                  drive=1.2, room=0.06, size=0.11, damp=0.8, peak=0.62, tail_ms=6, seed=127)


def toggle(on=True, seed=51):
    """Детент переключателя: короткое трение, затем защёлка."""
    dur = 0.26
    n = int(0.028 * SR)
    fric = noise_burst(0.028, seed)[:n] * np.exp(-np.linspace(0, 2.0, n))
    fric = sweep_filter(fric, 1400 if on else 2600, 2600 if on else 1400, q=1.5)
    fric = pad_to(fric / (np.abs(fric).max() + 1e-9) * 0.30, dur)
    t_snap = 0.032
    snap = at(bar(1620 if on else 1180, 0.14, ratios=[1, 2.36, 3.9, 5.4], t60=0.095,
                  beta=1.15, gamma=0.70, mallet=3.6, velocity=1.4, seed=seed + 1), t_snap, dur)
    body = at(bar(520 if on else 415, 0.14, ratios=[1, 2.7, 4.3], t60=0.085,
                  beta=1.25, gamma=0.78, mallet=2.8, velocity=1.1, seed=seed + 2), t_snap, dur)
    tick = at(pad_to(tick_noise(2.5, 3100, 2.4, 0.5, seed + 3), dur - t_snap), t_snap, dur)
    y = fric * 0.07 + snap * 1.0 + body * 0.58 + tick * 0.04
    return finish(y, hp=290, mud=(430, -2.0), presence=(3400, -3.0),
                  air=(9500, +1.0), room=0.09, size=0.15, damp=0.72, peak=0.74, tail_ms=8, seed=131)


def coin(seed=61, level=0.80):
    """
    Монета: тонкий металлический диск. Мерцание берётся из физики — две почти
    совпадающие моды дают биения около 9 Гц.
    """
    dur = 0.70
    f0 = 1680
    ratios = np.array(DISC['ratios'], dtype=float)
    freqs = ratios * f0
    freqs[4] *= 1.004
    top = np.array([1.0, 1.0, 0.95, 0.75, 0.7, 0.45, 0.28])   # гасим самые верхние моды
    t60s = damping_curve(freqs, f0, 0.62, 1.0, 0.5)
    gains = strike_gains(ratios, 0.42, 'bar') * top
    y = pad_to(modal(hertz_contact(2.6, 16.0), freqs, t60s, gains, seed=seed, detune=0.6), dur)
    tick = pad_to(tick_noise(2.0, 6800, 2.0, 0.75, seed + 1), dur)
    table = pad_to(bar(720, 0.09, ratios=[1, 2.4, 3.9], t60=0.035, beta=2.4, gamma=0.95,
                       mallet=4.5, velocity=1.0, seed=seed + 2), dur)
    y = y * 1.0 + tick * 0.08 + table * 0.42
    y = lowpass(y, 13000, 2)
    return finish(y, hp=400, mud=None, presence=(4200, -2.0),
                  air=(12000, -2.0), room=0.17, size=0.24, damp=0.5, peak=level, tail_ms=12, seed=149)


def correct(seed=71):
    """Правильный ответ: две ноты вверх на маримбе с резонаторной трубой."""
    dur = 0.62
    n1, n2 = N(84), N(91)
    a = bar(n1, dur, velocity=1.0, pos=0.30, seed=seed, tube=n1, tube_mix=0.55, **MARIMBA)
    b = at(bar(n2, 0.50, velocity=1.15, pos=0.30, seed=seed + 1, tube=n2,
               tube_mix=0.55, **MARIMBA), 0.105, dur)
    warm = bar(N(72), dur, ratios=[1, 4.0], t60=0.30, beta=2.6, gamma=0.9,
               mallet=1.6, velocity=0.6, seed=seed + 2)
    shim = at(bar(N(96), 0.45, velocity=0.5, pos=0.30, seed=seed + 3, **GLOCK), 0.225, dur)
    y = a * 1.0 + b * 1.05 + warm * 0.16 + shim * 0.18
    return finish(y, hp=300, mud=(520, -1.5), presence=(2800, -2.0),
                  air=(8000, +1.5), room=0.18, size=0.28, damp=0.5, peak=0.82, tail_ms=14, seed=151)


def wrong_soft(seed=81):
    """
    Мягкая ошибка: две приглушённые ноты вниз. Раньше они лежали в октаве,
    которую телефон не воспроизводит, — теперь на октаву выше и слышны.
    """
    dur = 0.55
    n1, n2 = N(74), N(70)                      # D5 -> A#4, нисходящая м3
    a = bar(n1, dur, ratios=[1, 3.99, 9.2], t60=0.26, beta=2.0, gamma=0.85,
            mallet=2.4, velocity=0.85, pos=0.5, seed=seed, tube=n1, tube_mix=0.45)
    b = at(bar(n2, 0.42, ratios=[1, 3.99, 9.2], t60=0.30, beta=2.0, gamma=0.85,
               mallet=2.2, velocity=0.8, pos=0.5, seed=seed + 1,
               tube=n2, tube_mix=0.45), 0.155, dur)
    thud = bar(N(62), dur, ratios=[1, 2.4, 4.1], t60=0.11, beta=2.4, gamma=0.95,
               mallet=2.6, velocity=0.7, seed=seed + 2)
    y = a * 1.0 + b * 0.95 + thud * 0.14
    y = lowpass(y, 7500, 2)
    return finish(y, hp=260, mud=(400, -2.0), presence=(2600, -1.5),
                  drive=1.15, room=0.13, size=0.22, damp=0.7, peak=0.68, tail_ms=14, seed=163)


def open_sheet(seed=91):
    """
    Открытие слоя. Раньше это было широкополосное шумовое облако — ровно тот
    «звук волн», который бесил. Теперь ведущий голос тональный, а материал
    только подмешан коротким призвуком.
    """
    dur = 0.34
    n = int(0.055 * SR)
    cloth = noise_burst(0.09, seed)[:n]
    cloth *= np.concatenate([np.linspace(0, 1, int(n * 0.3)) ** 2,
                             np.exp(-np.linspace(0, 3.4, n - int(n * 0.3)))])
    cloth = bandpass(cloth, 1100, 4200, 2)
    cloth = pad_to(cloth / (np.abs(cloth).max() + 1e-9), dur)
    lift = pad_to(bar(N(81), 0.30, velocity=0.75, pos=0.30, seed=seed + 1,
                      tube=N(81), tube_mix=0.5, **MARIMBA), dur)
    settle = at(bar(N(88), 0.26, velocity=0.65, pos=0.30, seed=seed + 2,
                    tube=N(88), tube_mix=0.5, **MARIMBA), 0.105, dur)
    y = cloth * 0.045 + lift * 1.0 + settle * 0.82
    return finish(y, hp=300, mud=(520, -1.5), presence=(3000, -2.5),
                  air=(9000, +1.0), room=0.16, size=0.24, damp=0.6, peak=0.66, tail_ms=12, seed=173)


def roar(seed=101):
    """
    Рёв динозавра: модель «источник-фильтр». Связки дают импульсы с джиттером,
    нелинейность превращает их в рык, движущиеся форманты — раскрывающаяся
    пасть. Низ оставлен для хороших колонок, но характер несут форманты и
    рычащий призвук в 700–4000 Гц, иначе на телефоне остаётся невнятное бурчание.
    """
    dur = 1.6
    n = int(dur * SR)
    t = np.arange(n) / SR
    r = rng(seed)

    f = 86 * np.exp(-((t - 0.40) ** 2) / 0.50) + 52
    jitter = np.cumsum(r.standard_normal(n)) * 0.00040
    jitter -= jitter.mean()
    phase = np.cumsum(2 * np.pi * (f * (1 + jitter)) / SR)
    glottal = -np.sign(np.sin(phase)) * (0.5 + 0.5 * np.cos(phase * 0.5)) ** 2
    glottal += 0.4 * signal.sawtooth(phase, 0.3)

    growl = 0.5 + 0.5 * np.sin(2 * np.pi * 31 * t + 1.4 * np.sin(2 * np.pi * 3.7 * t))
    src = saturate(glottal * growl * 2.8, 3.0)

    body = np.zeros(n)
    for f_s, f_e, q, g in [(560, 860, 4.5, 1.0), (1250, 1650, 5.5, 0.85),
                           (2650, 2150, 7.0, 0.50), (3900, 3200, 8.0, 0.22)]:
        body += sweep_filter(src, f_s, f_e, q=q)[:n] * g

    # хрип: верхняя гармоника рыка, именно она читается на маленьком динамике
    rasp = highpass(saturate(src * 4.0, 4.0), 1800, 2)[:n]
    rasp *= (0.35 + 0.35 * growl)

    chest = np.sin(2 * np.pi * np.cumsum(f * 0.5) / SR) * np.exp(-((t - 0.48) ** 2) / 0.6)
    breath = bandpass(noise_burst(dur, seed + 3), 900, 5200, 2)[:n]
    breath *= np.clip((t - 0.5) / 0.3, 0, 1) * np.exp(-np.clip(t - 0.85, 0, None) * 2.6) * 0.55

    amp = np.clip(t / 0.11, 0, 1) * np.exp(-np.clip(t - 0.88, 0, None) ** 1.4 * 3.4)
    y = (body * 1.0 + rasp * 0.55 + chest * 0.30 + breath * 0.5) * amp
    y = compress(y, -16, 3.0, 4, 90)
    return finish(y, hp=150, mud=(300, -4.0), presence=(3400, -2.0),
                  air=(8000, +1.0), drive=1.0, room=0.20, size=0.38, damp=0.45,
                  peak=0.94, tail_ms=40, seed=181)


def slide_whistle(up=True, seed=111):
    """Свистулька: воздушный столб с движущимся резонансом и дыханием."""
    dur = 0.38
    n = int(0.28 * SR)
    t = np.arange(n) / SR
    p = t / t[-1]
    f = (950 * (3000 / 950) ** p) if up else (3000 * (820 / 3000) ** p)
    ph = np.cumsum(2 * np.pi * f / SR)
    tone = np.sin(ph) + 0.14 * np.sin(2 * ph) + 0.05 * np.sin(3 * ph)
    br = sweep_filter(noise_burst(0.28, seed)[:n], f[0] * 1.8, f[-1] * 1.8, q=3.5)[:n]
    env = np.clip(t / 0.018, 0, 1) * np.clip((t[-1] - t) / 0.045, 0, 1)
    piston = sweep_filter(noise_burst(0.28, seed + 5)[:n], f[0] * 0.5, f[-1] * 0.5, q=6.0)[:n]
    y = pad_to((tone * 0.78 + br * 0.26 + piston * 0.09) * env, dur)
    return finish(y, hp=420, mud=None, presence=(3800, -3.0),
                  drive=1.1, room=0.14, size=0.22, damp=0.6, peak=0.74, tail_ms=12, seed=191)


def reward(seed=121):
    """Награда: монета, затем короткое разрешение на глокеншпиле."""
    dur = 1.15
    y = pad_to(coin(seed, level=0.55) * 0.72, dur)
    for t0, m, g in [(0.15, 88, 0.75), (0.285, 92, 0.72), (0.42, 95, 0.85)]:
        y = y + at(bar(N(m), 0.8, velocity=g * 1.4, pos=0.30, seed=seed + m, **GLOCK), t0, dur) * g * 1.05
    warm = at(bar(N(76), 0.9, ratios=[1, 4.0], t60=0.34, beta=2.6, gamma=0.9,
                  mallet=1.8, velocity=0.7, seed=seed + 9,
                  tube=N(76), tube_mix=0.45), 0.42, dur)
    y = y + warm * 0.22
    return finish(y, hp=380, mud=(620, -2.0), presence=(3500, -2.5),
                  air=(10000, +1.0), room=0.20, size=0.32, damp=0.5, peak=0.88, tail_ms=20, seed=197)


def lesson_complete(seed=131):
    """Длинная сцена: восходящий мотив, каденция IV–V–I, короткий хвост."""
    dur = 2.7
    y = np.zeros(int(dur * SR))
    for t0, m in [(0.00, 72), (0.135, 76), (0.27, 79), (0.405, 84)]:
        y += at(bar(N(m), 1.0, velocity=1.0, pos=0.30, seed=seed + m,
                    tube=N(m), tube_mix=0.55, **MARIMBA), t0, dur) * 0.85
    for t0, notes, g in [(0.72, [65, 69, 72], 0.60), (1.02, [67, 71, 74], 0.66),
                         (1.40, [60, 64, 67, 72], 0.95)]:
        for i, m in enumerate(notes):
            y += at(bar(N(m + 12), 1.5, velocity=g, pos=0.30, seed=seed + m + i,
                        tube=N(m + 12), tube_mix=0.5, **MARIMBA), t0 + i * 0.012, dur) * g * 0.6
        y += at(bar(N(notes[0]), 1.2, ratios=[1, 4.0], t60=0.38, beta=2.6,
                    gamma=0.9, mallet=1.8, velocity=g * 0.7, seed=seed + 50), t0, dur) * g * 0.18
    for i, (t0, m) in enumerate([(1.55, 96), (1.72, 99), (1.90, 103)]):
        y += at(bar(N(m), 1.1, velocity=0.55, pos=0.30, seed=seed + m, **GLOCK), t0, dur) * (0.32 - i * 0.07)
    y = compress(y, -20, 2.4, 6, 110)
    return finish(y, hp=290, mud=(500, -2.0), presence=(2900, -2.0),
                  air=(8500, +1.5), room=0.22, size=0.36, damp=0.5, peak=0.90, tail_ms=40, seed=211)





# ============================================================================
#  v13.1 — прокрутка, победы, награды, прогресс, навигация, система
# ============================================================================

GLASS = dict(ratios=[1, 2.02, 3.05, 4.10, 5.2], t60=1.9, beta=0.8, gamma=0.45, mallet=6.0)
TUBULAR = dict(ratios=[1, 2.76, 5.40, 8.93, 13.34], t60=3.0, beta=0.7, gamma=0.42, mallet=5.0)


def finish_stereo(y, width=0.75, size=0.34, damp=0.5, seed=7, hp=280,
                  mud=(500, -2.0), presence=(2900, -2.0), air=(8500, 1.5),
                  peak=0.9, tail_ms=40):
    """Доводка для длинных сцен: та же коррекция, но с декоррелированным хвостом."""
    y = highpass(y, hp, 2)
    if mud:
        y = biquad(y, 'peak', mud[0], q=1.0, gain_db=mud[1])
    if presence:
        y = biquad(y, 'peak', presence[0], q=1.2, gain_db=presence[1])
    if air:
        y = biquad(y, 'highshelf', air[0], q=0.7, gain_db=air[1])
    st = stereo_pair(y, width=width, size=size, damp=damp, seed=seed, amount=0.75)
    st = st / (np.abs(st).max() + 1e-12) * peak
    n = int(tail_ms * SR / 1000)
    if 2 < n < len(st):
        st[-n:] *= np.linspace(1, 0, n)[:, None] ** 2
    return st


def chord_at(y, dur, t0, notes, gain, preset=MARIMBA, octave=12, spread=0.014,
             seed=1, tube=True, decay=1.0):
    """Аккорд с лёгким арпеджио — живой удар не бывает идеально одновременным."""
    for i, m in enumerate(notes):
        f = N(m + octave)
        y = y + at(bar(f, 1.6, velocity=gain, pos=0.30, seed=seed + m + i,
                       tube=f if tube else None, tube_mix=0.5 if tube else 0.0,
                       **preset), t0 + i * spread, dur) * gain * 0.6 * decay
    return y


# ------------------------------------------------------------------ ПРОКРУТКА

def scroll_tick(seed=301):
    """
    Тик прокрутки. Самый опасный звук в наборе: он повторяется десятками раз
    подряд, поэтому обязан быть очень коротким, тихим и узким по спектру.
    Любой хвост или низ здесь накапливается и утомляет за две секунды.
    """
    dur = 0.055
    body = bar(2650, dur, ratios=[1, 2.41, 3.72], t60=0.045, beta=0.95, gamma=0.65,
               mallet=4.0, velocity=0.55, pos=0.33, seed=seed)
    click = pad_to(tick_noise(1.4, 4200, 3.0, 0.5, seed + 1, decay=4.0), dur)
    y = body * 1.0 + click * 0.025
    return finish(y, hp=900, mud=None, presence=(5200, -2.5), air=(12000, -3.0),
                  drive=1.0, room=0.03, size=0.08, damp=0.85, peak=0.30, tail_ms=4, seed=301)


def scroll_detent(seed=311):
    """Более весомая засечка: снап колеса выбора, шаг карусели."""
    dur = 0.10
    body = bar(1760, dur, ratios=[1, 2.41, 3.72, 5.06], t60=0.032, beta=1.4, gamma=0.75,
               mallet=4.5, velocity=0.85, pos=0.31, seed=seed)
    low = bar(620, dur, ratios=[1, 2.7], t60=0.026, beta=1.6, gamma=0.85,
              mallet=3.0, velocity=0.7, seed=seed + 1)
    y = body * 1.0 + low * 0.35
    return finish(y, hp=520, mud=None, presence=(4400, -2.5), air=(11000, -1.5),
                  drive=1.05, room=0.05, size=0.11, damp=0.8, peak=0.46, tail_ms=6, seed=311)


def scroll_snap(seed=321):
    """Элемент встал на место: щелчок плюс маленькое тело."""
    dur = 0.16
    snap = bar(1340, dur, ratios=[1, 2.41, 3.72, 5.06], t60=0.055, beta=1.2, gamma=0.7,
               mallet=4.0, velocity=1.0, pos=0.30, seed=seed)
    body = bar(536, dur, ratios=[1, 2.7, 4.4], t60=0.06, beta=1.3, gamma=0.8,
               mallet=2.8, velocity=0.85, seed=seed + 1)
    y = snap * 1.0 + body * 0.45
    return finish(y, hp=380, mud=(560, -1.5), presence=(3800, -2.5), air=(10000, 1.0),
                  room=0.08, size=0.14, damp=0.75, peak=0.60, tail_ms=8, seed=321)


def scroll_edge(seed=331):
    """
    Край списка: резинка. Волновод с сильным демпфированием и падением строя —
    именно падение высоты читается как «дальше не пускает».
    """
    dur = 0.34
    band = waveguide(540, 0.30, damping=0.62, brightness=0.30, seed=seed, pluck_pos=0.4)
    t = np.arange(len(band)) / SR
    band = band * np.exp(-t / 0.075)
    band = pad_to(band, dur)
    thud = bar(390, dur, ratios=[1, 2.4, 4.1], t60=0.070, beta=1.8, gamma=0.9,
               mallet=2.2, velocity=0.9, seed=seed + 1)
    y = band * 0.75 + thud * 0.8
    y = lowpass(y, 4200, 2)
    return finish(y, hp=250, mud=(360, -2.0), presence=(2400, -2.0),
                  drive=1.15, room=0.10, size=0.18, damp=0.72, peak=0.62, tail_ms=12, seed=331)


def pull_refresh(seed=341):
    """Натяжение при потягивании: строй ползёт вверх, тембр раскрывается."""
    dur = 0.55
    n = int(0.44 * SR)
    t = np.arange(n) / SR
    p = t / t[-1]
    f = 470 * (2.15 ** p)
    ph = np.cumsum(2 * np.pi * f / SR)
    tone = np.sin(ph) + 0.25 * np.sin(2 * ph) + 0.09 * np.sin(3 * ph)
    env = np.clip(t / 0.05, 0, 1) * np.clip((t[-1] - t) / 0.09, 0, 1) * (0.4 + 0.6 * p)
    y = pad_to(sweep_filter(tone * env, 700, 2600, q=1.1, kind='low')[:n], dur)
    return finish(y, hp=280, mud=(420, -2.0), presence=(3000, -2.0),
                  drive=1.1, room=0.10, size=0.18, damp=0.7, peak=0.58, tail_ms=14, seed=341)


def refresh_done(seed=351):
    """Обновление завершено: короткая восходящая пара."""
    dur = 0.45
    a = bar(N(79), dur, velocity=0.9, pos=0.30, seed=seed, tube=N(79), tube_mix=0.5, **MARIMBA)
    b = at(bar(N(86), 0.38, velocity=0.95, pos=0.30, seed=seed + 1,
               tube=N(86), tube_mix=0.5, **MARIMBA), 0.09, dur)
    y = a * 0.9 + b * 1.0
    return finish(y, hp=320, mud=(560, -1.5), presence=(3000, -2.0), air=(8500, 1.5),
                  room=0.16, size=0.24, damp=0.55, peak=0.72, tail_ms=14, seed=351)


# -------------------------------------------------------------------- ПОБЕДЫ

def victory(seed=401):
    """
    Победа. Восходящий мотив G-C-E-G и разрешение в до-мажор.
    Короткая: победа должна успеть закончиться до того, как надоест.
    """
    dur = 1.5
    y = np.zeros(int(dur * SR))
    for i, (t0, m) in enumerate([(0.0, 67), (0.10, 72), (0.20, 76), (0.30, 79)]):
        f = N(m + 12)
        y += at(bar(f, 1.0, velocity=1.0, pos=0.30, seed=seed + m,
                    tube=f, tube_mix=0.55, **MARIMBA), t0, dur) * (0.85 + i * 0.03)
    y = chord_at(y, dur, 0.44, [60, 64, 67, 72], 0.95, seed=seed)
    for i, (t0, m) in enumerate([(0.60, 91), (0.74, 96)]):
        y += at(bar(N(m), 0.9, velocity=0.6, pos=0.30, seed=seed + m, **GLOCK), t0, dur) * (0.30 - i * 0.07)
    y += at(bar(N(60), 1.5, velocity=0.5, pos=0.30, seed=seed + 7, **TUBULAR), 0.46, dur) * 0.22
    y = compress(y, -20, 2.4, 6, 110)
    return finish_stereo(y, width=0.7, size=0.32, seed=401, peak=0.90)


def victory_big(seed=411):
    """Большая победа: мотив, каденция IV–V–I с медью, колокол и каскад."""
    dur = 2.6
    y = np.zeros(int(dur * SR))
    for t0, m in [(0.0, 60), (0.11, 64), (0.22, 67), (0.33, 72), (0.44, 76)]:
        f = N(m + 12)
        y += at(bar(f, 1.1, velocity=1.0, pos=0.30, seed=seed + m,
                    tube=f, tube_mix=0.55, **MARIMBA), t0, dur) * 0.8
    y = chord_at(y, dur, 0.68, [65, 69, 72], 0.62, seed=seed)          # IV
    y = chord_at(y, dur, 0.98, [67, 71, 74], 0.68, seed=seed + 3)      # V
    y = chord_at(y, dur, 1.34, [60, 64, 67, 72, 76], 1.0, seed=seed + 6)  # I
    for i, m in enumerate([60, 64, 67]):
        y += at(pad_to(brass_tone(N(m + 12), 1.1, gain=0.32, bright=1.0, seed=seed + m), dur - 1.32),
                1.32 + i * 0.02, dur) * 0.55
    y += at(bar(N(60), 2.2, velocity=0.7, pos=0.30, seed=seed + 11, **TUBULAR), 1.36, dur) * 0.30
    for i, (t0, m) in enumerate([(1.62, 91), (1.78, 96), (1.94, 100)]):
        y += at(bar(N(m), 1.0, velocity=0.6, pos=0.30, seed=seed + m, **GLOCK), t0, dur) * (0.32 - i * 0.07)
    y = compress(y, -21, 2.6, 6, 120)
    return finish_stereo(y, width=0.85, size=0.40, seed=411, peak=0.93)


def perfect(seed=421):
    """Идеальный результат: то же разрешение, но выше и с большим блеском."""
    dur = 2.1
    y = np.zeros(int(dur * SR))
    for t0, m in [(0.0, 72), (0.10, 76), (0.20, 79), (0.30, 84), (0.40, 88)]:
        f = N(m + 6)
        y += at(bar(f, 0.9, velocity=1.0, pos=0.30, seed=seed + m,
                    tube=f, tube_mix=0.5, **MARIMBA), t0, dur) * 0.78
    y = chord_at(y, dur, 0.58, [67, 71, 74, 79], 0.62, seed=seed)
    y = chord_at(y, dur, 0.98, [60, 64, 67, 71, 74], 0.98, seed=seed + 5)   # Cmaj9
    for i, (t0, m) in enumerate([(1.20, 96), (1.34, 100), (1.48, 103), (1.62, 108)]):
        y += at(bar(N(m), 1.1, velocity=0.62, pos=0.30, seed=seed + m, **GLOCK), t0, dur) * (0.34 - i * 0.06)
    y += at(bar(N(72), 1.6, velocity=0.55, pos=0.30, seed=seed + 9, **GLASS), 1.02, dur) * 0.20
    y = compress(y, -21, 2.4, 6, 110)
    return finish_stereo(y, width=0.8, size=0.36, seed=421, peak=0.90,
                         presence=(3000, -1.5), air=(9000, 2.0))


def level_up(seed=431):
    """Новый уровень: подъём по ступеням, затем прибытие."""
    dur = 1.8
    y = np.zeros(int(dur * SR))
    for i, m in enumerate([60, 62, 64, 67, 69]):
        f = N(m + 12)
        y += at(bar(f, 0.8, velocity=0.85 + i * 0.04, pos=0.30, seed=seed + m,
                    tube=f, tube_mix=0.5, **MARIMBA), i * 0.085, dur) * 0.75
    y = chord_at(y, dur, 0.52, [67, 71, 74], 0.6, seed=seed)
    y = chord_at(y, dur, 0.86, [72, 76, 79, 84], 1.0, seed=seed + 4)
    y += at(bar(N(72), 1.6, velocity=0.65, pos=0.30, seed=seed + 8, **TUBULAR), 0.88, dur) * 0.26
    for i, (t0, m) in enumerate([(1.10, 96), (1.26, 103)]):
        y += at(bar(N(m), 0.9, velocity=0.58, pos=0.30, seed=seed + m, **GLOCK), t0, dur) * (0.30 - i * 0.08)
    y = compress(y, -20, 2.4, 6, 110)
    return finish_stereo(y, width=0.72, size=0.34, seed=431, peak=0.90)


def unit_complete(seed=441):
    """Раздел завершён: узлы пути собираются в веху."""
    dur = 2.3
    y = np.zeros(int(dur * SR))
    for i, m in enumerate([55, 60, 62, 67, 69, 72]):
        f = N(m + 12)
        y += at(bar(f, 0.8, velocity=0.8 + i * 0.03, pos=0.30, seed=seed + m,
                    tube=f, tube_mix=0.5, **MARIMBA), i * 0.135, dur) * 0.72
    y = chord_at(y, dur, 0.90, [65, 69, 72], 0.6, seed=seed)
    y = chord_at(y, dur, 1.18, [67, 71, 74], 0.66, seed=seed + 3)
    y = chord_at(y, dur, 1.52, [60, 64, 67, 72], 0.98, seed=seed + 6)
    y += at(bar(N(60), 1.9, velocity=0.62, pos=0.30, seed=seed + 9, **TUBULAR), 1.54, dur) * 0.26
    y += at(bar(N(96), 0.9, velocity=0.6, pos=0.30, seed=seed + 12, **GLOCK), 1.78, dur) * 0.26
    y = compress(y, -20, 2.4, 6, 110)
    return finish_stereo(y, width=0.75, size=0.36, seed=441, peak=0.90)


def streak(seed=451):
    """Серия: ускоряющиеся засечки, затем яркое подтверждение."""
    dur = 1.4
    y = np.zeros(int(dur * SR))
    times = [0.0, 0.16, 0.29, 0.39, 0.46, 0.51]
    for i, t0 in enumerate(times):
        y += at(bar(1500 + i * 130, 0.30, ratios=[1, 2.41, 3.72], t60=0.05,
                    beta=1.3, gamma=0.75, mallet=4.0, velocity=0.7 + i * 0.06,
                    seed=seed + i), t0, dur) * (0.5 + i * 0.06)
    y = chord_at(y, dur, 0.62, [64, 67, 72, 76], 0.95, seed=seed + 7)
    y += at(bar(N(91), 0.9, velocity=0.6, pos=0.30, seed=seed + 11, **GLOCK), 0.84, dur) * 0.28
    y = compress(y, -20, 2.4, 6, 100)
    return finish_stereo(y, width=0.65, size=0.30, seed=451, peak=0.88)


def fanfare(seed=461):
    """Короткая фанфара на меди."""
    dur = 1.2
    y = np.zeros(int(dur * SR))
    for t0, m, g in [(0.0, 67, 0.30), (0.13, 72, 0.32), (0.26, 76, 0.34)]:
        y += at(pad_to(brass_tone(N(m + 12), 0.42, gain=g, bright=1.1, attack=0.03, seed=seed + m), dur - t0), t0, dur)
    for i, m in enumerate([60, 64, 67, 72]):
        y += at(pad_to(brass_tone(N(m + 12), 0.85, gain=0.30, bright=1.0, attack=0.04, seed=seed + m + 40),
                       dur - 0.42), 0.42 + i * 0.014, dur) * 0.9
    y += at(bar(N(72), 1.0, velocity=0.6, pos=0.30, seed=seed + 20, **TUBULAR), 0.44, dur) * 0.22
    y = compress(y, -19, 2.8, 5, 100)
    return finish_stereo(y, width=0.7, size=0.32, seed=461, peak=0.90,
                         presence=(2600, -3.0))


# -------------------------------------------------------------------- НАГРАДЫ

def coin_multi(seed=471):
    """Несколько монет подряд, каждая выше предыдущей."""
    dur = 0.95
    y = np.zeros(int(dur * SR))
    for i, t0 in enumerate([0.0, 0.125, 0.26]):
        c = coin(seed + i * 13, level=0.62 + i * 0.08)
        y += at(c * (0.7 + i * 0.08), t0, dur)
    y = chord_at(y, dur, 0.44, [72, 76, 79], 0.55, seed=seed)
    return finish(y, hp=380, mud=(620, -2.0), presence=(3500, -2.5), air=(10000, 1.0),
                  room=0.18, size=0.30, damp=0.5, peak=0.88, tail_ms=18, seed=471)


def coin_rain(seed=481):
    """Дождь монет: россыпь с насыщением, стопка и разрешение."""
    dur = 2.4
    y = np.zeros(int(dur * SR))
    r = np.random.default_rng(seed)
    for i in range(14):
        t0 = 0.05 + 1.35 * (i / 13) ** 0.92 + float(r.uniform(-0.02, 0.02))
        y += at(coin(seed + i * 7, level=0.5) * float(r.uniform(0.42, 0.68)), max(0, t0), dur)
    y += at(bar(440, 0.42, ratios=MEMBRANE['ratios'], t60=0.14, beta=1.5, gamma=0.82,
                mallet=2.6, velocity=1.4, seed=seed + 40), 1.52, dur) * 0.45
    y = chord_at(y, dur, 1.62, [60, 64, 67, 72], 0.85, seed=seed + 3)
    y += at(bar(N(96), 1.0, velocity=0.6, pos=0.30, seed=seed + 50, **GLOCK), 1.90, dur) * 0.26
    y = compress(y, -20, 2.6, 6, 110)
    return finish_stereo(y, width=0.7, size=0.34, seed=481, peak=0.90)


def gem(seed=491):
    """Кристалл: стеклянные моды с долгим затуханием."""
    dur = 1.1
    a = bar(N(88), dur, velocity=1.0, pos=0.30, seed=seed, **GLASS)
    b = at(bar(N(95), 0.9, velocity=0.7, pos=0.30, seed=seed + 1, **GLASS), 0.10, dur)
    shine = at(bar(N(100), 0.8, velocity=0.5, pos=0.30, seed=seed + 2, **GLOCK), 0.20, dur)
    y = a * 1.0 + b * 0.7 + shine * 0.30
    return finish(y, hp=460, mud=None, presence=(4200, -2.0), air=(11000, 1.5),
                  room=0.22, size=0.30, damp=0.45, peak=0.80, tail_ms=18, seed=491)


def star(seed=501):
    """Звезда: удар и три искры вверх."""
    dur = 1.0
    y = pad_to(bar(N(79), 0.8, velocity=1.0, pos=0.30, seed=seed,
                   tube=N(79), tube_mix=0.5, **MARIMBA), dur)
    for i, (t0, m) in enumerate([(0.11, 91), (0.22, 96), (0.33, 100)]):
        y += at(bar(N(m), 0.7, velocity=0.6, pos=0.30, seed=seed + m, **GLOCK), t0, dur) * (0.42 - i * 0.09)
    return finish(y, hp=340, mud=(560, -1.5), presence=(3600, -2.0), air=(9500, 1.5),
                  room=0.18, size=0.28, damp=0.5, peak=0.80, tail_ms=16, seed=501)


def badge(seed=511):
    """Значок: вес удара и подтверждающий аккорд."""
    dur = 1.3
    y = pad_to(bar(500, 0.42, ratios=MEMBRANE['ratios'], t60=0.15, beta=1.5, gamma=0.8,
                   mallet=2.4, velocity=1.5, seed=seed), dur) * 0.55
    y = chord_at(y, dur, 0.09, [60, 64, 67, 72], 0.9, seed=seed + 2)
    y += at(bar(N(60), 1.1, velocity=0.6, pos=0.30, seed=seed + 5, **TUBULAR), 0.11, dur) * 0.26
    y += at(bar(N(91), 0.8, velocity=0.55, pos=0.30, seed=seed + 8, **GLOCK), 0.34, dur) * 0.24
    return finish(y, hp=280, mud=(480, -2.0), presence=(3000, -2.0), air=(8500, 1.0),
                  room=0.20, size=0.30, damp=0.5, peak=0.88, tail_ms=20, seed=511)


def chest_anticipation(seed=521):
    """Ожидание: сундук дрожит, засечки ускоряются."""
    dur = 1.2
    y = np.zeros(int(dur * SR))
    for i in range(11):
        t0 = 1.0 * (i / 10) ** 1.7
        y += at(bar(900 + (i % 4) * 70, 0.20, ratios=[1, 2.41, 3.72], t60=0.030,
                    beta=1.6, gamma=0.85, mallet=3.6, velocity=0.55 + i * 0.035,
                    seed=seed + i), t0, dur) * (0.35 + i * 0.035)
    return finish(y, hp=380, mud=(560, -2.0), presence=(3400, -2.5),
                  drive=1.1, room=0.10, size=0.18, damp=0.7, peak=0.66, tail_ms=12, seed=521)


def chest_open(seed=531):
    """Открытие: удар крышки, раскрытие, сияние."""
    dur = 2.0
    y = pad_to(bar(470, 0.45, ratios=MEMBRANE['ratios'], t60=0.16, beta=1.5, gamma=0.8,
                   mallet=2.4, velocity=1.7, seed=seed), dur) * 0.5
    y = chord_at(y, dur, 0.14, [65, 69, 72], 0.6, seed=seed + 2)
    y = chord_at(y, dur, 0.52, [60, 64, 67, 72, 76], 1.0, seed=seed + 5)
    y += at(bar(N(60), 1.8, velocity=0.7, pos=0.30, seed=seed + 9, **TUBULAR), 0.54, dur) * 0.30
    for i, (t0, m) in enumerate([(0.80, 91), (0.96, 96), (1.12, 100), (1.28, 103)]):
        y += at(bar(N(m), 0.9, velocity=0.58, pos=0.30, seed=seed + m, **GLOCK), t0, dur) * (0.32 - i * 0.06)
    y = compress(y, -20, 2.5, 6, 110)
    return finish_stereo(y, width=0.78, size=0.36, seed=531, peak=0.92)


# ------------------------------------------------------------------- ПРОГРЕСС

def progress_step(seed=541):
    """
    Шаг прогресса. Играется подряд много раз, поэтому короткий и без хвоста;
    высота поднимается на каждом шаге уже в приложении, одним сэмплом.
    """
    dur = 0.13
    y = bar(N(84), dur, ratios=[1, 3.99, 9.2], t60=0.075, beta=1.5, gamma=0.75,
            mallet=3.4, velocity=0.8, pos=0.30, seed=seed, tube=N(84), tube_mix=0.45)
    return finish(y, hp=420, mud=None, presence=(3600, -2.5), air=(10000, 1.0),
                  room=0.07, size=0.13, damp=0.75, peak=0.52, tail_ms=8, seed=541)


def progress_complete(seed=551):
    """Полоса заполнена."""
    dur = 0.85
    a = bar(N(84), dur, velocity=0.95, pos=0.30, seed=seed, tube=N(84), tube_mix=0.5, **MARIMBA)
    y = pad_to(a, dur) * 0.9
    y = chord_at(y, dur, 0.12, [67, 72, 76], 0.82, seed=seed + 3)
    y += at(bar(N(96), 0.7, velocity=0.55, pos=0.30, seed=seed + 7, **GLOCK), 0.30, dur) * 0.24
    return finish(y, hp=340, mud=(560, -1.5), presence=(3200, -2.0), air=(9000, 1.5),
                  room=0.16, size=0.26, damp=0.55, peak=0.78, tail_ms=16, seed=551)


def checkpoint(seed=561):
    """Контрольная точка: три ступени вверх."""
    dur = 0.95
    y = np.zeros(int(dur * SR))
    for i, m in enumerate([72, 76, 79]):
        f = N(m)
        y += at(bar(f, 0.7, velocity=0.9, pos=0.30, seed=seed + m,
                    tube=f, tube_mix=0.5, **MARIMBA), i * 0.135, dur) * 0.85
    y += at(bar(N(91), 0.8, velocity=0.55, pos=0.30, seed=seed + 9, **GLOCK), 0.42, dur) * 0.26
    return finish(y, hp=330, mud=(560, -1.5), presence=(3100, -2.0), air=(8800, 1.5),
                  room=0.17, size=0.26, damp=0.55, peak=0.78, tail_ms=16, seed=561)


def goal_complete(seed=571):
    """Цель дня закрыта."""
    dur = 1.4
    y = np.zeros(int(dur * SR))
    for i, m in enumerate([67, 72, 76]):
        f = N(m + 12)
        y += at(bar(f, 0.8, velocity=0.95, pos=0.30, seed=seed + m,
                    tube=f, tube_mix=0.5, **MARIMBA), i * 0.105, dur) * 0.8
    y = chord_at(y, dur, 0.38, [60, 64, 67, 72], 0.92, seed=seed + 4)
    y += at(bar(N(96), 0.9, velocity=0.58, pos=0.30, seed=seed + 8, **GLOCK), 0.62, dur) * 0.26
    y = compress(y, -20, 2.4, 6, 100)
    return finish_stereo(y, width=0.6, size=0.28, seed=571, peak=0.86)


# -------------------------------------------------------------------- ОТВЕТЫ

def answer_select(seed=601):
    """Вариант выбран — ещё не проверен, поэтому нейтрально и тихо."""
    dur = 0.20
    y = bar(N(81), dur, ratios=[1, 3.99, 9.2], t60=0.10, beta=1.5, gamma=0.78,
            mallet=3.2, velocity=0.75, pos=0.30, seed=seed, tube=N(81), tube_mix=0.45)
    return finish(y, hp=400, mud=None, presence=(3400, -2.5), air=(9500, 1.0),
                  room=0.09, size=0.15, damp=0.72, peak=0.56, tail_ms=10, seed=601)


def answer_submit(seed=611):
    """Ответ уходит на проверку: движение вперёд без оценки."""
    dur = 0.38
    a = bar(N(79), dur, velocity=0.85, pos=0.30, seed=seed, tube=N(79), tube_mix=0.5, **MARIMBA)
    b = at(bar(N(84), 0.32, velocity=0.9, pos=0.30, seed=seed + 1,
               tube=N(84), tube_mix=0.5, **MARIMBA), 0.075, dur)
    y = a * 0.85 + b * 1.0
    return finish(y, hp=350, mud=(560, -1.5), presence=(3200, -2.0), air=(9000, 1.0),
                  room=0.13, size=0.22, damp=0.6, peak=0.66, tail_ms=12, seed=611)


def perfect_answer(seed=621):
    """Идеальный ответ: то же движение, что у верного, но ярче и на терцию выше."""
    dur = 0.85
    y = np.zeros(int(dur * SR))
    for i, (t0, m) in enumerate([(0.0, 84), (0.095, 88), (0.19, 91)]):
        f = N(m)
        y += at(bar(f, 0.7, velocity=1.0, pos=0.30, seed=seed + m,
                    tube=f, tube_mix=0.55, **MARIMBA), t0, dur) * (0.9 + i * 0.04)
    y += at(bar(N(103), 0.7, velocity=0.55, pos=0.30, seed=seed + 9, **GLOCK), 0.30, dur) * 0.26
    return finish(y, hp=340, mud=(560, -1.5), presence=(2900, -2.0), air=(8500, 2.0),
                  room=0.18, size=0.28, damp=0.5, peak=0.82, tail_ms=14, seed=621)


def nearly(seed=631):
    """Почти верно: две ноты без движения вверх или вниз — оценка отложена."""
    dur = 0.55
    a = bar(N(76), dur, ratios=[1, 3.99, 9.2], t60=0.24, beta=1.9, gamma=0.82,
            mallet=2.6, velocity=0.8, pos=0.42, seed=seed, tube=N(76), tube_mix=0.45)
    b = at(bar(N(76), 0.42, ratios=[1, 3.99, 9.2], t60=0.26, beta=1.9, gamma=0.82,
               mallet=2.5, velocity=0.75, pos=0.42, seed=seed + 1,
               tube=N(75), tube_mix=0.45), 0.145, dur)
    y = a * 1.0 + b * 0.9
    return finish(y, hp=320, mud=(500, -2.0), presence=(2800, -2.0),
                  drive=1.1, room=0.13, size=0.22, damp=0.68, peak=0.68, tail_ms=14, seed=631)


def wrong_hard(seed=641):
    """
    Жёсткая ошибка: заметнее мягкой, но по-прежнему не наказывает —
    нисходящая кварта на задемпфированном стержне, без диссонанса и без зуммера.
    """
    dur = 0.65
    a = bar(N(74), dur, ratios=[1, 3.99, 9.2], t60=0.24, beta=1.9, gamma=0.84,
            mallet=2.8, velocity=1.0, pos=0.5, seed=seed, tube=N(74), tube_mix=0.45)
    b = at(bar(N(69), 0.5, ratios=[1, 3.99, 9.2], t60=0.28, beta=1.9, gamma=0.84,
               mallet=2.6, velocity=0.95, pos=0.5, seed=seed + 1,
               tube=N(69), tube_mix=0.45), 0.15, dur)
    body = bar(N(62), dur, ratios=[1, 2.4, 4.1], t60=0.13, beta=2.2, gamma=0.92,
               mallet=2.6, velocity=0.85, seed=seed + 2)
    y = a * 1.0 + b * 1.0 + body * 0.22
    y = lowpass(y, 6800, 2)
    return finish(y, hp=290, mud=(430, -2.0), presence=(2600, -1.5),
                  drive=1.2, room=0.13, size=0.22, damp=0.7, peak=0.76, tail_ms=14, seed=641)


def hint(seed=651):
    """Подсказка: искра сверху, затем спокойное подтверждение."""
    dur = 0.75
    y = pad_to(bar(N(96), 0.7, velocity=0.6, pos=0.30, seed=seed, **GLOCK), dur) * 0.55
    y += at(bar(N(84), 0.6, velocity=0.85, pos=0.30, seed=seed + 3,
                tube=N(84), tube_mix=0.5, **MARIMBA), 0.145, dur) * 0.9
    return finish(y, hp=360, mud=(600, -1.5), presence=(3300, -2.0), air=(9500, 1.5),
                  room=0.18, size=0.26, damp=0.5, peak=0.70, tail_ms=14, seed=651)


# ----------------------------------------------------------------- НАВИГАЦИЯ

def close_sheet(seed=661):
    """Закрытие: зеркало открытия — движение вниз и вниз по строю."""
    dur = 0.30
    a = bar(N(86), dur, velocity=0.75, pos=0.30, seed=seed, tube=N(86), tube_mix=0.5, **MARIMBA)
    b = at(bar(N(79), 0.26, velocity=0.7, pos=0.30, seed=seed + 1,
               tube=N(79), tube_mix=0.5, **MARIMBA), 0.095, dur)
    n = int(0.045 * SR)
    cloth = noise_burst(0.07, seed + 2)[:n] * np.exp(-np.linspace(0, 3.4, n))
    cloth = pad_to(bandpass(cloth, 900, 3400, 2), dur)
    y = a * 0.85 + b * 1.0 + cloth * 0.04
    return finish(y, hp=300, mud=(520, -1.5), presence=(3000, -2.5), air=(9000, 0.5),
                  room=0.14, size=0.22, damp=0.65, peak=0.60, tail_ms=12, seed=661)


def nav_step(forward=True, seed=671):
    """Шаг вперёд или назад: одинаковый жест, направление задаёт интервал."""
    dur = 0.26
    n1, n2 = (81, 86) if forward else (86, 81)
    a = bar(N(n1), dur, ratios=[1, 3.99, 9.2], t60=0.12, beta=1.6, gamma=0.78,
            mallet=3.2, velocity=0.8, pos=0.30, seed=seed, tube=N(n1), tube_mix=0.45)
    b = at(bar(N(n2), 0.22, ratios=[1, 3.99, 9.2], t60=0.13, beta=1.6, gamma=0.78,
               mallet=3.2, velocity=0.85, pos=0.30, seed=seed + 1,
               tube=N(n2), tube_mix=0.45), 0.075, dur)
    y = a * 0.8 + b * 1.0
    return finish(y, hp=380, mud=None, presence=(3300, -2.5), air=(9500, 1.0),
                  room=0.11, size=0.18, damp=0.68, peak=0.58, tail_ms=10,
                  seed=671 if forward else 677)


def tab_switch(seed=681):
    """Вкладка: короткая фиксация без мелодии."""
    dur = 0.18
    snap = bar(1180, dur, ratios=[1, 2.41, 3.72, 5.06], t60=0.05, beta=1.2, gamma=0.72,
               mallet=3.8, velocity=0.9, pos=0.30, seed=seed)
    body = bar(N(83), dur, ratios=[1, 3.99], t60=0.09, beta=1.8, gamma=0.85,
               mallet=3.0, velocity=0.7, seed=seed + 1)
    y = snap * 0.85 + body * 0.7
    return finish(y, hp=400, mud=None, presence=(3600, -2.5), air=(10000, 1.0),
                  room=0.09, size=0.15, damp=0.72, peak=0.58, tail_ms=8, seed=681)


def modal_open(seed=691):
    """Модалка приближается: строй идёт вверх, тембр раскрывается."""
    dur = 0.42
    y = np.zeros(int(dur * SR))
    for i, (t0, m) in enumerate([(0.0, 76), (0.085, 83), (0.17, 88)]):
        f = N(m)
        y += at(bar(f, 0.42, velocity=0.7 + i * 0.1, pos=0.30, seed=seed + m,
                    tube=f, tube_mix=0.5, **MARIMBA), t0, dur) * (0.6 + i * 0.14)
    return finish(y, hp=340, mud=(560, -1.5), presence=(3100, -2.0), air=(9000, 1.0),
                  room=0.16, size=0.24, damp=0.58, peak=0.66, tail_ms=12, seed=691)


def modal_close(seed=701):
    """Модалка уходит назад."""
    dur = 0.36
    y = np.zeros(int(dur * SR))
    for i, (t0, m) in enumerate([(0.0, 88), (0.08, 83), (0.16, 76)]):
        f = N(m)
        y += at(bar(f, 0.36, velocity=0.85 - i * 0.1, pos=0.30, seed=seed + m,
                    tube=f, tube_mix=0.5, **MARIMBA), t0, dur) * (0.85 - i * 0.14)
    return finish(y, hp=320, mud=(520, -1.5), presence=(3000, -2.5), air=(9000, 0.5),
                  room=0.14, size=0.22, damp=0.65, peak=0.60, tail_ms=12, seed=701)


# -------------------------------------------------------------------- СИСТЕМА

def notify(seed=711):
    """Уведомление: две ноты, заметно, но без тревоги."""
    dur = 0.75
    a = bar(N(91), dur, velocity=0.8, pos=0.30, seed=seed, **GLOCK)
    b = at(bar(N(96), 0.6, velocity=0.75, pos=0.30, seed=seed + 1, **GLOCK), 0.135, dur)
    warm = at(bar(N(84), 0.5, velocity=0.6, pos=0.30, seed=seed + 2,
                  tube=N(84), tube_mix=0.5, **MARIMBA), 0.135, dur)
    y = a * 0.8 + b * 0.85 + warm * 0.45
    return finish(y, hp=420, mud=None, presence=(3600, -2.0), air=(10000, 1.5),
                  room=0.18, size=0.26, damp=0.5, peak=0.72, tail_ms=14, seed=711)


def success_small(seed=721):
    """Маленькое подтверждение: сохранено, применено."""
    dur = 0.40
    a = bar(N(84), dur, velocity=0.85, pos=0.30, seed=seed, tube=N(84), tube_mix=0.5, **MARIMBA)
    b = at(bar(N(91), 0.32, velocity=0.8, pos=0.30, seed=seed + 1, **GLOCK), 0.085, dur)
    y = a * 1.0 + b * 0.42
    return finish(y, hp=380, mud=None, presence=(3400, -2.0), air=(9500, 1.5),
                  room=0.14, size=0.22, damp=0.55, peak=0.66, tail_ms=12, seed=721)


def message_send(seed=731):
    """Сообщение уходит: строй вверх, звук отдаляется."""
    dur = 0.32
    a = bar(N(79), dur, ratios=[1, 3.99, 9.2], t60=0.12, beta=1.7, gamma=0.8,
            mallet=3.0, velocity=0.85, pos=0.30, seed=seed, tube=N(79), tube_mix=0.45)
    b = at(bar(N(86), 0.26, ratios=[1, 3.99], t60=0.11, beta=1.8, gamma=0.85,
               mallet=3.0, velocity=0.7, pos=0.30, seed=seed + 1), 0.085, dur)
    y = a * 1.0 + b * 0.6
    return finish(y, hp=380, mud=None, presence=(3300, -2.5), air=(9500, 1.0),
                  room=0.20, size=0.26, damp=0.55, peak=0.60, tail_ms=12, seed=731)


def message_receive(seed=741):
    """Сообщение приходит: строй вниз, звук приближается."""
    dur = 0.38
    a = bar(N(88), dur, ratios=[1, 3.99], t60=0.11, beta=1.8, gamma=0.85,
            mallet=3.0, velocity=0.65, pos=0.30, seed=seed)
    b = at(bar(N(81), 0.32, ratios=[1, 3.99, 9.2], t60=0.13, beta=1.7, gamma=0.8,
               mallet=3.0, velocity=0.9, pos=0.30, seed=seed + 1,
               tube=N(81), tube_mix=0.45), 0.085, dur)
    y = a * 0.55 + b * 1.0
    return finish(y, hp=360, mud=(560, -1.5), presence=(3200, -2.0), air=(9000, 1.0),
                  room=0.16, size=0.24, damp=0.55, peak=0.64, tail_ms=12, seed=741)


# ============================================================================
#  Полный реестр библиотеки
# ============================================================================

CATALOG = [
    ('Нажатия', [
        ('tap',            'Нажатие',            'Вудблок 1240 Гц + тёплый слой 455 Гц',      tap),
        ('tap-soft',       'Лёгкое касание',     'Тот же корпус, слабее удар — сам темнее',   tap_soft),
        ('tap-heavy',      'Сильное нажатие',    'Корпус 690 Гц + мембрана 305 Гц',           tap_heavy),
        ('key',            'Клавиша',            'Щелчок механизма и приземление',            key_press),
        ('toggle-on',      'Переключатель вкл',  'Трение, затем защёлка 1620 Гц',             lambda: toggle(True)),
        ('toggle-off',     'Переключатель выкл', 'Обратный ход, защёлка 1180 Гц',             lambda: toggle(False)),
        ('tab-switch',     'Вкладка',            'Короткая фиксация без мелодии',             tab_switch),
    ]),
    ('Прокрутка', [
        ('scroll-tick',    'Тик прокрутки',      'Засечка 45 мс, узкая полоса, без хвоста',   scroll_tick),
        ('scroll-detent',  'Засечка колеса',     'Весомее тика: шаг карусели или пикера',     scroll_detent),
        ('scroll-snap',    'Снап элемента',      'Элемент встал на место',                    scroll_snap),
        ('scroll-edge',    'Край списка',        'Резинка: волновод с падением строя',        scroll_edge),
        ('pull-refresh',   'Потягивание',        'Натяжение: строй ползёт вверх',             pull_refresh),
        ('refresh-done',   'Обновлено',          'Короткая восходящая пара',                  refresh_done),
    ]),
    ('Ответы', [
        ('answer-select',  'Выбор ответа',       'Нейтрально: оценки ещё нет',                answer_select),
        ('answer-submit',  'Отправка ответа',    'Движение вперёд без оценки',                answer_submit),
        ('correct',        'Правильный ответ',   'Маримба C6→G6 с резонаторной трубой',       correct),
        ('perfect-answer', 'Идеальный ответ',    'То же движение, ярче и выше',               perfect_answer),
        ('nearly',         'Почти верно',        'Две ноты без движения — оценка отложена',   nearly),
        ('wrong-soft',     'Мягкая ошибка',      'Приглушённая м3 вниз D5→A#4',               wrong_soft),
        ('wrong-hard',     'Жёсткая ошибка',     'Кварта вниз, заметно, но без наказания',    wrong_hard),
        ('hint',           'Подсказка',          'Искра сверху, затем подтверждение',         hint),
    ]),
    ('Прогресс', [
        ('progress-step',     'Шаг прогресса',   'Высота растёт с шагом — уже в плеере',      progress_step),
        ('progress-complete', 'Полоса заполнена','Нота и аккорд',                             progress_complete),
        ('checkpoint',        'Контрольная точка','Три ступени вверх',                        checkpoint),
        ('goal-complete',     'Цель дня',        'Мотив и разрешение',                        goal_complete),
    ]),
    ('Победы', [
        ('victory',        'Победа',             'Мотив G-C-E-G и разрешение в до-мажор',     victory),
        ('victory-big',    'Большая победа',     'Каденция IV–V–I с медью и колоколом',       victory_big),
        ('perfect',        'Идеальный урок',     'Выше и с большим блеском, Cmaj9',           perfect),
        ('level-up',       'Новый уровень',      'Подъём по ступеням, затем прибытие',        level_up),
        ('unit-complete',  'Раздел завершён',    'Узлы пути собираются в веху',               unit_complete),
        ('streak',         'Серия',              'Ускоряющиеся засечки и подтверждение',      streak),
        ('fanfare',        'Фанфара',            'Медь: раскрывающийся фильтр на атаке',      fanfare),
        ('lesson',         'Урок пройден',       'Мотив, каденция IV–V–I, хвост глокеншпиля', lesson_complete),
    ]),
    ('Награды', [
        ('coin',           'Монета',             'Моды диска 1:1.73:2.33:3.91, биения 9 Гц',  coin),
        ('coin-multi',     'Несколько монет',    'Каждая выше предыдущей',                    coin_multi),
        ('coin-rain',      'Дождь монет',        'Россыпь, стопка и разрешение',              coin_rain),
        ('gem',            'Кристалл',           'Стеклянные моды с долгим затуханием',       gem),
        ('star',           'Звезда',             'Удар и три искры вверх',                    star),
        ('badge',          'Значок',             'Вес удара и подтверждающий аккорд',         badge),
        ('reward',         'Награда',            'Монета и глокеншпиль E6-G#6-B6',            reward),
        ('chest-anticipation', 'Ожидание сундука','Засечки ускоряются',                       chest_anticipation),
        ('chest-open',     'Сундук открыт',      'Удар крышки, раскрытие, сияние',            chest_open),
    ]),
    ('Навигация', [
        ('open',           'Открытие',           'Маримба A5→E6, материал только призвуком',  open_sheet),
        ('close',          'Закрытие',           'Зеркало открытия: движение вниз',           close_sheet),
        ('forward',        'Вперёд',             'Интервал вверх',                            lambda: nav_step(True)),
        ('back',           'Назад',              'Интервал вниз',                             lambda: nav_step(False)),
        ('modal-open',     'Модалка открыта',    'Строй вверх, тембр раскрывается',           modal_open),
        ('modal-close',    'Модалка закрыта',    'Уходит назад',                              modal_close),
    ]),
    ('Система и характер', [
        ('notify',         'Уведомление',        'Две ноты, заметно и без тревоги',           notify),
        ('success-small',  'Сохранено',          'Маленькое подтверждение',                   success_small),
        ('message-send',   'Сообщение отправлено','Строй вверх, звук отдаляется',             message_send),
        ('message-receive','Сообщение получено', 'Строй вниз, звук приближается',             message_receive),
        ('roar',           'Рёв динозавра',      'Связки с джиттером, форманты пасти, хрип',  roar),
        ('whistle-up',     'Свистулька вверх',   'Воздушный столб 950→3000 Гц',               lambda: slide_whistle(True)),
        ('whistle-down',   'Свистулька вниз',    'Воздушный столб 3000→820 Гц',               lambda: slide_whistle(False)),
    ]),
]

REGISTRY = {sid: fn for _, items in CATALOG for sid, _, _, fn in items}
META = {sid: {'title': t, 'note': n, 'category': cat}
        for cat, items in CATALOG for sid, t, n, _ in items}
