"""
Привязка вибро к спектру звука, а не только к его громкости.

До сих пор паттерн строился по широкополосной огибающей RMS: громче — плотнее
щелчки. Это давало форму, но не давало РАЗНИЦЫ между звуками. Стекло и бревно
одинаковой громкости ощущались одинаково, хотя слышатся совершенно по-разному.

Два места, где спектр должен участвовать.

1. ГРОМКОСТЬ. RMS считает энергию, а ухо слышит громкость: на 3 кГц оно
   чувствительнее, чем на 200 Гц, примерно на 10 дБ. Наши звуки специально
   посажены в 400 Гц – 6 кГц (динамики телефонов ниже 400 Гц заваливают), и
   при подсчёте по энергии тихий, но звонкий хвост проваливается, хотя его
   отлично слышно. Поэтому огибающая считается по сигналу, взвешенному
   кривой A — стандартным приближением равногромкости.

2. ХАРАКТЕР. В движке web-haptics ровно один управляющий параметр — intensity,
   и он же задаёт частоту щелчков: 16 + (1 - intensity) * 184 мс. Частота
   щелчков читается рукой как ЗЕРНО: 16–25 мс — гладкий тонкий гул, 60–120 мс —
   крупная шероховатость. Это прямой аналог яркости звука. Поэтому
   спектральный центроид на каждом кадре подмешивается в силу: звонкое
   (стекло, треугольник, свисток) ощущается мелким и гладким, глухое (бревно,
   мембрана, камень) — крупным и шершавым.

Так один рычаг несёт обе величины: уровень задаёт основу, яркость — поправку.
"""
import numpy as np

FRAME_MS = 32.0


def a_weight(freqs):
    """
    Кривая A: приближение равногромкости, IEC 61672.
    Приводит энергию спектра к тому, как её слышно.
    """
    f2 = freqs ** 2
    num = (12194.0 ** 2) * (f2 ** 2)
    den = ((f2 + 20.6 ** 2)
           * np.sqrt((f2 + 107.7 ** 2) * (f2 + 737.9 ** 2))
           * (f2 + 12194.0 ** 2))
    with np.errstate(divide='ignore', invalid='ignore'):
        ra = np.where(den > 0, num / den, 0.0)
    return ra * (10.0 ** (2.0 / 20.0))     # нормировка: +2 дБ, единица на 1 кГц


def weighted(y, sr):
    """Сигнал, взвешенный кривой A, — основа для огибающей громкости."""
    mono = y.mean(axis=1) if y.ndim == 2 else y
    spec = np.fft.rfft(mono)
    gain = a_weight(np.fft.rfftfreq(len(mono), 1.0 / sr))
    return np.fft.irfft(spec * gain, n=len(mono))


