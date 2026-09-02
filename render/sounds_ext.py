"""
CueLab v13.2 — расширение библиотеки.

Новые семейства материалов (дерево, камень, металл, стекло), разные свистки
и большие многофазные победы.
"""
import numpy as np
from scipy import signal

from dsp import *
from sounds import (N, bar, finish, finish_stereo, chord_at, tick_noise, coin,
                    MARIMBA, GLOCK, WOODBLOCK, DISC, MEMBRANE, GLASS, TUBULAR)

# --------------------------------------------------------------- материалы
#
# Камень жёстче дерева: моды выше, спектр сильнее негармоничен, затухание
# заметно короче. Именно короткое затухание и негармоничность читаются ухом
# как «камень», а не как «маленький барабан».
STONE  = dict(ratios=[1, 1.62, 2.31, 2.96, 3.77, 4.55], t60=0.048, beta=1.5, gamma=0.80, mallet=9.0)
GRANITE= dict(ratios=[1, 1.58, 2.24, 3.05, 3.92], t60=0.075, beta=1.3, gamma=0.72, mallet=7.0)
CLAVES = dict(ratios=[1, 3.02, 5.40, 8.1], t60=0.115, beta=1.0, gamma=0.62, mallet=5.0)
TEMPLE = dict(ratios=[1, 2.11, 3.32, 4.6], t60=0.175, beta=1.15, gamma=0.70, mallet=3.4)
LOGDRUM= dict(ratios=[1, 2.48, 4.31, 6.2], t60=0.38, beta=1.2, gamma=0.68, mallet=2.8)
BAMBOO = dict(ratios=[1, 2.76, 5.10, 8.2], t60=0.28, beta=1.1, gamma=0.62, mallet=4.0)
ANVIL  = dict(ratios=[1, 2.34, 3.61, 5.12, 7.05, 9.3], t60=1.6, beta=0.75, gamma=0.45, mallet=12.0)
CHIME  = dict(ratios=[1, 2.76, 5.40, 8.93, 13.34, 18.4], t60=4.2, beta=0.62, gamma=0.38, mallet=6.0)


def gong(f0, dur, gain=1.0, seed=1, sr=SR):
    """
    Гонг: много негармоничных мод плюс медленное нарастание. У настоящего гонга
    энергия перетекает вверх по спектру уже ПОСЛЕ удара — отсюда характерное
    «расцветание». Здесь это сделано вторым слоем с задержанной атакой.
    """
    r = rng(seed)
    ratios = np.array([1, 1.41, 1.73, 2.09, 2.45, 2.83, 3.31, 3.87, 4.52, 5.31, 6.2, 7.4])
    ratios = ratios * (1 + r.standard_normal(len(ratios)) * 0.012)
    freqs = ratios * f0
    t60s = damping_curve(freqs, f0, 3.4, 0.85, 0.45)
    gains = 1.0 / (1.0 + 0.22 * np.arange(len(ratios)) ** 0.85)
    body = pad_to(modal(hertz_contact(1.8, 4.0), freqs, t60s, gains, seed=seed, detune=0.8), dur)
    # «расцветание»: верхние моды входят с задержкой
    hi = pad_to(modal(hertz_contact(1.2, 9.0), freqs[5:] * 1.5,
                      damping_curve(freqs[5:] * 1.5, f0, 2.2, 1.0, 0.5),
                      gains[5:] * 0.55, seed=seed + 7, detune=1.2), dur)
    t = np.arange(len(hi)) / sr
    hi *= np.clip((t - 0.09) / 0.35, 0, 1)
    return (body + hi * 0.7) * gain


def scrape(dur, ribs, f_lo, f_hi, gain=1.0, seed=1, accel=1.0, sr=SR):
    """Скребок по рёбрам: гуиро, реко-реко, зубчатая рейка."""
    y = np.zeros(int(dur * sr))
    for i in range(ribs):
        p = (i / max(1, ribs - 1)) ** accel
        t0 = p * dur * 0.92
        f = f_lo + (f_hi - f_lo) * p
        tick = bar(f, 0.06, ratios=[1, 2.4, 3.9], t60=0.018, beta=1.6, gamma=0.85,
                   mallet=6.0, velocity=0.6 + 0.4 * np.sin(p * np.pi), seed=seed + i)
        y += at(tick, t0, dur) * (0.55 + 0.45 * np.sin(p * np.pi))
    bed = bandpass(noise_burst(dur, seed + 91), f_lo * 1.4, f_hi * 1.8, 2)[:len(y)]
    t = np.arange(len(y)) / sr
    bed *= np.clip(t / 0.02, 0, 1) * np.clip((dur * 0.92 - t) / 0.06, 0, 1)
    return (y + bed * 0.18) * gain


# ------------------------------------------------------------------ СВИСТКИ

def whistle_bird(seed=801):
    """Птичья трель: быстрые перегибы строя, как у настоящей птицы."""
    dur = 0.62
    n = int(0.52 * SR)
    t = np.arange(n) / SR
    base = 2400 + 900 * np.sin(2 * np.pi * 5.5 * t) * np.exp(-t * 1.4)
    warble = 1 + 0.22 * np.sin(2 * np.pi * 22 * t) * np.exp(-t * 2.2)
    f = base * warble
    ph = np.cumsum(2 * np.pi * f / SR)
    tone = np.sin(ph) + 0.10 * np.sin(2 * ph)
    env = np.clip(t / 0.012, 0, 1) * np.exp(-np.clip(t - 0.18, 0, None) * 4.2)
    br = sweep_filter(noise_burst(0.52, seed)[:n], 3800, 5200, q=3.0)[:n]
    y = pad_to((tone * 0.8 + br * 0.14) * env, dur)
    return finish(y, hp=900, mud=None, presence=(4200, -2.5), air=(12000, -1.0),
                  room=0.16, size=0.24, damp=0.55, peak=0.70, tail_ms=12, seed=801)


