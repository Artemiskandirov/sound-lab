"""
Выгрузка библиотеки для трёх платформ.

Ключевая мысль: у платформ разные возможности, и одинаковый файл для всех —
это обеднение самой сильной из них.

  web      — Vibration API не умеет амплитуду, силу приходится кодировать
             длительностью импульса; плюс браузер обрезает паттерны длиннее
             примерно десяти элементов;
  ios      — Core Haptics принимает десятки событий с отдельными
             HapticIntensity и HapticSharpness;
  android  — VibrationEffect.createWaveform задаёт амплитуду 0..255 на каждый
             отрезок, поэтому сила передаётся честно.
"""
import json
import os
import re
import shutil
import subprocess
import wave

import numpy as np

import haptics
import haptics_dense as HD
import haptics_rich as HR
import native as NAT
import tactile as T
import render_all as R
from check import profile
from dsp import SR

ROOT = '../cuelab-production-v13/export'


def clean(path):
    if os.path.exists(path):
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)


def write_wav(path, y, sr=SR):
    y = np.asarray(y)
    channels = 2 if y.ndim == 2 else 1
    data = (np.clip(y, -1, 1) * 32767).astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())


def ff(args):
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error'] + args, check=True)


def raw_name(sid, index):
    """
    Имя под Android res/raw: только строчные латинские, цифры и подчёркивание,
    и начинаться должно с буквы. Дефисы в именах ресурсов Android не допускает —
    без переименования проект просто не соберётся.
    """
    name = f'cue_{sid}_{index}'.lower()
    name = re.sub(r'[^a-z0-9_]', '_', name)
    return re.sub(r'_+', '_', name)


