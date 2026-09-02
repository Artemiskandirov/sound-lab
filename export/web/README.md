# CueLab — веб

## Установка

Скопируйте `audio/`, `cuelab-sounds.json`, `cuelab-haptics.json` и
`cuelab-haptics.js` в статику.

```js
import CueLabHaptics from './cuelab-haptics.js';

const patterns = await (await fetch('/cuelab-haptics.json')).json();
const haptics = new CueLabHaptics(patterns);

button.addEventListener('click', () => {
  haptics.play('tap');   // строго синхронно из обработчика жеста
  playSound('tap');
});
```

## Два формата звука — это не перестраховка

Ни один кодек не покрывает все браузеры: **AAC не декодируется в открытых
сборках Chromium**, **Vorbis не поддерживает Safari**. Пробуйте Opus первым и
падайте на AAC при ошибке декодирования:

```js
async function decode(ctx, variant) {
  for (const key of ['opus', 'aac']) {
    try {
      const r = await fetch(variant[key]);
      return await ctx.decodeAudioData(await r.arrayBuffer());
    } catch (_) { /* пробуем следующий */ }
  }
  throw new Error('нет пригодного формата');
}
```

Если в проде только реальные браузеры — можно оставить один Opus и уполовинить
вес.

## Варианты

У повторяющихся звуков несколько вариантов: у тика прокрутки десять, у
микротика восемь, у нажатия шесть. Меняйте их по кругу — одинаковость повторов
выдаёт синтетику первой.

## Движок — порт web-haptics

MIT, © 2025 Lochie Axon, https://github.com/lochie/web-haptics. Формат паттерна
тот же: `[{delay, duration, intensity}, ...]`, где `delay` — пауза ПЕРЕД
импульсом, а `duration` — отрезок, внутри которого вибрация ДЕРЖИТСЯ.

```js
import CueLabHaptics from './cuelab-haptics.js';

const lib = await (await fetch('/cuelab-haptics.json')).json();
const haptics = new CueLabHaptics(lib);

button.addEventListener('click', () => {
  haptics.play('tap');            // паттерн из библиотеки
  haptics.trigger('success');     // пресет web-haptics
  haptics.sustain(1000, 1);       // ровная вибрация на секунду
});
```

Отладка: `new CueLabHaptics(lib, { showSwitch: true, debug: true })` покажет
переключатель внизу слева и будет щёлкать им даже там, где есть `vibrate`.

## Три вещи, которые легко упустить

**Частота щелчков на iOS.** `navigator.vibrate` отсутствует в Safari на iOS,
iPadOS и macOS во всех версиях, а все браузеры на iPhone работают на WebKit.
Единственный системный хаптик, доступный вебу, — тик переключателя
`<input type="checkbox" switch>`. Непрерывной вибрации там нет как примитива,
она складывается из щелчков, и интервал между ними равен

```
16 + (1 - intensity) * 184 мс
```

На полной силе это каждый кадр. На интервале в 30–90 мс получается пунктир, а
не вибрация — проверено на своей шкуре.

**Элемент.** `<label for=id>` с `<input type="checkbox" switch>` внутри, оба в
`display:none`, у input `all:initial; appearance:auto`. Кликается **label**.
`display:none` хаптику не мешает.

**Амплитуда на Android.** У Vibration API силы нет. Импульс режется на окна по
20 мс, доля включённого равна силе — широтно-импульсная модуляция. Сила 0,55 на
180 мс даёт `[11, 9, 11, 9, ...]`. Мотор успевает отработать, и слабое
ощущается слабым, а не просто коротким.

## Плюс нарезка на куски

Спецификация Vibration API: «Let *max length* have the value 10. If the length
of the *pattern* is greater than *max length*, truncate *pattern*». Активация
при этом sticky, а не transient, поэтому длинный паттерн режется на куски по
десять записей и выдаётся по таймеру встык. В самом web-haptics этого нет —
длинный паттерн на Android обрывается на десятой записи. Готовые куски лежат в
`cuelab-haptics.json` в поле `chunks`.

## Побочный эффект, о котором стоит знать

Клик по `<label>` фокусирует чекбокс, а браузер подкручивает фокус в кадр —
страница прыгает на каждом щелчке. При шестидесяти щелчках в секунду прокрутка
уезжает на тысячи пикселей. Модуль снимает позицию до клика и возвращает сразу
после: фокусный скролл происходит синхронно внутри dispatch, так что этого
достаточно и мигания не видно.

## Оговорка

Хаптик на программное переключение Apple нигде не обещает — это обход, а не
документированный API. При включённом «Уменьшении движения», в фоне и на части
устройств он может не сработать. Для гарантии нужен нативный слой с Core
Haptics; AHAP лежит в `../ios/`.