def whistle_train(seed=811):
    """Паровозный свисток: аккорд из нескольких труб, поэтому он «воет»."""
    dur = 1.5
    n = int(1.35 * SR)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for i, (mult, g) in enumerate([(1.0, 1.0), (1.19, 0.75), (1.5, 0.55), (2.0, 0.3)]):
        f = 560 * mult * (1 + 0.006 * np.sin(2 * np.pi * 4.4 * t))
        ph = np.cumsum(2 * np.pi * f / SR)
        y += (np.sin(ph) + 0.22 * np.sin(2 * ph) + 0.07 * np.sin(3 * ph)) * g
    env = np.clip(t / 0.10, 0, 1) * np.clip((t[-1] - t) / 0.30, 0, 1)
    steam = bandpass(noise_burst(1.35, seed + 3), 1600, 6000, 2)[:n] * env * 0.16
    y = pad_to((y / 2.6 + steam) * env, dur)
    return finish(y, hp=330, mud=(520, -2.0), presence=(3200, -2.0), air=(9000, 1.0),
                  drive=1.15, room=0.22, size=0.36, damp=0.5, peak=0.86, tail_ms=24, seed=811)


def whistle_referee(seed=821):
    """Судейский свисток: горошина внутри даёт быструю амплитудную дрожь."""
    dur = 0.75
    n = int(0.62 * SR)
    t = np.arange(n) / SR
    f = 3150 * (1 + 0.012 * np.sin(2 * np.pi * 3.0 * t))
    ph = np.cumsum(2 * np.pi * f / SR)
    pea = 0.55 + 0.45 * np.sin(2 * np.pi * 38 * t + 1.6 * np.sin(2 * np.pi * 7 * t))
    tone = (np.sin(ph) + 0.30 * np.sin(2 * ph) + 0.12 * np.sin(3 * ph)) * pea
    env = np.clip(t / 0.014, 0, 1) * np.clip((t[-1] - t) / 0.08, 0, 1)
    air = sweep_filter(noise_burst(0.62, seed)[:n], 4200, 5000, q=2.2)[:n] * env * 0.22
    y = pad_to(tone * env * 0.9 + air, dur)
    return finish(y, hp=1100, mud=None, presence=(5200, -3.0), air=(12000, -2.0),
                  drive=1.2, room=0.14, size=0.22, damp=0.6, peak=0.82, tail_ms=14, seed=821)


def whistle_boatswain(seed=831):
    """Боцманская дудка: подъём, трель наверху, спад."""
    dur = 1.35
    n = int(1.2 * SR)
    t = np.arange(n) / SR
    p = t / t[-1]
    base = np.interp(p, [0, 0.18, 0.30, 0.72, 0.86, 1.0],
                     [1400, 2600, 2650, 2650, 2400, 1500])
    trill = 1 + 0.10 * np.sin(2 * np.pi * 17 * t) * np.clip((p - 0.32) / 0.08, 0, 1) * np.clip((0.74 - p) / 0.08, 0, 1)
    ph = np.cumsum(2 * np.pi * base * trill / SR)
    tone = np.sin(ph) + 0.13 * np.sin(2 * ph)
    env = np.clip(t / 0.03, 0, 1) * np.clip((t[-1] - t) / 0.10, 0, 1)
    br = sweep_filter(noise_burst(1.2, seed)[:n], 2600, 4600, q=3.2)[:n] * env * 0.16
    y = pad_to(tone * env * 0.85 + br, dur)
    return finish(y, hp=700, mud=None, presence=(4200, -2.5), air=(11000, -1.0),
                  room=0.18, size=0.28, damp=0.55, peak=0.78, tail_ms=16, seed=831)


def whistle_two_tone(seed=841):
    """Двухтональный сигнал: две ноты подряд, как у почтальона."""
    dur = 0.70
    y = np.zeros(int(dur * SR))
    for t0, f in [(0.0, 1450.0), (0.24, 1050.0)]:
        n = int(0.30 * SR)
        t = np.arange(n) / SR
        ph = np.cumsum(2 * np.pi * np.full(n, f) / SR)
        tone = np.sin(ph) + 0.20 * np.sin(2 * ph) + 0.06 * np.sin(3 * ph)
        env = np.clip(t / 0.014, 0, 1) * np.clip((t[-1] - t) / 0.07, 0, 1)
        br = sweep_filter(noise_burst(0.30, seed + int(f))[:n], f * 1.7, f * 1.9, q=3.5)[:n]
        y += at(pad_to(tone * env * 0.85 + br * env * 0.14, dur - t0), t0, dur)
    return finish(y, hp=520, mud=None, presence=(3800, -2.5), air=(10000, 0.5),
                  room=0.16, size=0.26, damp=0.55, peak=0.78, tail_ms=14, seed=841)


