import numpy as np
from dsp import SR

def profile(y, sr=SR):
    N = len(y)
    sp = np.abs(np.fft.rfft(y)) ** 2
    fr = np.fft.rfftfreq(N, 1 / sr)
    tot = sp.sum() + 1e-20
    centroid = float((fr * sp).sum() / tot)
    low = float(sp[fr < 300].sum() / tot)
    mid = float(sp[(fr >= 400) & (fr < 6000)].sum() / tot)
    air = float(sp[fr >= 6000].sum() / tot)
    # Спектральная плоскостность (энтропия Винера): 0 — чистый тон,
    # 1 — белый шум. Позволяет отличить звенящее тело от шипения.
    band = sp[(fr >= 300) & (fr < 12000)] + 1e-16
    flat = float(np.exp(np.log(band).mean()) / band.mean())
    # длительность до -40 дБ от пика
    env = np.abs(y)
    pk = env.max() + 1e-12
    idx = np.where(env > pk * 0.01)[0]
    dur = (idx[-1] - idx[0]) / sr if len(idx) else 0.0
    return dict(centroid=centroid, low=low, mid=mid, air=air, dur=dur,
                flat=flat, peak=float(pk))

LIMITS = dict(centroid=(700, 4200), low=(0.0, 0.18), mid=(0.45, 1.0), flat=(0.0, 0.14))

def report(items):
    print(f'{"звук":14s}{"центроид":>10s}{"<300Гц":>9s}{"400–6к":>9s}{"шумность":>10s}{"длит":>8s}  вердикт')
    bad = []
    for name, y in items:
        p = profile(y)
        flags = []
        if not (LIMITS['centroid'][0] <= p['centroid'] <= LIMITS['centroid'][1]):
            flags.append('центроид')
        if p['low'] > LIMITS['low'][1]:
            flags.append('суббас')
        if p['mid'] < LIMITS['mid'][0]:
            flags.append('нет мидов')
        # Порог тональности зависит от длительности: в звуке короче 25 мс
        # физически не помещается достаточно периодов, чтобы он читался как
        # тон. Требовать от детента прокрутки тональности бруска — ошибка
        # метрики, а не звука.
        flat_limit = LIMITS['flat'][1] * (2.0 if p['dur'] < 0.025 else 1.0)
        if p['flat'] > flat_limit:
            flags.append('шум вместо тела')
        verdict = 'ок' if not flags else '! ' + ', '.join(flags)
        if flags:
            bad.append(name)
        print(f'{name:14s}{p["centroid"]:9.0f}Гц{p["low"]*100:8.1f}%{p["mid"]*100:8.1f}%{p["flat"]:10.3f}{p["dur"]*1000:7.0f}мс  {verdict}')
    print(f'\nпроблемных: {len(bad)}/{len(items)}' + (f' -> {", ".join(bad)}' if bad else ''))
    return bad
