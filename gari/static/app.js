'use strict';
const S = { token: localStorage.getItem('gari_token'), user: null, garage: null, page: 'workshop', mechanics: [], refresh: () => {} };
const LABEL = { intake: 'Checked in', diagnosing: 'Diagnosing', quoted: 'Quoted', approved: 'Approved', in_progress: 'In repair', qa: 'Quality check', ready: 'Ready for pickup', invoiced: 'Invoiced', cancelled: 'Cancelled' };
const STAGES = ['intake', 'diagnosing', 'quoted', 'approved', 'in_progress', 'qa', 'ready'];
const root = document.getElementById('root');
const isStaff = () => S.user && S.user.role !== 'mechanic';

async function api(path, o = {}) {
  const r = await fetch('/api' + path, { method: o.method || 'GET', headers: { 'Content-Type': 'application/json', ...(S.token ? { Authorization: 'Bearer ' + S.token } : {}) }, body: o.body ? JSON.stringify(o.body) : undefined });
  let d = null; try { d = await r.json(); } catch (_) {}
  if (r.status === 401 && S.token && !path.startsWith('/auth')) { logout(); throw new Error('Your session expired. Sign in again.'); }
  if (!r.ok) throw Object.assign(new Error((d && d.error) || 'Request failed'), { field: d && d.field, status: r.status });
  return d;
}
const fail = e => toast(e.message, true);
function logout() { localStorage.removeItem('gari_token'); S.token = S.user = null; S.page = 'workshop'; renderAuth(); }
const pill = st => h('span', { class: 'pill', style: { '--c': `var(--s-${st})` }, text: LABEL[st] || st });
const plate = (p, lg) => h('span', { class: 'plate' + (lg ? ' lg' : ''), text: p.replace(/^([A-Z]{3})(\d{3}[A-Z]?)$/, '$1 $2') });


const NS = 'http://www.w3.org/2000/svg';
const ICON = {
  workshop: [['rect', { x: 3, y: 3, width: 7, height: 7, rx: 2 }], ['rect', { x: 14, y: 3, width: 7, height: 7, rx: 2 }], ['rect', { x: 3, y: 14, width: 7, height: 7, rx: 2 }], ['rect', { x: 14, y: 14, width: 7, height: 7, rx: 2 }]],
  vehicles: [['path', { d: 'M3 16v-3l2-5.2A2 2 0 0 1 6.9 6.5h10.2A2 2 0 0 1 19 7.8L21 13v3' }], ['path', { d: 'M3 13h18' }], ['circle', { cx: 7.5, cy: 16.5, r: 1.8 }], ['circle', { cx: 16.5, cy: 16.5, r: 1.8 }]],
  stock: [['path', { d: 'M21 8l-9-5-9 5 9 5 9-5z' }], ['path', { d: 'M3 8v8l9 5 9-5V8' }], ['path', { d: 'M12 13v8' }]],
  invoices: [['path', { d: 'M6 3h12v18l-3-2-3 2-3-2-3 2V3z' }], ['path', { d: 'M9 8h6M9 12h6' }]],
  reports: [['path', { d: 'M4 20V10M10 20V4M16 20v-7M22 20H2' }]],
  team: [['circle', { cx: 9, cy: 8, r: 3.2 }], ['path', { d: 'M3 20c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5' }], ['path', { d: 'M16 5.2a3 3 0 0 1 0 5.6M18 14.8c1.8.7 3 2.4 3 5.2' }]]
};
function icon(n) { const s = document.createElementNS(NS, 'svg'); s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('aria-hidden', 'true'); for (const [t, at] of ICON[n]) { const e = document.createElementNS(NS, t); for (const k in at) e.setAttribute(k, at[k]); s.append(e); } return s; }
const dots = (f, t, c, n = 28) => { const on = t ? Math.round(n * Math.min(1, f / t)) : 0; return h('div', { class: 'dots', 'aria-hidden': 'true', style: { '--c': c } }, Array.from({ length: n }, (_, i) => h('i', { class: i < on ? 'on' : '' }))); };
function ring(pct, color, big, small, label) {
  const n = 60, R = 84, on = Math.round(n * Math.max(0, Math.min(100, pct)) / 100), svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 200 200'); svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', label);
  for (let i = 0; i < n; i++) { const an = (-90 + 360 * i / n) * Math.PI / 180, c = document.createElementNS(NS, 'circle'); c.setAttribute('cx', 100 + R * Math.cos(an)); c.setAttribute('cy', 100 + R * Math.sin(an)); c.setAttribute('r', 2.8); c.setAttribute('fill', i < on ? color : 'rgba(60,45,30,.14)'); svg.append(c); }
  return h('div', { class: 'ring' }, svg, h('div', { class: 'mid' }, h('b', { text: big }), h('span', { text: small })));
}

/* ---------- forms & overlays ---------- */
function field(label, name, o = {}) {
  let inp;
  if (o.type === 'select') inp = h('select', { name }, (o.options || []).map(x => h('option', { value: x.v, text: x.l })));
  else if (o.type === 'textarea') inp = h('textarea', { name, maxlength: o.max, placeholder: o.ph });
  else inp = h('input', { name, type: o.type || 'text', placeholder: o.ph, autocomplete: o.auto || 'off', min: o.min, max: o.max, maxlength: o.maxlength, inputmode: o.mode });
  if (o.value != null) inp.value = o.value;
  const el = h('label', { class: 'f', 'data-name': name }, h('span', { text: label }), inp);
  return { el, inp, name };
}
function showErr(root_, e) {
  root_.querySelectorAll('.err').forEach(x => x.remove()); root_.querySelectorAll('.bad').forEach(x => x.classList.remove('bad'));
  const l = e.field && root_.querySelector(`label[data-name="${e.field}"]`);
  if (l) { l.classList.add('bad'); l.append(h('div', { class: 'err', role: 'alert', text: e.message })); l.querySelector('input,select,textarea').focus(); } else fail(e);
}
function overlay(content, center) {
  const prev = document.activeElement;
  const scrim = h('div', { class: 'scrim' + (center ? ' center' : '') });
  const close = () => { scrim.remove(); document.removeEventListener('keydown', esc); if (prev && prev.focus) prev.focus(); if (scrim.onclose) scrim.onclose(); };
  const esc = e => { if (e.key === 'Escape' && scrim === [...document.querySelectorAll('.scrim')].pop()) close(); };
  scrim.addEventListener('mousedown', e => { if (e.target === scrim) close(); });
  document.addEventListener('keydown', esc);
  scrim.append(content); document.body.append(scrim);
  const f = content.querySelector('input,select,textarea,button'); if (f) f.focus();
  return { close, scrim };
}
function formModal({ title, fields, submit = 'Save', note, onSubmit }) {
  const form = h('form', { novalidate: true }, note ? h('p', { class: 'muted small', text: note }) : null, fields.map(f => f.el), h('div', { class: 'row', style: { justifyContent: 'flex-end', marginTop: '6px' } }));
  const m = h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': title }, h('h2', { text: title }), form);
  const o = overlay(m, true);
  const sb = h('button', { class: 'btn primary', type: 'submit', text: submit });
  form.lastChild.append(h('button', { class: 'btn ghost', type: 'button', text: 'Cancel', onclick: o.close }), sb);
  form.addEventListener('submit', async ev => {
    ev.preventDefault(); const v = {}; fields.forEach(f => v[f.name] = f.inp.value); sb.disabled = true;
    try { await onSubmit(v, o.close); } catch (e) { showErr(form, e); } finally { sb.disabled = false; }
  });
  return o;
}
const confirmBox = (title, text, onYes, yes = 'Confirm') => formModal({ title, fields: [], submit: yes, note: text, onSubmit: async (_, c) => { await onYes(); c(); } });