SWIFT = '''//  CueLabHaptics.swift — общий проигрыватель звука и вибро для всей библиотеки.
//
//  В вебе вибрация ИМИТИРУЕТСЯ: там единственный доступный рычаг — частота
//  щелчков скрытого переключателя. Здесь имитировать нечего. Core Haptics
//  принимает непрерывные события с кривыми параметров, поэтому паттерн
//  устроен принципиально иначе:
//
//    HapticContinuous на каждый звучащий участок,
//    HapticTransient  на каждую атаку — со своей силой и резкостью,
//    ParameterCurve HapticIntensityControl — множитель силы 0…1 по огибающей
//        громкости, посчитанной по кривой A (IEC 61672), а не по энергии:
//        ухо на 3 кГц чувствительнее, чем на 200 Гц, примерно на 10 дБ;
//    ParameterCurve HapticSharpnessControl — СДВИГ резкости −1…1 по
//        спектральному центроиду. Именно сдвиг, а не множитель, поэтому
//        базовая резкость события 0.5, а кривая уводит её в обе стороны.
//
//  Из-за этого гонг ощущается низким тяжёлым гулом, а свисток — тонкой иглой,
//  хотя громкость у них одна.

import AVFoundation
import CoreHaptics
import UIKit

public final class CueLab {

    public static let shared = CueLab()

    private var engine: CHHapticEngine?
    private var players: [String: CHHapticPatternPlayer] = [:]
    private var sounds: [String: AVAudioPlayer] = [:]
    private let supportsHaptics = CHHapticEngine.capabilitiesForHardware().supportsHaptics

    private init() {
        startEngine()
    }

    // MARK: - Движок

    private func startEngine() {
        guard supportsHaptics else { return }
        engine = try? CHHapticEngine()
        // Движок гасят звонок, сворачивание приложения и переключение сцены.
        // Без этих обработчиков хаптик тихо перестаёт играть после первого же
        // перерыва, и со стороны это выглядит как «вибро сломалось».
        engine?.resetHandler = { [weak self] in
            guard let self else { return }
            try? self.engine?.start()
            self.players.removeAll()          // плееры умерли вместе с движком
        }
        engine?.stoppedHandler = { reason in
            print("CueLab: движок остановлен — \(reason.rawValue)")
        }
        engine?.playsHapticsOnly = true
        engine?.isAutoShutdownEnabled = true
        try? engine?.start()
    }

    // MARK: - Воспроизведение

    /// Звук и вибро с общего момента. Расхождение больше ~20 мс уже читается
    /// как рассинхрон, поэтому обе дорожки стартуют из одного вызова.
    public func play(_ id: String, variant: Int = 0, withSound: Bool = true) {
        if withSound { playSound(id, variant: variant) }
        playHaptic(id)
    }

    public func playHaptic(_ id: String) {
        guard supportsHaptics else {
            // iPhone 6s и старше, все iPad: Core Haptics нет, остаётся
            // системный отклик — беднее, но лучше тишины.
            UIImpactFeedbackGenerator(style: .medium).impactOccurred()
            return
        }
        do {
            try engine?.start()
            try player(for: id)?.start(atTime: CHHapticTimeImmediate)
        } catch {
            // Одна попытка перезапуска: движок мог остановиться между
            // подготовкой и нажатием.
            try? engine?.start()
            players[id] = nil
            try? player(for: id)?.start(atTime: CHHapticTimeImmediate)
        }
    }

    public func playSound(_ id: String, variant: Int = 0) {
        let key = "\(id)-\(variant)"
        if sounds[key] == nil,
           let url = Bundle.main.url(forResource: key, withExtension: "m4a",
                                     subdirectory: "CueLabAudio") {
            sounds[key] = try? AVAudioPlayer(contentsOf: url)
            sounds[key]?.prepareToPlay()
        }
        sounds[key]?.currentTime = 0
        sounds[key]?.play()
    }

    public func stop(_ id: String) {
        try? players[id]?.stop(atTime: CHHapticTimeImmediate)
    }

    /// Плееры кэшируются: разбор AHAP и makePlayer стоят миллисекунды, а
    /// хаптик обязан стартовать в тот же кадр, что и нажатие.
    private func player(for id: String) -> CHHapticPatternPlayer? {
        if let existing = players[id] { return existing }
        guard let engine,
              let url = Bundle.main.url(forResource: id, withExtension: "ahap",
                                        subdirectory: "CueLabHaptics"),
              let pattern = try? CHHapticPattern(contentsOf: url),
              let made = try? engine.makePlayer(with: pattern) else { return nil }
        players[id] = made
        return made
    }

    /// Прогрев перед экраном, где вибро пойдёт часто.
    public func preload(_ ids: [String]) {
        ids.forEach { _ = player(for: $0) }
    }
}
'''

