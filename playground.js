/*  Песочница: интерактивные элементы, у каждого свой звук и синхронное вибро.
 *
 *  Правило одно и оно важное: и звук, и хаптик запускаются СИНХРОННО из
 *  обработчика жеста. Vibration API требует пользовательской активации, а
 *  в Safari системный хаптик вообще срабатывает только в момент касания —
 *  любой setTimeout между жестом и вызовом ломает вибрацию.
 */

export function buildPlayground(root, fire) {
  const el = (tag, cls, html) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html !== undefined) n.innerHTML = html;
    return n;
  };

  /** Карточка элемента: заголовок, тело, подпись с именем звука. */
  const card = (title, note, body) => {
    const c = el('div', 'pg-card');
    c.appendChild(el('div', 'pg-head', `<strong>${title}</strong><small>${note}</small>`));
    const b = el('div', 'pg-body');
    b.appendChild(body);
    c.appendChild(b);
    return c;
  };

  const groups = [];
  const group = (name) => {
    const g = { name, items: [] };
    groups.push(g);
    return g;
  };

  // ------------------------------------------------------------- КНОПКИ
  const g1 = group('Кнопки и касания');

  const btn = (label, cls, sound) => {
    const b = el('button', `pg-btn ${cls}`, label);
    b.addEventListener('click', () => fire(sound));
    return b;
  };
  g1.items.push(card('Основная кнопка', 'tap', btn('Продолжить', '', 'tap')));
  g1.items.push(card('Вторичная', 'tap-soft', btn('Позже', 'soft', 'tap-soft')));
  g1.items.push(card('Опасное действие', 'tap-heavy', btn('Удалить', 'danger', 'tap-heavy')));
  g1.items.push(card('Иконка', 'micro-blip', (() => {
    const b = el('button', 'pg-icon', '★');
    b.addEventListener('click', () => fire('micro-blip'));
    return b;
  })()));

  g1.items.push(card('Двойное касание', 'micro-tick, затем coin', (() => {
    const b = el('button', 'pg-btn soft', 'Тапни дважды');
    let last = 0;
    b.addEventListener('click', () => {
      const now = performance.now();
      if (now - last < 320) { fire('coin'); b.textContent = 'Двойное!'; }
      else { fire('micro-tick'); b.textContent = 'Тапни дважды'; }
      last = now;
    });
    return b;
  })()));

  g1.items.push(card('Удержание', 'long-press', (() => {
    const wrap = el('div', 'pg-hold');
    const b = el('button', 'pg-btn', 'Держи');
    const bar = el('div', 'pg-hold-bar');
    const fill = el('i');
    bar.appendChild(fill);
    let timer = 0, start = 0, raf = 0;
    const stop = ok => {
      clearTimeout(timer); cancelAnimationFrame(raf);
      fill.style.width = '0%';
      b.textContent = ok ? 'Готово' : 'Держи';
    };
    b.addEventListener('pointerdown', () => {
      fire('tap-soft');
      start = performance.now();
      const step = () => {
        const p = Math.min(1, (performance.now() - start) / 900);
        fill.style.width = `${p * 100}%`;
        if (p < 1) raf = requestAnimationFrame(step);
      };
      raf = requestAnimationFrame(step);
      timer = setTimeout(() => { fire('long-press'); stop(true); }, 900);
    });
    ['pointerup', 'pointerleave', 'pointercancel'].forEach(t =>
      b.addEventListener(t, () => stop(false)));
    wrap.appendChild(b); wrap.appendChild(bar);
    return wrap;
  })()));

  // ------------------------------------------------------------- ПЕРЕКЛЮЧАТЕЛИ
  const g2 = group('Переключатели и выбор');

  g2.items.push(card('Переключатель', 'toggle-on / toggle-off', (() => {
    const t = el('button', 'pg-toggle', '<i></i>');
    t.addEventListener('click', () => {
      const on = !t.classList.contains('is-on');
      t.classList.toggle('is-on', on);
      fire(on ? 'toggle-on' : 'toggle-off');
    });
    return t;
  })()));

  g2.items.push(card('Чекбоксы', 'answer-select / dismiss', (() => {
    const wrap = el('div', 'pg-col');
    ['Звук', 'Хаптик', 'Анимация'].forEach(label => {
      const row = el('button', 'pg-check', `<i></i><span>${label}</span>`);
      row.addEventListener('click', () => {
        const on = !row.classList.contains('is-on');
        row.classList.toggle('is-on', on);
        fire(on ? 'answer-select' : 'dismiss');
      });
      wrap.appendChild(row);
    });
    return wrap;
  })()));

  g2.items.push(card('Радиогруппа', 'tab-switch', (() => {
    const wrap = el('div', 'pg-col');
    ['Лёгкий', 'Обычный', 'Сложный'].forEach((label, i) => {
      const row = el('button', `pg-radio ${i === 1 ? 'is-on' : ''}`, `<i></i><span>${label}</span>`);
      row.addEventListener('click', () => {
        wrap.querySelectorAll('.pg-radio').forEach(r => r.classList.remove('is-on'));
        row.classList.add('is-on');
        fire('tab-switch');
      });
      wrap.appendChild(row);
    });
    return wrap;
  })()));

  g2.items.push(card('Сегменты', 'tab-switch', (() => {
    const wrap = el('div', 'pg-seg');
    ['День', 'Неделя', 'Месяц'].forEach((label, i) => {
      const b = el('button', i === 0 ? 'is-on' : '', label);
      b.addEventListener('click', () => {
        wrap.querySelectorAll('button').forEach(x => x.classList.remove('is-on'));
        b.classList.add('is-on');
        fire('tab-switch');
      });
      wrap.appendChild(b);
    });
    return wrap;
  })()));

  g2.items.push(card('Чипы-фильтры', 'answer-select / dismiss', (() => {
    const wrap = el('div', 'pg-chips');
    ['Дерево', 'Камень', 'Металл', 'Стекло', 'Свистки'].forEach(label => {
      const b = el('button', '', label);
      b.addEventListener('click', () => {
        const on = !b.classList.contains('is-on');
        b.classList.toggle('is-on', on);
        fire(on ? 'answer-select' : 'dismiss');
      });
      wrap.appendChild(b);
    });
    return wrap;
  })()));

  g2.items.push(card('Выпадающий список', 'modal-open / scroll-snap', (() => {
    const wrap = el('div', 'pg-select');
    const head = el('button', 'pg-btn soft', 'Выбрать материал ▾');
    const list = el('div', 'pg-select-list');
    ['Маримба', 'Вудблок', 'Камень', 'Стекло', 'Металл'].forEach(label => {
      const item = el('button', '', label);
      item.addEventListener('click', () => {
        head.textContent = label + ' ▾';
        list.classList.remove('is-open');
        fire('scroll-snap');
      });
      list.appendChild(item);
    });
    head.addEventListener('click', () => {
      const open = !list.classList.contains('is-open');
      list.classList.toggle('is-open', open);
      fire(open ? 'modal-open' : 'modal-close');
    });
    wrap.appendChild(head); wrap.appendChild(list);
    return wrap;
  })()));

  // ------------------------------------------------------------- ЗНАЧЕНИЯ
  const g3 = group('Значения и шаги');

  g3.items.push(card('Слайдер с засечками', 'scroll-detent на каждой засечке', (() => {
    const wrap = el('div', 'pg-col');
    const input = el('input', 'pg-slider');
    input.type = 'range'; input.min = 0; input.max = 10; input.value = 5;
    const out = el('div', 'pg-value', '5');
    let last = 5;
    input.addEventListener('input', () => {
      const v = Number(input.value);
      out.textContent = v;
      if (v !== last) { last = v; fire('scroll-detent'); }
    });
    input.addEventListener('change', () => fire('scroll-snap'));
    wrap.appendChild(input); wrap.appendChild(out);
    return wrap;
  })()));

  g3.items.push(card('Степпер', 'micro-blip / dismiss', (() => {
    const wrap = el('div', 'pg-stepper');
    const minus = el('button', '', '−');
    const value = el('b', '', '1');
    const plus = el('button', '', '+');
    let n = 1;
    minus.addEventListener('click', () => { if (n > 0) { n--; value.textContent = n; fire('dismiss'); } });
    plus.addEventListener('click', () => { n++; value.textContent = n; fire('micro-blip'); });
    wrap.append(minus, value, plus);
    return wrap;
  })()));

  g3.items.push(card('Рейтинг', 'coin по нарастающей', (() => {
    const wrap = el('div', 'pg-stars');
    for (let i = 1; i <= 5; i++) {
      const s = el('button', '', '★');
      s.addEventListener('click', () => {
        [...wrap.children].forEach((c, j) => c.classList.toggle('is-on', j < i));
        fire(i === 5 ? 'star' : 'coin');
      });
      wrap.appendChild(s);
    }
    return wrap;
  })()));

  g3.items.push(card('Колесо выбора', 'scroll-detent, снап на scroll-snap', (() => {
    const wrap = el('div', 'pg-wheel');
    const inner = el('div', 'pg-wheel-inner');
    for (let i = 0; i <= 30; i += 1) inner.appendChild(el('div', 'pg-wheel-item', `${i} мин`));
    wrap.appendChild(inner);
    let lastNotch = 0, lastTime = 0, snapTimer = 0;
    wrap.addEventListener('scroll', () => {
      const notch = Math.round(wrap.scrollTop / 34);
      const now = performance.now();
      if (notch !== lastNotch && now - lastTime > 34) {
        lastNotch = notch; lastTime = now;
        fire('scroll-detent', { quiet: true });
      }
      clearTimeout(snapTimer);
      snapTimer = setTimeout(() => fire('scroll-snap', { quiet: true }), 160);
    }, { passive: true });
    return wrap;
  })()));

  g3.items.push(card('Прогресс', 'progress-step, высота растёт', (() => {
    const wrap = el('div', 'pg-col');
    const track = el('div', 'pg-progress');
    const fill = el('i');
    track.appendChild(fill);
    const row = el('div', 'pg-row');
    const step = el('button', 'pg-btn soft', 'Шаг');
    const reset = el('button', 'pg-btn soft', 'Сброс');
    let n = 0;
    step.addEventListener('click', () => {
      if (n >= 8) { fire('progress-complete'); return; }
      n++;
      fill.style.width = `${n / 8 * 100}%`;
      if (n === 8) fire('progress-complete');
      else fire('progress-step', { pitch: n - 1 });
    });
    reset.addEventListener('click', () => { n = 0; fill.style.width = '0%'; fire('dismiss'); });
    row.append(step, reset);
    wrap.append(track, row);
    return wrap;
  })()));

  g3.items.push(card('Счётчик монет', 'coin, затем coin-multi', (() => {
    const wrap = el('div', 'pg-col');
    const out = el('div', 'pg-value big', '0');
    const row = el('div', 'pg-row');
    let n = 0;
    const one = el('button', 'pg-btn soft', '+1');
    const many = el('button', 'pg-btn soft', '+10');
    one.addEventListener('click', () => { n += 1; out.textContent = n; fire('coin'); });
    many.addEventListener('click', () => { n += 10; out.textContent = n; fire('coin-multi'); });
    row.append(one, many);
    wrap.append(out, row);
    return wrap;
  })()));

  // ------------------------------------------------------------- ВВОД
  const g4 = group('Ввод');

  g4.items.push(card('Печать', 'key на каждый символ', (() => {
    const i = el('input', 'pg-input');
    i.placeholder = 'Печатай здесь';
    i.addEventListener('keydown', e => {
      if (e.key.length === 1 || e.key === 'Backspace') fire('key', { quiet: true });
      if (e.key === 'Enter') fire('answer-submit');
    });
    return i;
  })()));

  g4.items.push(card('Поиск с очисткой', 'key, затем dismiss', (() => {
    const wrap = el('div', 'pg-search');
    const i = el('input', 'pg-input');
    i.placeholder = 'Найти';
    const clear = el('button', '', '×');
    i.addEventListener('keydown', e => {
      if (e.key.length === 1 || e.key === 'Backspace') fire('key', { quiet: true });
    });
    clear.addEventListener('click', () => { i.value = ''; fire('dismiss'); });
    wrap.append(i, clear);
    return wrap;
  })()));

  g4.items.push(card('Пин-код', 'micro-tick, успех на correct', (() => {
    const wrap = el('div', 'pg-col');
    const dots = el('div', 'pg-pin');
    for (let i = 0; i < 4; i++) dots.appendChild(el('i'));
    const pad = el('div', 'pg-pad');
    let n = 0;
    for (let d = 1; d <= 9; d++) {
      const b = el('button', '', String(d));
      b.addEventListener('click', () => {
        if (n >= 4) return;
        dots.children[n].classList.add('is-on');
        n++;
        if (n === 4) fire('correct');
        else fire('micro-tick');
      });
      pad.appendChild(b);
    }
    const clr = el('button', 'wide', 'Стереть');
    clr.addEventListener('click', () => {
      n = 0;
      [...dots.children].forEach(c => c.classList.remove('is-on'));
      fire('dismiss');
    });
    pad.appendChild(clr);
    wrap.append(dots, pad);
    return wrap;
  })()));

  // ------------------------------------------------------------- ЖЕСТЫ
  const g5 = group('Жесты и движение');

  g5.items.push(card('Лента с тиками', 'scroll-tick, край на scroll-edge', (() => {
    const list = el('div', 'pg-list');
    ['Сложение', 'Вычитание', 'Умножение', 'Деление', 'Дроби', 'Проценты',
     'Уравнения', 'Периметр', 'Площадь', 'Объём', 'Углы', 'Графики']
      .forEach((t, i) => list.appendChild(el('div', 'pg-list-item', `<i></i>${t}<span>${(i + 1) * 5} мин</span>`)));
    let lastNotch = 0, lastTime = 0;
    list.addEventListener('scroll', () => {
      const notch = Math.round(list.scrollTop / 46);
      const now = performance.now();
      if (notch === lastNotch || now - lastTime < 38) return;
      lastNotch = notch; lastTime = now;
      const atEdge = list.scrollTop <= 0 ||
        list.scrollTop + list.clientHeight >= list.scrollHeight - 1;
      fire(atEdge ? 'scroll-edge' : 'scroll-tick', { quiet: true });
    }, { passive: true });
    return list;
  })()));

  g5.items.push(card('Свайп карточки', 'swipe, удаление на wood-knock', (() => {
    const wrap = el('div', 'pg-swipe');
    const c = el('div', 'pg-swipe-card', 'Тяни влево');
    let startX = 0, dx = 0, dragging = false;
    c.addEventListener('pointerdown', e => {
      dragging = true; startX = e.clientX; c.setPointerCapture(e.pointerId);
      fire('tap-soft', { quiet: true });
    });
    c.addEventListener('pointermove', e => {
      if (!dragging) return;
      dx = Math.min(0, e.clientX - startX);
      c.style.transform = `translateX(${dx}px)`;
      c.style.opacity = String(1 + dx / 300);
    });
    const end = () => {
      if (!dragging) return;
      dragging = false;
      if (dx < -110) {
        fire('wood-knock');
        c.style.transform = 'translateX(-120%)';
        setTimeout(() => {
          c.style.transition = 'none'; c.style.transform = ''; c.style.opacity = '1';
          requestAnimationFrame(() => { c.style.transition = ''; });
        }, 320);
      } else {
        fire('swipe');
        c.style.transform = ''; c.style.opacity = '1';
      }
      dx = 0;
    };
    ['pointerup', 'pointercancel', 'pointerleave'].forEach(t => c.addEventListener(t, end));
    wrap.appendChild(c);
    return wrap;
  })()));

  g5.items.push(card('Перетаскивание', 'tap-soft, посадка на scroll-snap', (() => {
    const wrap = el('div', 'pg-drag');
    const item = el('div', 'pg-drag-item', '⬤');
    const zone = el('div', 'pg-drop', 'Сюда');
    let dragging = false, ox = 0, oy = 0;
    item.addEventListener('pointerdown', e => {
      dragging = true; item.setPointerCapture(e.pointerId);
      const r = item.getBoundingClientRect();
      ox = e.clientX - r.left; oy = e.clientY - r.top;
      item.classList.add('is-drag');
      fire('tap-soft', { quiet: true });
    });
    item.addEventListener('pointermove', e => {
      if (!dragging) return;
      const p = wrap.getBoundingClientRect();
      item.style.left = `${e.clientX - p.left - ox}px`;
      item.style.top = `${e.clientY - p.top - oy}px`;
      const z = zone.getBoundingClientRect();
      zone.classList.toggle('is-over',
        e.clientX > z.left && e.clientX < z.right && e.clientY > z.top && e.clientY < z.bottom);
    });
    const drop = e => {
      if (!dragging) return;
      dragging = false;
      item.classList.remove('is-drag');
      const over = zone.classList.contains('is-over');
      zone.classList.remove('is-over');
      fire(over ? 'scroll-snap' : 'error-tiny');
      if (over) { item.style.left = ''; item.style.top = ''; }
    };
    ['pointerup', 'pointercancel'].forEach(t => item.addEventListener(t, drop));
    wrap.append(item, zone);
    return wrap;
  })()));

  g5.items.push(card('Потянуть для обновления', 'pull-refresh, затем refresh-done', (() => {
    const b = el('button', 'pg-btn soft', 'Потянуть');
    b.addEventListener('click', () => {
      fire('pull-refresh');
      b.textContent = 'Обновляю…';
      setTimeout(() => { fire('refresh-done'); b.textContent = 'Потянуть'; }, 700);
    });
    return b;
  })()));

  g5.items.push(card('Карусель', 'swipe и scroll-snap', (() => {
    const wrap = el('div', 'pg-col');
    const view = el('div', 'pg-carousel');
    const strip = el('div', 'pg-carousel-strip');
    ['Один', 'Два', 'Три', 'Четыре'].forEach(t => strip.appendChild(el('div', '', t)));
    view.appendChild(strip);
    const row = el('div', 'pg-row');
    let i = 0;
    const go = d => {
      i = Math.max(0, Math.min(3, i + d));
      strip.style.transform = `translateX(${-i * 100}%)`;
      fire(d > 0 ? 'forward' : 'back');
    };
    const prev = el('button', 'pg-btn soft', '‹');
    const next = el('button', 'pg-btn soft', '›');
    prev.addEventListener('click', () => go(-1));
    next.addEventListener('click', () => go(1));
    row.append(prev, next);
    wrap.append(view, row);
    return wrap;
  })()));

  // ------------------------------------------------------------- СЛОИ
  const g6 = group('Слои и уведомления');

  g6.items.push(card('Модалка', 'modal-open / modal-close', (() => {
    const b = el('button', 'pg-btn', 'Открыть');
    b.addEventListener('click', () => {
      fire('modal-open');
      const back = el('div', 'pg-modal-back');
      const box = el('div', 'pg-modal', '<strong>Модальное окно</strong><p>Закрой меня</p>');
      const close = el('button', 'pg-btn soft', 'Закрыть');
      close.addEventListener('click', () => { fire('modal-close'); back.remove(); });
      box.appendChild(close);
      back.appendChild(box);
      back.addEventListener('click', e => {
        if (e.target === back) { fire('modal-close'); back.remove(); }
      });
      document.body.appendChild(back);
    });
    return b;
  })()));

  g6.items.push(card('Аккордеон', 'open / close', (() => {
    const wrap = el('div', 'pg-col');
    ['Как это работает', 'Почему так', 'Что дальше'].forEach(title => {
      const item = el('div', 'pg-acc');
      const head = el('button', '', title);
      const body = el('div', 'pg-acc-body', 'Звук и вибрация здесь синхронны: оба запускаются из одного обработчика жеста.');
      head.addEventListener('click', () => {
        const open = !item.classList.contains('is-open');
        item.classList.toggle('is-open', open);
        fire(open ? 'open' : 'close');
      });
      item.append(head, body);
      wrap.appendChild(item);
    });
    return wrap;
  })()));

  g6.items.push(card('Уведомления', 'notify, success-small, error-tiny', (() => {
    const row = el('div', 'pg-col');
    [['Уведомление', 'notify'], ['Сохранено', 'success-small'], ['Ошибка', 'error-tiny']]
      .forEach(([label, sound]) => {
        const b = el('button', 'pg-btn soft', label);
        b.addEventListener('click', () => {
          fire(sound);
          const t = el('div', 'pg-toast', label);
          document.body.appendChild(t);
          requestAnimationFrame(() => t.classList.add('is-in'));
          setTimeout(() => { t.classList.remove('is-in'); setTimeout(() => t.remove(), 250); }, 1600);
        });
        row.appendChild(b);
      });
    return row;
  })()));

  g6.items.push(card('Сообщения', 'message-send / message-receive', (() => {
    const wrap = el('div', 'pg-col');
    const feed = el('div', 'pg-feed');
    const b = el('button', 'pg-btn soft', 'Отправить');
    b.addEventListener('click', () => {
      fire('message-send');
      const m = el('div', 'pg-msg out', 'Привет');
      feed.appendChild(m); feed.scrollTop = feed.scrollHeight;
      setTimeout(() => {
        fire('message-receive');
        const r = el('div', 'pg-msg in', 'И тебе');
        feed.appendChild(r); feed.scrollTop = feed.scrollHeight;
      }, 800);
    });
    wrap.append(feed, b);
    return wrap;
  })()));

  // ------------------------------------------------------------- ОБУЧЕНИЕ
  const g7 = group('Обучение');

  g7.items.push(card('Проверка ответа', 'correct / wrong-soft', (() => {
    const wrap = el('div', 'pg-col');
    const q = el('div', 'pg-q', 'Сколько будет 7 × 8?');
    const opts = el('div', 'pg-col');
    [['54', false], ['56', true], ['58', false]].forEach(([label, right]) => {
      const b = el('button', 'pg-answer', label);
      b.addEventListener('click', () => {
        opts.querySelectorAll('.pg-answer').forEach(x => x.classList.remove('ok', 'no'));
        b.classList.add(right ? 'ok' : 'no');
        fire(right ? 'correct' : 'wrong-soft');
      });
      opts.appendChild(b);
    });
    wrap.append(q, opts);
    return wrap;
  })()));

  g7.items.push(card('Подсказка', 'hint', (() => {
    const b = el('button', 'pg-btn soft', 'Показать подсказку');
    b.addEventListener('click', () => fire('hint'));
    return b;
  })()));

  g7.items.push(card('Идеальный ответ', 'perfect-answer', (() => {
    const b = el('button', 'pg-btn', 'Без единой ошибки');
    b.addEventListener('click', () => fire('perfect-answer'));
    return b;
  })()));

  g7.items.push(card('Контрольная точка', 'checkpoint', (() => {
    const b = el('button', 'pg-btn soft', 'Пройдена');
    b.addEventListener('click', () => fire('checkpoint'));
    return b;
  })()));

  // ------------------------------------------------------------- ПОБЕДЫ
  const g8 = group('Победы и награды');

  [['Победа', 'victory'], ['Большая победа', 'victory-big'], ['Идеальный урок', 'perfect'],
   ['Новый уровень', 'level-up'], ['Раздел завершён', 'unit-complete'], ['Серия', 'streak'],
   ['Фанфара', 'fanfare'], ['Урок пройден', 'lesson'], ['Месячный марафон', 'marathon-win'],
   ['Крутой приз', 'grand-prize'], ['Раскрытие', 'epic-reveal'], ['Кубок', 'trophy'],
   ['Овация', 'crowd-cheer'], ['Дождь монет', 'coin-rain'], ['Сундук', 'chest-open'],
   ['Ожидание сундука', 'chest-anticipation'], ['Значок', 'badge'], ['Кристалл', 'gem'],
   ['Звезда', 'star'], ['Цель дня', 'goal-complete']]
    .forEach(([label, sound]) => {
      const b = el('button', 'pg-btn warm', label);
      b.addEventListener('click', () => fire(sound));
      g8.items.push(card(label, sound, b));
    });

  // ------------------------------------------------------------- МАТЕРИАЛЫ
  const g9 = group('Материалы');

  [['Дерево', 'wood-tap'], ['Полое дерево', 'wood-hollow'], ['Клавес', 'wood-claves'],
   ['Лог-драм', 'wood-log'], ['Гуиро', 'wood-guiro'], ['Кастаньеты', 'wood-castanets'],
   ['Бамбук', 'wood-bamboo'], ['Стук в дверь', 'wood-knock'],
   ['Камень', 'stone-tap'], ['Галька', 'stone-pebble'], ['Мрамор', 'stone-marble'],
   ['Камень о камень', 'stone-grind'], ['Валун', 'stone-heavy'],
   ['Колокольчик', 'metal-chime'], ['Наковальня', 'metal-anvil'], ['Гонг', 'metal-gong'],
   ['Треугольник', 'metal-triangle'], ['Стекло', 'glass-tap'], ['Бокал', 'glass-ring'],
   ['Птичья трель', 'whistle-bird'], ['Паровозный', 'whistle-train'],
   ['Судейский', 'whistle-referee'], ['Боцманская дудка', 'whistle-boatswain'],
   ['Двухтональный', 'whistle-two-tone'], ['Панфлейта', 'whistle-pan'],
   ['Глиссандо', 'whistle-long'], ['Свист-блик', 'whistle-tiny'],
   ['Рёв динозавра', 'roar']]
    .forEach(([label, sound]) => {
      const b = el('button', 'pg-btn soft', label);
      b.addEventListener('click', () => fire(sound));
      g9.items.push(card(label, sound, b));
    });

  // --------------------------------------------------------------- вывод
  root.innerHTML = '';
  groups.forEach(g => {
    const section = el('section', 'pg-group');
    section.appendChild(el('h3', 'pg-group-title', `${g.name} <small>${g.items.length}</small>`));
    const grid = el('div', 'pg-grid');
    g.items.forEach(i => grid.appendChild(i));
    section.appendChild(grid);
    root.appendChild(section);
  });
  return groups.reduce((n, g) => n + g.items.length, 0);
}
