"""
CueLab v13 — офлайн-DSP.

Ключевое отличие от браузерного синтеза: здесь нет ограничений реального времени,
поэтому можно считать физику честно.

Главные приёмы, которых не хватало в v12:
  1. Модальный синтез как БАНК РЕЗОНАТОРОВ, возбуждаемых силой контакта,
     а не как сумма синусов с готовой огибающей. Это принципиально: реальная
     мода — затухающий осциллятор, которому передаётся импульс силы.
  2. Модель удара по Герцу: F = k·x^1.5. Ширина импульса силы зависит от
     скорости и жёсткости, поэтому сильный удар САМ получается ярче — связь
     «громче → ярче» возникает из физики, а не прописывается вручную.
  3. Частотно-зависимое затухание: высокие моды гаснут быстрее низких.
     Без этого любой модальный синтез звучит как электронный колокольчик.
  4. Позиция удара определяет, какие моды возбуждаются (узлы не звучат).
  5. Тело/резонатор и короткая комната — свёрткой.
"""
import numpy as np
from scipy import signal

SR = 48000


# ---------------------------------------------------------------- утилиты

def rng(seed):
    return np.random.default_rng(seed)


def silence(dur, sr=SR):
    return np.zeros(int(dur * sr))


def db(x):
    return 10 ** (x / 20)


def fade_out(x, ms=6.0, sr=SR):
    n = int(ms * sr / 1000)
    if n < 2 or n > len(x):
        return x
    x = x.copy()
    x[-n:] *= np.linspace(1, 0, n) ** 2
    return x


def pad_to(x, dur, sr=SR):
    n = int(dur * sr)
    if len(x) >= n:
        return x[:n]
    return np.concatenate([x, np.zeros(n - len(x))])


def mix(*layers):
    n = max(len(l) for l in layers)
    out = np.zeros(n)
    for l in layers:
        out[:len(l)] += l
    return out


def at(x, t, total=None, sr=SR):
    """Сдвинуть сигнал на t секунд."""
    n = int(t * sr)
    out = np.concatenate([np.zeros(n), x])
    if total is not None:
        out = pad_to(out, total, sr)
    return out


# ------------------------------------------------------- возбуждение (удар)

def hertz_contact(velocity=1.0, hardness=1.0, mass=1.0, sr=SR, roughness=0.08):
    """
    Импульс силы при ударе по модели Герца.

    Молоточек массы m летит со скоростью v, контакт нелинейный: F = k·x^1.5.
    Интегрируем численно. Результат: короткий импульс, чей спектр тем шире,
    чем выше скорость и жёсткость — ровно как у настоящего удара.
    """
    # Жёсткость калибрована так, чтобы hardness=1 давал ~3 мс (мягкая киянка),
    # hardness=3.5 — ~1 мс (резина), hardness=7 — ~0.5 мс (металл/стекло).
    # Время контакта по Герцу ~ k^(-2/5), поэтому k растёт как hardness^2.5.
    k = 2.5e7 * hardness ** 2.5
    dt = 1.0 / sr
    x = 0.0          # сжатие
    v = velocity     # скорость сближения
    out = []
    for _ in range(int(0.02 * sr)):
        f = k * max(x, 0.0) ** 1.5
        v -= f / mass * dt
        x += v * dt
        out.append(f)
        if x <= 0 and len(out) > 2:
            break
    f = np.array(out, dtype=float)
    if f.max() > 0:
        f /= f.max()
    # Шероховатость поверхности: реальный удар всегда добавляет широкополосный
    # призвук. Он должен возбуждать МОДЫ, а не подмешиваться отдельным слоем,
    # иначе щелчок живёт сам по себе и звучит наклеенным.
    if roughness > 0:
        r = rng(int(hardness * 1000) + len(f))
        f = f + r.standard_normal(len(f)) * f * roughness
    return f


def noise_burst(dur, seed, sr=SR, color=0.0):
    """Шум со случайным сдвигом — каждый вызов даёт РАЗНУЮ волну."""
    r = rng(seed)
    n = int(dur * sr)
    x = r.standard_normal(n)
    if color:      # color>0 — ярче (дифференцирование), <0 — темнее
        for _ in range(int(abs(color))):
            x = np.diff(x, prepend=0) if color > 0 else np.cumsum(x) / 8
    return x / (np.abs(x).max() + 1e-12)