/* ---------- auth ---------- */
function renderAuth() {
  let mode = location.hash === '#signup' ? 'up' : 'in';
  const shell = (...kids) => root.replaceChildren(h('div', { class: 'auth' }, h('div', { class: 'box' }, h('div', { class: 'brand' }, h('i'), 'Gari'), kids)));
  const drawForgot = () => {
    const em = field('Email', 'email', { type: 'email', auto: 'username' });
    const form = h('form', { novalidate: true }, em.el, h('button', { class: 'btn primary', type: 'submit', text: 'Send reset link' }));
    form.addEventListener('submit', async ev => {
      ev.preventDefault();
      try {
        const d = await api('/auth/forgot', { method: 'POST', body: { email: em.inp.value } });
        shell(h('h1', { text: 'Check your email' }), h('p', { class: 'sub', id: 'forgot-done', text: d.message }),
          h('p', { class: 'small muted', text: 'Nothing arrived? Check spam, or ask your garage owner or manager to set a temporary password for you.' }), h('button', { class: 'link', type: 'button', text: 'Back to sign in', onclick: () => { mode = 'in'; draw(); } }));
      } catch (er) { showErr(form, er); }
    });
    shell(h('h1', { text: 'Reset your password' }), h('p', { class: 'sub', text: 'Enter your account email and we\u2019ll send you a link to choose a new one.' }), form,
      h('p', { style: { textAlign: 'center', marginBottom: 0 } }, h('button', { class: 'link', type: 'button', id: 'back-signin', text: 'Back to sign in', onclick: () => { mode = 'in'; draw(); } })));
  };
  const draw = () => {
    if (mode === 'forgot') return drawForgot();
    const f = mode === 'in' ? [field('Email', 'email', { type: 'email', auto: 'username' }), field('Password', 'password', { type: 'password', auto: 'current-password' })]
      : [field('Garage name', 'garage_name'), field('Your name', 'name'), field('Phone', 'phone', { type: 'tel', ph: '0712 345 678' }), field('KRA PIN (optional)', 'kra_pin', { ph: 'A123456789Z' }), field('Email', 'email', { type: 'email' }), field('Password', 'password', { type: 'password', auto: 'new-password', ph: '8+ characters, letters and numbers' })];
    const form = h('form', { novalidate: true }, f.map(x => x.el), h('button', { class: 'btn primary', type: 'submit', text: mode === 'in' ? 'Sign in' : 'Create garage account' }));
    form.addEventListener('submit', async ev => {
      ev.preventDefault(); const body = {}; f.forEach(x => body[x.name] = x.inp.value);
      try { const d = await api(mode === 'in' ? '/auth/login' : '/auth/register', { method: 'POST', body }); S.token = d.token; localStorage.setItem('gari_token', d.token); boot(); } catch (er) { showErr(form, er); }
    });
    shell(h('h1', { text: mode === 'in' ? 'Run the workshop floor' : 'Set up your garage' }), h('p', { class: 'sub', text: 'Job cards, stock and payments in one place.' }),
      h('div', { class: 'tabs', role: 'tablist' }, [['in', 'Sign in'], ['up', 'Create account']].map(([k, l]) => h('button', { role: 'tab', 'aria-selected': String(mode === k), text: l, onclick: () => { mode = k; draw(); } }))), form,
      mode === 'in' ? h('p', { style: { textAlign: 'center', marginBottom: 0 } }, h('button', { class: 'link', type: 'button', id: 'forgot-link', text: 'Forgot password?', onclick: () => { mode = 'forgot'; draw(); } })) : null);
  };
  draw();
}

/* ---------- shell ---------- */
async function boot() {
  if (!S.token) return renderAuth();
  try { const d = await api('/me'); S.user = d.user; S.garage = d.garage; if (isStaff()) S.mechanics = (await api('/users')).filter(u => u.role === 'mechanic' && u.active); } catch (e) { if (S.token) { toast(e.message, true); } return; }
  const pages = [['workshop', 'Workshop'], ['vehicles', 'Vehicles'], ['stock', 'Stock'], ...(isStaff() ? [['invoices', 'Invoices'], ['reports', 'Reports'], ['team', 'Team']] : [])];
  if (!pages.find(p => p[0] === S.page)) S.page = 'workshop';
  const main = h('main', { id: 'main', tabindex: '-1' });
  const initials = S.user.name.split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase();
  let menu = null; const closeMenu = () => { if (menu) { menu.remove(); menu = null; } };
  document.addEventListener('mousedown', ev => { if (menu && !ev.target.closest('.userbox')) closeMenu(); });
  document.addEventListener('keydown', ev => { if (ev.key === 'Escape') closeMenu(); });
  const box = h('div', { class: 'userbox' }, h('button', { class: 'avatar', 'aria-label': 'Account', 'aria-haspopup': 'true', text: initials, onclick: () => {
    if (menu) return closeMenu();
    menu = h('div', { class: 'menu', role: 'menu' }, h('div', { class: 'who' }, h('b', { text: S.user.name }), h('span', { class: 'small muted', text: S.user.role + ' · ' + S.user.email })),
      h('button', { role: 'menuitem', id: 'change-pw', text: 'Change password', onclick: () => { closeMenu(); changePassword(); } }), h('button', { role: 'menuitem', text: 'Sign out', onclick: () => { closeMenu(); logout(); } }));
    box.append(menu); menu.querySelector('button').focus(); } }));
  const top = h('header', { class: 'topbar' }, h('div', { class: 'brand' }, h('i'), h('div', {}, 'Gari', h('small', { class: 'garage-name', text: S.garage.name }))),
    h('nav', { class: 'rail', 'aria-label': 'Main' }, pages.map(([k, l]) => h('button', { class: 'nav', 'data-page': k, title: l, 'aria-label': l, 'aria-current': k === S.page ? 'page' : null, onclick: () => go(k) }, icon(k), h('span', { text: l })))), box);
  root.replaceChildren(h('div', { id: 'app' }, h('div', { class: 'sheet' }, top, main)));
  go(S.page);
}
function go(p) {
  S.page = p; document.querySelectorAll('nav.rail .nav').forEach(b => b.getAttribute('data-page') === p ? b.setAttribute('aria-current', 'page') : b.removeAttribute('aria-current'));
  const m = document.getElementById('main'); m.replaceChildren(); S.refresh = () => PAGES[p](m).catch(fail); S.refresh();
}
const header = (t, ...r) => h('div', { class: 'head' }, h('h1', { text: t }), h('span', { class: 'grow' }), r);
function changePassword() {
  const fs = [field('Current password', 'current', { type: 'password', auto: 'current-password' }), field('New password', 'password', { type: 'password', auto: 'new-password', ph: '8+ characters, letters and numbers' })];
  formModal({ title: 'Change password', fields: fs, submit: 'Update password', note: 'Other devices signed in to your account will be signed out.', onSubmit: async (v, close) => {
    const d = await api('/me/password', { method: 'POST', body: v }); S.token = d.token; localStorage.setItem('gari_token', d.token); close(); toast('Password updated'); } });
}

