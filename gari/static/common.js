/* shared helpers (safe DOM builder: never uses innerHTML) */
function h(tag, props, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'text') e.textContent = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'style' && typeof v === 'object') { for (const [p, x] of Object.entries(v)) p.startsWith('--') ? e.style.setProperty(p, x) : (e.style[p] = x); }
    else e.setAttribute(k, v === true ? '' : v);
  }
  (function add(list) { for (const c of list) { if (c == null || c === false) continue; if (Array.isArray(c)) add(c); else e.append(c.nodeType ? c : document.createTextNode(String(c))); } })(kids);
  return e;
}
/* DOM replaceChildren() turns null into the text "null"; drop empty children instead */
const _rc = Element.prototype.replaceChildren;
Element.prototype.replaceChildren = function (...k) { return _rc.apply(this, k.flat(Infinity).filter(x => x != null && x !== false)); };
const kes = n => 'KES ' + Number(n || 0).toLocaleString('en-KE');
function toast(msg, bad) {
  const t = h('div', { class: 'toast' + (bad ? ' bad' : ''), text: msg });
  document.getElementById('toasts').append(t); setTimeout(() => t.remove(), bad ? 5000 : 2800);
}
const parseUtc = s => new Date(s.replace(' ', 'T') + 'Z');
function when(s) { return s ? parseUtc(s).toLocaleString('en-KE', { timeZone: 'Africa/Nairobi', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : ''; }
function ago(s) {
  const m = Math.max(0, Math.round((Date.now() - parseUtc(s)) / 60000));
  if (m < 60) return m + ' min'; if (m < 1440) return Math.round(m / 60) + ' h'; return Math.round(m / 1440) + ' d';
}