# ------------------------------------------------------------- модальный банк

def modal(force, freqs, t60s, gains, sr=SR, detune=0.0, seed=1):
    """
    Банк резонаторов, возбуждаемых сигналом силы.

    Каждая мода — двухполюсный резонатор:
        y[k] = 2·e^(-αT)·cos(ωT)·y[k-1] − e^(-2αT)·y[k-2] + g·f[k]
    где α = 6.9078 / T60 (спад на 60 дБ).
    """
    r = rng(seed)
    n = len(force) + int(max(t60s) * sr * 1.2)
    src = np.concatenate([force, np.zeros(n - len(force))])
    out = np.zeros(n)
    for f0, t60, g in zip(freqs, t60s, gains):
        if f0 <= 0 or f0 >= sr / 2 * 0.95 or g <= 0:
            continue
        f = f0 * (1.0 + detune * r.standard_normal() * 0.01)
        alpha = 6.9078 / max(t60, 1e-3)
        w = 2 * np.pi * f / sr
        rr = np.exp(-alpha / sr)
        a = [1.0, -2 * rr * np.cos(w), rr * rr]
        b = [g * (1 - rr) * np.sin(w), 0.0, 0.0]
        out += signal.lfilter(b, a, src)
    return out


def damping_curve(f, f0, t60_base, beta=1.0, gamma=0.65):
    """Высокие моды гаснут быстрее — иначе звучит как синтезатор."""
    return t60_base / (1.0 + beta * (np.asarray(f) / f0) ** gamma)


def strike_gains(ratios, position=0.28, kind='bar'):
    """
    Амплитуда моды зависит от точки удара: в узле мода не возбуждается.
    Для стержня n-я мода ~ sin(n·π·x).
    """
    ratios = np.asarray(ratios, dtype=float)
    if kind == 'bar':
        idx = np.arange(1, len(ratios) + 1)
        g = np.abs(np.sin(idx * np.pi * position))
    else:
        g = np.ones(len(ratios))
    roll = 1.0 / (1.0 + 0.30 * np.arange(len(ratios)) ** 0.90)
    return g * roll


# ----------------------------------------------------------------- волновод

def waveguide(f0, dur, damping=0.35, brightness=0.55, seed=1, sr=SR,
              pluck_pos=0.28, excite=None):
    """
    Струна как цифровой волновод: линия задержки + фильтр потерь + всепропускающий
    фильтр дробной задержки. Дробная задержка обязательна — без неё строй
    квантуется по целым сэмплам и всё, что выше примерно 500 Гц, детонирует.
    """
    r = rng(seed)
    total = int(dur * sr)
    b = float(np.clip(brightness, 0.05, 0.95))
    # Полная задержка петли складывается из линии, фазовой задержки фильтра
    # потерь и дробной задержки allpass. Если не вычесть задержку фильтра,
    # строй уходит вверх по частоте тем сильнее, чем короче линия.
    delay = sr / float(f0)
    d_lp = (1.0 - b) / b                       # групповая задержка однополюсника
    n_int = int(np.floor(delay - d_lp - 0.5))
    if n_int < 3:
        return np.zeros(total)
    d_ap = delay - d_lp - n_int                # остаток на allpass, ~0.5…1.5
    eta = (1.0 - d_ap) / (1.0 + d_ap)

    # начальное состояние: щипок в точке pluck_pos + немного шума медиатора
    idx = np.arange(n_int) / n_int
    shape = np.minimum(idx / pluck_pos, (1 - idx) / max(1e-6, 1 - pluck_pos))
    buf = shape * 0.75 + r.standard_normal(n_int) * 0.25
    buf -= buf.mean()
    if excite is not None:
        m = min(len(excite), n_int)
        buf[:m] += excite[:m]

    loss = np.exp(-np.pi * f0 * damping / (sr * 6.0))

    out = np.zeros(total)
    lp = 0.0        # состояние однополюсного фильтра потерь
    ap_x = 0.0      # вход allpass на предыдущем шаге
    ap_y = 0.0      # выход allpass на предыдущем шаге
    pos = 0
    for i in range(total):
        s_in = buf[pos]
        out[i] = s_in
        lp = b * s_in + (1.0 - b) * lp                  # демпфирование
        v = lp * loss
        ap_y = eta * v + ap_x - eta * ap_y              # дробная задержка
        ap_x = v
        buf[pos] = ap_y
        pos += 1
        if pos >= n_int:
            pos = 0
    return out


