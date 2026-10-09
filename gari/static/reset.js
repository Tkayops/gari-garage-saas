(function () {
  const token = location.pathname.split('/').pop(), root = document.getElementById('root');
  const mk = (label, name, ph) => { const inp = h('input', { name, type: 'password', autocomplete: 'new-password', placeholder: ph }); return { inp, el: h('label', { class: 'f', 'data-name': name }, h('span', { text: label }), inp) }; };
  const a = mk('New password', 'password', '8+ characters, letters and numbers'), b = mk('Confirm new password', 'confirm', 'Type it again');
  const err = (f, m) => { document.querySelectorAll('.err').forEach(x => x.remove()); f.el.append(h('div', { class: 'err', role: 'alert', text: m })); f.inp.focus(); };
  const btn = h('button', { class: 'btn primary', type: 'submit', text: 'Save new password' });
  const form = h('form', { novalidate: true }, a.el, b.el, btn);
  form.addEventListener('submit', async e => {
    e.preventDefault(); document.querySelectorAll('.err').forEach(x => x.remove());
    if (a.inp.value !== b.inp.value) return err(b, 'The two passwords don\u2019t match');
    btn.disabled = true;
    const r = await fetch('/api/auth/reset', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token, password: a.inp.value }) });
    const d = await r.json().catch(() => ({}));
    if (r.ok) { root.replaceChildren(h('div', { class: 'auth' }, h('div', { class: 'box' }, h('h1', { id: 'done', text: 'Password updated' }), h('p', { class: 'sub', text: 'You\u2019ve been signed out everywhere. Sign in with your new password.' }), h('a', { class: 'btn primary', href: '/app', text: 'Go to sign in' })))); return; }
    btn.disabled = false; err(d.field === 'password' ? a : b, d.error || 'Something went wrong');
  });
  root.append(h('div', { class: 'auth' }, h('div', { class: 'box' }, h('div', { class: 'brand' }, h('i'), 'Gari'), h('h1', { text: 'Choose a new password' }), h('p', { class: 'sub', text: 'This link works once and expires 30 minutes after it was sent.' }), form)));
})();