/* ---------- workshop board ---------- */
const PAGES = {};
PAGES.workshop = async m => {
  const jobs = await api('/jobs?status=open');
  const cols = STAGES.map(st => {
    const list = jobs.filter(j => j.status === st), c = `var(--s-${st})`;
    return h('section', { class: 'lane' + (list.length ? '' : ' none'), style: { '--c': c }, 'aria-label': LABEL[st] }, h('header', {}, h('span', { text: LABEL[st] }), h('b', { class: 'num', text: list.length })),
      h('div', { class: 'cards' }, list.length ? list.map(j => h('button', { class: 'card', style: { '--c': c }, onclick: () => openJob(j.id), 'data-job': j.number },
        h('div', { class: 't' }, plate(j.plate), h('span', { class: 'small muted num', text: ago(j.updated_at) })),
        h('div', { style: { fontWeight: 500 }, text: [j.make, j.model].filter(Boolean).join(' ') || j.customer }),
        h('p', { text: j.complaint }),
        h('div', { class: 'm' }, h('span', { text: j.mechanic || 'Unassigned' }), isStaff() && j.totals.subtotal ? h('span', { class: 'num', text: kes(j.totals.total) }) : null),
        j.needs_reapproval ? h('div', { style: { marginTop: '8px' } }, h('span', { class: 'tag warn', text: 'Extra work needs approval' })) : null,
        dots(STAGES.indexOf(st) + 1, STAGES.length, c, 24))) : h('div', { class: 'empty', text: 'Nothing here' })));
  });
  const board = jobs.length || isStaff() ? h('div', { class: 'board' }, cols) : h('div', { class: 'panel empty', text: 'No jobs assigned to you yet. Your manager will assign one.' });
  if (!isStaff()) return m.replaceChildren(header('My jobs'), board);

  const by = s => jobs.filter(j => j.status === s), open = jobs.length, reappr = jobs.filter(j => j.needs_reapproval), unassigned = jobs.filter(j => !j.mechanic && j.status !== 'ready');
  const kpi = (l, v, tag, tagCls, f, c, sub) => h('div', { class: 'kpi', 'data-kpi': l }, h('div', { class: 'l', text: l }), h('div', { class: 'v num' }, String(v).padStart(2, '0'), tag ? h('em', { class: 'tag ' + tagCls, text: tag }) : null), dots(f, Math.max(open, 1), c, 34), h('div', { class: 's', text: sub }));
  const items = [
    ...reappr.map(j => ({ j, c: 'var(--bad)', t: 'Extra work needs approval', tag: 'Approve', cls: 'bad' })),
    ...by('quoted').map(j => ({ j, c: 'var(--s-quoted)', t: 'Quote waiting for customer', tag: 'Waiting', cls: 'warn' })),
    ...by('ready').map(j => ({ j, c: 'var(--s-ready)', t: 'Ready, customer to collect', tag: 'Pickup', cls: 'ok' })),
    ...unassigned.map(j => ({ j, c: 'var(--s-diagnosing)', t: 'No mechanic assigned', tag: 'Assign', cls: 'warn' }))].slice(0, 6);
  const attn = h('div', { class: 'panel' }, h('h2', { text: 'Needs attention' }), items.length ? h('ul', { class: 'alerts' }, items.map(x => h('li', { style: { '--c': x.c, cursor: 'pointer' }, tabindex: 0, onclick: () => openJob(x.j.id), onkeydown: ev => ev.key === 'Enter' && openJob(x.j.id) },
    h('span', { class: 'dot' }), h('div', { class: 't' }, h('b', { text: x.j.plate + ' · ' + ([x.j.make, x.j.model].filter(Boolean).join(' ') || x.j.customer) }), h('span', { text: x.t })), h('span', { class: 'tag ' + x.cls, text: x.tag })))) : h('div', { class: 'empty', text: 'All clear. Nothing is waiting on you.' }));
  const first = S.user.name.split(' ')[0];
  m.replaceChildren(
    h('div', { class: 'head' }, h('div', {}, h('h1', {}, 'Welcome back, ', h('b', { text: first }), ' \u{1F44B}'), h('p', { text: 'Here\u2019s what\u2019s on the workshop floor right now.' })), h('span', { class: 'grow' }), h('button', { class: 'btn primary', id: 'new-job', text: 'New job card', onclick: () => newJob() })),
    h('div', { class: 'hero' }, h('div', { class: 'kpis', style: { marginBottom: 0, alignContent: 'start' } },
      kpi('Open jobs', open, unassigned.length ? unassigned.length + ' unassigned' : null, 'warn', by('in_progress').length + by('qa').length + by('ready').length, 'var(--brand)', 'Past approval: repair, QA or ready'),
      kpi('Awaiting customer', by('quoted').length, null, '', by('quoted').length, 'var(--s-quoted)', 'Quotes sent, no answer yet'),
      kpi('Ready for pickup', by('ready').length, null, '', by('ready').length, 'var(--s-ready)', 'Waiting to be invoiced and paid'),
      kpi('Extra work', reappr.length, reappr.length ? 'urgent' : null, 'bad', reappr.length, 'var(--bad)', 'Added after the customer approved')), attn),
    h('div', { class: 'panel', style: { padding: '18px 16px 8px' } }, h('h2', { style: { paddingLeft: '6px' }, text: 'Job board' }), board));
};

function newJob(vehicle) {
  const veh = field('Vehicle (plate, owner or phone)', 'vq', { ph: 'Start typing, e.g. KDA' }); let vid = vehicle ? vehicle.id : null;
  const sugg = h('div', { class: 'sugg hidden' }); const chosen = h('p', { class: 'small', style: { fontWeight: 600 }, text: vehicle ? `${vehicle.plate} · ${vehicle.customer}` : '' });
  let t; veh.inp.addEventListener('input', () => { clearTimeout(t); vid = null; chosen.textContent = ''; t = setTimeout(async () => {
    if (!veh.inp.value.trim()) return sugg.classList.add('hidden');
    const r = await api('/vehicles?q=' + encodeURIComponent(veh.inp.value)).catch(() => []);
    sugg.replaceChildren(...r.map(v => h('button', { type: 'button', onclick: () => { vid = v.id; chosen.textContent = `${v.plate} · ${v.customer}`; veh.inp.value = v.plate; sugg.classList.add('hidden'); } }, h('span', { text: v.plate + ' ' + [v.make, v.model].filter(Boolean).join(' ') }), h('span', { class: 'muted', text: v.customer }))),
      h('button', { type: 'button', onclick: () => { addVehicle(v2 => newJob(v2)); } }, h('span', { text: '+ Register a new vehicle' })));
    sugg.classList.remove('hidden'); }, 200); });
  const fs = [field('What does the customer say is wrong?', 'complaint', { type: 'textarea', max: 1000 }), field('Mileage in (km)', 'mileage_in', { type: 'number', mode: 'numeric' }),
    field('Fuel level', 'fuel_level', { type: 'select', options: ['', 'Empty', '1/4', '1/2', '3/4', 'Full'].map(x => ({ v: x, l: x || 'Not recorded' })) }),
    field('Items left in the car', 'belongings', { ph: 'e.g. spare wheel, jack, phone charger' }),
    field('Assign mechanic', 'mechanic_id', { type: 'select', options: [{ v: '', l: 'Assign later' }, ...S.mechanics.map(u => ({ v: u.id, l: u.name }))] })];
  const o = formModal({ title: 'New job card', fields: [veh, ...fs], submit: 'Open job card', onSubmit: async (v, close) => {
    if (!vid) throw Object.assign(new Error('Pick a vehicle from the list or register a new one'), { field: 'vq' });
    const body = { vehicle_id: vid }; fs.forEach(f => { if (v[f.name] !== '') body[f.name] = v[f.name]; });
    const j = await api('/jobs', { method: 'POST', body }); close(); toast('Job card ' + j.number + ' opened'); S.refresh(); openJob(j.id); } });
  veh.el.append(sugg, chosen);
}
function addVehicle(done) {
  const fs = [field('Number plate', 'plate', { ph: 'KDA 123A' }), field('Owner name', 'customer_name'), field('Owner phone', 'phone', { type: 'tel', ph: '0712 345 678' }), field('Make', 'make', { ph: 'Toyota' }), field('Model', 'model', { ph: 'Axio' }), field('Year', 'year', { type: 'number' }), field('Mileage (km)', 'mileage', { type: 'number' })];
  formModal({ title: 'Register vehicle', fields: fs, submit: 'Register vehicle', onSubmit: async (v, close) => {
    const body = {}; fs.forEach(f => { if (v[f.name] !== '') body[f.name] = v[f.name]; });
    const r = await api('/vehicles', { method: 'POST', body }); document.querySelectorAll('.scrim').forEach(x => { if (x.querySelector('[aria-label="New job card"]')) x.remove(); });
    close(); toast('Vehicle registered'); S.refresh(); if (done) done({ id: r.id, plate: r.plate, customer: v.customer_name }); } });
}