# ------------------------------------------------------------------ фильтры

def biquad(x, kind, f, q=0.707, gain_db=0.0, sr=SR):
    f = np.clip(f, 20, sr / 2 * 0.98)
    if kind in ('peak', 'lowshelf', 'highshelf'):
        b, a = _shelf(kind, f, q, gain_db, sr)
    else:
        b, a = signal.butter(2, f / (sr / 2), btype=kind) if kind in ('low', 'high') else \
               signal.iirpeak(f / (sr / 2), q)
    return signal.lfilter(b, a, x)


def _shelf(kind, f, q, gain_db, sr):
    A = 10 ** (gain_db / 40)
    w = 2 * np.pi * f / sr
    alpha = np.sin(w) / (2 * q)
    c = np.cos(w)
    if kind == 'peak':
        b = [1 + alpha * A, -2 * c, 1 - alpha * A]
        a = [1 + alpha / A, -2 * c, 1 - alpha / A]
    elif kind == 'lowshelf':
        s = 2 * np.sqrt(A) * alpha
        b = [A * ((A + 1) - (A - 1) * c + s), 2 * A * ((A - 1) - (A + 1) * c), A * ((A + 1) - (A - 1) * c - s)]
        a = [(A + 1) + (A - 1) * c + s, -2 * ((A - 1) + (A + 1) * c), (A + 1) + (A - 1) * c - s]
    else:
        s = 2 * np.sqrt(A) * alpha
        b = [A * ((A + 1) + (A - 1) * c + s), -2 * A * ((A - 1) + (A + 1) * c), A * ((A + 1) + (A - 1) * c - s)]
        a = [(A + 1) - (A - 1) * c + s, 2 * ((A - 1) - (A + 1) * c), (A + 1) - (A - 1) * c - s]
    return np.array(b) / a[0], np.array(a) / a[0]


def lowpass(x, f, order=4, sr=SR):
    b, a = signal.butter(order, np.clip(f, 20, sr / 2 * 0.98) / (sr / 2), btype='low')
    return signal.lfilter(b, a, x)


def highpass(x, f, order=2, sr=SR):
    b, a = signal.butter(order, np.clip(f, 10, sr / 2 * 0.98) / (sr / 2), btype='high')
    return signal.lfilter(b, a, x)


def bandpass(x, lo, hi, order=2, sr=SR):
    lo = np.clip(lo, 15, sr / 2 * 0.9)
    hi = np.clip(hi, lo * 1.05, sr / 2 * 0.97)
    b, a = signal.butter(order, [lo / (sr / 2), hi / (sr / 2)], btype='band')
    return signal.lfilter(b, a, x)


def resonator(x, f, q=8.0, sr=SR):
    b, a = signal.iirpeak(np.clip(f, 30, sr / 2 * 0.95) / (sr / 2), q)
    return signal.lfilter(b, a, x)


