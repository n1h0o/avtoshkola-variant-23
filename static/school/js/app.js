(() => {
  const toggle = document.querySelector('.menu-toggle');
  const nav = document.querySelector('#main-nav');
  if (toggle && nav) {
    toggle.addEventListener('click', () => {
      const open = toggle.getAttribute('aria-expanded') !== 'true';
      toggle.setAttribute('aria-expanded', String(open));
      nav.classList.toggle('is-open', open);
    });
  }

  document.querySelectorAll('form[data-validate]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      let valid = form.checkValidity();
      form.querySelectorAll('input[type="email"]').forEach((field) => {
        if (field.value && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(field.value)) {
          field.setCustomValidity('Введите корректный адрес электронной почты.');
          valid = false;
        } else field.setCustomValidity('');
      });
      form.querySelectorAll('input[type="tel"]').forEach((field) => {
        if (field.value && field.value.replace(/\D/g, '').length < 10) {
          field.setCustomValidity('Укажите телефон с кодом страны.');
          valid = false;
        } else field.setCustomValidity('');
      });
      form.querySelectorAll('textarea[maxlength], input[maxlength]').forEach((field) => {
        const max = Number(field.getAttribute('maxlength'));
        if (max && field.value.length > max) {
          field.setCustomValidity(`Максимальная длина - ${max} символов.`);
          valid = false;
        } else field.setCustomValidity('');
      });
      if (!valid) {
        event.preventDefault();
        form.reportValidity();
      }
    });
  });

  document.querySelectorAll('form[data-confirm]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  const results = document.querySelector('#slot-results');
  if (!results) return;
  const dateInput = document.querySelector('#filter-date');
  const instructorInput = document.querySelector('#filter-instructor');
  const searchInput = document.querySelector('#slot-search');
  const count = document.querySelector('#results-count');
  const loading = document.querySelector('#loading-state');
  const loadMore = document.querySelector('#load-more');
  let nextPage = 2;
  let hasNext = false;
  let items = Array.from(results.querySelectorAll('.slot-card')).map((card) => ({
    element: card,
    search: card.dataset.search || ''
  }));

  const text = (parent, tag, value, className) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    node.textContent = value;
    parent.append(node);
    return node;
  };

  function render(list) {
    const needle = (searchInput?.value || '').trim().toLocaleLowerCase('ru');
    const filtered = list.filter((item) => item.search.toLocaleLowerCase('ru').includes(needle));
    results.replaceChildren();
    if (!filtered.length) {
      const empty = document.createElement('div');
      empty.className = 'empty-state card';
      text(empty, 'strong', 'Подходящих занятий не найдено');
      text(empty, 'p', 'Измените фильтры или попробуйте другой запрос.');
      results.append(empty);
    } else filtered.forEach((item) => results.append(item.element));
    if (count) count.textContent = `${filtered.length} ${filtered.length === 1 ? 'вариант' : 'вариантов'}`;
  }

  function makeCard(slot) {
    const card = document.createElement('article');
    card.className = 'slot-card';
    card.dataset.search = `${slot.instructor} ${slot.vehicle} ${slot.location}`;
    const top = document.createElement('div');
    top.className = 'slot-top';
    text(top, 'span', slot.start, 'slot-day');
    text(top, 'span', 'Свободно', 'status-pill');
    card.append(top);
    text(card, 'h2', slot.start.slice(-5));
    text(card, 'p', slot.instructor);
    const meta = document.createElement('div');
    meta.className = 'slot-meta';
    text(meta, 'span', `${slot.vehicle} · ${slot.gearbox}`);
    text(meta, 'span', slot.location);
    card.append(meta);
    const link = text(card, 'a', 'Подробнее и записаться', 'button button-outline button-full');
    link.href = slot.url;
    return {
      element: card,
      search: card.dataset.search
    };
  }

  function makeEndpoint(page = 1) {
    const endpoint = new URL(results.dataset.feed, window.location.origin);
    if (dateInput?.value) endpoint.searchParams.set('date', dateInput.value);
    if (instructorInput?.value) endpoint.searchParams.set('instructor', instructorInput.value);
    endpoint.searchParams.set('page', String(page));
    return endpoint;
  }

  async function refresh() {
    results.setAttribute('aria-busy', 'true');
    if (loading) loading.hidden = false;
    try {
      const response = await fetch(makeEndpoint(1), {
        headers: {
          Accept: 'application/json'
        }
      });
      if (!response.ok) throw new Error('Не удалось обновить список');
      const payload = await response.json();
      items = payload.items.map(makeCard);
      nextPage = payload.page + 1;
      hasNext = payload.has_next;
      render(items);
      if (loadMore) loadMore.hidden = !hasNext;
    } catch (error) {
      if (!items.length) {
        results.replaceChildren();
        const warning = document.createElement('div');
        warning.className = 'empty-state card';
        text(warning, 'strong', 'Не удалось загрузить расписание');
        text(warning, 'p', 'Обновите страницу или попробуйте позже.');
        results.append(warning);
      }
    } finally {
      results.setAttribute('aria-busy', 'false');
      if (loading) loading.hidden = true;
    }
  }

  async function loadNextPage() {
    if (!hasNext) return;
    if (loadMore) loadMore.disabled = true;
    if (loading) loading.hidden = false;
    try {
      const response = await fetch(makeEndpoint(nextPage), {
        headers: {
          Accept: 'application/json'
        }
      });
      if (!response.ok) throw new Error('Не удалось загрузить следующую страницу');
      const payload = await response.json();
      items = items.concat(payload.items.map(makeCard));
      nextPage = payload.page + 1;
      hasNext = payload.has_next;
      render(items);
      if (loadMore) {
        loadMore.hidden = !hasNext;
        loadMore.disabled = false;
      }
    } catch (error) {
      if (loadMore) loadMore.disabled = false;
    } finally {
      if (loading) loading.hidden = true;
    }
  }

  dateInput?.addEventListener('change', refresh);
  instructorInput?.addEventListener('change', refresh);
  searchInput?.addEventListener('input', () => render(items));
  loadMore?.addEventListener('click', loadNextPage);
  document.querySelector('#clear-filters')?.addEventListener('click', () => {
    if (dateInput) dateInput.value = '';
    if (instructorInput) instructorInput.value = '';
    if (searchInput) searchInput.value = '';
    refresh();
  });
  refresh();
})();
