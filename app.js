import CueLabHaptics, { PRESETS, clickTimes } from './haptics.js';
import { buildPlayground } from './playground.js';

const VERSION = '13.9.0';
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

const state = {
  manifest: [], byId: new Map(), buffers: new Map(), rr: new Map(),
  selected: null, variant: 0, soundOn: true, hapticOn: true,
  codec: 'opus', category: 'Все', hapticMode: 'dense', tick: 0
};

let ctx = null, master = null;
let haptics = null;

/* ============================================================================
   ЗВУК
   ============================================================================ */

function audio() {
  if (!ctx) {
    const C = window.AudioContext || window.webkitAudioContext;
    ctx = new C();
    master = ctx.createGain();
    master.gain.value = 0.9;
    master.connect(ctx.destination);
  }
  if (ctx.state === 'suspended') ctx.resume().catch(() => {});
  return ctx;
}

/* Ни один кодек не покрывает все браузеры: AAC не декодируется в открытых
   сборках Chromium, Vorbis не поддерживает Safari. Пробуем Opus, падаем на AAC. */
async function decodeVariant(c, variant) {
  const order = state.codec === 'aac' ? ['aac', 'opus'] : ['opus', 'aac'];
  let lastError = null;
  for (const key of order) {
    if (!variant[key]) continue;
    try {
      const r = await fetch(variant[key]);
      if (!r.ok) throw new Error(r.status);
      const buf = await c.decodeAudioData(await r.arrayBuffer());
      state.codec = key;
      return buf;
    } catch (error) { lastError = error; }
  }
  throw lastError || new Error('нет пригодного формата');
}

async function loadAll() {
  const data = await (await fetch('sounds.json')).json();
  state.manifest = data.sounds;
  data.sounds.forEach(s => state.byId.set(s.id, s));
  const probe = document.createElement('audio');
  state.codec = probe.canPlayType('audio/ogg; codecs=opus') ? 'opus' : 'aac';
  const c = audio();
  let done = 0;
  const total = data.sounds.reduce((n, s) => n + s.variants.length, 0);
  await Promise.all(data.sounds.map(async sound => {
    const bufs = await Promise.all(sound.variants.map(async v => {
      const b = await decodeVariant(c, v);
      $('#loadStatus').textContent = `Загрузка ${++done}/${total}`;
      return b;
    }));
    state.buffers.set(sound.id, bufs);
  }));
  $('#loadStatus').textContent =
    `${data.sounds.length} звуков · ${total} вариантов · ${state.codec === 'opus' ? 'Opus' : 'AAC'}`;

  // Библиотека для хаптиков: чанки для Vibration API, огибающая и дорожка —
  // для iOS, где длинная вибрация собирается из щелчков переключателя.
  const library = {};
  data.sounds.forEach(s => {
    library[s.id] = { pattern: s.pattern || [{ duration: 25, intensity: 0.7 }] };
  });
  haptics = new CueLabHaptics(library);
}

function playSound(id, { variant = null, pitch = 0 } = {}) {
  if (!state.soundOn) return;
  const bufs = state.buffers.get(id);
  if (!bufs || !bufs.length) return;
  const c = audio();
  let index = variant;
  if (index === null) {
    const prev = state.rr.get(id) ?? -1;
    index = bufs.length > 1 ? (prev + 1) % bufs.length : 0;
    state.rr.set(id, index);
  }
  const src = c.createBufferSource();
  src.buffer = bufs[clamp(index, 0, bufs.length - 1)];
  if (pitch) src.playbackRate.value = Math.pow(2, pitch / 12);
  src.connect(master);
  src.start();
  return index;
}

/* Звук и вибрация запускаются из одного вызова, синхронно с жестом. */
function fire(id, opts = {}) {
  if (state.hapticOn && haptics) haptics.play(id, { mode: state.hapticMode });
  playSound(id, opts);
  state.tick += 1;
  if (!opts.quiet) renderDiag();
  else if (state.tick % 8 === 0) renderDiag();
}

/* ============================================================================
   ИНТЕРФЕЙС
   ============================================================================ */

function preserveScroll(render) {
  const nodes = [document.scrollingElement, $('.list-pane')].filter(Boolean);
  const saved = nodes.map(n => [n, n.scrollTop, n.scrollLeft]);
  render();
  const restore = () => saved.forEach(([n, t, l]) => {
    if (n.scrollTop !== t) n.scrollTop = t;
    if (n.scrollLeft !== l) n.scrollLeft = l;
  });
  restore();
  requestAnimationFrame(restore);
}

function categories() {
  const seen = [];
  state.manifest.forEach(s => { if (!seen.includes(s.category)) seen.push(s.category); });
  return ['Все', ...seen];
}