def whistle_pan(seed=851):
    """Панфлейта: три ноты вверх, много дыхания."""
    dur = 0.95
    y = np.zeros(int(dur * SR))
    for i, (t0, m) in enumerate([(0.0, 79), (0.16, 84), (0.32, 88)]):
        n = int(0.42 * SR)
        t = np.arange(n) / SR
        f = N(m) * (1 + 0.008 * np.sin(2 * np.pi * 5.0 * t) * np.clip((t - 0.09) / 0.1, 0, 1))
        ph = np.cumsum(2 * np.pi * f / SR)
        tone = np.sin(ph) + 0.07 * np.sin(2 * ph)
        env = np.clip(t / 0.035, 0, 1) * np.clip((t[-1] - t) / 0.13, 0, 1)
        br = sweep_filter(noise_burst(0.42, seed + m)[:n], N(m) * 1.6, N(m) * 2.4, q=2.4)[:n]
        y += at(pad_to((tone * 0.75 + br * 0.34) * env, dur - t0), t0, dur) * (0.85 + i * 0.05)
    return finish(y, hp=420, mud=None, presence=(3400, -2.0), air=(10000, 1.0),
                  room=0.20, size=0.30, damp=0.5, peak=0.76, tail_ms=18, seed=851)


def whistle_long(seed=861):
    """Длинное глиссандо: полторы секунды снизу доверху."""
    dur = 1.6
    n = int(1.45 * SR)
    t = np.arange(n) / SR
    p = t / t[-1]
    f = 520 * (7.0 ** p)
    ph = np.cumsum(2 * np.pi * f / SR)
    tone = np.sin(ph) + 0.14 * np.sin(2 * ph) + 0.05 * np.sin(3 * ph)
    env = np.clip(t / 0.05, 0, 1) * np.clip((t[-1] - t) / 0.12, 0, 1) * (0.55 + 0.45 * p)
    br = sweep_filter(noise_burst(1.45, seed)[:n], f[0] * 1.8, f[-1] * 1.4, q=3.0)[:n]
    y = pad_to((tone * 0.8 + br * 0.22) * env, dur)
    return finish(y, hp=430, mud=None, presence=(4000, -3.0), air=(12000, -1.5),
                  room=0.18, size=0.30, damp=0.55, peak=0.80, tail_ms=18, seed=861)


def whistle_tiny(seed=871):
    """Совсем короткий свист-блик, 90 мс."""
    dur = 0.14
    n = int(0.095 * SR)
    t = np.arange(n) / SR
    p = t / t[-1]
    f = 2600 * (1.55 ** p)
    ph = np.cumsum(2 * np.pi * f / SR)
    env = np.clip(t / 0.006, 0, 1) * np.clip((t[-1] - t) / 0.03, 0, 1)
    y = pad_to((np.sin(ph) + 0.12 * np.sin(2 * ph)) * env, dur)
    return finish(y, hp=1100, mud=None, presence=(5000, -2.5), air=(12000, -2.0),
                  room=0.07, size=0.13, damp=0.7, peak=0.56, tail_ms=8, seed=871)


# -------------------------------------------------------------------- ДЕРЕВО

def wood_tap(seed=901):
    dur = 0.20
    y = bar(1180, dur, velocity=1.0, pos=0.31, seed=seed, **WOODBLOCK)
    y = y + bar(495, dur, ratios=[1, 2.7, 4.4], t60=0.08, beta=1.4, gamma=0.85,
                mallet=2.8, velocity=0.8, seed=seed + 1) * 0.32
    return finish(y, hp=280, mud=(420, -2.0), presence=(3200, -2.5), air=(9500, 1.0),
                  room=0.09, size=0.16, damp=0.72, peak=0.72, tail_ms=10, seed=901)


def wood_hollow(seed=911):
    dur = 0.32
    y = bar(820, dur, velocity=1.0, pos=0.29, seed=seed, **TEMPLE)
    return finish(y, hp=300, mud=(460, -1.5), presence=(3000, -2.5), air=(9000, 0.5),
                  room=0.12, size=0.20, damp=0.7, peak=0.74, tail_ms=12, seed=911)


def wood_claves(seed=921):
    dur = 0.24
    y = bar(1720, dur, velocity=1.1, pos=0.32, seed=seed, **CLAVES)
    return finish(y, hp=520, mud=None, presence=(4000, -2.5), air=(11000, 0.5),
                  room=0.10, size=0.17, damp=0.72, peak=0.76, tail_ms=10, seed=921)


def wood_log(seed=931):
    dur = 0.55
    y = bar(580, dur, velocity=1.0, pos=0.28, seed=seed, **LOGDRUM)
    return finish(y, hp=260, mud=(400, -2.0), presence=(2800, -2.0), air=(8500, 0.5),
                  room=0.14, size=0.22, damp=0.65, peak=0.80, tail_ms=14, seed=931)


def wood_guiro(seed=941):
    """Гуиро: скребок по рёбрам."""
    y = scrape(0.55, 16, 1500, 2400, gain=0.9, seed=seed, accel=0.85)
    return finish(y, hp=620, mud=None, presence=(3600, -2.5), air=(11000, -1.0),
                  room=0.10, size=0.18, damp=0.72, peak=0.74, tail_ms=12, seed=941)


