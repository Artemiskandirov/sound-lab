//  CueLabHaptics.swift — общий проигрыватель звука и вибро для всей библиотеки.
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
