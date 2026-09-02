import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal
from dsp import SR
from check import profile

def sheet(items, path, title='', cols=3):
    n = len(items)
    rows = int(np.ceil(n / cols))
    fig = plt.figure(figsize=(cols * 5.2, rows * 3.0))
    fig.patch.set_facecolor('#0e1014')
    gs = fig.add_gridspec(rows * 2, cols, height_ratios=[0.8, 2.4] * rows,
                          hspace=0.55, wspace=0.16)
    for i, (name, y) in enumerate(items):
        r, c = divmod(i, cols)
        p = profile(y)
        aw = fig.add_subplot(gs[r * 2, c])
        asp = fig.add_subplot(gs[r * 2 + 1, c])
        t = np.arange(len(y)) / SR
        aw.plot(t, y, lw=0.4, color='#ffb454')
        aw.set_xlim(0, t[-1]); aw.set_ylim(-1.05, 1.05)
        aw.set_title(f'{name}  ·  {p["dur"]*1000:.0f} мс  ·  центроид {p["centroid"]:.0f} Гц  ·  <300 Гц {p["low"]*100:.0f}%',
                     color='#e8e8e8', fontsize=9, pad=3)
        aw.set_facecolor('#15181e'); aw.set_xticks([]); aw.set_yticks([])
        for s in aw.spines.values(): s.set_color('#333')

        nper = 512
        f, tt, S = signal.spectrogram(y, SR, nperseg=nper, noverlap=nper - 64,
                                      window='hann', scaling='spectrum')
        S = 10 * np.log10(S + 1e-14)
        S -= S.max()
        asp.pcolormesh(tt, f, S, vmin=-72, vmax=0, cmap='inferno', shading='auto', rasterized=True)
        asp.set_yscale('log'); asp.set_ylim(120, 20000)
        asp.set_yticks([200, 500, 1000, 2000, 5000, 10000, 20000])
        asp.set_yticklabels(['200', '500', '1k', '2k', '5k', '10k', '20k'])
        asp.axhline(400, color='#39d0ff', lw=0.7, ls='--', alpha=0.55)
        asp.axhline(6000, color='#39d0ff', lw=0.7, ls='--', alpha=0.55)
        asp.tick_params(colors='#999', labelsize=6)
        asp.set_facecolor('#000')
        for s in asp.spines.values(): s.set_color('#333')
    fig.suptitle(title + '     (пунктир — полоса 400 Гц – 6 кГц, которую реально отдаёт динамик телефона)',
                 color='#fff', fontsize=12, y=0.995)
    fig.savefig(path, dpi=100, facecolor=fig.get_facecolor(), bbox_inches='tight')
    plt.close(fig)
