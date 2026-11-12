import { request } from './api.js';
import { Camera } from './camera.js';
import { $, h, setChip } from './ui.js';

const COLORS = { marked: '#3ddc97', already: '#5aa9ff', confirming: '#f5b942', unknown: '#ff6b6b' };
const INTERVAL_MS = 300;

function label(face) {
  if (face.status === 'unknown') return 'Unknown';
  const suffix = { marked: ' ✓', already: ' ✓', confirming: ' …' }[face.status];
  return `${face.name}${suffix}`;
}

export function initScan() {
  const overlay = $('scan-overlay');
  const log = $('scan-log');
  const camera = new Camera($('scan-video'), $('scan-stage'));
  let running = false;
  let busy = false;
  let timer = 0;
  let failures = 0;
  const logged = new Set();

  function clearOverlay() {
    overlay.getContext('2d').clearRect(0, 0, overlay.width, overlay.height);
  }

  function draw(data) {
    const rect = overlay.getBoundingClientRect();
    const ratio = window.devicePixelRatio || 1;
    overlay.width = Math.round(rect.width * ratio);
    overlay.height = Math.round(rect.height * ratio);
    const ctx = overlay.getContext('2d');
    ctx.scale(ratio, ratio);
    const sx = rect.width / data.image.width;
    const sy = rect.height / data.image.height;
    ctx.font = '600 14px system-ui, sans-serif';
    ctx.textBaseline = 'middle';
    for (const face of data.faces) {
      const [x, y, w, hgt] = face.box;
      // The video is shown mirrored, so mirror the boxes too.
      const left = rect.width - (x + w) * sx;
      const top = y * sy;
      const color = COLORS[face.status];
      ctx.lineWidth = 3;
      ctx.strokeStyle = color;
      ctx.strokeRect(left, top, w * sx, hgt * sy);
      const text = label(face);
      const pad = 7;
      const width = ctx.measureText(text).width + pad * 2;
      const tagTop = top > 26 ? top - 26 : top + hgt * sy;
      ctx.fillStyle = color;
      ctx.fillRect(left - 1.5, tagTop, width, 24);
      ctx.fillStyle = '#07110f';
      ctx.fillText(text, left - 1.5 + pad, tagTop + 12.5);
    }
  }

  function addLog(face) {
    log.querySelector('.muted')?.remove();
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const text = face.status === 'marked'
      ? `${face.name} marked present`
      : `${face.name} was already marked today`;
    log.prepend(h('li', { class: face.status }, text, h('time', {}, time)));
    while (log.children.length > 30) log.lastChild.remove();
  }

  function report(data) {
    for (const face of data.faces) {
      if ((face.status === 'marked' || face.status === 'already') && !logged.has(face.code)) {
        logged.add(face.code);
        addLog(face);
      }
    }
    const count = data.faces.length;
    const unknown = data.faces.filter((f) => f.status === 'unknown').length;
    if (!count) setChip($('scan-status'), 'No face in view', 'warn');
    else if (unknown) setChip($('scan-status'), `${unknown} unknown`, 'bad');
    else setChip($('scan-status'), `${count} recognised`, 'ok');
  }

  async function scanOnce() {
    const blob = await camera.capture();
    const form = new FormData();
    form.append('frame', blob, 'frame.jpg');
    const response = await request('/api/recognize', { method: 'POST', body: form });
    const data = await response.json();
    if (running) {
      draw(data);
      report(data);
    }
  }

  async function loop() {
    if (!running) return;
    if (!busy && camera.ready && !document.hidden) {
      busy = true;
      try {
        await scanOnce();
        failures = 0;
      } catch (error) {
        failures += 1;
        setChip($('scan-status'), error.message, 'bad');
      } finally {
        busy = false;
      }
    }
    timer = setTimeout(loop, failures ? 1500 : INTERVAL_MS);
  }

  async function start() {
    try {
      await camera.start();
    } catch (error) {
      setChip($('scan-status'), error.message, 'bad');
      return;
    }
    running = true;
    failures = 0;
    $('scan-empty').hidden = true;
    $('scan-toggle').textContent = 'Stop camera';
    setChip($('scan-status'), 'Scanning', 'ok');
    loop();
  }

  function stop() {
    running = false;
    clearTimeout(timer);
    camera.stop();
    clearOverlay();
    $('scan-empty').hidden = false;
    $('scan-toggle').textContent = 'Start camera';
    setChip($('scan-status'), 'Camera off');
  }

  $('scan-toggle').addEventListener('click', () => (running ? stop() : start()));
  return { stop };
}
