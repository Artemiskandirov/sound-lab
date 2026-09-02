/*  cuelab-haptics.js — вибро CueLab для веба.
 *
 *  Движок — порт web-haptics Лохи Экcона (MIT, © 2025 Lochie Axon,
 *  npm i web-haptics, https://haptics.lochie.me). Три вещи, которые в нём
 *  важны и которые легко упустить, если писать своё:
 *
 *  1. ЧАСТОТА ЩЕЛЧКОВ. На iOS непрерывной вибрации не существует как
 *     примитива: navigator.vibrate там отсутствует во всех версиях, а все
 *     браузеры на iPhone работают на WebKit. Единственный системный хаптик,
 *     доступный вебу, — тик переключателя <input type="checkbox" switch>.
 *     Вибрация складывается из щелчков, и интервал между ними равен
 *         16 + (1 - intensity) * 184 мс
 *     то есть на полной силе — каждый кадр. Именно это даёт ощущение
 *     непрерывности; на интервале в 30–90 мс получается пунктир.
 *
 *  2. ЭЛЕМЕНТ. <label for=id> с <input type="checkbox" switch> внутри, оба в
 *     display:none, и кликается ИМЕННО LABEL. display:none хаптику не мешает.
 *
 *  3. АМПЛИТУДА НА ANDROID. У Vibration API силы нет. Импульс режется на окна
 *     по 20 мс, и доля «включено» внутри окна равна силе — широтно-импульсная
 *     модуляция. Мотор успевает отработать, и слабое ощущается слабым, а не
 *     просто коротким.
 *
 *  Сверху добавлена нарезка на куски по десять записей: спецификация
 *  Vibration API задаёт «Let max length have the value 10» и обрезает
 *  остальное, а активация при этом sticky, а не transient — значит куски
 *  можно выдавать по таймеру встык. В самом web-haptics этого нет, и длинный
 *  паттерн на Android обрывается на десятой записи.
 *
 *  Формат паттерна: [{delay, duration, intensity}, ...], delay — пауза ПЕРЕД
 *  импульсом. Готовые паттерны всех звуков лежат в cuelab-haptics.json.
 */

const CLICK_MIN_MS = 16;
const CLICK_RANGE_MS = 184;
const PWM_FRAME_MS = 20;
const MAX_DURATION_MS = 1000;
const VIBRATE_MAX_ENTRIES = 10;

/** Пресеты web-haptics — те же имена и значения. */
export const PRESETS = {
  success: [{ duration: 30, intensity: 0.5 }, { delay: 60, duration: 40, intensity: 1 }],
  warning: [{ duration: 40, intensity: 0.8 }, { delay: 100, duration: 40, intensity: 0.6 }],
  error: [{ duration: 40, intensity: 0.9 }, { delay: 40, duration: 40, intensity: 0.9 },
          { delay: 40, duration: 40, intensity: 0.9 }],
  light: [{ duration: 15, intensity: 0.4 }],
  medium: [{ duration: 25, intensity: 0.7 }],
  heavy: [{ duration: 35, intensity: 1 }],
  soft: [{ duration: 40, intensity: 0.5 }],
  rigid: [{ duration: 10, intensity: 1 }],
  selection: [{ duration: 8, intensity: 0.3 }],
  nudge: [{ duration: 80, intensity: 0.8 }, { delay: 80, duration: 50, intensity: 0.3 }],
  buzz: [{ duration: 1000, intensity: 1 }],
};

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

/** Паттерн -> плоский массив для navigator.vibrate. */
export function toFlat(vibrations, defaultIntensity = 0.5) {
  const out = [];
  for (const v of vibrations) {
    const intensity = Math.max(0, Math.min(1, v.intensity == null ? defaultIntensity : v.intensity));
    const delay = v.delay || 0;
    if (delay > 0) {
      if (out.length > 0 && out.length % 2 === 0) out[out.length - 1] += delay;
      else { if (!out.length) out.push(0); out.push(delay); }
    }
    const frames = pwm(v.duration, intensity);
    if (!frames.length) {
      if (out.length > 0 && out.length % 2 === 0) out[out.length - 1] += v.duration;
      else if (v.duration > 0) out.push(0, v.duration);
      continue;
    }
    for (const f of frames) out.push(f);
  }
  return out;
}

/** Куски не длиннее десяти записей; кусок обязан заканчиваться вибрацией. */
export function toChunks(flat, maxLen = VIBRATE_MAX_ENTRIES) {
  const out = [];
  let at = 0, i = 0;
  if (flat.length >= 2 && flat[0] === 0) { at += flat[1]; i = 2; }
  while (i < flat.length) {
    let piece = flat.slice(i, i + maxLen);
    if (piece.length % 2 === 0) piece = piece.slice(0, -1);
    if (!piece.length) break;
    out.push({ at, pattern: piece.map(v => Math.round(v)) });
    at += piece.reduce((a, b) => a + b, 0);
    i += piece.length;
    if (i < flat.length) { at += flat[i]; i += 1; }
  }
  return out;
}

