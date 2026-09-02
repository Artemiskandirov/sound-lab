"""
Рендер библиотеки: варианты, стерео для сцен, хаптик из аудио,
WAV -> Opus + AAC, манифест.
"""
import json
import os
import zlib
import subprocess
import wave

import numpy as np

import haptics
import sounds
import sounds_ext
from check import profile
from dsp import SR, normalize

OUT = '../cuelab-production-v13/audio'
os.makedirs(OUT, exist_ok=True)

CATALOG = sounds.CATALOG + sounds_ext.EXT_CATALOG
REGISTRY = {sid: fn for _, items in CATALOG for sid, _, _, fn in items}

# Чем чаще звук повторяется подряд, тем больше нужно вариантов: одинаковость
# повторов выдаёт синтетику первой. Тик прокрутки — рекордсмен по повторам.
VARIANTS = {
    'scroll-tick': 10, 'micro-tick': 8, 'scroll-detent': 6, 'progress-step': 6,
    'key': 6, 'tap': 6, 'coin': 5, 'scroll-snap': 4, 'tap-soft': 4, 'tap-heavy': 4,
    'answer-select': 4, 'tab-switch': 4, 'micro-blip': 4, 'focus-in': 4,
    'wood-tap': 4, 'wood-claves': 4, 'stone-tap': 4, 'stone-pebble': 3,
    'glass-tap': 3, 'swipe': 3, 'dismiss': 3, 'error-tiny': 3,
    'message-send': 3, 'message-receive': 3, 'wood-hollow': 3, 'whistle-tiny': 4,
}
DEFAULT_VARIANTS = 3

# Длинные сцены композиционно уникальны — вариант там не нужен.
SINGLE = {'lesson', 'victory-big', 'perfect', 'unit-complete', 'coin-rain',
          'chest-open', 'marathon-win', 'grand-prize', 'epic-reveal',
          'crowd-cheer', 'metal-gong', 'whistle-train', 'whistle-boatswain'}

# Разброс высоты между вариантами, полутоны. Для повторяющихся звуков он
# важнее всего: без него быстрая прокрутка звучит как очередь из пулемёта.
PITCH_SPREAD = {
    'scroll-tick': 1.6, 'micro-tick': 1.8, 'scroll-detent': 1.0, 'key': 0.8,
    'tap': 0.5, 'coin': 0.7, 'scroll-snap': 0.6, 'wood-tap': 0.9,
    'wood-claves': 0.9, 'stone-tap': 1.1, 'glass-tap': 0.8, 'micro-blip': 1.2,
    'whistle-tiny': 1.4, 'tab-switch': 0.6, 'answer-select': 0.5, 'focus-in': 0.6,
}


def write_wav(path, y, sr=SR):
    y = np.asarray(y)
    channels = 2 if y.ndim == 2 else 1
    data = (np.clip(y, -1, 1) * 32767).astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())


def encode(src, base, bitrate):
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', src, '-c:a', 'libopus',
                    '-b:a', bitrate, '-vbr', 'on', '-application', 'audio',
                    base + '.ogg'], check=True)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', src, '-c:a', 'aac',
                    '-b:a', bitrate, '-movflags', '+faststart',
                    base + '.m4a'], check=True)
    return os.path.getsize(base + '.ogg'), os.path.getsize(base + '.m4a')


def trim(y, floor_db=-62, tail_ms=12, sr=SR):
    """
    Обрезка хвоста ниже порога слышимости. После ревербератора 40% библиотеки
    было тишиной: она ничего не добавляет, но занимает место.
    """
    mono = y.mean(axis=1) if y.ndim == 2 else y
    env = np.abs(mono)
    peak = env.max()
    if peak <= 0:
        return y
    live = np.where(env > peak * 10 ** (floor_db / 20))[0]
    if not len(live):
        return y
    end = min(len(mono), live[-1] + int(tail_ms * sr / 1000) + 1)
    start = max(0, live[0] - int(2 * sr / 1000))
    out = y[start:end].copy()
    n = int(tail_ms * sr / 1000)
    if 2 < n < len(out):
        ramp = np.linspace(1, 0, n) ** 2
        out[-n:] = out[-n:] * (ramp[:, None] if out.ndim == 2 else ramp)
    return out