KOTLIN = '''//  CueLabHaptics.kt — общий проигрыватель звука и вибро для всей библиотеки.
//
//  В вебе силу приходится кодировать частотой щелчков: амплитуды у Vibration
//  API нет. Здесь она есть, поэтому передаётся честно. Три пути, от лучшего
//  к запасному, выбор делается по возможностям мотора:
//
//    1. VibrationEffect.Composition (API 30+) — примитивы на атаках. Примитив
//       отрабатывается мотором со своей огибающей и ощущается чище
//       прямоугольного импульса. TICK для звонкого, CLICK для среднего,
//       THUD для глухого — тип выбран по спектральному центроиду атаки.
//    2. createWaveform с амплитудами 0..255 — огибающая громкости с шагом
//       16 мс, посчитанная по кривой A, а не по энергии.
//    3. createWaveform без амплитуд — на моторах без hasAmplitudeControl()
//       остаётся ритм.
//
//  Данные лежат в assets/haptics.json, звуки — в res/raw.

package cuelab

import android.content.Context
import android.media.AudioAttributes
import android.media.SoundPool
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import org.json.JSONObject

class CueLab(private val context: Context) {

    private val vibrator: Vibrator =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            context.getSystemService(VibratorManager::class.java).defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            context.getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
        }

    // Хаптик интерфейса — отклик на действие, а не уведомление: с этим
    // usage его не заглушит режим «не беспокоить».
    private val attrs = AudioAttributes.Builder()
        .setUsage(AudioAttributes.USAGE_ASSISTANCE_SONIFICATION)
        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
        .build()

    private val pool = SoundPool.Builder().setMaxStreams(8)
        .setAudioAttributes(attrs).build()

    private val data: JSONObject by lazy {
        context.assets.open("haptics.json").bufferedReader().use {
            JSONObject(it.readText())
        }
    }
    private val soundIds = mutableMapOf<String, Int>()

    /** Звук и вибро с одного вызова: расхождение больше ~20 мс уже читается. */
    fun play(id: String, variant: Int = 0) {
        playSound(id, variant)
        playHaptic(id)
    }

    fun playSound(id: String, variant: Int = 0) {
        val name = "cue_${id.replace('-', '_')}_$variant"
        val key = name
        val res = context.resources.getIdentifier(name, "raw", context.packageName)
        if (res == 0) return
        val sid = soundIds.getOrPut(key) { pool.load(context, res, 1) }
        pool.play(sid, 1f, 1f, 1, 0, 1f)
    }

    fun playHaptic(id: String) {
        if (!vibrator.hasVibrator()) return
        val cue = data.optJSONObject(id) ?: return

        composition(cue)?.let { vibrator.vibrate(it, attrs); return }

        val timings = cue.getJSONArray("timings")
        val amplitudes = cue.getJSONArray("amplitudes")
        val t = LongArray(timings.length()) { timings.getLong(it) }
        val a = IntArray(amplitudes.length()) { amplitudes.getInt(it) }
        val effect = if (vibrator.hasAmplitudeControl()) {
            VibrationEffect.createWaveform(t, a, -1)
        } else {
            VibrationEffect.createWaveform(t, -1)
        }
        vibrator.vibrate(effect, attrs)
    }

    fun stop() = vibrator.cancel()

    /** null, если устройство не умеет нужные примитивы — тогда идём в waveform. */
    private fun composition(cue: JSONObject): VibrationEffect? {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return null
        val list = cue.optJSONArray("composition") ?: return null
        if (list.length() == 0) return null

        val ids = (0 until list.length()).map { primitiveId(list.getJSONObject(it).getString("primitive")) }
        if (!vibrator.areAllPrimitivesSupported(*ids.toIntArray())) return null

        var composition = VibrationEffect.startComposition()
        for (i in 0 until list.length()) {
            val item = list.getJSONObject(i)
            composition = composition.addPrimitive(
                primitiveId(item.getString("primitive")),
                item.getDouble("scale").toFloat(),
                item.getInt("delayMs"),
            )
        }
        return composition.compose()
    }

    private fun primitiveId(name: String): Int = when (name) {
        "TICK" -> VibrationEffect.Composition.PRIMITIVE_TICK
        "THUD" -> VibrationEffect.Composition.PRIMITIVE_THUD
        else -> VibrationEffect.Composition.PRIMITIVE_CLICK
    }
}
'''

WEB_JS = '''/*  cuelab-haptics.js — вибро CueLab для веба.
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
'''