export class CueLabHaptics {
  /**
   * @param {object} library   id -> { pattern } из cuelab-haptics.json
   * @param {object} options   { showSwitch, debug }
   */
  constructor(library, options = {}) {
    this.library = library || {};
    this.timers = [];
    this.rafId = null;
    this.label = null;
    this.input = null;
    this.clicks = 0;
    this.showSwitch = !!options.showSwitch;
    this.debug = !!options.debug;
    this.hasVibrate = typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function';
  }

  ensureDOM() {
    if (this.label || typeof document === 'undefined') return;
    const id = 'cuelab-haptics-switch';
    const label = document.createElement('label');
    label.setAttribute('for', id);
    label.textContent = 'Haptics';
    label.style.cssText = 'position:fixed;bottom:10px;left:10px;padding:5px 10px;' +
      'background:rgba(0,0,0,.7);color:#fff;font:14px sans-serif;border-radius:4px;' +
      'z-index:9999;user-select:none';
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.setAttribute('switch', '');
    input.id = id;
    input.style.all = 'initial';
    input.style.appearance = 'auto';
    if (!this.showSwitch) { label.style.display = 'none'; input.style.display = 'none'; }
    label.appendChild(input);
    document.body.appendChild(label);
    this.label = label;
    this.input = input;
  }

  setShowSwitch(on) {
    this.showSwitch = on;
    this.ensureDOM();
    if (!this.label) return;
    this.label.style.display = on ? '' : 'none';
    this.input.style.display = on ? '' : 'none';
  }

  click() {
    if (!this.label) return;
    // Клик по label фокусирует чекбокс, и браузер подкручивает фокус в кадр —
    // страница прыгает на каждом щелчке. Снимаем позицию до и возвращаем
    // сразу после: фокусный скролл идёт синхронно внутри dispatch.
    const sx = window.scrollX, sy = window.scrollY;
    try { this.label.click(); this.clicks += 1; } catch (_) {}
    if (window.scrollX !== sx || window.scrollY !== sy) window.scrollTo(sx, sy);
  }

  /**
   * Серия щелчков по паттерну. Кадровый цикл, а не цепочка setTimeout: на
   * интервале 16 мс таймеры копят дрейф и уезжают от звука.
   */
  runPattern(vibrations, defaultIntensity, firedAtStart) {
    const spans = [];
    let end = 0;
    for (const v of vibrations) {
      const intensity = Math.max(0, Math.min(1, v.intensity == null ? defaultIntensity : v.intensity));
      if (v.delay > 0) { end += v.delay; spans.push({ end, on: false, intensity: 0 }); }
      end += v.duration;
      spans.push({ end, on: true, intensity });
    }
    let start = 0, lastClick = -1, fired = firedAtStart;
    const step = now => {
      if (!start) start = now;
      const t = now - start;
      if (t >= end) { this.rafId = null; return; }
      let span = spans[0];
      for (const s of spans) { if (t < s.end) { span = s; break; } }
      if (span.on) {
        const gap = CLICK_MIN_MS + (1 - span.intensity) * CLICK_RANGE_MS;
        if (lastClick === -1) { if (!fired) { this.click(); fired = true; } lastClick = now; }
        else if (now - lastClick >= gap) { this.click(); lastClick = now; }
      }
      this.rafId = requestAnimationFrame(step);
    };
    this.rafId = requestAnimationFrame(step);
  }

  /** Вызывать синхронно из обработчика жеста. */
  trigger(pattern, { intensity = 0.5 } = {}) {
    this.stop();
    const vibrations = (typeof pattern === 'string' ? PRESETS[pattern] : pattern) || [];
    if (!vibrations.length) return false;
    for (const v of vibrations) if (v.duration > MAX_DURATION_MS) v.duration = MAX_DURATION_MS;

    if (this.hasVibrate) {
      toChunks(toFlat(vibrations, intensity)).forEach(chunk => {
        const fire = () => { try { navigator.vibrate(chunk.pattern); } catch (_) {} };
        if (chunk.at <= 0) fire();
        else this.timers.push(setTimeout(fire, chunk.at));
      });
    }
    if (!this.hasVibrate || this.debug) {
      this.ensureDOM();
      if (!this.label) return false;
      const immediate = (vibrations[0].delay || 0) === 0;
      if (immediate) this.click();          // первый щелчок — внутри жеста
      this.runPattern(vibrations, intensity, immediate);
    }
    return true;
  }

  /** Хаптик звука по id. */
  play(id, options) {
    const entry = this.library[id];
    if (!entry || !entry.pattern) return false;
    return this.trigger(entry.pattern, { intensity: 0.7, ...options });
  }

  /** Ровная вибрация заданной длины. */
  sustain(durationMs = 1000, intensity = 1) {
    return this.trigger([{ duration: Math.min(durationMs, MAX_DURATION_MS), intensity }], { intensity });
  }

  stop() {
    this.timers.forEach(clearTimeout);
    this.timers = [];
    if (this.rafId !== null) { cancelAnimationFrame(this.rafId); this.rafId = null; }
    if (this.hasVibrate) { try { navigator.vibrate(0); } catch (_) {} }
  }
}

export default CueLabHaptics;