def wood_castanets(seed=951):
    """Кастаньеты: сдвоенный щелчок с крошечным зазором."""
    dur = 0.26
    y = pad_to(bar(1560, 0.18, velocity=1.1, pos=0.33, seed=seed, **CLAVES), dur)
    y += at(bar(1470, 0.18, velocity=0.85, pos=0.33, seed=seed + 1, **CLAVES), 0.032, dur) * 0.8
    y += at(bar(1660, 0.16, velocity=0.7, pos=0.33, seed=seed + 2, **CLAVES), 0.066, dur) * 0.55
    return finish(y, hp=620, mud=None, presence=(4200, -2.5), air=(11500, 0.5),
                  room=0.10, size=0.17, damp=0.72, peak=0.78, tail_ms=10, seed=951)


def wood_bamboo(seed=961):
    """Бамбуковая подвеска: несколько трубок сталкиваются."""
    dur = 1.5
    y = np.zeros(int(dur * SR))
    r = rng(seed)
    for i in range(9):
        t0 = float(r.uniform(0, 0.85)) ** 1.2
        f = float(r.choice([494, 587, 659, 740, 831, 988]))
        y += at(bar(f, 0.9, velocity=float(r.uniform(0.5, 1.0)), pos=0.30,
                    seed=seed + i, **BAMBOO), t0, dur) * float(r.uniform(0.5, 0.95))
    return finish(y, hp=280, mud=(430, -1.5), presence=(3000, -2.0), air=(9500, 1.0),
                  room=0.20, size=0.32, damp=0.55, peak=0.82, tail_ms=20, seed=961)


def wood_knock(seed=971):
    """Стук в дверь: три удара по толстой доске."""
    dur = 0.95
    y = np.zeros(int(dur * SR))
    for i, t0 in enumerate([0.0, 0.22, 0.44]):
        y += at(bar(470, 0.34, ratios=[1, 2.41, 3.72, 5.06], t60=0.09, beta=1.4,
                    gamma=0.80, mallet=2.8, velocity=1.2 - i * 0.08, seed=seed + i),
                t0, dur) * (0.95 - i * 0.06)
    return finish(y, hp=330, mud=(470, -2.5), presence=(2900, -2.0),
                  drive=1.2, room=0.16, size=0.26, damp=0.62, peak=0.86, tail_ms=14, seed=971)


# --------------------------------------------------------------------- КАМЕНЬ

def stone_tap(seed=1001):
    dur = 0.16
    y = bar(1850, dur, velocity=1.0, pos=0.34, seed=seed, **STONE)
    y = y + bar(760, dur, ratios=[1, 1.6, 2.3], t60=0.035, beta=1.5, gamma=0.85,
                mallet=6.0, velocity=0.85, seed=seed + 1) * 0.45
    return finish(y, hp=420, mud=None, presence=(3800, -2.5), air=(11000, 0.5),
                  room=0.08, size=0.15, damp=0.75, peak=0.72, tail_ms=8, seed=1001)


def stone_pebble(seed=1011):
    """Галька: удар с отскоками, интервалы сокращаются как при падении."""
    dur = 0.85
    y = np.zeros(int(dur * SR))
    t0, gain = 0.0, 1.0
    gap = 0.16
    for i in range(6):
        y += at(bar(2100 + i * 90, 0.12, velocity=gain, pos=0.34,
                    seed=seed + i, **STONE), t0, dur) * gain
        t0 += gap
        gap *= 0.62
        gain *= 0.66
    return finish(y, hp=460, mud=None, presence=(4000, -2.5), air=(11000, 0.5),
                  room=0.12, size=0.20, damp=0.7, peak=0.76, tail_ms=12, seed=1011)


def stone_marble(seed=1021):
    """Мрамор: катится и щёлкает о край."""
    dur = 0.9
    roll = scrape(0.55, 22, 900, 1400, gain=0.35, seed=seed, accel=1.2)
    y = pad_to(roll, dur)
    y += at(bar(2600, 0.20, velocity=1.1, pos=0.34, seed=seed + 5, **STONE), 0.56, dur) * 0.9
    return finish(y, hp=430, mud=None, presence=(3600, -2.5), air=(10500, 0.5),
                  room=0.13, size=0.22, damp=0.68, peak=0.74, tail_ms=12, seed=1021)


def stone_grind(seed=1031):
    """Камень по камню: плотный скребок без выраженной высоты."""
    dur = 0.75
    n = int(0.62 * SR)
    t = np.arange(n) / SR
    bed = bandpass(noise_burst(0.62, seed), 700, 3200, 2)[:n]
    grain_mod = 0.6 + 0.4 * np.sin(2 * np.pi * 34 * t + 2.0 * np.sin(2 * np.pi * 5 * t))
    env = np.clip(t / 0.05, 0, 1) * np.clip((t[-1] - t) / 0.16, 0, 1)
    y = pad_to(bed * grain_mod * env, dur)
    y += pad_to(bar(430, 0.3, ratios=[1, 1.62, 2.31], t60=0.06, beta=1.5, gamma=0.85,
                    mallet=5.0, velocity=0.7, seed=seed + 3), dur) * 0.3
    return finish(y, hp=380, mud=(560, -2.0), presence=(2800, -2.0),
                  drive=1.2, room=0.12, size=0.22, damp=0.7, peak=0.72, tail_ms=14, seed=1031)


