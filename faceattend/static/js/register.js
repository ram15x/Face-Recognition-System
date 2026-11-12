import { request } from './api.js';
import { Camera } from './camera.js';
import { withAuth } from './login.js';
import { $, h, sleep, toast } from './ui.js';

const PROMPTS = [
  'Look straight at the camera',
  'Turn your head slightly left',
  'Turn your head slightly right',
  'Tilt your chin up a little',
  'Look straight at the camera',
];
const GAP_MS = 800;

export function initRegister() {
  const form = $('reg-form');
  const message = $('reg-message');
  const prompt = $('reg-prompt');
  const dots = $('reg-dots');
  const camera = new Camera($('reg-video'), $('reg-stage'));
  let capturing = false;

  function say(text, kind = '') {
    message.textContent = text;
    message.className = `message ${kind}`.trim();
  }

  function refreshButtons() {
    $('reg-submit').disabled = !camera.active || capturing;
    $('reg-camera').textContent = camera.active ? 'Stop camera' : 'Start camera';
    $('reg-camera').disabled = capturing;
  }

  async function toggleCamera() {
    if (camera.active) {
      camera.stop();
      $('reg-empty').hidden = false;
    } else {
      try {
        await camera.start();
        $('reg-empty').hidden = true;
        say('');
      } catch (error) {
        say(error.message, 'bad');
      }
    }
    refreshButtons();
  }

  async function captureFrames() {
    dots.replaceChildren(...PROMPTS.map(() => h('i')));
    prompt.hidden = false;
    prompt.textContent = 'Get ready…';
    await sleep(1200);
    const blobs = [];
    for (const [index, text] of PROMPTS.entries()) {
      prompt.textContent = text;
      await sleep(GAP_MS);
      blobs.push(await camera.capture());
      dots.children[index].classList.add('done');
    }
    prompt.hidden = true;
    return blobs;
  }

  async function submit(event) {
    event.preventDefault();
    if (!camera.ready || capturing) return;
    capturing = true;
    refreshButtons();
    say('');
    try {
      const blobs = await captureFrames();
      say('Checking photos…');
      const person = await withAuth(() => {
        const body = new FormData();
        body.append('name', $('reg-name').value);
        body.append('code', $('reg-code').value);
        body.append('consent', $('reg-consent').checked ? 'true' : 'false');
        blobs.forEach((blob, i) => body.append('frames', blob, `frame${i}.jpg`));
        return request('/api/persons', { admin: true, method: 'POST', body }).then((r) => r.json());
      });
      say(`Registered ${person.name} (${person.samples} samples).`, 'ok');
      toast(`${person.name} registered`, 'ok');
      form.reset();
    } catch (error) {
      say(error.message, 'bad');
    } finally {
      prompt.hidden = true;
      dots.replaceChildren();
      capturing = false;
      refreshButtons();
    }
  }

  $('reg-camera').addEventListener('click', toggleCamera);
  form.addEventListener('submit', submit);
  return {
    stop() {
      camera.stop();
      $('reg-empty').hidden = false;
      refreshButtons();
    },
  };
}
