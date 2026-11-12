export const $ = (id) => document.getElementById(id);

/** Build an element. Children are always added as text, so names can never inject HTML. */
export function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === 'class') node.className = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (value === true) node.setAttribute(key, '');
    else if (value !== false && value != null) node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

let toastTimer = 0;
export function toast(message, kind = '') {
  const el = $('toast');
  el.textContent = message;
  el.className = kind;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 3500);
}

export function setChip(el, text, kind = '') {
  el.textContent = text;
  el.className = `chip ${kind}`.trim();
}

export const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