def stone_heavy(seed=1041):
    """Тяжёлый валун: удар с весом, но без ухода в суббас."""
    dur = 0.6
    y = bar(560, dur, velocity=2.2, pos=0.30, seed=seed, **GRANITE)
    y = y + bar(300, dur, ratios=MEMBRANE['ratios'], t60=0.13, beta=1.5, gamma=0.82,
                mallet=2.4, velocity=1.8, seed=seed + 1) * 0.55
    dust = pad_to(bandpass(noise_burst(0.3, seed + 2), 900, 4200, 2)[:int(0.22 * SR)] *
                  np.exp(-np.linspace(0, 4, int(0.22 * SR))), dur)
    y = y + dust * 0.07
    return finish(y, hp=250, mud=(360, -3.0), presence=(2800, -2.5),
                  drive=1.35, room=0.16, size=0.26, damp=0.6, peak=0.90, tail_ms=14, seed=1041)


# ------------------------------------------------------------- МЕТАЛЛ, СТЕКЛО

def metal_chime(seed=1101):
    dur = 2.4
    y = pad_to(bar(N(84), 2.2, velocity=0.9, pos=0.30, seed=seed, **CHIME), dur)
    y += at(bar(N(91), 1.8, velocity=0.6, pos=0.30, seed=seed + 1, **CHIME), 0.13, dur) * 0.55
    return finish(y, hp=420, mud=None, presence=(3600, -2.0), air=(11000, 1.5),
                  room=0.24, size=0.38, damp=0.42, peak=0.82, tail_ms=24, seed=1101)


def metal_anvil(seed=1111):
    dur = 1.3
    y = bar(1240, dur, velocity=1.6, pos=0.33, seed=seed, **ANVIL)
    y = y + bar(520, dur, ratios=[1, 2.34, 3.61], t60=0.12, beta=1.5, gamma=0.8,
                mallet=8.0, velocity=1.4, seed=seed + 1) * 0.4
    return finish(y, hp=400, mud=(620, -2.0), presence=(4200, -3.0), air=(12000, 0.5),
                  drive=1.25, room=0.18, size=0.30, damp=0.5, peak=0.88, tail_ms=18, seed=1111)


def metal_gong(seed=1121):
    dur = 3.2
    y = gong(300, dur, gain=0.9, seed=seed)
    return finish_stereo(y, width=0.8, size=0.42, seed=1121, hp=340,
                         mud=(520, -3.0), presence=(2800, -2.0), air=(9000, 1.5),
                         peak=0.90, tail_ms=40)


def metal_triangle(seed=1131):
    dur = 2.0
    y = bar(N(96), 1.9, ratios=[1, 2.53, 4.11, 6.47, 9.31, 13.2],
            t60=2.6, beta=0.65, gamma=0.40, mallet=11.0, velocity=0.8,
            pos=0.36, seed=seed)
    return finish(y, hp=900, mud=None, presence=(5200, -2.0), air=(13000, 1.0),
                  room=0.24, size=0.34, damp=0.42, peak=0.72, tail_ms=24, seed=1131)


def glass_tap(seed=1141):
    dur = 0.55
    y = bar(N(88), dur, velocity=1.0, pos=0.32, seed=seed, **GLASS)
    return finish(y, hp=520, mud=None, presence=(4400, -2.0), air=(12000, 1.0),
                  room=0.16, size=0.24, damp=0.5, peak=0.74, tail_ms=14, seed=1141)


def glass_ring(seed=1151):
    """Бокал: долгий чистый тон с лёгкими биениями."""
    dur = 2.6
    ratios = np.array(GLASS['ratios'], dtype=float)
    freqs = ratios * N(84)
    freqs[1] *= 1.0035
    t60s = damping_curve(freqs, N(84), 2.6, 0.6, 0.35)
    gains = strike_gains(ratios, 0.34, 'bar')
    y = pad_to(modal(hertz_contact(1.2, 7.0), freqs, t60s, gains, seed=seed, detune=0.3), dur)
    return finish(y, hp=460, mud=None, presence=(4200, -2.0), air=(12000, 1.5),
                  room=0.22, size=0.34, damp=0.45, peak=0.78, tail_ms=28, seed=1151)


# -------------------------------------------------------------- БОЛЬШИЕ ПОБЕДЫ