def main():
    clean(ROOT)
    for sub in ['masters', 'web/audio', 'ios/audio', 'ios/haptics', 'android/res/raw']:
        os.makedirs(f'{ROOT}/{sub}', exist_ok=True)

    manifest = []
    web_patterns = {}
    android_map = {}
    sizes = {'masters': 0, 'web': 0, 'ios': 0, 'android': 0}

    for category, items in R.CATALOG:
        for sid, title, note, _ in items:
            count = 1 if sid in R.SINGLE else R.VARIANTS.get(sid, R.DEFAULT_VARIANTS)
            files = []
            first = None
            for i in range(count):
                y = R.render_variant(sid, i)
                if first is None:
                    first = y
                # Мастер во FLAC: без потерь, вдвое меньше WAV.
                # Обратно в WAV — одной командой ffmpeg.
                wav_tmp = f'/tmp/master-{sid}-{i}.wav'
                write_wav(wav_tmp, y)
                master = f'{ROOT}/masters/{sid}-{i}.flac'
                ff(['-i', wav_tmp, '-c:a', 'flac', '-compression_level', '8', master])
                sizes['masters'] += os.path.getsize(master)

                seconds = len(y) / SR
                stereo = y.ndim == 2
                rate = '56k' if seconds < 0.35 else '72k' if seconds < 1.2 else '96k'
                if stereo:
                    rate = '96k' if seconds < 1.2 else '112k'

                master = wav_tmp   # для перекодировки берём несжатый временный
                web_ogg = f'{ROOT}/web/audio/{sid}-{i}.ogg'
                web_aac = f'{ROOT}/web/audio/{sid}-{i}.m4a'
                ff(['-i', master, '-c:a', 'libopus', '-b:a', rate, '-vbr', 'on',
                    '-application', 'audio', web_ogg])
                ff(['-i', master, '-c:a', 'aac', '-b:a', rate, '-movflags', '+faststart', web_aac])
                sizes['web'] += os.path.getsize(web_ogg) + os.path.getsize(web_aac)

                # iOS: AAC в m4a — родной для AVAudioPlayer
                ios_m4a = f'{ROOT}/ios/audio/{sid}-{i}.m4a'
                shutil.copyfile(web_aac, ios_m4a)
                sizes['ios'] += os.path.getsize(ios_m4a)

                # Android: ogg, имя под res/raw
                raw = raw_name(sid, i)
                and_ogg = f'{ROOT}/android/res/raw/{raw}.ogg'
                shutil.copyfile(web_ogg, and_ogg)
                sizes['android'] += os.path.getsize(and_ogg)

                files.append({
                    'index': i,
                    'master': f'masters/{sid}-{i}.flac',
                    'opus': f'audio/{sid}-{i}.ogg',
                    'aac': f'audio/{sid}-{i}.m4a',
                    'androidRes': raw,
                    'bytes': os.path.getsize(web_ogg),
                })
                os.remove(wav_tmp)

            mono = first.mean(axis=1) if first.ndim == 2 else first
            p = profile(mono)
            web_pat = haptics.pattern(first)
            # Огибающая громкости — по кривой A, а не по энергии: ухо на
            # 3 кГц чувствительнее, чем на 200 Гц, примерно на 10 дБ.
            # Яркость — спектральный центроид по кадрам.
            level = T.loudness_env(first, SR)
            bright = T.brightness(first, SR)
            env100 = [int(round(v * 100)) for v in level]
            bright100 = [int(round(v * 100)) for v in bright]
            env_step_ms = int(T.FRAME_MS)

            onset_t, flux = haptics.onsets(first, SR)
            native_onsets = []
            if len(onset_t):
                norm = flux / (flux.max() + 1e-9)
                for t, w in zip(onset_t, norm):
                    k = min(len(level) - 1, int(round(t * 1000 / T.FRAME_MS)))
                    strength = float(np.clip(max(level[k], 0.35 + 0.65 * w ** 0.55), 0.05, 1.0))
                    native_onsets.append((t * 1000, strength, float(bright[k])))

            # Веб: отрезки {delay, duration, intensity} формата web-haptics.
            webh = T.segments(level, bright, onset_ms=[t * 1000 for t in onset_t])
            flat = HD.to_flat_web(webh, 0.7)
            chunks = HD.to_chunks_web(flat)
            clicks = HD.click_times(webh, 0.7)

            # Нативный хаптик строится не из россыпи событий, а из непрерывных
            # событий с кривыми параметров — см. native.py.
            ahap = NAT.ahap(level, bright, native_onsets, sid)
            android = NAT.android(level, bright, native_onsets)
            evs = [{'time': round(t / 1000, 4), 'intensity': round(st, 3),
                    'sharpness': round(sh, 3)} for t, st, sh in native_onsets]

            with open(f'{ROOT}/ios/haptics/{sid}.ahap', 'w', encoding='utf-8') as f:
                json.dump(ahap, f, ensure_ascii=False, indent=1)
            sizes['ios'] += os.path.getsize(f'{ROOT}/ios/haptics/{sid}.ahap')

            web_patterns[sid] = {
                'pattern': webh, 'chunks': chunks, 'clicks': len(clicks),
            }
            android_map[sid] = {**android, 'variants': len(files)}

            manifest.append({
                'id': sid, 'title': title, 'note': note, 'category': category,
                'variants': files, 'stereo': bool(first.ndim == 2),
                'durationMs': round(len(first) / SR * 1000),
                'centroidHz': round(p['centroid']), 'lowPct': round(p['low'] * 100, 1),
                'midPct': round(p['mid'] * 100, 1), 'flatness': round(p['flat'], 3),
                'haptic': web_pat,
                'hapticPulses': haptics.pulses(web_pat),
                'hapticEvents': evs,
                'ahap': f'haptics/{sid}.ahap',
                # Плотная дорожка: повторяет огибающую звука. Играется
                # несколькими вызовами vibrate() — спецификация режет паттерн
                # до десяти записей, поэтому длинное вибро идёт чанками.
                'pattern': webh,
                'webHaptics': webh,
                'chunks': chunks,
                'clicks': len(clicks),
                'clickGapMs': int(sorted(clicks[i + 1] - clicks[i]
                                         for i in range(len(clicks) - 1))[len(clicks) // 2])
                              if len(clicks) > 1 else 16,
                'env': env100,
                'bright': bright100,
                'envStepMs': env_step_ms,
                'webHaptics': webh,
            })
        print(f'{category:22s} {len(items):3d}')

    with open(f'{ROOT}/web/cuelab-sounds.json', 'w', encoding='utf-8') as f:
        json.dump({'sampleRate': SR, 'sounds': manifest}, f, ensure_ascii=False, indent=1)
    with open(f'{ROOT}/web/cuelab-haptics.json', 'w', encoding='utf-8') as f:
        json.dump(web_patterns, f, ensure_ascii=False, indent=1)
    with open(f'{ROOT}/web/cuelab-haptics.js', 'w', encoding='utf-8') as f:
        f.write(WEB_JS)
    shutil.copyfile(f'{ROOT}/web/cuelab-sounds.json', f'{ROOT}/ios/cuelab-sounds.json')
    with open(f'{ROOT}/ios/CueLabHaptics.swift', 'w', encoding='utf-8') as f:
        f.write(SWIFT)
    os.makedirs(f'{ROOT}/android/assets', exist_ok=True)
    with open(f'{ROOT}/android/assets/haptics.json', 'w', encoding='utf-8') as f:
        json.dump({'sounds': android_map}, f, ensure_ascii=False, indent=1)
    with open(f'{ROOT}/android/CueLabHaptics.kt', 'w', encoding='utf-8') as f:
        f.write(KOTLIN)

    with open(f'{ROOT}/MANIFEST.json', 'w', encoding='utf-8') as f:
        json.dump({
            'sounds': len(manifest),
            'variants': sum(len(m['variants']) for m in manifest),
            'categories': len({m['category'] for m in manifest}),
            'platforms': {
                'web': {'audio': 'opus + aac', 'haptics': 'cuelab-haptics.js',
                        'amplitude': False, 'maxPatternEntries': 9},
                'ios': {'audio': 'm4a (aac)', 'haptics': 'ahap',
                        'amplitude': True, 'sharpness': True},
                'android': {'audio': 'ogg в res/raw', 'haptics': 'VibrationEffect.createWaveform',
                            'amplitude': True, 'sharpness': False},
            },
            'bytes': sizes,
        }, f, ensure_ascii=False, indent=1)

    print()
    for k, v in sizes.items():
        print(f'{k:10s} {v / 1024 / 1024:6.1f} МБ')
    print(f'\nзвуков {len(manifest)}, вариантов {sum(len(m["variants"]) for m in manifest)}')


if __name__ == '__main__':
    main()
