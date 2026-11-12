import { getJson, request } from './api.js';
import { withAuth } from './login.js';
import { $, h, toast } from './ui.js';

function shiftDay(iso, days) {
  const date = new Date(`${iso}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function fill(tbody, rows) {
  tbody.replaceChildren(...rows);
}

export function initDashboard() {
  async function refresh() {
    const picked = $('dash-day').value;
    const query = picked ? `?day=${encodeURIComponent(picked)}` : '';
    try {
      const [attendance, summary, people] = await withAuth(() =>
        Promise.all([
          getJson(`/api/attendance${query}`, { admin: true }),
          getJson('/api/attendance/summary?days=14', { admin: true }),
          getJson('/api/persons', { admin: true }),
        ]),
      );
      render(attendance, summary, people);
    } catch (error) {
      toast(error.message, 'bad');
    }
  }

  function render(attendance, summary, people) {
    $('dash-day').value = attendance.day;
    if (!$('exp-end').value) {
      $('exp-end').value = attendance.day;
      $('exp-start').value = shiftDay(attendance.day, -29);
    }

    const present = attendance.records.length;
    const registered = attendance.registered;
    $('stat-present').textContent = present;
    $('stat-absent').textContent = attendance.absent.length;
    $('stat-registered').textContent = registered;
    $('stat-rate').textContent = registered ? `${Math.round((present / registered) * 100)}%` : '–';

    fill(
      $('present-table').tBodies[0],
      attendance.records.map((r) =>
        h('tr', {}, h('td', {}, r.name), h('td', {}, r.code), h('td', {}, r.time), h('td', {}, r.score.toFixed(2))),
      ),
    );
    $('present-empty').hidden = present > 0;
    $('present-table').hidden = present === 0;

    $('absent-list').replaceChildren(
      ...attendance.absent.map((p) => h('li', {}, p.name, h('small', {}, p.code))),
    );
    $('absent-empty').hidden = attendance.absent.length > 0 || registered === 0;

    renderTrend(summary, attendance.day);
    renderPeople(people);
  }

  function renderTrend(summary, selectedDay) {
    const max = Math.max(summary.registered, ...summary.days.map((d) => d.present), 1);
    $('trend').replaceChildren(
      ...summary.days.map((d) => {
        const bar = h('div', { class: `bar${d.day === selectedDay ? ' today' : ''}` });
        bar.style.setProperty('--h', `${(d.present / max) * 100}%`);
        return h(
          'div',
          { class: 'col', title: `${d.day}: ${d.present} present` },
          h('span', { class: 'count' }, d.present),
          bar,
          h('span', { class: 'day' }, d.day.slice(8)),
        );
      }),
    );
  }

  function renderPeople(people) {
    fill(
      $('people-table').tBodies[0],
      people.map((p) =>
        h(
          'tr',
          {},
          h('td', {}, p.name),
          h('td', {}, p.code),
          h('td', {}, p.samples),
          h('td', {}, p.created_at.slice(0, 10)),
          h('td', { class: 'num' }, h('button', { class: 'btn small danger', type: 'button', onclick: () => remove(p) }, 'Delete')),
        ),
      ),
    );
    $('people-empty').hidden = people.length > 0;
    $('people-table').hidden = people.length === 0;
  }

  async function remove(person) {
    const ok = confirm(
      `Delete ${person.name}?\n\nTheir face template and attendance history will be permanently removed.`,
    );
    if (!ok) return;
    try {
      await withAuth(() =>
        request(`/api/persons/${person.id}`, { admin: true, method: 'DELETE' }).then((r) => r.text()),
      );
      toast(`${person.name} deleted`, 'ok');
      refresh();
    } catch (error) {
      toast(error.message, 'bad');
    }
  }

  async function exportCsv() {
    const start = $('exp-start').value;
    const end = $('exp-end').value;
    try {
      const response = await withAuth(() =>
        request(`/api/attendance/export?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`, { admin: true }),
      );
      const url = URL.createObjectURL(await response.blob());
      const link = h('a', { href: url, download: `attendance_${start}_${end}.csv` });
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      toast(error.message, 'bad');
    }
  }

  $('dash-refresh').addEventListener('click', refresh);
  $('dash-day').addEventListener('change', refresh);
  $('exp-go').addEventListener('click', exportCsv);
  return { refresh };
}
