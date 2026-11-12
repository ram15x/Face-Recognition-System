import { initDashboard } from './dashboard.js';
import { initRegister } from './register.js';
import { initScan } from './scan.js';

const VIEWS = ['scan', 'register', 'dashboard'];
const scan = initScan();
const register = initRegister();
const dashboard = initDashboard();

function show(name) {
  const view = VIEWS.includes(name) ? name : 'scan';
  for (const id of VIEWS) {
    document.getElementById(`view-${id}`).hidden = id !== view;
  }
  for (const tab of document.querySelectorAll('.tab')) {
    if (tab.dataset.view === view) tab.setAttribute('aria-current', 'page');
    else tab.removeAttribute('aria-current');
  }
  // Never leave a camera running in a view nobody is looking at.
  if (view !== 'scan') scan.stop();
  if (view !== 'register') register.stop();
  if (view === 'dashboard') dashboard.refresh();
}

for (const tab of document.querySelectorAll('.tab')) {
  tab.addEventListener('click', () => {
    location.hash = tab.dataset.view;
  });
}
window.addEventListener('hashchange', () => show(location.hash.slice(1)));
show(location.hash.slice(1));