function renderCategories() {
  $('#catStrip').innerHTML = categories().map(c =>
    `<button class="cat-chip ${c === state.category ? 'is-active' : ''}" type="button" data-cat="${c}">${c}</button>`).join('');
  $$('[data-cat]').forEach(b => b.addEventListener('click', () => {
    state.category = b.dataset.cat;
    preserveScroll(() => { renderCategories(); renderList(); });
  }));
}

function renderList() {
  $('#soundCount').textContent = state.manifest.length;
  const visible = state.manifest.filter(s => state.category === 'Все' || s.category === state.category);
  let html = '';
  let last = null;
  visible.forEach(s => {
    if (state.category === 'Все' && s.category !== last) {
      html += `<div class="cat-title">${s.category}</div>`;
      last = s.category;
    }
    const ev = s.clickGapMs || 0;
    html += `<button class="sound-row ${s.id === state.selected ? 'is-active' : ''}" type="button" data-sound="${s.id}">
      <span><strong>${s.title}</strong><small>${s.variants.length} вар. · зерно ${ev} мс</small></span>
      <span>${s.durationMs} мс</span></button>`;
  });
  $('#soundList').innerHTML = html;
  $$('[data-sound]').forEach(b => b.addEventListener('click', () => {
    select(b.dataset.sound);
    fire(b.dataset.sound, { variant: state.variant });
  }));
}

function select(id) {
  if (!state.byId.has(id)) return;
  if (id !== state.selected) state.variant = 0;
  state.selected = id;
  preserveScroll(() => { renderList(); renderDetail(); });
  drawWave();
  drawHaptic();
}

/* Интервал между щелчками рука читает как зерно: чем чаще, тем глаже. */
function grainNote(gap) {
  if (gap <= 22) return 'мелкое, гладкое';
  if (gap <= 40) return 'среднее';
  return 'крупное, шершавое';
}

function metric(label, value, note, ok) {
  return `<div class="metric ${ok === true ? 'ok' : ok === false ? 'warn' : ''}"><b>${value}</b><small>${label}</small><small>${note}</small></div>`;
}

function renderDetail() {
  const s = state.byId.get(state.selected);
  if (!s) return;
  const segs = (s.pattern || []).length;
  $('#detailMeta').textContent = `${s.category} · ${s.durationMs} мс · ${s.variants.length} вар.`;
  $('#detailTitle').textContent = s.title;
  $('#detailNote').textContent = s.note;
  $('#metrics').innerHTML =
    metric('Центроид', `${s.centroidHz} Гц`, 'норма 700–4200', s.centroidHz >= 700 && s.centroidHz <= 4200) +
    metric('Ниже 300 Гц', `${s.lowPct}%`, 'норма до 18%', s.lowPct <= 18) +
    metric('400 Гц – 6 кГц', `${s.midPct}%`, 'норма от 45%', s.midPct >= 45) +
    metric('Отрезков вибро', segs, 'формат web-haptics') +
    metric('Зерно вибро', `${s.clickGapMs || 0} мс`, grainNote(s.clickGapMs || 0)) +
    metric('Яркость', (s.brightness || 0).toFixed(2), 'центроид -> частота щелчков');
  $('#variantRow').innerHTML = s.variants.map((v, i) =>
    `<button class="variant-chip ${i === state.variant ? 'is-active' : ''}" type="button" data-variant="${i}">Вариант ${i + 1}</button>`).join('');
  $$('[data-variant]').forEach(b => b.addEventListener('click', () => {
    state.variant = Number(b.dataset.variant);
    preserveScroll(renderDetail);
    drawWave(); drawHaptic();
    fire(s.id, { variant: state.variant });
  }));
  renderExport();
}

function drawWave() {
  const canvas = $('#waveCanvas');
  const bufs = state.buffers.get(state.selected);
  if (!canvas || !bufs) return;
  const buf = bufs[clamp(state.variant, 0, bufs.length - 1)];
  const ratio = window.devicePixelRatio || 1;
  const w = canvas.clientWidth || 600, h = 130;
  canvas.width = Math.floor(w * ratio); canvas.height = Math.floor(h * ratio);
  const g = canvas.getContext('2d');
  g.setTransform(ratio, 0, 0, ratio, 0, 0);
  g.clearRect(0, 0, w, h);
  g.strokeStyle = 'rgba(255,255,255,.10)';
  g.beginPath(); g.moveTo(0, h / 2); g.lineTo(w, h / 2); g.stroke();
  const d = buf.getChannelData(0);
  const step = Math.max(1, Math.floor(d.length / w));
  g.fillStyle = '#ffb454';
  for (let x = 0; x < w; x += 1) {
    let min = 1, max = -1;
    for (let i = 0; i < step; i += 1) {
      const v = d[x * step + i] || 0;
      if (v < min) min = v;
      if (v > max) max = v;
    }
    g.fillRect(x, (1 - max) * h / 2, 1, Math.max(1, (max - min) * h / 2));
  }
  g.fillStyle = 'rgba(255,255,255,.45)';
  g.font = '10px system-ui';
  g.fillText(`звук · ${(buf.duration * 1000).toFixed(0)} мс`, 10, 15);
}