/* ---------- job drawer ---------- */
async function openJob(id) {
  const box = h('div', { class: 'drawer', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Job card' });
  const o = overlay(box); o.scrim.onclose = () => S.refresh();
  const render = async j => {
    if (!j) j = await api('/jobs/' + id);
    const st = j.status, editable = ['intake', 'diagnosing', 'quoted', 'approved', 'in_progress'].includes(st), c = `var(--s-${st})`;
    const go_ = async (to) => { try { render(await api(`/jobs/${id}/status`, { method: 'POST', body: { status: to } })); } catch (e) { fail(e); } };
    const act = (to, label, cls) => h('button', { class: 'btn ' + (cls || ''), 'data-to': to, text: label, onclick: () => go_(to) });
    const acts = [];
    if (st === 'intake') acts.push(act('diagnosing', 'Start diagnosis', 'primary'));
    if (st === 'diagnosing') acts.push(act('quoted', 'Send for quote', 'primary'));
    if (st === 'quoted') acts.push(act('diagnosing', 'Back to diagnosis'));
    if (st === 'approved') acts.push(act('in_progress', 'Start repair', 'primary'));
    if (st === 'in_progress') acts.push(act('qa', 'Send to quality check', 'primary'), act('quoted', 'Needs new quote'));
    if (st === 'qa') { if (isStaff()) acts.push(act('ready', 'Mark ready for pickup', 'primary')); acts.push(act('in_progress', 'Back to repair')); }
    if (st === 'ready' && isStaff()) acts.push(h('button', { class: 'btn primary', id: 'make-invoice', text: 'Create invoice', onclick: async () => { try { const i = await api(`/jobs/${id}/invoice`, { method: 'POST' }); toast('Invoice ' + i.number + ' created'); render(); openInvoice(i.id); } catch (e) { fail(e); } } }), act('in_progress', 'Reopen repair'));
    if (st === 'invoiced' && j.invoice) acts.push(h('button', { class: 'btn primary', text: 'Open invoice ' + j.invoice.number, onclick: () => openInvoice(j.invoice.id) }));
    const approvalBtn = () => h('button', { class: 'btn', id: 'record-approval', text: 'Record customer approval', onclick: () => {
      const f = field('How did the customer approve?', 'method', { type: 'select', options: [{ v: 'phone', l: 'Phone call' }, { v: 'whatsapp', l: 'WhatsApp message' }, { v: 'sms', l: 'SMS' }, { v: 'in_person', l: 'In person' }] });
      formModal({ title: 'Record customer approval', fields: [f], submit: 'Record approval', note: 'This locks the approved amount' + (j.totals ? ' at ' + kes(j.totals.total) : '') + '. Any extra work after this needs approval again.', onSubmit: async (v, close) => { const r = await api(`/jobs/${id}/approve`, { method: 'POST', body: v }); close(); toast('Approval recorded'); render(r); } }); } });
    if (isStaff() && st === 'quoted' && j.approval_token) {
      const link = location.origin + '/q/' + j.approval_token;
      acts.push(h('button', { class: 'btn', id: 'copy-link', text: 'Copy quote link', onclick: async () => { try { await navigator.clipboard.writeText(link); toast('Quote link copied'); } catch (_) { prompt('Copy this link', link); } } }),
        h('a', { class: 'btn', target: '_blank', rel: 'noopener', text: 'Send on WhatsApp', href: 'https://wa.me/' + j.phone.replace(/\D/g, '') + '?text=' + encodeURIComponent(`Hello ${j.customer}, here is your repair quote from ${S.garage.name}: ${link}`) }));
    }
    if (isStaff() && st === 'quoted') acts.push(approvalBtn());
    if (isStaff() && ['intake', 'diagnosing', 'quoted', 'approved'].includes(st)) acts.push(h('button', { class: 'btn danger', text: 'Cancel job', onclick: () => confirmBox('Cancel this job?', 'Parts on the job go back into stock.', async () => { render(await api(`/jobs/${id}/status`, { method: 'POST', body: { status: 'cancelled' } })); }, 'Cancel job') }));

    const mech = isStaff() && !['invoiced', 'cancelled'].includes(st) ? h('select', { 'aria-label': 'Assigned mechanic', id: 'assign', onchange: async e => { try { render(await api('/jobs/' + id, { method: 'PATCH', body: { mechanic_id: e.target.value || null } })); toast('Mechanic updated'); } catch (er) { fail(er); } } },
      [h('option', { value: '', text: 'Unassigned' }), ...S.mechanics.map(u => h('option', { value: u.id, text: u.name }))]) : null;
    if (mech) mech.value = j.mechanic_id || '';

    const diag = h('textarea', { 'aria-label': 'Diagnosis and work done', id: 'diagnosis', placeholder: 'Findings and work done', disabled: !editable && st !== 'ready' && st !== 'qa' }); diag.value = j.diagnosis || '';
    const items = j.items.length ? h('div', { class: 'tbl' }, h('table', {}, h('thead', {}, h('tr', {}, h('th', { text: 'Item' }), h('th', { class: 'right', text: 'Qty' }), isStaff() ? [h('th', { class: 'right', text: 'Price' }), h('th', { class: 'right', text: 'Amount' })] : null, h('th'))),
      h('tbody', {}, j.items.map(i => h('tr', {}, h('td', {}, i.description, h('div', { class: 'small muted', text: (i.kind === 'part' ? 'Part' : 'Labour') + (i.added_by ? ' · ' + i.added_by : '') })), h('td', { class: 'right num', text: i.qty }),
        isStaff() ? [h('td', { class: 'right num', text: kes(i.unit_price) }), h('td', { class: 'right num', text: kes(i.qty * i.unit_price) })] : null,
        h('td', { class: 'right' }, editable ? h('button', { class: 'btn sm ghost danger', 'aria-label': 'Remove ' + i.description, text: 'Remove', onclick: async () => { try { render(await api(`/jobs/${id}/items/${i.id}`, { method: 'DELETE' })); } catch (e) { fail(e); } } }) : null)))))) : h('p', { class: 'muted small', text: 'No parts or labour added yet.' });

    // add part
    const ps = h('input', { id: 'part-search', placeholder: 'Search parts by name or SKU', 'aria-label': 'Search parts' }), pq = h('input', { type: 'number', min: 1, value: 1, 'aria-label': 'Quantity', style: { width: '80px' } }), sg = h('div', { class: 'sugg hidden' }); let pid = null, pt;
    ps.addEventListener('input', () => { clearTimeout(pt); pid = null; pt = setTimeout(async () => { if (!ps.value.trim()) return sg.classList.add('hidden'); const r = await api('/parts?q=' + encodeURIComponent(ps.value)).catch(() => []);
      sg.replaceChildren(...(r.length ? r.slice(0, 8).map(p => h('button', { type: 'button', onclick: () => { pid = p.id; ps.value = p.name; sg.classList.add('hidden'); } }, h('span', { text: p.name }), h('span', { class: 'muted num', text: p.qty + ' in stock' }))) : [h('div', { class: 'empty', text: 'No matching parts' })])); sg.classList.remove('hidden'); }, 180); });
    const addPart = h('button', { class: 'btn', id: 'add-part', text: 'Add part', onclick: async () => { try { if (!pid) throw new Error('Pick a part from the list'); render((await api(`/jobs/${id}/items`, { method: 'POST', body: { kind: 'part', part_id: pid, qty: pq.value } }))); } catch (e) { fail(e); } } });
    const ld = h('input', { id: 'labour-desc', placeholder: 'Labour, e.g. Brake pad replacement', 'aria-label': 'Labour description' }), lq = h('input', { type: 'number', min: 1, value: 1, 'aria-label': 'Hours or units', style: { width: '70px' } }), lp = h('input', { id: 'labour-price', type: 'number', min: 0, placeholder: 'Price', 'aria-label': 'Labour price', style: { width: '110px' } });
    const addLab = h('button', { class: 'btn', id: 'add-labour', text: 'Add labour', onclick: async () => { try { render(await api(`/jobs/${id}/items`, { method: 'POST', body: { kind: 'labour', description: ld.value, qty: lq.value, unit_price: lp.value } })); } catch (e) { fail(e); } } });

    box.replaceChildren(
      h('div', { class: 'row wrap' }, plate(j.plate, true), pill(st), h('span', { class: 'grow' }), h('button', { class: 'btn ghost', 'aria-label': 'Close', text: 'Close', onclick: o.close })),
      h('h1', { style: { marginTop: '10px' }, text: j.number }), h('p', { class: 'muted', style: { margin: '2px 0' }, text: `${[j.make, j.model].filter(Boolean).join(' ') || 'Vehicle'} · ${j.customer} · ${j.phone}` }),
      h('p', { class: 'muted small', style: { margin: 0 }, text: `In ${when(j.created_at)}` + (j.mileage_in ? ` · ${Number(j.mileage_in).toLocaleString()} km` : '') + (j.fuel_level ? ` · fuel ${j.fuel_level}` : '') + (j.belongings ? ` · left in car: ${j.belongings}` : '') }),
      st !== 'cancelled' ? h('div', { class: 'steps', 'aria-hidden': 'true', style: { '--c': c } }, STAGES.map((s2, k) => h('i', { class: k <= Math.max(STAGES.indexOf(st), st === 'invoiced' ? 99 : 0) ? 'on' : '' }))) : null,
      h('div', { class: 'panel', style: { marginBottom: '12px' } }, h('h3', { text: 'Customer said' }), h('p', { style: { margin: '4px 0 0' }, text: j.complaint })),
      j.needs_reapproval ? h('div', { class: 'banner warn', role: 'alert', id: 'reapproval' }, h('b', { text: 'Extra work added after approval. ' }), isStaff() ? ['Get the customer to approve the new total before this job can be marked ready. ', approvalBtn()] : 'Your manager needs to get the customer to approve before this job can move on.') : null,
      h('div', { class: 'row wrap', style: { margin: '12px 0' } }, acts),
      mech ? h('label', { class: 'f', style: { maxWidth: '260px' } }, h('span', { text: 'Mechanic' }), mech) : h('p', { class: 'small muted', text: 'Mechanic: ' + (j.mechanic || 'Unassigned') }),
      h('div', { class: 'panel', style: { marginBottom: '12px' } }, h('h2', { text: 'Diagnosis and work done' }), diag, h('div', { style: { marginTop: '8px' } }, h('button', { class: 'btn sm', id: 'save-diag', text: 'Save notes', onclick: async () => { try { render(await api('/jobs/' + id, { method: 'PATCH', body: { diagnosis: diag.value } })); toast('Notes saved'); } catch (e) { fail(e); } } }))),
      h('div', { class: 'panel', style: { marginBottom: '12px' } }, h('h2', { text: 'Parts and labour' }), items,
        isStaff() && j.totals ? h('div', { class: 'right num small', style: { marginTop: '8px' } }, h('div', { text: 'Subtotal ' + kes(j.totals.subtotal) }), h('div', { text: 'VAT 16% ' + kes(j.totals.vat) }), h('div', { style: { fontWeight: 700, fontSize: '16px' }, 'data-total': j.totals.total, text: 'Total ' + kes(j.totals.total) }), j.approved_total != null ? h('div', { class: 'muted', text: 'Approved ' + kes(j.approved_total) }) : null) : null,
        editable ? h('div', { style: { marginTop: '14px' } }, h('div', { class: 'row' }, h('div', { class: 'grow' }, ps), pq, addPart), sg,
          isStaff() ? h('div', { class: 'row wrap', style: { marginTop: '8px' } }, h('div', { class: 'grow', style: { minWidth: '160px' } }, ld), lq, lp, addLab) : null) : null),
      h('div', { class: 'panel' }, h('h2', { text: 'Timeline' }), h('ul', { class: 'timeline' }, j.events.map(e => h('li', {}, e.text, h('div', { class: 'small muted', text: when(e.created_at) + (e.user ? ' · ' + e.user : '') }))))));
  };
  try { await render(); } catch (e) { o.close(); fail(e); }
}

/* ---------- vehicles ---------- */
PAGES.vehicles = async m => {
  const q = h('input', { class: 'search', placeholder: 'Search plate, owner or phone', 'aria-label': 'Search vehicles', id: 'vehicle-search' }), body = h('div', { class: 'panel tbl' });
  const load = async () => {
    const r = await api('/vehicles?q=' + encodeURIComponent(q.value));
    body.replaceChildren(r.length ? h('table', {}, h('thead', {}, h('tr', {}, ['Plate', 'Vehicle', 'Owner', 'Phone', 'Mileage'].map(x => h('th', { text: x })))), h('tbody', {}, r.map(v => h('tr', { class: 'click', tabindex: 0, onclick: () => vehicleHistory(v.id), onkeydown: e => e.key === 'Enter' && vehicleHistory(v.id) },
      h('td', {}, plate(v.plate)), h('td', { text: [v.make, v.model, v.year].filter(Boolean).join(' ') }), h('td', { text: v.customer }), h('td', { class: 'num', text: v.phone }), h('td', { class: 'num', text: v.mileage ? Number(v.mileage).toLocaleString() + ' km' : '' }))))) : h('div', { class: 'empty', text: q.value ? 'No vehicle matches that search.' : 'No vehicles yet. Register the first one when a customer arrives.' }));
  };
  let t; q.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => load().catch(fail), 200); });
  m.replaceChildren(header('Vehicles', q, isStaff() ? h('button', { class: 'btn primary', id: 'add-vehicle', text: 'Register vehicle', onclick: () => addVehicle() }) : null), body); await load();
};
async function vehicleHistory(id) {
  const d = await api('/vehicles/' + id).catch(e => { fail(e); return null; }); if (!d) return; const v = d.vehicle;
  const m = h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Vehicle history' }, h('div', { class: 'row' }, plate(v.plate, true), h('span', { class: 'muted', text: [v.make, v.model, v.year].filter(Boolean).join(' ') })),
    h('p', { class: 'muted', text: `${v.customer} · ${v.phone}` }), h('h2', { text: 'Service history' }),
    d.jobs.length ? h('table', {}, h('tbody', {}, d.jobs.map(j => h('tr', { class: 'click', onclick: () => openJob(j.id) }, h('td', { text: j.number }), h('td', { text: j.complaint.slice(0, 50) }), h('td', {}, pill(j.status)), h('td', { class: 'small muted', text: when(j.created_at) }))))) : h('p', { class: 'muted', text: 'No jobs yet for this vehicle.' }),
    h('div', { class: 'row', style: { justifyContent: 'flex-end', marginTop: '14px' } }, isStaff() ? h('button', { class: 'btn primary', id: 'job-from-vehicle', text: 'New job card', onclick: () => { o.close(); newJob({ id: v.id, plate: v.plate, customer: v.customer }); } }) : null, h('button', { class: 'btn', text: 'Close', onclick: () => o.close() })));
  const o = overlay(m, true);
}

