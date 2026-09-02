/*  CueLab — вибро для веба.
 *
 *  Движок здесь — порт web-haptics Лохи Экcона (MIT, © 2025 Lochie Axon,
 *  npm i web-haptics, https://haptics.lochie.me). Я скачал пакет и прочитал
 *  dist, потому что три моих собственных догадки оказались неверными:
 *
 *  1. ЧАСТОТА. Я держал интервал между щелчками в границах 26–90 мс, считая,
 *     что чаще система их склеит. В web-haptics интервал считается как
 *         16 + (1 - intensity) * 184 мс
 *     то есть на полной силе щелчки идут КАЖДЫЙ КАДР, через 16 мс. Именно
 *     поэтому у них ощущается непрерывная вибрация, а у меня — пунктир.
 *
 *  2. ЭЛЕМЕНТ. Я перебирал, куда его спрятать: за край экрана, в кадр с
 *     opacity, pointer-events:none. У них — один <label for=id> с
 *     <input type="checkbox" switch> внутри, оба в display:none, label
 *     зафиксирован снизу слева, и кликается ИМЕННО LABEL. display:none
 *     хаптику не мешает.
 *
 *  3. АМПЛИТУДА НА ANDROID. У Vibration API нет силы, и я кодировал её длиной
 *     импульса. В web-haptics импульс режется на окна по 20 мс, и внутри окна
 *     доля «включено» равна intensity — широтно-импульсная модуляция. Мотор
 *     успевает отработать, и слабое ощущается слабым, а не коротким.
 *
 *  Что добавлено сверху: нарезка длинного паттерна на куски по десять записей.
 *  Спецификация Vibration API прямо задаёт «Let max length have the value 10»
 *  и обрезает остальное; активация при этом sticky, а не transient, поэтому
 *  куски можно выдавать по таймеру встык. В самом web-haptics этого нет, и
 *  длинный паттерн там на Android обрывается.
 *
 *  Формат паттерна тот же, что у них: [{delay, duration, intensity}, ...],
 *  где delay — пауза ПЕРЕД импульсом.
 */

const CLICK_MIN_MS = 16;        // интервал на полной силе
const CLICK_RANGE_MS = 184;     // добавка на нулевой силе: 16 + 184 = 200 мс
const PWM_FRAME_MS = 20;        // окно широтно-импульсной модуляции
const MAX_DURATION_MS = 1000;   // предел одного импульса
const VIBRATE_MAX_ENTRIES = 10; // «Let max length have the value 10»

/* Пресеты web-haptics — чтобы можно было сравнить с их сайтом на том же
   устройстве, не переключаясь между вкладками. */
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

/**
 * Импульс -> череда «включено/выключено» окнами по 20 мс.
 * Доля включённого времени равна силе: так у Vibration API появляется
 * амплитуда, которой в нём нет.
 */
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