/* Рисунок вибрации под волной: сразу видно, что импульсы повторяют форму. */
function drawHaptic() {
  const canvas = $('#hapticCanvas');
  const s = state.byId.get(state.selected);
  if (!canvas || !s) return;
  const pattern = s.pattern || [];
  const ratio = window.devicePixelRatio || 1;
  const w = canvas.clientWidth || 600, h = 78;
  canvas.width = Math.floor(w * ratio); canvas.height = Math.floor(h * ratio);
  const g = canvas.getContext('2d');
  g.setTransform(ratio, 0, 0, ratio, 0, 0);
  g.clearRect(0, 0, w, h);
  const span = Math.max(s.durationMs, 1);

  // Отрезки паттерна: высота — сила, ширина — сколько вибрация держится,
  // цвет — яркость звука на этом участке. Фиолетовое глухое, оранжевое звонкое:
  // яркость входит в силу, а сила и есть частота щелчков.
  const bright = s.bright || [];
  const bStep = s.envStepMs || 32;
  let t = 0;
  pattern.forEach(v => {
    t += v.delay || 0;
    const x = t / span * w;
    const width = Math.max(1.5, v.duration / span * w);
    const height = (h - 32) * (0.2 + 0.8 * v.intensity);
    const b = (bright[Math.floor(t / bStep)] || 40) / 100;
    const r = Math.round(124 + (255 - 124) * b);
    const gr = Math.round(108 + (180 - 108) * b);
    const bl = Math.round(255 - (255 - 84) * b);
    g.fillStyle = `rgba(${r},${gr},${bl},${0.4 + 0.5 * v.intensity})`;
    g.fillRect(x, h - 18 - height, width, height);
    t += v.duration;
  });

  // Щелчки переключателя — то, из чего вибрация складывается на iPhone.
  g.fillStyle = 'rgba(255,180,84,.8)';
  clickTimes(pattern, 0.7).forEach(ms => {
    g.fillRect(ms / span * w, h - 12, 1, 8);
  });

  g.fillStyle = 'rgba(255,255,255,.45)';
  g.font = '10px system-ui';
  g.fillText(`вибро · ${pattern.length} отрезков · ${s.clicks || 0} щелчков · зерно ${s.clickGapMs || 0} мс`, 10, 15);
}

/* ============================================================================
   ЭКСПОРТ — отдельно звук, веб, iOS, Android
   ============================================================================ */

function download(href, name) {
  const a = document.createElement('a');
  a.href = href; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
}