def frames(y, sr, frame_ms=FRAME_MS):
    hop = max(1, int(frame_ms / 1000 * sr))
    n = max(1, len(y) // hop)
    return hop, n


def loudness_env(y, sr, frame_ms=FRAME_MS, floor_db=-48.0):
    """Огибающая громкости 0..1 по кадрам, в децибелах относительно пика."""
    w = weighted(y, sr)
    hop, n = frames(w, sr, frame_ms)
    env = np.array([np.sqrt((w[i * hop:(i + 1) * hop] ** 2).mean() + 1e-12)
                    for i in range(n)])
    peak = env.max()
    if peak <= 0:
        return np.zeros(n)
    db = 20 * np.log10(env / peak + 1e-9)
    return np.clip((db - floor_db) / (0.0 - floor_db), 0.0, 1.0)


def brightness(y, sr, frame_ms=FRAME_MS, lo=300.0, hi=8000.0):
    """
    Яркость 0..1 по кадрам: спектральный центроид, отображённый логарифмически
    из полосы 300 Гц – 8 кГц. Тихие кадры наследуют яркость предыдущего, иначе
    в хвостах центроид пляшет по шуму.
    """
    mono = y.mean(axis=1) if y.ndim == 2 else y
    hop, n = frames(mono, sr, frame_ms)
    # Окно только на спаде. Полное окно Ханна обнуляет начало кадра, а именно
    # там сидит атака: у тяжёлого валуна центроид всего звука уезжал с 990 Гц
    # до 2850, потому что окно съедало низкий удар и оставляло звонкий хвост.
    win = np.ones(hop)
    if hop > 2:
        half = np.hanning(hop)
        win[hop // 2:] = half[hop // 2:]
    out = np.zeros(n)
    amp = np.abs(mono)
    gate = amp.max() * 0.005

    def norm(centroid):
        centroid = min(max(centroid, lo), hi)
        return float(np.log(centroid / lo) / np.log(hi / lo))

    def centroid_of(chunk, window):
        # Взвешивание по МОЩНОСТИ, а не по амплитуде. По амплитуде центроид
        # уезжает вверх на всём, где есть широкополосный шум: у рёва динозавра
        # он давал 5 кГц против измеренных 1179 Гц, и рёв оказывался «звонче»
        # свистка.
        power = np.abs(np.fft.rfft(chunk * window)) ** 2
        total = power.sum()
        return float((np.fft.rfftfreq(len(chunk), 1.0 / sr) * power).sum() / total) if total > 0 else 0.0

    # Запасное значение — центроид всего звука: у сигналов короче кадра
    # (микротик, тик прокрутки) кадровых окон просто нет.
    whole = centroid_of(mono, np.ones(len(mono)))
    last = norm(whole) if whole > 0 else 0.5

    for i in range(n):
        chunk = mono[i * hop:i * hop + hop]
        if len(chunk) < hop or np.abs(chunk).max() < gate:
            out[i] = last
            continue
        c = centroid_of(chunk, win)
        if c <= 0:
            out[i] = last
            continue
        last = norm(c)
        out[i] = last
    return out


SEG_FLOOR = 0.06      # тише этого — пауза, а не вибрация
SEG_CURVE = 0.4       # уровень -> сила: тихое подтягивается вверх
SEG_QUANT = 0.125     # шаг квантования силы
SEG_SMOOTH = 3        # кадров скользящего максимума: убирает дрожь огибающей
SEG_MAX_MS = 240      # дольше этого отрезок не тянем: сила должна пересчитываться
BRIGHT_LOW = 0.78     # множитель силы у самого глухого звука
BRIGHT_SPAN = 0.30    # добавка у самого звонкого
ATTACK_RISE = 0.12    # скачок уровня, который считаем атакой
ACCENT = 0.22         # добавка силы на атаке
ARTICULATION_MS = 24  # пауза перед атакой: без неё удары сливаются в гул
ARTICULATION_GAP_MS = 110  # чаще этого паузы не ставим: трель не должна заикаться
MIN_SEG_MS = 16       # короче этого отрезок не оставляем


def intensity_track(level, bright, onsets=None):
    """
    Уровень и яркость -> сила (она же частота щелчков).

    Яркость входит множителем: глухое получает 0,78 от силы, звонкое — до 1,08
    с обрезкой по единице. При уровне 0,5 глухое даёт щелчок раз в ~62 мс
    (крупное зерно), звонкое — раз в ~26 мс (мелкое, гладкое).

    На атаке сила подскакивает, и тем сильнее, чем звонче звук: у стекла
    транзиент должен читаться иглой, у бревна — тупым толчком.
    """
    base = np.power(np.clip(level, 0.0, 1.0), SEG_CURVE)
    out = base * (BRIGHT_LOW + BRIGHT_SPAN * np.clip(bright, 0.0, 1.0))
    mark = np.diff(np.clip(level, 0.0, 1.0), prepend=0.0) > ATTACK_RISE
    if onsets is not None:
        mark = mark | np.asarray(onsets, dtype=bool)
    out[mark] += ACCENT * (0.6 + 0.4 * np.clip(bright[mark], 0.0, 1.0))
    return np.clip(out, 0.0, 1.0)


def segments(level, bright, step_ms=FRAME_MS, max_ms=6000, onset_ms=()):
    """
    Дорожки -> паттерн web-haptics: [{delay, duration, intensity}, ...].

    Длинный звук нельзя отдавать одной плитой постоянной силы. Замер по
    библиотеке показал, что до правки длинные сцены проводили от 27% до 95%
    времени внутри одного отрезка длиннее 300 мс, и из 373 атак вибрация
    отмечала 106 — остальное сливалось в ровный гул. Поэтому:

    * отрезок не длиннее 240 мс — сила пересчитывается по ходу сцены;
    * на каждой атаке принудительная граница отрезка и добавка к силе;
    * перед атакой откусывается 24 мс паузы от предыдущего отрезка. Пауза
      обязательна: без разрыва два соседних отрезка играются встык и удар не
      читается как удар. Время при этом не съезжает — пауза берётся из
      предыдущего отрезка, а не добавляется.
    """
    lvl = np.array([level[max(0, i - SEG_SMOOTH + 1):i + 1].max()
                    for i in range(len(level))])
    n = len(lvl)
    onset_frames = np.zeros(n, dtype=bool)
    for t in onset_ms:
        idx = int(round(t / step_ms))
        if 0 <= idx < n:
            onset_frames[idx] = True
    force = intensity_track(lvl, np.asarray(bright), onset_frames)

    out = []
    pending = 0.0
    i = 0
    last_gap_ms = -1e9
    while i < n and i * step_ms < max_ms:
        if lvl[i] < SEG_FLOOR:
            pending += step_ms
            i += 1
            continue
        started_on_attack = bool(onset_frames[i])
        q = round(float(force[i]) / SEG_QUANT)
        acc = []
        j = i
        while (j < n and lvl[j] >= SEG_FLOOR
               and round(float(force[j]) / SEG_QUANT) == q
               and (j - i) * step_ms < SEG_MAX_MS
               and not (j > i and onset_frames[j])):
            acc.append(float(force[j]))
            j += 1
        duration = int((j - i) * step_ms)
        # пауза перед ударом: откусываем от предыдущего отрезка
        # Пауза ставится не чаще чем раз в 110 мс. У судейского свистка трель
        # даёт атаку каждые ~68 мс, и разрыв на каждой превращал ровный свист
        # в заикание. Частые атаки всё равно ломают отрезок и получают добавку
        # к силе — просто без разрыва.
        at_ms = i * step_ms
        if (started_on_attack and pending == 0 and out
                and at_ms - last_gap_ms >= ARTICULATION_GAP_MS
                and out[-1]['duration'] > ARTICULATION_MS + MIN_SEG_MS):
            out[-1]['duration'] -= ARTICULATION_MS
            pending = ARTICULATION_MS
            last_gap_ms = at_ms
        item = {'duration': duration,
                'intensity': round(min(1.0, max(0.2, sum(acc) / len(acc))), 2)}
        if pending > 0:
            item['delay'] = int(pending)
        out.append(item)
        pending = 0.0
        i = j
    return out or [{'duration': 25, 'intensity': 0.7}]
