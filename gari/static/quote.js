(async function () {
  const root = document.getElementById('root'), tok = location.pathname.split('/').pop();
  const r = await fetch('/api/public/quote/' + encodeURIComponent(tok)); const d = await r.json();
  if (!r.ok) { root.append(h('h1', { text: 'Quote unavailable' }), h('p', { class: 'muted', text: d.error })); return; }
  const approve = h('button', { class: 'btn primary', id: 'approve-btn', text: 'Approve this quote', onclick: async e => {
    e.target.disabled = true;
    const x = await fetch('/api/public/quote/' + encodeURIComponent(tok) + '/approve', { method: 'POST' });
    if (x.ok) { root.replaceChildren(h('h1', { text: 'Approved. Thank you.' }), h('p', { class: 'muted', text: d.garage + ' will start work on your vehicle. Call ' + (d.garage_phone || 'the garage') + ' if anything changes.' })); }
    else { e.target.disabled = false; toast((await x.json()).error, true); }
  } });
  root.append(h('p', { class: 'muted', text: d.garage }), h('h1', { text: 'Repair quote ' + d.number }),
    h('p', {}, h('span', { class: 'plate lg', text: d.vehicle.plate }), ' ', h('span', { class: 'muted', text: [d.vehicle.make, d.vehicle.model].filter(Boolean).join(' ') })),
    d.diagnosis ? h('div', { class: 'panel', style: { margin: '12px 0' } }, h('h3', { text: 'What we found' }), h('p', { text: d.diagnosis })) : null,
    h('div', { class: 'panel tbl' }, h('table', {}, h('thead', {}, h('tr', {}, h('th', { text: 'Item' }), h('th', { class: 'right', text: 'Qty' }), h('th', { class: 'right', text: 'Amount' }))),
      h('tbody', {}, d.items.map(i => h('tr', {}, h('td', { text: i.description }), h('td', { class: 'right num', text: i.qty }), h('td', { class: 'right num', text: kes(i.qty * i.unit_price) })))),
      h('tfoot', {}, ['Subtotal', 'VAT 16%', 'Total'].map((l, k) => h('tr', {}, h('td', { colspan: 2, class: 'right', text: l }), h('td', { class: 'right num', style: { fontWeight: k == 2 ? 700 : 400 }, text: kes([d.subtotal, d.vat, d.total][k]) })))))),
    h('div', { class: 'row', style: { marginTop: '16px' } }, approve));
})();
