//  CueLabHaptics.kt — общий проигрыватель звука и вибро для всей библиотеки.
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