function downloadText(text, name, type = 'text/plain') {
  const url = URL.createObjectURL(new Blob([text], { type }));
  download(url, name);
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

async function copyText(text, label) {
  try {
    await navigator.clipboard.writeText(text);
    toast(label + ' — скопировано');
  } catch (_) {
    window.prompt(label, text);
  }
}

function webSnippet(s) {
  const pattern = JSON.stringify(s.pattern || [], null, 2);
  const name = s.id.replace(/-/g, '_');
  return `// CueLab — «${s.title}» (${s.id})
// Вибро повторяет огибающую звука: ${(s.pattern || []).length} отрезков,
// ${s.clicks || 0} щелчков переключателя.
//
// Движок — порт web-haptics Лохи Экcона (MIT, © 2025 Lochie Axon,
// npm i web-haptics). Три вещи, которые в нём важны и которые легко упустить:
//
//  * интервал между щелчками = 16 + (1 - intensity) * 184 мс. На полной силе
//    это каждый кадр, и именно поэтому ощущается непрерывная вибрация;
//  * элемент — <label for=id> с <input type="checkbox" switch> внутри, оба в
//    display:none; кликается ИМЕННО label;
//  * на Android амплитуда имитируется широтно-импульсной модуляцией: импульс
//    режется на окна по 20 мс, доля включённого равна силе.
//
// Сверху добавлена нарезка на куски по десять записей: спецификация Vibration
// API задаёт «Let max length have the value 10» и обрезает остальное.

export const ${name}Pattern = ${pattern};

const CLICK_MIN_MS = 16, CLICK_RANGE_MS = 184, PWM_FRAME_MS = 20;
const hasVibrate = typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function';

function pwm(duration, intensity) {
  if (intensity >= 1) return [duration];
  if (intensity <= 0) return [];
  const on = Math.max(1, Math.round(PWM_FRAME_MS * intensity));
  const off = PWM_FRAME_MS - on;
  const out = [];
  let rest = duration;
  while (rest >= PWM_FRAME_MS) { out.push(on, off); rest -= PWM_FRAME_MS; }
  if (rest > 0) {
    const tail = Math.max(1, Math.round(rest * intensity));
    out.push(tail);
    if (rest - tail > 0) out.push(rest - tail);
  }
  return out;
}

function toFlat(vibrations) {
  const out = [];
  for (const v of vibrations) {
    const delay = v.delay || 0;
    if (delay > 0) {
      if (out.length > 0 && out.length % 2 === 0) out[out.length - 1] += delay;
      else { if (!out.length) out.push(0); out.push(delay); }
    }
    for (const f of pwm(v.duration, v.intensity)) out.push(f);
  }
  return out;
}

function toChunks(flat) {
  const out = [];
  let at = 0, i = 0;
  if (flat.length >= 2 && flat[0] === 0) { at += flat[1]; i = 2; }
  while (i < flat.length) {
    let piece = flat.slice(i, i + 10);
    if (piece.length % 2 === 0) piece = piece.slice(0, -1);
    if (!piece.length) break;
    out.push({ at, pattern: piece.map(Math.round) });
    at += piece.reduce((a, b) => a + b, 0);
    i += piece.length;
    if (i < flat.length) { at += flat[i]; i += 1; }
  }
  return out;
}

let timers = [];
let rafId = null;
let hapticLabel = null;

function ensureDOM() {
  if (hapticLabel) return hapticLabel;
  const id = 'cuelab-haptics-${name}';
  const label = document.createElement('label');
  label.setAttribute('for', id);
  label.style.display = 'none';
  const input = document.createElement('input');
  input.type = 'checkbox';
  input.setAttribute('switch', '');
  input.id = id;
  input.style.all = 'initial';
  input.style.appearance = 'auto';
  input.style.display = 'none';
  label.appendChild(input);
  document.body.appendChild(label);
  hapticLabel = label;
  return label;
}

function click() {
  // Клик по label фокусирует чекбокс, и браузер подкручивает фокус в кадр —
  // страница прыгает. Снимаем позицию до и возвращаем сразу после.
  const sx = window.scrollX, sy = window.scrollY;
  try { hapticLabel.click(); } catch (_) {}
  if (window.scrollX !== sx || window.scrollY !== sy) window.scrollTo(sx, sy);
}

export function stop${pascal(s.id)}() {
  timers.forEach(clearTimeout);
  timers = [];
  if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null; }
  if (hasVibrate) { try { navigator.vibrate(0); } catch (_) {} }
}

/** Вызывать синхронно из обработчика жеста. */
export function play${pascal(s.id)}() {
  stop${pascal(s.id)}();
  const vibrations = ${name}Pattern;

  if (hasVibrate) {
    toChunks(toFlat(vibrations)).forEach(chunk => {
      const fire = () => { try { navigator.vibrate(chunk.pattern); } catch (_) {} };
      if (chunk.at <= 0) fire();
      else timers.push(setTimeout(fire, chunk.at));
    });
    return true;
  }

  // iOS: непрерывной вибрации нет как примитива, её собирают из щелчков.
  ensureDOM();
  const spans = [];
  let end = 0;
  for (const v of vibrations) {
    if (v.delay > 0) { end += v.delay; spans.push({ end, on: false, intensity: 0 }); }
    end += v.duration;
    spans.push({ end, on: true, intensity: v.intensity });
  }
  let fired = (vibrations[0].delay || 0) === 0;
  if (fired) click();                       // первый щелчок — внутри жеста
  let start = 0, lastClick = -1;
  const step = now => {
    if (!start) start = now;
    const t = now - start;
    if (t >= end) { rafId = null; return; }
    let span = spans[0];
    for (const sp of spans) { if (t < sp.end) { span = sp; break; } }
    if (span.on) {
      const gap = CLICK_MIN_MS + (1 - span.intensity) * CLICK_RANGE_MS;
      if (lastClick === -1) { if (!fired) { click(); fired = true; } lastClick = now; }
      else if (now - lastClick >= gap) { click(); lastClick = now; }
    }
    rafId = requestAnimationFrame(step);
  };
  rafId = requestAnimationFrame(step);
  return true;
}
`;
}

/* PascalCase из id: marathon-win -> MarathonWin. */
function pascal(id) {
  return id.split(/[-_]/).filter(Boolean)
    .map(w => w.charAt(0).toUpperCase() + w.slice(1)).join('')
    .replace(/[^A-Za-z]/g, '');
}

function swiftSnippet(s) {
  const evs = (s.hapticEvents || []).length;
  const curves = ((s.ahap || {}).Pattern || []).filter(p => p.ParameterCurve).length;
  const points = ((s.ahap || {}).Pattern || [])
    .filter(p => p.ParameterCurve)
    .reduce((n, p) => n + p.ParameterCurve.ParameterCurveControlPoints.length, 0);
  return `//  CueLab — «${s.title}» (${s.id})
//
//  В вебе вибрация ИМИТИРУЕТСЯ: там единственный рычаг — частота щелчков.
//  Здесь имитировать нечего, амплитуда настоящая и меняется непрерывно,
//  поэтому паттерн устроен иначе.
//
//  ${s.id}.ahap: ${evs} транзиентов на атаках + непрерывные события на
//  звучащих участках, поверх — ${curves} кривые параметров, ${points} точек:
//
//    HapticIntensityControl — множитель силы 0…1 по огибающей громкости,
//      посчитанной по кривой A (IEC 61672), а не по энергии: ухо на 3 кГц
//      чувствительнее, чем на 200 Гц, примерно на 10 дБ;
//    HapticSharpnessControl — СДВИГ резкости −1…1 по спектральному центроиду.
//      Именно сдвиг, а не множитель, поэтому базовая резкость события 0.5.
//
//  Положите рядом ${s.id}.ahap и ${s.id}-0.m4a — оба в export/ios/.

import AVFoundation
import CoreHaptics
import UIKit

final class ${pascal(s.id)}Cue {

    private var engine: CHHapticEngine?
    private var player: CHHapticPatternPlayer?
    private var audio: AVAudioPlayer?
    private let supportsHaptics = CHHapticEngine.capabilitiesForHardware().supportsHaptics

    init() {
        prepare()
    }

    private func prepare() {
        if let url = Bundle.main.url(forResource: "${s.id}-0", withExtension: "m4a") {
            audio = try? AVAudioPlayer(contentsOf: url)
            audio?.prepareToPlay()
        }
        guard supportsHaptics else { return }
        engine = try? CHHapticEngine()
        // Движок гасят звонок, сворачивание и переключение сцены. Без этих
        // двух обработчиков хаптик тихо перестаёт играть после первого же
        // перерыва, и выглядит это как «вибро сломалось».
        engine?.resetHandler = { [weak self] in
            try? self?.engine?.start()
            self?.loadPattern()
        }
        engine?.stoppedHandler = { reason in
            print("CueLab: движок остановлен — \\(reason.rawValue)")
        }
        engine?.playsHapticsOnly = true
        engine?.isAutoShutdownEnabled = true
        try? engine?.start()
        loadPattern()
    }

    private func loadPattern() {
        guard let engine,
              let url = Bundle.main.url(forResource: "${s.id}", withExtension: "ahap"),
              let pattern = try? CHHapticPattern(contentsOf: url) else { return }
        player = try? engine.makePlayer(with: pattern)
    }

    /// Звук и вибро с общего момента: расхождение больше ~20 мс уже читается
    /// как рассинхрон, поэтому обе дорожки стартуют от одного времени.
    func play(withSound: Bool = true) {
        if withSound {
            audio?.currentTime = 0
            audio?.play()
        }
        guard supportsHaptics else {
            // На устройствах без Core Haptics (iPhone 6s и старше, iPad)
            // остаётся системный отклик — лучше, чем ничего.
            UIImpactFeedbackGenerator(style: .medium).impactOccurred()
            return
        }
        do {
            try engine?.start()
            try player?.start(atTime: CHHapticTimeImmediate)
        } catch {
            // Одна попытка перезапуска: движок мог быть остановлен системой
            // между подготовкой и нажатием.
            try? engine?.start()
            loadPattern()
            try? player?.start(atTime: CHHapticTimeImmediate)
        }
    }

    func stop() {
        try? player?.stop(atTime: CHHapticTimeImmediate)
        audio?.stop()
    }
}
`;
}

function kotlinSnippet(s) {
  const and = s.android || { timings: [], amplitudes: [], composition: [] };
  const raw = `cue_${s.id.replace(/-/g, '_')}_0`;
  const comp = (and.composition || []);
  const prims = [...new Set(comp.map(c => c.primitive))];
  return `//  CueLab — «${s.title}» (${s.id})
//
//  Здесь амплитуда настоящая, поэтому силу не надо кодировать длительностью,
//  как в вебе. Два пути, от лучшего к запасному:
//
//   1. Composition из примитивов (API 30+) — ${comp.length} шт. на атаках.
//      Примитив отрабатывает мотором с собственной огибающей и ощущается
//      чище прямоугольного импульса. TICK для звонкого, CLICK для среднего,
//      THUD для глухого — тип выбран по спектральному центроиду атаки.
//   2. Waveform с амплитудами 0..255 — ${(and.timings || []).length} отрезков
//      по огибающей громкости, шаг ${and.stepMs || 16} мс.
//   3. Waveform без амплитуд — на моторах без hasAmplitudeControl()
//      остаётся только ритм.

package cuelab

import android.content.Context
import android.media.AudioAttributes
import android.media.SoundPool
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager

object ${pascal(s.id)}Cue {

    private val timings = longArrayOf(${(and.timings || []).join(', ')})
    private val amplitudes = intArrayOf(${(and.amplitudes || []).join(', ')})

    private fun vibrator(context: Context): Vibrator =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            context.getSystemService(VibratorManager::class.java).defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            context.getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
        }

    /** Звук и вибро с одного вызова: расхождение больше ~20 мс уже читается. */
    fun play(context: Context, pool: SoundPool, soundId: Int) {
        pool.play(soundId, 1f, 1f, 1, 0, 1f)   // ресурс res/raw/${raw}.ogg

        val vibrator = vibrator(context)
        if (!vibrator.hasVibrator()) return

        // Хаптик интерфейса — это отклик на действие, а не уведомление:
        // с USAGE_TOUCH его не заглушит режим «не беспокоить».
        val attrs = AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_ASSISTANCE_SONIFICATION)
            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
            .build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R && composition(vibrator) != null) {
            vibrator.vibrate(composition(vibrator)!!, attrs)
            return
        }
        val effect = if (vibrator.hasAmplitudeControl()) {
            VibrationEffect.createWaveform(timings, amplitudes, -1)
        } else {
            VibrationEffect.createWaveform(timings, -1)
        }
        vibrator.vibrate(effect, attrs)
    }

    /** null, если устройство не умеет нужные примитивы — тогда идём в waveform. */
    private fun composition(vibrator: Vibrator): VibrationEffect? {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return null
        val ids = intArrayOf(${prims.map(p => `VibrationEffect.Composition.PRIMITIVE_${p}`).join(', ') || 'VibrationEffect.Composition.PRIMITIVE_CLICK'})
        if (!vibrator.areAllPrimitivesSupported(*ids)) return null
        return VibrationEffect.startComposition()
${comp.map(c => `            .addPrimitive(VibrationEffect.Composition.PRIMITIVE_${c.primitive}, ${c.scale}f, ${c.delayMs})`).join('\n') || '            .addPrimitive(VibrationEffect.Composition.PRIMITIVE_CLICK, 1f, 0)'}
            .compose()
    }

    fun stop(context: Context) = vibrator(context).cancel()
}
`;
}

function renderExport() {
  const s = state.byId.get(state.selected);
  const node = $('#exportPanel');
  if (!node || !s) return;
  const stem = `${s.id}-${state.variant}`;
  const raw = `cue_${s.id.replace(/-/g, '_')}_${state.variant}`;
  const evs = (s.hapticEvents || []).length;
  const curvePoints = ((s.ahap || {}).Pattern || [])
    .filter(p => p.ParameterCurve)
    .reduce((n, p) => n + p.ParameterCurve.ParameterCurveControlPoints.length, 0);

  node.innerHTML = `
    <div class="ex-card">
      <div class="ex-head"><b>Звук</b><small>${s.durationMs} мс · вариант ${state.variant + 1}</small></div>
      <p>Мастер без потерь и сжатые версии для веба и приложений.</p>
      <div class="ex-row">
        <button class="btn btn-dark" data-x="flac">FLAC мастер</button>
        <button class="btn btn-light" data-x="opus">Opus</button>
        <button class="btn btn-light" data-x="aac">AAC / m4a</button>
        <button class="btn btn-light" data-x="raw">Ogg для res/raw</button>
      </div>
    </div>

    <div class="ex-card">
      <div class="ex-head"><b>Вибро для веба</b><small>${(s.pattern || []).length} отрезков · ${s.clicks || 0} щелчков</small></div>
      <p>Формат <code>{delay, duration, intensity}</code> и движок web-haptics: щелчки переключателя каждые <code>16 + (1−сила)·184</code> мс на iOS, широтно-импульсная амплитуда и куски по десять записей на Android.</p>
      <div class="ex-row">
        <button class="btn btn-dark" data-x="web-js">Скачать .js</button>
        <button class="btn btn-light" data-x="web-json">Скачать .json</button>
        <button class="btn btn-light" data-x="web-copy">Копировать код</button>
        <button class="btn btn-light" data-x="web-test">Проиграть вибро</button>
        <button class="btn btn-light" data-x="web-test-ios">Проиграть как на iOS</button>
      </div>
    </div>

    <div class="ex-card">
      <div class="ex-head"><b>iOS</b><small>${evs} транзиентов · ${curvePoints} точек кривых</small></div>
      <p>AHAP с непрерывными событиями и кривыми <code>HapticIntensityControl</code> и <code>HapticSharpnessControl</code>: сила идёт за огибающей, резкость — за спектральным центроидом. Плюс класс на Swift с перезапуском движка и синхронным звуком.</p>
      <div class="ex-row">
        <button class="btn btn-dark" data-x="ahap">Скачать .ahap</button>
        <button class="btn btn-light" data-x="swift">Скачать .swift</button>
        <button class="btn btn-light" data-x="swift-copy">Копировать код</button>
      </div>
    </div>

    <div class="ex-card">
      <div class="ex-head"><b>Android</b><small>${(s.android || {}).composition?.length || 0} примитивов · ${((s.android || {}).timings || []).length} отрезков</small></div>
      <p><code>Composition</code> из примитивов на атаках для API 30+, <code>createWaveform</code> с амплитудами 0..255 как запасной путь, и ритм без амплитуд для моторов, которые её не умеют.</p>
      <div class="ex-row">
        <button class="btn btn-dark" data-x="kotlin">Скачать .kt</button>
        <button class="btn btn-light" data-x="and-json">Скачать .json</button>
        <button class="btn btn-light" data-x="kotlin-copy">Копировать код</button>
      </div>
    </div>`;

  const actions = {
    flac: () => download(`export/masters/${stem}.flac`, `${stem}.flac`),
    opus: () => download(`export/web/audio/${stem}.ogg`, `${stem}.ogg`),
    aac: () => download(`export/web/audio/${stem}.m4a`, `${stem}.m4a`),
    raw: () => download(`export/android/res/raw/${raw}.ogg`, `${raw}.ogg`),
    'web-js': () => downloadText(webSnippet(s), `${s.id}.haptics.js`, 'text/javascript'),
    'web-json': () => downloadText(JSON.stringify({
      id: s.id, pattern: s.pattern, chunks: s.chunks, clicks: s.clicks
    }, null, 1), `${s.id}.haptics.json`, 'application/json'),
    'web-copy': () => copyText(webSnippet(s), 'Код для веба'),
    'web-test': () => { if (haptics) haptics.play(s.id, { mode: 'dense' }); renderDiag(); },
    // послушать рукой именно iOS-путь: серия переключений вместо vibrate
    'web-test-ios': () => {
      if (!haptics) return;
      const back = haptics.force;
      haptics.setEngine('switch');
      haptics.play(s.id, { mode: 'dense' });
      const clicks = haptics.last.clicks;
      setTimeout(() => haptics.setEngine(back), Math.max(400, s.durationMs + 200));
      toast(`iOS-путь: ${clicks} щелчков`);
      renderDiag();
    },
    ahap: () => download(`export/ios/haptics/${s.id}.ahap`, `${s.id}.ahap`),
    swift: () => downloadText(swiftSnippet(s), `${s.id}.swift`, 'text/plain'),
    'swift-copy': () => copyText(swiftSnippet(s), 'Код для iOS'),
    kotlin: () => downloadText(kotlinSnippet(s), `${s.id}.kt`, 'text/plain'),
    'and-json': () => downloadText(JSON.stringify(s.android || {}, null, 1),
      `${s.id}.android.json`, 'application/json'),
    'kotlin-copy': () => copyText(kotlinSnippet(s), 'Код для Android'),
  };
  $$('[data-x]', node).forEach(b =>
    b.addEventListener('click', () => actions[b.dataset.x]?.()));
}

/* ============================================================================
   ДИАГНОСТИКА
   ============================================================================ */

/* Пресеты web-haptics — те же, что на haptics.lochie.me. Нужны, чтобы на
   одном и том же устройстве сравнить нашу вибрацию с эталонной, не
   переключаясь между вкладками. */
const PRESET_ORDER = ['selection', 'light', 'medium', 'heavy', 'soft', 'rigid',
                      'success', 'warning', 'error', 'nudge', 'buzz'];

/* Проверка непрерывности: одна и та же длительность на разной силе. Сила и
   есть частота щелчков, поэтому разница ощущается сразу. */
const HOLD_TESTS = [
  { label: 'держать 1 с · сила 1', ms: 1000, i: 1 },
  { label: 'держать 1 с · сила 0,6', ms: 1000, i: 0.6 },
  { label: 'держать 1 с · сила 0,3', ms: 1000, i: 0.3 },
];

function renderDiag() {
  const node = $('#diagBody');
  if (!node || !haptics) return;
  const last = haptics.last || {};
  const engine = haptics.engine === 'vibration-api' ? 'Vibration API'
    : haptics.engine === 'switch' ? 'переключатель (как в web-haptics)' : 'нет';
  const isSwitch = haptics.engine === 'switch';
  const rows = [
    ['движок', engine + (haptics.force !== 'auto' ? ' (принудительно)' : '')],
    ['разблокирован', haptics.unlocked ? 'да' : 'ещё нет'],
    ['переключатель switch поддержан', haptics.hasSwitch ? 'да' : (haptics.isIOS ? 'нет (но это iOS)' : 'нет')],
    ['режим', state.hapticMode === 'dense' ? 'плотный (весь паттерн)' : 'простой (один импульс)'],
    ['последний звук', last.id || '—'],
    isSwitch
      ? ['щелчков в паттерне', last.clicks || 0]
      : ['вызовов vibrate', (last.chunks || []).length],
    isSwitch
      ? ['щелчков отправлено всего', haptics.clicks]
      : ['первый паттерн', (last.chunks || [])[0] ? `[${last.chunks[0].pattern.join(', ')}]` : '—'],
    ['результат', last.result === null || last.result === undefined ? '—' : String(last.result)],
  ];
  node.innerHTML = rows.map(([k, v]) =>
    `<div class="diag-row"><span>${k}</span><b>${v}</b></div>`).join('');
}

function bindDiag() {
  $('#diagTests').innerHTML = HOLD_TESTS.map((t, i) =>
    `<button class="btn btn-light" type="button" data-hold="${i}">${t.label}</button>`).join('');
  $$('[data-hold]').forEach(b => b.addEventListener('click', () => {
    const t = HOLD_TESTS[Number(b.dataset.hold)];
    haptics.sustain(t.ms, t.i);
    renderDiag();
  }));

  $('#presetTests').innerHTML = PRESET_ORDER.map(name =>
    `<button class="btn btn-light" type="button" data-preset="${name}">${name}</button>`).join('');
  $$('[data-preset]').forEach(b => b.addEventListener('click', () => {
    haptics.trigger(PRESETS[b.dataset.preset], { intensity: 0.7, label: b.dataset.preset });
    renderDiag();
  }));

  $('#showSwitch').addEventListener('change', e => {
    haptics.setShowSwitch(e.target.checked);
  });
  $('#debugSwitch').addEventListener('change', e => {
    // щёлкать переключателем и там, где есть vibrate — видно глазами, что
    // серия действительно идёт
    haptics.setDebug(e.target.checked);
  });

  $$('[data-hengine]').forEach(b => b.addEventListener('click', () => {
    haptics.setEngine(b.dataset.hengine);
    $$('[data-hengine]').forEach(x => x.classList.toggle('is-on', x === b));
    renderDiag();
  }));
  $$('[data-hmode]').forEach(b => b.addEventListener('click', () => {
    state.hapticMode = b.dataset.hmode;
    $$('[data-hmode]').forEach(x => x.classList.toggle('is-on', x === b));
    renderDiag();
  }));
}

let toastTimer = 0;
function toast(message) {
  const t = $('#toast');
  t.textContent = message;
  t.classList.add('is-visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('is-visible'), 1900);
}

async function init() {
  $('#soundEnabled').addEventListener('change', e => state.soundOn = e.target.checked);
  $('#hapticEnabled').addEventListener('change', e => state.hapticOn = e.target.checked);
  $('#playButton').addEventListener('click', () => fire(state.selected, { variant: state.variant }));
  $('#stopButton').addEventListener('click', () => haptics && haptics.cancel());
  window.addEventListener('resize', () => { drawWave(); drawHaptic(); });

  try {
    await loadAll();
  } catch (error) {
    $('#loadStatus').textContent = 'Не удалось загрузить аудио';
    console.error(error);
    return;
  }

  state.selected = state.manifest[0].id;
  renderCategories(); renderList(); renderDetail();
  drawWave(); drawHaptic(); bindDiag(); renderDiag();
  const count = buildPlayground($('#playground'), fire);
  $('#pgCount').textContent = `${count} элементов`;

  window.__cuelab = {
    version: VERSION, state, fire, haptics,
    manifest: () => state.manifest, buffers: () => state.buffers,
    categories, snippets: { webSnippet, swiftSnippet, kotlinSnippet }
  };
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
else init();
