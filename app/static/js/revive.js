/* Revive JS v2.0 — Rivive design aligned */

document.addEventListener('DOMContentLoaded', function () {

  // ── Auto-dismiss flash messages ─────────────────────────────────────────
  document.querySelectorAll('.mc-flash').forEach(el => {
    setTimeout(() => { bootstrap.Alert.getOrCreateInstance(el)?.close(); }, 5000);
  });

  // ── Live datetime in topnav ─────────────────────────────────────────────
  const dtEl = document.getElementById('mc-datetime');
  function updateDT() {
    if (!dtEl) return;
    const n = new Date();
    const d = n.toLocaleDateString('en-IN', { day:'2-digit', month:'short', year:'numeric' });
    const t = n.toLocaleTimeString('en-IN', { hour:'2-digit', minute:'2-digit', hour12:true });
    dtEl.innerHTML = `<strong>${t}</strong>${d}`;
  }
  updateDT();
  setInterval(updateDT, 30000);

  // ── Left panel mobile toggle ────────────────────────────────────────────
  const panelToggle = document.getElementById('mc-panel-toggle');
  const leftPanel = document.querySelector('.mc-left-panel');
  if (panelToggle && leftPanel) {
    panelToggle.addEventListener('click', () => leftPanel.classList.toggle('open'));
    document.addEventListener('click', e => {
      if (leftPanel.classList.contains('open') &&
          !leftPanel.contains(e.target) && !panelToggle.contains(e.target)) {
        leftPanel.classList.remove('open');
      }
    });
  }

  // ── Confirm dialogs ─────────────────────────────────────────────────────
  document.querySelectorAll('[data-confirm]').forEach(el => {
    el.addEventListener('click', e => {
      if (!confirm(el.dataset.confirm || 'Are you sure?')) {
        e.preventDefault(); e.stopPropagation();
      }
    });
  });

  // ── DataTables auto-init ────────────────────────────────────────────────
  document.querySelectorAll('table.mc-datatable').forEach(table => {
    if (typeof $.fn !== 'undefined' && $.fn.DataTable) {
      $(table).DataTable({
        responsive: true,
        pageLength: 25,
        dom: '<"d-flex justify-content-between align-items-center mb-2"lf>rt<"d-flex justify-content-between align-items-center mt-2"ip>',
        language: {
          search: '', searchPlaceholder: 'Search…',
          lengthMenu: 'Show _MENU_',
          info: '_START_–_END_ of _TOTAL_',
          paginate: { previous: '‹', next: '›' },
        },
        order: [],
      });
    }
  });

  // ── Tab switching (mc-tab) ──────────────────────────────────────────────
  document.querySelectorAll('.mc-subnav-item[data-tab]').forEach(tab => {
    tab.addEventListener('click', function () {
      const group = this.closest('[data-tab-group]')?.dataset?.tabGroup || 'default';
      document.querySelectorAll(`.mc-subnav-item[data-tab]`).forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.mc-tab-pane').forEach(p => p.classList.add('d-none'));
      this.classList.add('active');
      const pane = document.getElementById('tab-' + this.dataset.tab);
      if (pane) pane.classList.remove('d-none');
    });
  });

  // ── AJAX Patient Search ─────────────────────────────────────────────────
  const psInput = document.getElementById('patient-search');
  const psId    = document.getElementById('patient-id-field');
  const psBox   = document.getElementById('patient-results');
  if (psInput && psBox) {
    let t;
    psInput.addEventListener('input', function () {
      clearTimeout(t);
      const q = this.value.trim();
      if (q.length < 2) { psBox.innerHTML = ''; psBox.style.display = 'none'; return; }
      t = setTimeout(() => {
        fetch('/patients/search-json?q=' + encodeURIComponent(q))
          .then(r => r.json())
          .then(data => {
            if (!data.length) {
              psBox.innerHTML = '<div class="p-2 text-muted small">No results</div>';
            } else {
              psBox.innerHTML = data.map(p =>
                `<div class="mc-ps-item p-2" data-id="${p.id}" data-name="${p.name}" data-uhid="${p.uhid}">
                  <strong>${p.name}</strong>
                  <span class="mc-uhid ms-1">${p.uhid}</span>
                  <span class="text-muted ms-2 small">${p.phone} ${p.gender||''} ${p.age||''}</span>
                </div>`
              ).join('');
            }
            psBox.style.display = 'block';
          });
      }, 280);
    });
    psBox.addEventListener('click', e => {
      const item = e.target.closest('.mc-ps-item');
      if (item) {
        psInput.value = `${item.dataset.name} (${item.dataset.uhid})`;
        if (psId) { psId.value = item.dataset.id; psId.dispatchEvent(new Event('change')); }
        psBox.style.display = 'none';
      }
    });
    document.addEventListener('click', e => {
      if (!psInput.contains(e.target)) psBox.style.display = 'none';
    });
  }

  // ── Upload zone drag/drop ───────────────────────────────────────────────
  const uz = document.querySelector('.mc-upload-zone');
  const fi = uz?.querySelector('input[type="file"]');
  if (uz && fi) {
    uz.addEventListener('click', () => fi.click());
    uz.addEventListener('dragover', e => { e.preventDefault(); uz.classList.add('dragover'); });
    uz.addEventListener('dragleave', () => uz.classList.remove('dragover'));
    uz.addEventListener('drop', e => {
      e.preventDefault(); uz.classList.remove('dragover');
      if (e.dataTransfer.files.length) {
        fi.files = e.dataTransfer.files;
        const fn = uz.querySelector('.mc-upload-fname');
        if (fn) fn.textContent = e.dataTransfer.files[0].name;
        uz.closest('form')?.querySelector('[data-upload-btn]')?.removeAttribute('disabled');
      }
    });
    fi.addEventListener('change', function () {
      const fn = uz.querySelector('.mc-upload-fname');
      if (fn && this.files.length) fn.textContent = this.files[0].name;
      uz.closest('form')?.querySelector('[data-upload-btn]')?.removeAttribute('disabled');
    });
  }

  // ── BMI auto-calc ───────────────────────────────────────────────────────
  const wt = document.getElementById('weight_kg');
  const ht = document.getElementById('height_cm');
  const bm = document.getElementById('bmi');
  function calcBMI() {
    const w = parseFloat(wt?.value), h = parseFloat(ht?.value) / 100;
    if (bm && w > 0 && h > 0) bm.value = (w / (h * h)).toFixed(1);
  }
  wt?.addEventListener('input', calcBMI);
  ht?.addEventListener('input', calcBMI);

  // ── Tooltip init ────────────────────────────────────────────────────────
  document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => new bootstrap.Tooltip(el));

  // ── Print ───────────────────────────────────────────────────────────────
  document.querySelectorAll('[data-print]').forEach(btn => btn.addEventListener('click', () => window.print()));

});

// Global helpers
function mcPost(url, data = {}) {
  const form = document.createElement('form');
  form.method = 'POST'; form.action = url;
  const csrf = document.querySelector('meta[name="csrf-token"]') || document.querySelector('input[name="csrf_token"]');
  if (csrf) {
    const i = document.createElement('input'); i.type='hidden'; i.name='csrf_token'; i.value=csrf.content||csrf.value;
    form.appendChild(i);
  }
  Object.entries(data).forEach(([k, v]) => {
    const i = document.createElement('input'); i.type='hidden'; i.name=k; i.value=v;
    form.appendChild(i);
  });
  document.body.appendChild(form); form.submit();
}

function mcINR(v) {
  return new Intl.NumberFormat('en-IN', { style:'currency', currency:'INR', maximumFractionDigits:2 }).format(v);
}