def marathon_win(seed=1201):
    """
    Победа в месячном марафоне — самая крупная сцена библиотеки, 7 секунд.
    Пять фаз: ожидание, разгон, прибытие, празднование, разрешение.
    Длинную сцену держит не громкость, а смена материала между фазами.
    """
    dur = 7.0
    y = np.zeros(int(dur * SR))

    # 1. ожидание: редкие засечки, пульс ускоряется
    t0, gap = 0.0, 0.30
    for i in range(7):
        y += at(bar(880 + i * 55, 0.26, ratios=[1, 2.41, 3.72], t60=0.05,
                    beta=1.4, gamma=0.8, mallet=4.2, velocity=0.5 + i * 0.05,
                    seed=seed + i), t0, dur) * (0.32 + i * 0.045)
        t0 += gap
        gap *= 0.88

    # 2. разгон: восходящая гамма
    scale = [72, 74, 76, 79, 81, 83, 84]
    for i, m in enumerate(scale):
        y += at(bar(N(m), 0.9, velocity=0.8 + i * 0.03, pos=0.30, seed=seed + m,
                    tube=N(m), tube_mix=0.55, **MARIMBA), 2.30 + i * 0.105, dur) * (0.62 + i * 0.04)

    # 3. прибытие: гонг, аккорд, медь
    y += at(gong(190, 3.0, gain=0.55, seed=seed + 40), 3.06, dur)
    y = chord_at(y, dur, 3.10, [60, 64, 67, 72], 0.95, seed=seed + 11)
    for i, m in enumerate([60, 64, 67, 72]):
        y += at(pad_to(brass_tone(N(m + 12), 1.5, gain=0.30, bright=1.1, seed=seed + m), dur - 3.12),
                3.12 + i * 0.016, dur) * 0.8
    y += at(bar(N(72), 3.2, velocity=0.75, pos=0.30, seed=seed + 21, **TUBULAR), 3.14, dur) * 0.34

    # 4. празднование: монеты и искры
    r = rng(seed + 5)
    for i in range(10):
        t = 4.05 + 1.15 * (i / 9) ** 0.9 + float(r.uniform(-0.02, 0.02))
        y += at(coin(seed + 60 + i, level=0.5) * float(r.uniform(0.34, 0.55)), t, dur)
    for i, (t, m) in enumerate([(4.30, 91), (4.52, 96), (4.74, 100), (4.96, 103)]):
        y += at(bar(N(m), 1.2, velocity=0.6, pos=0.30, seed=seed + m, **GLOCK), t, dur) * (0.30 - i * 0.05)

    # 5. разрешение
    y = chord_at(y, dur, 5.40, [65, 69, 72, 77], 0.62, seed=seed + 30)
    y = chord_at(y, dur, 5.72, [67, 71, 74, 79], 0.68, seed=seed + 33)
    y = chord_at(y, dur, 6.05, [60, 64, 67, 72, 76], 1.0, seed=seed + 36)
    y += at(bar(N(60), 2.4, velocity=0.8, pos=0.30, seed=seed + 44, **TUBULAR), 6.07, dur) * 0.34
    y += at(bar(N(96), 1.4, velocity=0.55, pos=0.30, seed=seed + 47, **GLOCK), 6.35, dur) * 0.24

    y = compress(y, -21, 2.6, 6, 130)
    return finish_stereo(y, width=0.9, size=0.46, seed=1201, peak=0.94, tail_ms=60)


def grand_prize(seed=1211):
    """Крутой приз: ожидание, удар, раскрытие, каскад, длинный хвост."""
    dur = 5.5
    y = np.zeros(int(dur * SR))
    for i in range(12):
        t0 = 1.35 * (i / 11) ** 1.8
        y += at(bar(760 + (i % 5) * 70, 0.22, ratios=[1, 2.41, 3.72], t60=0.035,
                    beta=1.6, gamma=0.85, mallet=3.8, velocity=0.45 + i * 0.04,
                    seed=seed + i), t0, dur) * (0.30 + i * 0.035)
    y += at(bar(520, 0.7, ratios=MEMBRANE['ratios'], t60=0.22, beta=1.5, gamma=0.8,
                mallet=2.2, velocity=2.0, seed=seed + 20), 1.52, dur) * 0.6
    y += at(gong(230, 2.6, gain=0.45, seed=seed + 25), 1.54, dur)
    y = chord_at(y, dur, 1.60, [65, 69, 72, 77], 0.7, seed=seed + 30)
    y = chord_at(y, dur, 2.10, [60, 64, 67, 72, 76], 1.0, seed=seed + 33)
    y += at(bar(N(72), 2.8, velocity=0.75, pos=0.30, seed=seed + 40, **TUBULAR), 2.12, dur) * 0.32
    for i, (t, m) in enumerate([(2.50, 91), (2.72, 96), (2.94, 100), (3.16, 103), (3.38, 108)]):
        y += at(bar(N(m), 1.3, velocity=0.6, pos=0.30, seed=seed + m, **GLOCK), t, dur) * (0.34 - i * 0.05)
    r = rng(seed + 7)
    for i in range(7):
        y += at(coin(seed + 70 + i, level=0.5) * float(r.uniform(0.3, 0.5)),
                2.60 + i * 0.145, dur)
    y = chord_at(y, dur, 4.00, [60, 64, 67, 72, 76], 0.85, seed=seed + 50)
    y += at(bar(N(60), 1.6, velocity=0.6, pos=0.30, seed=seed + 55, **CHIME), 4.02, dur) * 0.26
    y = compress(y, -21, 2.5, 6, 120)
    return finish_stereo(y, width=0.85, size=0.42, seed=1211, peak=0.93, tail_ms=50)


def epic_reveal(seed=1221):
    """Раскрытие: гонг и распахивающийся аккорд."""
    dur = 3.4
    y = pad_to(gong(260, 3.0, gain=0.7, seed=seed), dur)
    y = chord_at(y, dur, 0.28, [60, 67, 72, 76, 79], 0.95, seed=seed + 5)
    y += at(bar(N(72), 2.6, velocity=0.7, pos=0.30, seed=seed + 9, **TUBULAR), 0.30, dur) * 0.30
    for i, (t, m) in enumerate([(0.70, 91), (0.92, 96), (1.14, 103)]):
        y += at(bar(N(m), 1.2, velocity=0.58, pos=0.30, seed=seed + m, **GLOCK), t, dur) * (0.30 - i * 0.06)
    y = compress(y, -20, 2.4, 6, 110)
    return finish_stereo(y, width=0.85, size=0.42, seed=1221, peak=0.92, tail_ms=44)