/* ---------- stock ---------- */
PAGES.stock = async m => {
  const q = h('input', { class: 'search', placeholder: 'Search name, SKU or category', 'aria-label': 'Search stock', id: 'stock-search' }), low = h('input', { type: 'checkbox', id: 'low-only', style: { width: 'auto', minHeight: 0 } }), body = h('div', { class: 'panel tbl' });
  const load = async () => {
    const r = await api('/parts?q=' + encodeURIComponent(q.value) + (low.checked ? '&low=1' : ''));
    body.replaceChildren(r.length ? h('table', {}, h('thead', {}, h('tr', {}, ['SKU', 'Part', 'In stock', 'Price', isStaff() ? 'Cost' : null, ''].filter(x => x !== null).map(x => h('th', { class: ['In stock', 'Price', 'Cost'].includes(x) ? 'right' : '', text: x })))),
      h('tbody', {}, r.map(p => h('tr', { 'data-sku': p.sku }, h('td', { class: 'small muted', text: p.sku }), h('td', {}, p.name, p.supplier ? h('div', { class: 'small muted', text: p.supplier }) : null),
        h('td', { class: 'right num' }, p.low ? h('span', { class: 'tag ' + (p.qty === 0 ? 'bad' : 'warn'), style: { marginRight: '8px' }, text: p.qty === 0 ? 'Out' : 'Low' }) : null, String(p.qty)),
        h('td', { class: 'right num', text: kes(p.sell_price) }), isStaff() ? h('td', { class: 'right num muted', text: kes(p.unit_cost) }) : null,
        h('td', { class: 'right' }, isStaff() ? [h('button', { class: 'btn sm', 'data-act': 'adjust', text: 'Adjust', onclick: () => adjustStock(p) }), ' ', h('button', { class: 'btn sm ghost', text: 'History', onclick: () => stockHistory(p) })] : null))))) : h('div', { class: 'empty', text: q.value || low.checked ? 'No parts match.' : 'Your store is empty. Add parts to start tracking stock.' }));
  };
  let t; q.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => load().catch(fail), 200); }); low.addEventListener('change', () => load().catch(fail));
  m.replaceChildren(header('Stock', q, h('label', { class: 'row small' }, low, 'Low stock only'), isStaff() ? h('button', { class: 'btn primary', id: 'add-part-btn', text: 'Add part', onclick: addPartModal }) : null), body); await load();
};
function addPartModal() {
  const fs = [field('SKU', 'sku', { ph: 'OIL-5W30' }), field('Part name', 'name'), field('Category', 'category', { ph: 'Oils and fluids' }), field('Supplier', 'supplier'), field('Cost price (KES)', 'unit_cost', { type: 'number', min: 0 }), field('Selling price (KES)', 'sell_price', { type: 'number', min: 0 }), field('Opening quantity', 'qty', { type: 'number', min: 0 }), field('Reorder when stock falls to', 'reorder_level', { type: 'number', min: 0 })];
  formModal({ title: 'Add part', fields: fs, submit: 'Add part', onSubmit: async (v, close) => { const body = {}; fs.forEach(f => { if (v[f.name] !== '') body[f.name] = v[f.name]; }); await api('/parts', { method: 'POST', body }); close(); toast('Part added'); S.refresh(); } });
}
function adjustStock(p) {
  const fs = [field('Reason', 'reason', { type: 'select', options: [{ v: 'received', l: 'Received from supplier' }, { v: 'stocktake', l: 'Stocktake correction' }, { v: 'damaged', l: 'Damaged or lost' }, { v: 'returned to supplier', l: 'Returned to supplier' }] }), field('Quantity change (use − to remove)', 'delta', { type: 'number' }), field('New cost price (optional)', 'unit_cost', { type: 'number', min: 0 }), field('Reference (invoice or delivery note)', 'ref')];
  formModal({ title: 'Adjust ' + p.name, note: p.qty + ' currently in stock.', fields: fs, submit: 'Save adjustment', onSubmit: async (v, close) => {
    const body = { reason: v.reason, delta: v.delta }; if (v.unit_cost !== '') body.unit_cost = v.unit_cost; if (v.ref) body.ref = v.ref;
    await api(`/parts/${p.id}/adjust`, { method: 'POST', body }); close(); toast('Stock updated'); S.refresh(); } });
}
async function stockHistory(p) {
  const r = await api(`/parts/${p.id}/moves`).catch(e => { fail(e); return null; }); if (!r) return;
  const o = overlay(h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Stock history' }, h('h2', { text: p.name + ': stock history' }),
    r.length ? h('div', { class: 'tbl' }, h('table', {}, h('tbody', {}, r.map(x => h('tr', {}, h('td', { class: 'small muted', text: when(x.created_at) }), h('td', { text: x.reason + (x.ref ? ' · ' + x.ref : '') }), h('td', { class: 'small muted', text: x.user || '' }), h('td', { class: 'right num', style: { fontWeight: 600, color: x.delta < 0 ? 'var(--bad)' : 'var(--ok)' }, text: (x.delta > 0 ? '+' : '') + x.delta })))))) : h('p', { class: 'muted', text: 'No movements yet.' }),
    h('div', { class: 'row', style: { justifyContent: 'flex-end', marginTop: '12px' } }, h('button', { class: 'btn', text: 'Close', onclick: () => o.close() }))), true);
}