def render_variant(sid, index):
    """Вариант — это другой сид возбуждения плюс микро-расстройка."""
    # crc32, а не встроенный hash(): hash() для строк рандомизируется между
    # запусками (PYTHONHASHSEED), поэтому рендер был невоспроизводим — три
    # запуска давали три разных звука, и хаптики считались не из того аудио,
    # которое лежало в приложении.
    seed = 1300 + index * 41 + (zlib.crc32(sid.encode('utf-8')) % 400)
    fn = REGISTRY[sid]
    try:
        y = fn(seed) if index else fn()
    except TypeError:
        y = fn()
    y = np.asarray(y)
    spread = PITCH_SPREAD.get(sid, 0.0)
    if spread and index:
        r = np.random.default_rng(seed)
        rate = 2 ** (float(r.uniform(-spread, spread)) / 12.0)
        n = int(len(y) / rate)
        idx = np.clip(np.arange(n) * rate, 0, len(y) - 1.001)
        lo = idx.astype(int)
        frac = (idx - lo)[:, None] if y.ndim == 2 else (idx - lo)
        y = y[lo] * (1 - frac) + y[lo + 1] * frac
    return normalize(trim(y), 0.9)


def main():
    manifest, total = [], 0
    for category, items in CATALOG:
        for sid, title, note, _ in items:
            count = 1 if sid in SINGLE else VARIANTS.get(sid, DEFAULT_VARIANTS)
            files, first = [], None
            for i in range(count):
                y = render_variant(sid, i)
                if first is None:
                    first = y
                wav = f'/tmp/{sid}-{i}.wav'
                write_wav(wav, y)
                base = f'{OUT}/{sid}-{i}'
                seconds = len(y) / SR
                # Битрейты выверены round-trip замером: у короткого звука на
                # 56k Opus центроид 1638 Гц против 1650 в оригинале — разница
                # неразличима, а на 40k тембр уже заметно темнеет.
                stereo = y.ndim == 2
                rate = '56k' if seconds < 0.35 else '72k' if seconds < 1.2 else '96k'
                if stereo:
                    rate = '96k' if seconds < 1.2 else '112k'
                ogg, m4a = encode(wav, base, rate)
                total += ogg + m4a
                files.append({'opus': f'audio/{sid}-{i}.ogg',
                              'aac': f'audio/{sid}-{i}.m4a', 'bytes': ogg})
                os.remove(wav)
            mono = first.mean(axis=1) if first.ndim == 2 else first
            p = profile(mono)
            # Хаптик выводится из самой волны, поэтому импульсы стоят ровно
            # там, где в звуке события — и совпадение гарантировано для
            # любого нового звука без ручной работы.
            pat = haptics.pattern(first)
            hap_ms, sound_ms = haptics.coverage(first, pat)
            manifest.append({
                'id': sid, 'title': title, 'note': note, 'category': category,
                'variants': files, 'stereo': bool(first.ndim == 2),
                'durationMs': round(len(first) / SR * 1000),
                'centroidHz': round(p['centroid']), 'lowPct': round(p['low'] * 100, 1),
                'midPct': round(p['mid'] * 100, 1), 'flatness': round(p['flat'], 3),
                'haptic': pat,
                'hapticPulses': haptics.pulses(pat),
                'hapticMs': int(hap_ms),
            })
        print(f'{category:22s} {len(items):3d} звуков')
    with open('../cuelab-production-v13/sounds.json', 'w', encoding='utf-8') as f:
        json.dump({'sampleRate': SR, 'sounds': manifest}, f, ensure_ascii=False, indent=1)
    files = sum(len(m['variants']) for m in manifest)
    pulses = sum(m['hapticPulses'] for m in manifest)
    print(f'\n{len(manifest)} звуков, {files} вариантов, {total / 1024:.0f} КБ в двух форматах')
    print(f'хаптик-паттернов {len(manifest)}, суммарно {pulses} импульсов, все выведены из аудио')


if __name__ == '__main__':
    main()