def trophy(seed=1231):
    """Кубок: металл, аккорд, звон."""
    dur = 2.8
    y = pad_to(bar(880, 2.4, velocity=1.3, pos=0.33, seed=seed, **ANVIL), dur) * 0.55
    y = chord_at(y, dur, 0.16, [60, 64, 67, 72], 0.9, seed=seed + 4)
    y += at(bar(N(84), 2.2, velocity=0.7, pos=0.30, seed=seed + 8, **CHIME), 0.18, dur) * 0.34
    for i, (t, m) in enumerate([(0.56, 91), (0.76, 96)]):
        y += at(bar(N(m), 1.1, velocity=0.6, pos=0.30, seed=seed + m, **GLOCK), t, dur) * (0.28 - i * 0.06)
    y = compress(y, -20, 2.4, 6, 110)
    return finish_stereo(y, width=0.78, size=0.38, seed=1231, peak=0.90, tail_ms=36)


def crowd_cheer(seed=1241):
    """
    Овация: множество хлопков со случайными временами плюс общий гул.
    Регулярность — главный враг: как только хлопки становятся периодичными,
    толпа превращается в трещотку.
    """
    dur = 2.5
    n = int(dur * SR)
    y = np.zeros(n)
    r = rng(seed)
    for i in range(90):
        t0 = float(r.uniform(0, 1.9)) ** 0.75 * 1.9
        clap = bandpass(noise_burst(0.03, seed + i), 900, 4200, 2)
        clap = clap[:int(0.022 * SR)] * np.exp(-np.linspace(0, 5, int(0.022 * SR)))
        y += at(pad_to(clap, dur - t0), t0, dur) * float(r.uniform(0.25, 1.0))
    t = np.arange(n) / SR
    hum = bandpass(noise_burst(dur, seed + 300), 400, 2200, 2)[:n]
    hum *= np.clip(t / 0.25, 0, 1) * np.exp(-np.clip(t - 1.3, 0, None) * 1.8) * 0.35
    y = y * 0.55 + hum
    y = compress(y, -18, 3.0, 8, 140)
    return finish_stereo(y, width=0.9, size=0.40, seed=1241, hp=340,
                         mud=(600, -2.0), presence=(3000, -2.5), air=(9000, 0.5),
                         peak=0.86, tail_ms=40)


# ------------------------------------------------------------ ЕЩЁ КОРОТКИЕ

def micro_tick(seed=1301):
    dur = 0.045
    y = bar(3400, dur, ratios=[1, 2.41], t60=0.014, beta=1.2, gamma=0.7,
            mallet=6.0, velocity=0.5, pos=0.33, seed=seed)
    return finish(y, hp=1200, mud=None, presence=(5600, -2.5), air=(13000, -2.0),
                  room=0.02, size=0.07, damp=0.85, peak=0.26, tail_ms=4, seed=1301)


def micro_blip(seed=1311):
    dur = 0.08
    y = bar(N(96), dur, ratios=[1, 3.99], t60=0.035, beta=1.4, gamma=0.75,
            mallet=4.5, velocity=0.6, pos=0.30, seed=seed)
    return finish(y, hp=700, mud=None, presence=(4600, -2.5), air=(12000, 0.5),
                  room=0.05, size=0.11, damp=0.78, peak=0.40, tail_ms=6, seed=1311)


def focus_in(seed=1321):
    dur = 0.22
    y = bar(N(83), dur, ratios=[1, 3.99, 9.2], t60=0.11, beta=1.5, gamma=0.78,
            mallet=3.0, velocity=0.65, pos=0.30, seed=seed, tube=N(83), tube_mix=0.45)
    return finish(y, hp=420, mud=None, presence=(3400, -2.5), air=(9500, 1.0),
                  room=0.10, size=0.16, damp=0.72, peak=0.48, tail_ms=10, seed=1321)


def dismiss(seed=1331):
    dur = 0.26
    y = np.zeros(int(dur * SR))
    for i, (t0, m) in enumerate([(0.0, 83), (0.075, 76)]):
        y += at(bar(N(m), 0.24, ratios=[1, 3.99], t60=0.09, beta=1.6, gamma=0.82,
                    mallet=3.0, velocity=0.8 - i * 0.15, seed=seed + m), t0, dur) * (0.9 - i * 0.15)
    return finish(y, hp=380, mud=(520, -1.5), presence=(3200, -2.5),
                  room=0.11, size=0.18, damp=0.7, peak=0.56, tail_ms=10, seed=1331)


def swipe(seed=1341):
    """Свайп: короткий скребок и фиксация."""
    dur = 0.30
    y = pad_to(scrape(0.14, 7, 1700, 2600, gain=0.5, seed=seed, accel=0.8), dur)
    y += at(bar(1180, 0.18, ratios=[1, 2.41, 3.72], t60=0.05, beta=1.3, gamma=0.75,
                mallet=4.0, velocity=0.9, seed=seed + 5), 0.135, dur) * 0.85
    return finish(y, hp=520, mud=None, presence=(3800, -2.5), air=(11000, 0.5),
                  room=0.09, size=0.16, damp=0.72, peak=0.62, tail_ms=10, seed=1341)


def long_press(seed=1351):
    """Удержание: натяжение и фиксация в конце."""
    dur = 0.85
    n = int(0.62 * SR)
    t = np.arange(n) / SR
    p = t / t[-1]
    f = 520 * (1.5 ** p)
    ph = np.cumsum(2 * np.pi * f / SR)
    tone = (np.sin(ph) + 0.18 * np.sin(2 * ph)) * np.clip(t / 0.07, 0, 1) * (0.25 + 0.5 * p)
    y = pad_to(sweep_filter(tone, 900, 2200, q=1.1, kind='low')[:n], dur)
    y += at(bar(N(84), 0.4, velocity=1.0, pos=0.30, seed=seed, tube=N(84),
                tube_mix=0.5, **MARIMBA), 0.62, dur) * 0.9
    return finish(y, hp=340, mud=(500, -2.0), presence=(3000, -2.0), air=(9000, 1.0),
                  room=0.12, size=0.20, damp=0.7, peak=0.66, tail_ms=12, seed=1351)