/* ---------- invoices ---------- */
PAGES.invoices = async m => {
  const r = await api('/invoices');
  m.replaceChildren(header('Invoices'), h('div', { class: 'panel tbl' }, r.length ? h('table', {}, h('thead', {}, h('tr', {}, ['Invoice', 'Vehicle', 'Customer', 'Date', 'Total', 'Balance', 'Status'].map(x => h('th', { class: ['Total', 'Balance'].includes(x) ? 'right' : '', text: x })))),
    h('tbody', {}, r.map(i => h('tr', { class: 'click', tabindex: 0, 'data-inv': i.number, onclick: () => openInvoice(i.id), onkeydown: e => e.key === 'Enter' && openInvoice(i.id) }, h('td', { text: i.number }), h('td', {}, plate(i.plate)), h('td', { text: i.customer }), h('td', { class: 'small muted', text: when(i.created_at) }),
      h('td', { class: 'right num', text: kes(i.total) }), h('td', { class: 'right num', text: kes(i.total - i.paid) }), h('td', {}, h('span', { class: 'tag ' + (i.status === 'paid' ? 'ok' : i.status === 'partial' ? 'warn' : 'bad'), text: i.status === 'paid' ? 'Paid' : i.status === 'partial' ? 'Part paid' : 'Unpaid' })))))) : h('div', { class: 'empty', text: 'No invoices yet. Mark a job ready, then create its invoice.' })));
};
async function openInvoice(id) {
  const draw = async () => {
    const i = await api('/invoices/' + id);
    const pm = field('Payment method', 'method', { type: 'select', options: [{ v: 'mpesa', l: 'M-Pesa' }, { v: 'cash', l: 'Cash' }, { v: 'card', l: 'Card' }, { v: 'bank', l: 'Bank transfer' }] });
    const am = field('Amount (KES)', 'amount', { type: 'number', value: i.balance }), rf = field('M-Pesa code', 'reference', { ph: 'SGH7K2L9QP' });
    pm.inp.addEventListener('change', () => { rf.el.firstChild.textContent = pm.inp.value === 'mpesa' ? 'M-Pesa code' : 'Reference (optional)'; });
    const et = field('eTIMS invoice number', 'etims_ref', { value: i.etims_ref || '', ph: 'From KRA eTIMS' });
    const payForm = i.balance > 0 ? h('form', { class: 'noprint', novalidate: true, style: { marginTop: '14px' }, onsubmit: async e => { e.preventDefault(); try { await api(`/invoices/${id}/pay`, { method: 'POST', body: { method: pm.inp.value, amount: am.inp.value, reference: rf.inp.value } }); toast('Payment recorded'); S.refresh(); box(); } catch (er) { showErr(e.target, er); } } },
      h('h2', { text: 'Record payment' }), h('div', { class: 'grid2' }, pm.el, am.el), rf.el, h('button', { class: 'btn primary', id: 'record-payment', type: 'submit', text: 'Record payment' })) : null;
    const etForm = h('form', { class: 'noprint row', style: { alignItems: 'flex-end', marginTop: '12px' }, novalidate: true, onsubmit: async e => { e.preventDefault(); try { await api('/invoices/' + id, { method: 'PATCH', body: { etims_ref: et.inp.value } }); toast('eTIMS number saved'); } catch (er) { showErr(e.target, er); } } }, h('div', { class: 'grow' }, et.el), h('button', { class: 'btn', style: { marginBottom: '12px' }, type: 'submit', text: 'Save' }));
    const content = h('div', { class: 'modal printable', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Invoice ' + i.number },
      h('div', { class: 'row' }, h('div', { class: 'grow' }, h('h2', { style: { margin: 0 }, text: S.garage.name }), h('div', { class: 'small muted', text: 'KRA PIN: ' + (S.garage.kra_pin || 'not set') + (S.garage.phone ? ' · ' + S.garage.phone : '') })), h('div', { class: 'right' }, h('b', { text: i.number }), h('div', { class: 'small muted', text: when(i.created_at) }))),
      h('p', { style: { margin: '12px 0' } }, plate(i.plate), ' ', i.customer, ' ', h('span', { class: 'muted', text: i.phone })),
      h('table', {}, h('thead', {}, h('tr', {}, h('th', { text: 'Item' }), h('th', { class: 'right', text: 'Qty' }), h('th', { class: 'right', text: 'Price' }), h('th', { class: 'right', text: 'Amount' }))),
        h('tbody', {}, i.items.map(x => h('tr', {}, h('td', { text: x.description }), h('td', { class: 'right num', text: x.qty }), h('td', { class: 'right num', text: kes(x.unit_price) }), h('td', { class: 'right num', text: kes(x.qty * x.unit_price) }))))),
      h('div', { class: 'right num', style: { marginTop: '10px' } }, h('div', { text: 'Subtotal ' + kes(i.subtotal) }), h('div', { text: 'VAT 16% ' + kes(i.vat) }), h('div', { style: { fontWeight: 700, fontSize: '17px' }, text: 'Total ' + kes(i.total) }), h('div', { text: 'Paid ' + kes(i.paid) }), h('div', { 'data-balance': i.balance, style: { fontWeight: 700 }, text: 'Balance ' + kes(i.balance) })),
      i.payments.length ? h('div', { style: { marginTop: '10px' } }, h('h3', { text: 'Payments' }), i.payments.map(p => h('div', { class: 'small row', style: { justifyContent: 'space-between' } }, h('span', { text: `${when(p.created_at)} · ${p.method}${p.reference ? ' · ' + p.reference : ''}` }), h('span', { class: 'num', text: kes(p.amount) })))) : null,
      i.etims_ref ? h('p', { class: 'small', text: 'eTIMS invoice no: ' + i.etims_ref }) : null, payForm, etForm,
      h('div', { class: 'row noprint', style: { justifyContent: 'flex-end', marginTop: '8px' } }, h('button', { class: 'btn', text: 'Print', onclick: () => window.print() }), h('button', { class: 'btn', text: 'Close', onclick: () => o.close() })));
    return content;
  };
  const wrap = h('div'); const o = overlay(wrap, true); o.scrim.onclose = () => S.refresh();
  const box = async () => { try { wrap.replaceChildren(await draw()); } catch (e) { o.close(); fail(e); } }; await box();
}

/* ---------- reports ---------- */
PAGES.reports = async m => {
  const days = h('select', { 'aria-label': 'Period', id: 'period', style: { width: 'auto' } }, [7, 30, 90].map(d => h('option', { value: d, text: 'Last ' + d + ' days' })));
  days.value = S.days || 30; days.addEventListener('change', () => { S.days = days.value; S.refresh(); });
  const r = await api('/reports/summary?days=' + days.value);
  const plural = (n, w) => n + ' ' + w + (n === 1 ? '' : 's');
  const kpi = (l, v, sub, f, c) => h('div', { class: 'kpi' }, h('div', { class: 'l', text: l }), h('div', { class: 'v num', text: v }), f != null ? dots(f, 1, c, 34) : null, sub ? h('div', { class: 's', text: sub }) : null);
  const open = Object.entries(r.jobs_by_status).filter(([k]) => !['invoiced', 'cancelled'].includes(k)).reduce((x, [, v]) => x + v, 0);
  const rate = r.invoiced ? Math.min(100, Math.round(100 * r.collected / r.invoiced)) : 0;
  const chart = (() => {
    const W = 640, H = 200, pad = 28, d = r.daily, mx = Math.max(1, ...d.map(x => x.amount)), slot = (W - pad * 2) / Math.max(d.length, 1), bw = Math.min(22, slot - 8);
    const el = (t, at) => { const e2 = document.createElementNS(NS, t); for (const k in at) e2.setAttribute(k, at[k]); return e2; };
    const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, width: '100%', role: 'img', 'aria-label': 'Daily collections' });
    svg.append(el('line', { x1: pad, x2: W - pad, y1: H - 28, y2: H - 28, stroke: 'rgba(60,45,30,.15)' }));
    d.forEach((x, k) => { const bh = Math.max(3, (H - 66) * x.amount / mx), cx = pad + (k + .5) * slot; const rc = el('rect', { x: cx - bw / 2, y: H - 28 - bh, width: bw, height: bh, rx: 6, fill: 'var(--brand)' }); const tt = el('title', {}); tt.textContent = x.day + ': ' + kes(x.amount); rc.append(tt); svg.append(rc);
      const tx = el('text', { x: cx, y: H - 9, 'text-anchor': 'middle', 'font-size': 11, fill: 'rgba(60,45,30,.55)' }); tx.textContent = x.day.slice(5); svg.append(tx); });
    return d.length ? svg : h('div', { class: 'empty', text: 'No payments in this period yet.' });
  })();
  const tbl = (cols, rows_) => rows_.length ? h('div', { class: 'tbl' }, h('table', {}, h('thead', {}, h('tr', {}, cols.map(c => h('th', { class: c[1] ? 'right' : '', text: c[0] })))), h('tbody', {}, rows_.map(rw => h('tr', {}, rw.map((c, k) => h('td', { class: cols[k][1] ? 'right num' : '', text: c })))))) ) : h('div', { class: 'empty', text: 'Nothing to show yet.' });
  m.replaceChildren(h('div', { class: 'head' }, h('div', {}, h('h1', { text: 'Reports' }), h('p', { text: 'How the workshop is earning, and where the money is.' })), h('span', { class: 'grow' }), days),
    h('div', { class: 'kpis', id: 'kpis' }, kpi('Collected', kes(r.collected), r.by_method.map(x => x.method + ' ' + kes(x.amount)).join(' · ') || 'No payments yet', rate / 100, 'var(--s-ready)'), kpi('Invoiced', kes(r.invoiced), plural(r.invoice_count, 'invoice') + ' · VAT ' + kes(r.vat_collected)), kpi('Still owed', kes(r.outstanding), plural(r.outstanding_count, 'unpaid invoice'), r.invoiced ? r.outstanding / r.invoiced : 0, 'var(--bad)'), kpi('Gross profit', kes(r.gross_profit), 'before VAT and overheads'), kpi('Avg. turnaround', r.avg_turnaround_hours == null ? 'No data' : r.avg_turnaround_hours + ' h', open + ' jobs open now'), kpi('Stock value', kes(r.stock_value), plural(r.low_stock, 'part') + ' low or out')),
    h('div', { class: 'two' }, h('div', { class: 'panel' }, h('h2', { text: 'Daily collections' }), chart),
      h('div', { class: 'panel' }, h('h2', { text: 'Collection rate' }), ring(rate, 'var(--brand)', rate + '%', 'of invoiced is paid', 'Collection rate ' + rate + ' percent'))),
    h('div', { class: 'two' }, h('div', { class: 'panel' }, h('h2', { text: 'Mechanics' }), tbl([['Mechanic'], ['Jobs finished', 1], ['Labour billed', 1], ['Avg. hours per job', 1]], r.mechanics.map(x => [x.name, x.jobs, kes(x.labour_revenue), x.avg_hours]))),
      h('div', { class: 'panel' }, h('h2', { text: 'Top parts by profit' }), tbl([['Part'], ['Qty', 1], ['Profit', 1]], r.top_parts.map(p => [p.name, p.qty, kes(p.profit)])))));
};

