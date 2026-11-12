import { AuthError, auth } from './api.js';
import { $ } from './ui.js';

function ask(errorText) {
  const dialog = $('login');
  const input = $('login-token');
  $('login-error').textContent = errorText;
  input.value = '';
  return new Promise((resolve, reject) => {
    const done = (token) => {
      dialog.close();
      $('login-form').removeEventListener('submit', onSubmit);
      $('login-cancel').removeEventListener('click', onCancel);
      token ? resolve(token) : reject(new Error('Login cancelled.'));
    };
    const onSubmit = (event) => { event.preventDefault(); done(input.value.trim()); };
    const onCancel = () => done('');
    $('login-form').addEventListener('submit', onSubmit);
    $('login-cancel').addEventListener('click', onCancel);
    dialog.addEventListener('cancel', onCancel, { once: true });
    dialog.showModal();
    input.focus();
  });
}

/** Run an admin request; if the server wants a token, ask for it and try again. */
export async function withAuth(task) {
  let attempts = 0;
  for (;;) {
    try {
      return await task();
    } catch (error) {
      if (!(error instanceof AuthError)) throw error;
      auth.token = await ask(attempts++ ? 'That token was not accepted.' : '');
    }
  }
}