def sweep_filter(x, f_start, f_end, q=1.0, kind='band', sr=SR, blocks=96):
    """Плавно движущийся фильтр — форманты рта, открывающийся фильтр меди."""
    n = len(x)
    step = max(64, n // blocks)
    out = np.zeros(n)
    win = np.hanning(step * 2)
    for i in range(0, n, step):
        seg = x[max(0, i - step // 2): i + step + step // 2]
        if len(seg) < 8:
            continue
        p = i / max(1, n)
        f = f_start * (f_end / f_start) ** p
        if kind == 'band':
            y = resonator(seg, f, q)
        else:
            y = lowpass(seg, f)
        s = max(0, i - step // 2)
        seg_out = y[:len(seg)]
        w = np.ones(len(seg_out))
        fade = min(step // 2, len(seg_out) // 2)
        if fade > 1:
            w[:fade] = np.linspace(0, 1, fade)
            w[-fade:] = np.linspace(1, 0, fade)
        out[s:s + len(seg_out)] += seg_out * w
    return out


# ------------------------------------------------------- нелинейности, динамика

def saturate(x, drive=1.6):
    return np.tanh(x * drive) / np.tanh(drive)


def soft_limit(x, ceiling=0.94):
    peak = np.abs(x).max()
    if peak <= 1e-9:
        return x
    x = x / peak
    x = np.tanh(x * 1.35) / np.tanh(1.35)
    return x * ceiling


def compress(x, thresh_db=-18, ratio=3.0, attack_ms=3, release_ms=80, sr=SR):
    env = np.abs(signal.lfilter([1], [1, -np.exp(-1 / (0.001 * attack_ms * sr))], np.abs(x)))
    env /= (env.max() + 1e-12)
    env_db = 20 * np.log10(env + 1e-9)
    over = np.maximum(0, env_db - thresh_db)
    gain_db = -over * (1 - 1 / ratio)
    rel = np.exp(-1 / (0.001 * release_ms * sr))
    smoothed = signal.lfilter([1 - rel], [1, -rel], gain_db)
    return x * 10 ** (smoothed / 20)


def normalize(x, peak=0.9):
    m = np.abs(x).max()
    return x if m < 1e-9 else x / m * peak


# ---------------------------------------------------------------- пространство

_IR_CACHE = {}


def room_ir(size=0.22, damp=0.55, seed=7, sr=SR):
    """
    Комната на «бархатном шуме»: сотни случайно расставленных импульсов
    со случайным знаком, плотность и амплитуда падают экспоненциально.

    Прошлая версия использовала пять фиксированных ранних отражений с большими
    амплитудами. Такой отклик — это гребенчатый фильтр: его собственный спектр
    имел выраженные пики на 51/201/394/472/785 Гц, и он отпечатывался на КАЖДОМ
    звуке библиотеки. Из-за этого все звуки получали одну и ту же паразитную
    окраску и звучали как варианты одного тембра.
    """
    key = (round(size, 3), round(damp, 3), seed)
    if key in _IR_CACHE:
        return _IR_CACHE[key]
    r = rng(seed * 977 + 13)
    n = int(size * sr)
    t = np.arange(n) / sr
    ir = np.zeros(n)

    # бархатный шум: ~3500 импульсов в секунду, положение внутри ячейки случайно
    density = 3500
    cell = max(2, int(sr / density))
    for start_i in range(0, n, cell):
        k = start_i + int(r.integers(0, cell))
        if k >= n:
            break
        decay = np.exp(-6.9 * (k / sr) / max(size * 0.55, 1e-3))
        ir[k] += (1.0 if r.random() < 0.5 else -1.0) * decay

    # высокие частоты в комнате гаснут быстрее низких
    hi = highpass(ir, 2200, 2) * np.exp(-t / max(size * 0.16, 1e-3))
    lo = lowpass(ir, 2200, 2)
    ir = lo * (0.55 + 0.45 * damp) + hi * (1.0 - damp * 0.6)

    ir[:6] = 0.0                      # прямой звук добавляется отдельно, сухим
    ir = ir / (np.abs(ir).max() + 1e-12)
    _IR_CACHE[key] = ir
    return ir


def space(x, amount=0.16, size=0.22, damp=0.55, seed=7, sr=SR):
    """
    Сухой сигнал плюс диффузный хвост. seed разный у разных звуков, чтобы
    комната не оставляла на всех один и тот же отпечаток.
    """
    if amount <= 0:
        return x
    ir = room_ir(size, damp, seed=seed, sr=sr)
    wet = signal.fftconvolve(x, ir)
    wet = wet / (np.abs(wet).max() + 1e-12) * (np.abs(x).max() + 1e-12)
    dry = np.concatenate([x, np.zeros(len(wet) - len(x))])
    return dry + wet * amount


def stereo(left, right=None, width=0.0):
    if right is None:
        right = left
    n = max(len(left), len(right))
    l = pad_to(left, n / SR)
    r = pad_to(right, n / SR)
    if width:
        d = int(abs(width) * 0.0009 * SR)
        if d > 0:
            if width > 0:
                r = np.concatenate([np.zeros(d), r])[:n]
            else:
                l = np.concatenate([np.zeros(d), l])[:n]
    return np.stack([l, r], axis=1)


# ============================================================================
#  Инструменты, добавленные в v13.1 для победных сцен
# ============================================================================

def brass_tone(f0, dur, gain=1.0, bright=1.0, attack=0.045, seed=1, sr=SR):
    """
    Медь по схеме «источник-фильтр»: пилообразный источник с лёгким джиттером
    строя и фильтр, который РАСКРЫВАЕТСЯ на атаке. Именно раскрытие фильтра,
    а не громкость, читается ухом как «дунули сильнее».
    """
    n = int(dur * sr)
    t = np.arange(n) / sr
    r = rng(seed)
    src = np.zeros(n)
    for det in (-7.0, 0.0, 6.0):
        drift = np.cumsum(r.standard_normal(n)) * 2.5e-5
        drift -= drift.mean()
        f = f0 * 2 ** (det / 1200.0) * (1 + drift)
        ph = np.cumsum(2 * np.pi * f / sr)
        src += signal.sawtooth(ph) / 3.0
    # вибрато появляется только на длинных нотах, как у живого духовика
    if dur > 0.5:
        vib = 1 + 0.004 * np.sin(2 * np.pi * 5.2 * t) * np.clip((t - 0.22) / 0.3, 0, 1)
        src *= vib
    open_f = f0 * 1.6 * np.ones(n)
    ramp = np.clip(t / max(attack, 1e-3), 0, 1)
    # Наклон гармоник калиброван замером: у живой меди примерно -6…-9 дБ/окт.
    open_f = f0 * (2.2 + 14.0 * bright * ramp * np.exp(-np.clip(t - attack * 2, 0, None) * 1.2))
    out = sweep_filter(src, float(open_f[0]), float(np.percentile(open_f, 88)), q=1.4, kind='low')[:n]
    env = np.clip(t / max(attack, 1e-3), 0, 1) ** 1.5
    env *= np.exp(-np.clip(t - dur * 0.55, 0, None) * 5.0)
    out = out * env * gain
    return saturate(out * 1.4, 1.8)


def harp_note(f0, dur, gain=1.0, seed=1, bright=0.62, sr=SR):
    """Арфа: волновод со слабым демпфированием и мягким медиатором."""
    y = waveguide(f0, dur, damping=0.16, brightness=bright, seed=seed, pluck_pos=0.22)
    t = np.arange(len(y)) / sr
    y = y * np.exp(-t / max(dur * 0.42, 1e-3)) * gain
    return lowpass(y, 6500, 2)


def stereo_pair(y, width=1.0, size=0.30, damp=0.5, seed=7, amount=0.30, sr=SR):
    """
    Стерео для длинных сцен. Ширину даёт ТОЛЬКО декорреляция хвоста: сухой
    сигнал в обоих каналах одинаков, поэтому разводить надо два независимых
    диффузных отклика, а не крутить M/S у почти одинаковой пары — иначе
    корреляция остаётся 0.99 и стерео существует лишь на бумаге.
    Сумма в моно не страдает: сухой центр не трогаем.
    """
    ir_l = room_ir(size, damp, seed=seed, sr=sr)
    ir_r = room_ir(size * 1.07, damp, seed=seed + 991, sr=sr)
    n = len(y) + max(len(ir_l), len(ir_r))
    dry = pad_to(y, n / sr, sr)
    peak = np.abs(y).max() + 1e-12
    wl = pad_to(signal.fftconvolve(y, ir_l), n / sr, sr)
    wr = pad_to(signal.fftconvolve(y, ir_r), n / sr, sr)
    wl = wl / (np.abs(wl).max() + 1e-12) * peak
    wr = wr / (np.abs(wr).max() + 1e-12) * peak
    return np.stack([dry + wl * amount * width, dry + wr * amount * width], axis=1)