/* ---------- team ---------- */
PAGES.team = async m => {
  const u = await api('/users'); const aud = S.user.role === 'owner' ? await api('/audit') : [];
  const fs = () => [field('Full name', 'name'), field('Phone', 'phone', { type: 'tel', ph: '0712 345 678' }), field('Email', 'email', { type: 'email' }), field('Role', 'role', { type: 'select', options: [{ v: 'mechanic', l: 'Mechanic' }, ...(S.user.role === 'owner' ? [{ v: 'manager', l: 'Manager' }] : [])] }), field('Temporary password', 'password', { type: 'text', ph: '8+ characters, letters and numbers', auto: 'off' })];
  m.replaceChildren(header('Team', h('button', { class: 'btn primary', id: 'add-user', text: 'Add team member', onclick: () => { const f = fs(); formModal({ title: 'Add team member', fields: f, submit: 'Add member', onSubmit: async (v, close) => { await api('/users', { method: 'POST', body: v }); close(); toast('Team member added'); S.mechanics = (await api('/users')).filter(x => x.role === 'mechanic' && x.active); S.refresh(); } }); } })),
    h('div', { class: 'panel tbl' }, h('table', {}, h('thead', {}, h('tr', {}, ['Name', 'Role', 'Phone', 'Email', 'Status', ''].map(x => h('th', { text: x })))),
      h('tbody', {}, u.map(x => h('tr', {}, h('td', { text: x.name }), h('td', { text: x.role }), h('td', { class: 'num', text: x.phone || '' }), h('td', { text: x.email }), h('td', {}, h('span', { class: 'tag ' + (x.active ? 'ok' : 'bad'), text: x.active ? 'Active' : 'Disabled' })),
        h('td', { class: 'right' }, x.role !== 'owner' && (S.user.role === 'owner' || x.role === 'mechanic') ? h('button', { class: 'btn sm ghost', 'data-act': 'reset-pw', text: 'Reset password', onclick: () => resetMemberPassword(x) }) : null, ' ', x.role !== 'owner' ? h('button', { class: 'btn sm', text: x.active ? 'Disable' : 'Enable', onclick: async () => { try { await api('/users/' + x.id, { method: 'PATCH', body: { active: !x.active } }); S.mechanics = (await api('/users')).filter(y => y.role === 'mechanic' && y.active); S.refresh(); } catch (e) { fail(e); } } }) : null)))))),
    aud.length ? h('div', { class: 'panel', style: { marginTop: '16px' } }, h('h2', { text: 'Activity log' }), h('div', { class: 'tbl' }, h('table', {}, h('tbody', {}, aud.slice(0, 25).map(a => h('tr', {}, h('td', { class: 'small muted', text: when(a.created_at) }), h('td', { text: a.user || 'System' }), h('td', { text: a.action }), h('td', { class: 'small muted', text: a.detail || '' }))))))) : null);
};

function resetMemberPassword(u) {
  const f = field('New temporary password', 'password', { type: 'text', ph: '8+ characters, letters and numbers' });
  formModal({ title: 'Reset password for ' + u.name, fields: [f], submit: 'Set password', note: 'They\u2019ll be signed out everywhere. Tell them the new password in person, then ask them to change it after signing in.', onSubmit: async (v, close) => { await api(`/users/${u.id}/password`, { method: 'POST', body: v }); close(); toast('Password reset for ' + u.name); } });
}

boot();