/** Паттерн -> плоский массив [вибрация, пауза, ...] для navigator.vibrate. */
export function toFlat(vibrations, defaultIntensity = 0.5) {
  const out = [];
  for (const v of vibrations) {
    const intensity = Math.max(0, Math.min(1, v.intensity == null ? defaultIntensity : v.intensity));
    const delay = v.delay || 0;
    if (delay > 0) {
      // пауза приклеивается к предыдущей паузе, если запись уже чётная
      if (out.length > 0 && out.length % 2 === 0) out[out.length - 1] += delay;
      else { if (out.length === 0) out.push(0); out.push(delay); }
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

/**
 * Нарезка на куски не длиннее десяти записей.
 * Кусок обязан заканчиваться вибрацией: иначе следующий начнётся с паузы,
 * а vibrate() читает ПЕРВЫЙ элемент как вибрацию — пауза превратится в гул.
 */
export function toChunks(flat, maxLen = VIBRATE_MAX_ENTRIES) {
  const out = [];
  let at = 0;
  let i = 0;
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

/** Сколько всего щелчков переключателя даст паттерн — для метрик и рисунка. */
export function clickTimes(vibrations, defaultIntensity = 0.5) {
  const out = [];
  let t = 0;
  for (const v of vibrations) {
    t += v.delay || 0;
    const intensity = Math.max(0, Math.min(1, v.intensity == null ? defaultIntensity : v.intensity));
    const step = CLICK_MIN_MS + (1 - intensity) * CLICK_RANGE_MS;
    for (let u = 0; u < v.duration; u += step) out.push(Math.round(t + u));
    t += v.duration;
  }
  return out;
}

export class CueLabHaptics {
  constructor(library = {}, options = {}) {
    this.library = library;
    this.unlocked = false;
    this.timers = [];
    this.rafId = null;
    this.label = null;
    this.input = null;
    this.clicks = 0;
    this.force = 'auto';                       // auto | vibrate | switch
    this.showSwitch = !!options.showSwitch;    // показать переключатель на экране
    this.debug = !!options.debug;              // щёлкать переключателем и там, где есть vibrate
    this.last = { id: null, chunks: [], clicks: 0, result: null, mode: null, engine: null };
    this.hasVibrate = typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function';
    this.hasSwitch = (() => {
      try { return 'switch' in document.createElement('input'); } catch (_) { return false; }
    })();
    this.isIOS = typeof navigator !== 'undefined' &&
      (/iPhone|iPad|iPod/i.test(navigator.userAgent) ||
       (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1));
    ['pointerdown', 'touchstart', 'keydown'].forEach(type =>
      window.addEventListener(type, () => this.unlock(), { once: true, passive: true }));
  }

  get engine() {
    if (this.force === 'switch') return 'switch';
    if (this.force === 'vibrate') return this.hasVibrate ? 'vibration-api' : 'none';
    return this.hasVibrate ? 'vibration-api' : 'switch';
  }

  setEngine(mode) { this.force = mode; this.cancel(); }

  /* Разметка ровно как в web-haptics: label с for, input внутри, оба в
     display:none, если переключатель не показываем. Кликается label. */
  ensureDOM() {
    if (this.label || typeof document === 'undefined') return;
    const id = 'cuelab-haptics-switch';
    const label = document.createElement('label');
    label.setAttribute('for', id);
    label.textContent = 'Вибро';
    label.style.cssText = 'position:fixed;bottom:10px;left:10px;padding:5px 10px;' +
      'background:rgba(0,0,0,.7);color:#fff;font:14px sans-serif;border-radius:4px;' +
      'z-index:9999;user-select:none;display:flex;gap:8px;align-items:center';
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
    this.label.style.display = on ? 'flex' : 'none';
    this.input.style.display = on ? '' : 'none';
  }

  setDebug(on) { this.debug = on; }

  unlock() {
    if (this.unlocked) return;
    this.unlocked = true;
    if (this.hasVibrate) { try { navigator.vibrate(0); } catch (_) {} }
  }

  cancel() {
    this.timers.forEach(clearTimeout);
    this.timers = [];
    if (this.rafId !== null) { cancelAnimationFrame(this.rafId); this.rafId = null; }
    if (this.hasVibrate) { try { navigator.vibrate(0); } catch (_) {} }
  }

  /* Один щелчок. Клик по label фокусирует чекбокс, и браузер подкручивает
     фокус в кадр — страница прыгает. Позицию снимаем до и возвращаем после:
     фокусный скролл происходит синхронно внутри dispatch. */
  click() {
    if (!this.label) return;
    const sx = window.scrollX, sy = window.scrollY;
    try { this.label.click(); this.clicks += 1; } catch (_) {}
    if (window.scrollX !== sx || window.scrollY !== sy) window.scrollTo(sx, sy);
  }

  /**
   * Серия щелчков по паттерну.
   *
   * Кадровый цикл, а не цепочка setTimeout: на интервале 16 мс таймеры копят
   * дрейф и уезжают от звука. На каждом кадре смотрим, в каком отрезке
   * паттерна мы находимся, и щёлкаем, если с прошлого щелчка прошло
   * 16 + (1 - сила) * 184 мс.
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
    const total = end;
    let start = 0;
    let lastClick = -1;
    let fired = firedAtStart;
    const step = (now) => {
      if (!start) start = now;
      const t = now - start;
      if (t >= total) { this.rafId = null; return; }
      let span = spans[0];
      for (const s of spans) { if (t < s.end) { span = s; break; } }
      if (span.on) {
        const gap = CLICK_MIN_MS + (1 - span.intensity) * CLICK_RANGE_MS;
        if (lastClick === -1) {
          if (!fired) { this.click(); fired = true; }
          lastClick = now;
        } else if (now - lastClick >= gap) {
          this.click();
          lastClick = now;
        }
      }
      this.rafId = requestAnimationFrame(step);
    };
    this.rafId = requestAnimationFrame(step);
  }

  /**
   * Проиграть паттерн. Вызывать синхронно из обработчика жеста.
   * @param {Array|string} pattern  [{delay,duration,intensity}] или имя пресета
   */
  trigger(pattern, { intensity = 0.5, label = null } = {}) {
    this.unlock();
    this.cancel();
    const vibrations = (typeof pattern === 'string' ? PRESETS[pattern] : pattern) || [];
    if (!vibrations.length) return false;
    for (const v of vibrations) if (v.duration > MAX_DURATION_MS) v.duration = MAX_DURATION_MS;

    const engine = this.engine;
    let chunks = [];
    if (engine === 'vibration-api') {
      chunks = toChunks(toFlat(vibrations, intensity));
      chunks.forEach((chunk, index) => {
        const fire = () => {
          try {
            const ok = navigator.vibrate(chunk.pattern);
            if (index === 0) this.last.result = ok;
          } catch (_) {}
        };
        if (chunk.at <= 0) fire();
        else this.timers.push(setTimeout(fire, chunk.at));
      });
    }

    let clicks = 0;
    if (engine === 'switch' || this.debug) {
      this.ensureDOM();
      if (this.label) {
        // Первый щелчок — синхронно, внутри жеста: в WebKit это единственный
        // момент, в котором хаптик проходит гарантированно.
        const immediate = (vibrations[0].delay || 0) === 0;
        if (immediate) this.click();
        this.runPattern(vibrations, intensity, immediate);
        clicks = clickTimes(vibrations, intensity).length;
      }
    }

    this.last = {
      id: label, chunks, clicks, mode: this.last.mode, engine,
      result: engine === 'switch' ? `щелчков: ${clicks}` : this.last.result,
    };
    return true;
  }

  /** Хаптик звука из библиотеки. */
  play(id, { mode = 'dense' } = {}) {
    const entry = this.library[id];
    if (!entry) return false;
    const pattern = mode === 'simple'
      // «простой» режим: один импульс, как делает большинство библиотек
      ? [{ duration: 25, intensity: 0.7 }]
      : (entry.pattern || [{ duration: 25, intensity: 0.7 }]);
    const ok = this.trigger(pattern, { intensity: 0.7, label: id });
    this.last.mode = mode;
    return ok;
  }

  /** Ровная вибрация заданной длины. */
  sustain(durationMs = 1000, intensity = 1) {
    return this.trigger([{ duration: Math.min(durationMs, MAX_DURATION_MS), intensity }],
                        { intensity, label: 'sustain' });
  }

  /** Сырой паттерн Vibration API — стенд. */
  raw(flat) {
    this.unlock();
    this.cancel();
    const vibrations = [];
    for (let i = 0; i < flat.length; i += 2) {
      const item = { duration: flat[i], intensity: 1 };
      if (i > 0) item.delay = flat[i - 1];
      vibrations.push(item);
    }
    return this.trigger(vibrations, { intensity: 1, label: 'raw' });
  }
}

export default CueLabHaptics;