def error_tiny(seed=1361):
    """Маленькая ошибка: одна приглушённая нота вниз."""
    dur = 0.28
    y = bar(N(74), dur, ratios=[1, 3.99, 9.2], t60=0.12, beta=1.9, gamma=0.84,
            mallet=2.6, velocity=0.8, pos=0.5, seed=seed, tube=N(74), tube_mix=0.4)
    y = lowpass(y, 6600, 2)
    return finish(y, hp=300, mud=(440, -2.0), presence=(2700, -2.0),
                  drive=1.1, room=0.10, size=0.18, damp=0.72, peak=0.58, tail_ms=12, seed=1361)


EXT_CATALOG = [
    ('Свистки', [
        ('whistle-bird',      'Птичья трель',      'Быстрые перегибы строя',            whistle_bird),
        ('whistle-train',     'Паровозный',        'Аккорд из четырёх труб',            whistle_train),
        ('whistle-referee',   'Судейский',         'Горошина даёт дрожь 38 Гц',         whistle_referee),
        ('whistle-boatswain', 'Боцманская дудка',  'Подъём, трель наверху, спад',       whistle_boatswain),
        ('whistle-two-tone',  'Двухтональный',     'Две ноты подряд',                   whistle_two_tone),
        ('whistle-pan',       'Панфлейта',         'Три ноты вверх, много дыхания',     whistle_pan),
        ('whistle-long',      'Длинное глиссандо', '520 Гц → 3.6 кГц за 1.5 с',         whistle_long),
        ('whistle-tiny',      'Свист-блик',        'Совсем короткий, 90 мс',            whistle_tiny),
    ]),
    ('Дерево', [
        ('wood-tap',        'Дерево',            'Вудблок 980 Гц + тело 392 Гц',        wood_tap),
        ('wood-hollow',     'Полое дерево',      'Темпл-блок 620 Гц',                   wood_hollow),
        ('wood-claves',     'Клавес',            'Плотное твёрдое дерево, 1.7 кГц',     wood_claves),
        ('wood-log',        'Лог-драм',          'Щелевой барабан 430 Гц',              wood_log),
        ('wood-guiro',      'Гуиро',             'Скребок по 16 рёбрам',                wood_guiro),
        ('wood-castanets',  'Кастаньеты',        'Тройной щелчок с зазором 32 мс',      wood_castanets),
        ('wood-bamboo',     'Бамбук',            'Девять трубок сталкиваются',          wood_bamboo),
        ('wood-knock',      'Стук в дверь',      'Три удара по толстой доске',          wood_knock),
    ]),
    ('Камень', [
        ('stone-tap',    'Камень',        'Моды 1:1.62:2.31, затухание 48 мс',       stone_tap),
        ('stone-pebble', 'Галька',        'Отскоки с сокращающимся интервалом',      stone_pebble),
        ('stone-marble', 'Мрамор',        'Катится и щёлкает о край',                stone_marble),
        ('stone-grind',  'Камень о камень','Плотный скребок без высоты',             stone_grind),
        ('stone-heavy',  'Тяжёлый валун', 'Гранит и мембрана, вес без суббаса',      stone_heavy),
    ]),
    ('Металл и стекло', [
        ('metal-chime',    'Колокольчик',  'Трубчатые моды, затухание 4.2 с',        metal_chime),
        ('metal-anvil',    'Наковальня',   'Негармоничный металл 1.24 кГц',          metal_anvil),
        ('metal-gong',     'Гонг',         'Энергия перетекает вверх после удара',   metal_gong),
        ('metal-triangle', 'Треугольник',  'Высокий кластер, длинный звон',          metal_triangle),
        ('glass-tap',      'Стекло',       'Стеклянные моды 1:2.02:3.05',            glass_tap),
        ('glass-ring',     'Бокал',        'Долгий тон с биениями',                  glass_ring),
    ]),
    ('Большие победы', [
        ('marathon-win', 'Месячный марафон', 'Семь секунд, пять фаз, гонг и медь',   marathon_win),
        ('grand-prize',  'Крутой приз',      'Ожидание, удар, раскрытие, каскад',    grand_prize),
        ('epic-reveal',  'Раскрытие',        'Гонг и распахивающийся аккорд',        epic_reveal),
        ('trophy',       'Кубок',            'Металл, аккорд, звон',                 trophy),
        ('crowd-cheer',  'Овация',           '90 хлопков со случайными временами',   crowd_cheer),
    ]),
    ('Микро', [
        ('micro-tick',  'Микротик',    'Самый тихий звук набора, 45 мс',   micro_tick),
        ('micro-blip',  'Блик',        'Короткая нота C7',                 micro_blip),
        ('focus-in',    'Фокус',       'Поле получило фокус',              focus_in),
        ('dismiss',     'Отмена',      'Две ноты вниз',                    dismiss),
        ('swipe',       'Свайп',       'Скребок и фиксация',               swipe),
        ('long-press',  'Удержание',   'Натяжение и фиксация в конце',     long_press),
        ('error-tiny',  'Мелкая ошибка','Одна приглушённая нота вниз',     error_tiny),
    ]),
]
