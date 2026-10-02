/* =====================================================
   ONION_SURE Web Dashboard — app.js
   SIH 2026 PS26031 | Department of Consumer Affairs
   ===================================================== */

'use strict';

// ── State ──
const STATE = {
  apiUrl: localStorage.getItem('onion_api_url') || (window.location.protocol.startsWith('http') ? window.location.origin : 'http://127.0.0.1:8000'),
  token:  localStorage.getItem('onion_token') || null,
  user:   JSON.parse(localStorage.getItem('onion_user') || 'null'),
};

const ROLE_LABELS = {
  SUPER_ADMIN: 'Super Admin',
  CENTRE_ADMIN: 'Centre Admin',
  OPERATOR: 'Operator',
  AUDITOR: 'Auditor',
  INSPECTOR: 'Inspector',
  ADMIN: 'Admin',
  REVIEWER: 'Reviewer',
  OFFICER: 'Officer',
};

function normalizeRoleName(role) {
  return String(role || '').trim().toUpperCase().replace(/[-\s]+/g, '_');
}

function getUserRoles(user) {
  if (!user) return [];
  const rawRoles = Array.isArray(user.roles) ? user.roles : [user.role || 'OPERATOR'];
  return rawRoles.map(normalizeRoleName).filter(Boolean);
}

function getPrimaryRole(user) {
  const roles = getUserRoles(user);
  const priority = ['SUPER_ADMIN', 'CENTRE_ADMIN', 'OPERATOR', 'AUDITOR', 'INSPECTOR', 'ADMIN', 'REVIEWER', 'OFFICER'];
  for (const role of priority) {
    if (roles.includes(role)) return role;
  }
  return roles[0] || 'OPERATOR';
}

function applyRoleNavigation() {
  const primaryRole = getPrimaryRole(STATE.user);
  const allowedByRole = {
    SUPER_ADMIN: ['dashboard','farmers','centres','lots','inspections','upload','grading','review','reports','verify','settings'],
    CENTRE_ADMIN: ['dashboard','farmers','centres','lots','inspections','grading','review','reports','verify'],
    OPERATOR: ['dashboard','farmers','lots','inspections','upload','grading','reports'],
    AUDITOR: ['dashboard','inspections','review','reports','verify'],
    INSPECTOR: ['dashboard','inspections','upload','grading','reports','verify'],
    ADMIN: ['dashboard','farmers','centres','lots','inspections','review','reports','verify','settings'],
  };
  const allowed = allowedByRole[primaryRole] || allowedByRole.OPERATOR;
  document.querySelectorAll('.nav-item').forEach((nav) => {
    const view = nav.dataset.view;
    const visible = allowed.includes(view);
    nav.style.display = visible ? '' : 'none';
    nav.classList.toggle('hidden-by-role', !visible);
  });
  const activeView = document.querySelector('.nav-item:not([style*="display: none"])');
  if (activeView && !document.querySelector('.nav-item.active:not([style*="display: none"])')) {
    navigate(activeView.dataset.view);
  }
}

// ── API Helper ──
async function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...opts.headers };
  if (STATE.token) headers['Authorization'] = `Bearer ${STATE.token}`;
  if (opts.body instanceof FormData) delete headers['Content-Type'];

  const res = await fetch(`${STATE.apiUrl}${path}`, {
    method: opts.method || 'GET',
    headers,
    body: opts.body instanceof FormData ? opts.body : (opts.body ? JSON.stringify(opts.body) : undefined),
    signal: opts.signal,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.detail || data.message || res.statusText), { status: res.status, data });
  return data;
}

// ── Toast ──
function toast(msg, type = 'success') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `toast ${type}`;
  el.classList.remove('hidden');
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.add('hidden'), 3500);
}

// ── Auth ──
document.getElementById('login-btn').addEventListener('click', login);
document.getElementById('login-password').addEventListener('keydown', e => { if (e.key === 'Enter') login(); });

async function login() {
  const btn  = document.getElementById('login-btn');
  const spin = document.getElementById('login-btn-spinner');
  const txt  = document.getElementById('login-btn-text');
  const err  = document.getElementById('login-error');
  const rawUser = document.getElementById('login-username').value.trim();
  const pass = document.getElementById('login-password').value.trim();

  if (!rawUser || !pass) { showErr(err, 'Please enter username and password.'); return; }

  const email = rawUser.includes('@') ? rawUser : `${rawUser}@onionsure.gov.in`;

  txt.classList.add('hidden'); spin.classList.remove('hidden'); err.classList.add('hidden');
  try {
    let res = await fetch(`${STATE.apiUrl}/api/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password: pass }),
    });

    let data = await res.json().catch(() => ({}));

    // Auto-register on 401 if user doesn't exist yet in dev mode
    if (!res.ok && res.status === 401) {
      try {
        const regRes = await fetch(`${STATE.apiUrl}/api/v1/auth/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email,
            full_name: rawUser.charAt(0).toUpperCase() + rawUser.slice(1),
            password: pass,
            role_names: ['INSPECTOR'],
          }),
        });
        if (regRes.ok) {
          res = await fetch(`${STATE.apiUrl}/api/v1/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password: pass }),
          });
          data = await res.json().catch(() => ({}));
        }
      } catch (_) {}
    }

    if (!res.ok) throw new Error(data.detail || data.message || 'Login failed. Please check credentials.');

    STATE.token = data.access_token;
    localStorage.setItem('onion_token', STATE.token);

    // fetch profile
    try {
      const me = await api('/api/v1/users/me');
      STATE.user = me;
      localStorage.setItem('onion_user', JSON.stringify(me));
    } catch (_) {
      STATE.user = { email: data.email, full_name: data.full_name || rawUser, roles: data.roles || ['INSPECTOR'] };
      localStorage.setItem('onion_user', JSON.stringify(STATE.user));
    }

    bootApp();
  } catch (e) {
    showErr(err, e.message);
  } finally {
    txt.classList.remove('hidden'); spin.classList.add('hidden');
  }
}

function fillDemo(email, pass) {
  document.getElementById('login-username').value = email;
  document.getElementById('login-password').value = pass;
  login();
}

function showErr(el, msg) { el.textContent = msg; el.classList.remove('hidden'); }

function logout() {
  STATE.token = null; STATE.user = null;
  localStorage.removeItem('onion_token'); localStorage.removeItem('onion_user');
  const loginScreen = document.getElementById('screen-login');
  const appScreen   = document.getElementById('screen-app');
  if (appScreen) {
    appScreen.classList.remove('active');
    appScreen.classList.add('hidden');
    appScreen.style.display = 'none';
  }
  if (loginScreen) {
    loginScreen.classList.remove('hidden');
    loginScreen.classList.add('active');
    loginScreen.style.display = 'flex';
  }
}

document.getElementById('logout-btn').addEventListener('click', logout);

// ── Boot ──
function bootApp() {
  const loginScreen = document.getElementById('screen-login');
  const appScreen   = document.getElementById('screen-app');
  if (loginScreen) {
    loginScreen.classList.remove('active');
    loginScreen.classList.add('hidden');
    loginScreen.style.display = 'none';
  }
  if (appScreen) {
    appScreen.classList.remove('hidden');
    appScreen.classList.add('active');
    appScreen.style.display = 'flex';
  }
  setUserUI();
  navigate('dashboard');
  pingHealth();
}

function setUserUI() {
  const u = STATE.user;
  if (!u) return;
  const name = u.full_name || u.email || 'Inspector';
  const role = getPrimaryRole(u);
  const nameEl = document.getElementById('user-name');
  const roleEl = document.getElementById('user-role');
  const avatarEl = document.getElementById('user-avatar');
  if (nameEl) nameEl.textContent = name;
  if (roleEl) roleEl.textContent = ROLE_LABELS[role] || role;
  if (avatarEl) avatarEl.textContent = name.charAt(0).toUpperCase();
  applyRoleNavigation();
}

// ── Navigation ──
function navigate(view) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  const el = document.getElementById(`view-${view}`);
  if (el) el.classList.add('active');
  const nav = document.querySelector(`[data-view="${view}"]`);
  if (nav) nav.classList.add('active');

  const titles = {
    dashboard: 'Dashboard', farmers: 'Farmers', centres: 'Procurement Centres',
    lots: 'Lots', inspections: 'Inspections', upload: 'Upload Image',
    grading: 'AI Grading Results', review: 'Manual Review', reports: 'Reports',
    verify: 'QR Verification', settings: 'Settings',
  };
  document.getElementById('topbar-title').textContent = titles[view] || view;

  // Lazy-load data
  switch (view) {
    case 'dashboard':   loadDashboard(); break;
    case 'farmers':     loadFarmers(); break;
    case 'centres':     loadCentres(); break;
    case 'lots':        loadLots(); break;
    case 'inspections': loadInspections(); break;
    case 'review':      loadReview(); break;
    case 'reports':     loadReports(); break;
    case 'settings':    loadSettings(); break;
  }
}

document.querySelectorAll('.nav-item').forEach(n => {
  n.addEventListener('click', e => { e.preventDefault(); navigate(n.dataset.view); closeSidebar(); });
});

// ── Sidebar toggle (mobile) ──
document.getElementById('sidebar-toggle').addEventListener('click', () => {
  document.getElementById('sidebar').classList.toggle('open');
});
function closeSidebar() { document.getElementById('sidebar').classList.remove('open'); }

// ── Health ──
async function pingHealth() {
  try {
    const h = await api('/health');
    const el = document.getElementById('api-status-indicator');
    if (h.status === 'ok') { el.textContent = '● Live'; el.className = 'api-status'; }
    else { el.textContent = '● Degraded'; el.className = 'api-status offline'; }
  } catch (_) {
    const el = document.getElementById('api-status-indicator');
    el.textContent = '● Offline'; el.className = 'api-status offline';
  }
}

// ── DASHBOARD ──
async function loadDashboard() {
  // Load stats in parallel
  const [lotsData, inspData, farmersData, reportsData] = await Promise.allSettled([
    api('/api/v1/lots?limit=100'),
    api('/api/v1/inspections?limit=100'),
    api('/api/v1/farmers?limit=100'),
    api('/api/v1/reports?limit=100'),
  ]);

  const lots  = getValue(lotsData, []);
  const insps = getValue(inspData, []);
  const farms = getValue(farmersData, []);
  const reps  = getValue(reportsData, []);

  const lotsArr  = Array.isArray(lots)  ? lots  : (lots.items || []);
  const inspsArr = Array.isArray(insps) ? insps : (insps.items || []);
  const farmsArr = Array.isArray(farms) ? farms : (farms.items || []);
  const repsArr  = Array.isArray(reps)  ? reps  : (reps.items || []);

  const gradeA  = repsArr.filter(r => r.lot_decision === 'ACCEPT_GRADE_A' || r.lot_decision === 'ACCEPTABLE').length;
  const urs     = repsArr.filter(r => r.lot_decision === 'ACCEPT_URS' || r.lot_decision === 'CONDITIONAL_URS').length;
  const reject  = repsArr.filter(r => r.lot_decision === 'REJECT_LOT' || r.lot_decision === 'REJECTED').length;
  const review  = inspsArr.filter(r => r.status === 'PENDING_REVIEW' || r.status === 'REVIEW_REQUIRED' || r.status === 'MANUAL_REVIEW').length;

  setVal('stat-grade-a', gradeA || repsArr.length ? gradeA : (inspsArr.filter(i => i.lot_decision === 'ACCEPTABLE').length || '1'));
  setVal('stat-urs',     urs);
  setVal('stat-reject',  reject);
  setVal('stat-review',  review);
  setVal('stat-inspections', inspsArr.length);
  setVal('stat-farmers', farmsArr.length);

  // Recent inspections table
  const recent = inspsArr.slice(0, 10);
  const tbody = recent.map(i => `
    <tr>
      <td><code class="mono">${i.inspection_code || short(i.id)}</code></td>
      <td>${i.lot_number || short(i.lot_id)}</td>
      <td>${fmtDate(i.created_at)}</td>
      <td>${statusBadge(i.status)}</td>
      <td><button class="btn btn-sm btn-outline" onclick="loadGradingForInsp('${i.id}')">View</button></td>
    </tr>`).join('');
  const html = recent.length
    ? `<table class="data-table"><thead><tr><th>ID</th><th>Lot</th><th>Date</th><th>Status</th><th></th></tr></thead><tbody>${tbody}</tbody></table>`
    : `<div class="empty-state">No inspections yet. <a href="#" onclick="navigate('inspections')">Create one →</a></div>`;
  document.getElementById('dashboard-inspections-table').innerHTML = html;
}

function getValue(settled, def) { return settled.status === 'fulfilled' ? settled.value : def; }
function setVal(id, v) { const el = document.getElementById(id); if (el) el.textContent = v; }

// ── FARMERS ──
async function loadFarmers() {
  try {
    const data = await api('/api/v1/farmers?limit=100');
    const arr  = Array.isArray(data) ? data : (data.items || []);
    renderFarmers(arr);
  } catch (e) { document.getElementById('farmers-table').innerHTML = errRow(e); }
}

function renderFarmers(arr) {
  if (!arr.length) { document.getElementById('farmers-table').innerHTML = '<div class="empty-state">No farmers registered yet.</div>'; return; }
  const rows = arr.map(f => `<tr data-search="${(f.name||f.full_name||'').toLowerCase()}">
    <td><strong>${f.name || f.full_name || '—'}</strong></td>
    <td>${f.phone || '—'}</td>
    <td>${f.village ? `${f.village}, ${f.district || ''}` : '—'}</td>
    <td>${statusBadge('active')}</td>
    <td><code class="mono">${f.farmer_code || short(f.id)}</code></td>
  </tr>`).join('');
  document.getElementById('farmers-table').innerHTML =
    `<table class="data-table"><thead><tr><th>Name</th><th>Phone</th><th>Village / District</th><th>Status</th><th>Code</th></tr></thead><tbody>${rows}</tbody></table>`;
}

async function createFarmer() {
  const name = val('farmer-name');
  const phone = val('farmer-phone');
  const village = val('farmer-village') || 'Lasalgaon';
  const aadhaar = val('farmer-aadhaar');
  if (!name) { toast('Name is required', 'error'); return; }

  const code = `FMR-${Date.now().toString().slice(-6)}`;
  const payload = {
    farmer_code: code,
    name: name,
    phone: phone || '+91 99999 00000',
    village: village,
    district: 'Nashik',
    state: 'Maharashtra',
    aadhaar_masked: aadhaar ? `XXXXXXXX${aadhaar}` : 'XXXXXXXX1234',
  };
  try {
    await api('/api/v1/farmers', { method: 'POST', body: payload });
    toast('Farmer created!'); closeModal('modal-farmer'); loadFarmers();
  } catch (e) { toast(e.message, 'error'); }
}

// ── CENTRES ──
async function loadCentres() {
  try {
    const data = await api('/api/v1/procurement-centres?limit=100');
    const arr  = Array.isArray(data) ? data : (data.items || []);
    if (!arr.length) { document.getElementById('centres-table').innerHTML = '<div class="empty-state">No centres registered yet.</div>'; return; }
    const rows = arr.map(c => `<tr>
      <td><strong>${c.name || '—'}</strong></td>
      <td>${c.district || c.location || '—'}</td>
      <td>${c.state || '—'}</td>
      <td>${statusBadge('active')}</td>
      <td><code class="mono">${c.centre_code || short(c.id)}</code></td>
    </tr>`).join('');
    document.getElementById('centres-table').innerHTML =
      `<table class="data-table"><thead><tr><th>Centre Name</th><th>District</th><th>State</th><th>Status</th><th>Code</th></tr></thead><tbody>${rows}</tbody></table>`;
  } catch (e) { document.getElementById('centres-table').innerHTML = errRow(e); }
}

async function createCentre() {
  const name = val('centre-name');
  const loc = val('centre-location') || 'Nashik';
  const state = val('centre-state') || 'Maharashtra';
  if (!name) { toast('Centre name is required', 'error'); return; }

  const code = `PC-${Date.now().toString().slice(-6)}`;
  const payload = { centre_code: code, name: name, district: loc, state: state };
  try {
    await api('/api/v1/procurement-centres', { method: 'POST', body: payload });
    toast('Centre created!'); closeModal('modal-centre'); loadCentres();
  } catch (e) { toast(e.message, 'error'); }
}

async function loadLotFormOptions() {
  try {
    const [farmersData, centresData] = await Promise.all([
      api('/api/v1/farmers?limit=100'),
      api('/api/v1/procurement-centres?limit=100')
    ]);

    const farmers = Array.isArray(farmersData)
      ? farmersData
      : (farmersData.items || []);

    const centres = Array.isArray(centresData)
      ? centresData
      : (centresData.items || []);

    const farmerSelect = document.getElementById('lot-farmer-id');
    const centreSelect = document.getElementById('lot-centre-id');

    if (farmerSelect) {
      farmerSelect.innerHTML =
        '<option value="">Select Farmer</option>' +
        farmers.map(f =>
          `<option value="${f.id}">
            ${f.name || f.full_name || 'Unknown'} — ${f.farmer_code || short(f.id)}
          </option>`
        ).join('');
    }

    if (centreSelect) {
      centreSelect.innerHTML =
        '<option value="">Select Centre</option>' +
        centres.map(c =>
          `<option value="${c.id}">
            ${c.name || 'Unknown'} — ${c.centre_code || short(c.id)}
          </option>`
        ).join('');
    }

  } catch (e) {
    toast('Could not load farmers or centres', 'error');
  }
}
// ── LOTS ──
async function loadLots() {
  await loadLotFormOptions();

  try {
    const data = await api('/api/v1/lots?limit=100');
    const arr  = Array.isArray(data) ? data : (data.items || []);
    if (!arr.length) { document.getElementById('lots-table').innerHTML = '<div class="empty-state">No lots yet.</div>'; return; }
    const rows = arr.map(l => `<tr data-search="${(l.lot_number||'').toLowerCase()}">
      <td><strong>${l.lot_number || '—'}</strong></td>
      <td>${l.variety || '—'}</td>
      <td>${l.quantity_quintals ? l.quantity_quintals + ' Qtl' : (l.quantity_kg ? l.quantity_kg + ' kg' : '—')}</td>
      <td>${fmtDate(l.created_at)}</td>
      <td>${statusBadge(l.status || 'pending')}</td>
      <td><code class="mono">${short(l.id)}</code></td>
    </tr>`).join('');
    document.getElementById('lots-table').innerHTML =
      `<table class="data-table"><thead><tr><th>Lot No.</th><th>Variety</th><th>Quantity</th><th>Date</th><th>Status</th><th>ID</th></tr></thead><tbody>${rows}</tbody></table>`;
  } catch (e) { document.getElementById('lots-table').innerHTML = errRow(e); }
}

async function createLot() {
  const lotNum = val('lot-number');
  if (!lotNum) { toast('Lot number is required', 'error'); return; }

  let farmerId = val('lot-farmer-id');
  let centreId = val('lot-centre-id');

  // Fallback to existing farmer and centre if not manually entered
  if (!farmerId) {
    try {
      const f = await api('/api/v1/farmers?limit=1');
      const farr = Array.isArray(f) ? f : (f.items || []);
      if (farr.length) farmerId = farr[0].id;
    } catch (_) {}
  }
  if (!centreId) {
    try {
      const c = await api('/api/v1/procurement-centres?limit=1');
      const carr = Array.isArray(c) ? c : (c.items || []);
      if (carr.length) centreId = carr[0].id;
    } catch (_) {}
  }

  if (!farmerId || !centreId) { toast('Farmer ID and Centre ID are required', 'error'); return; }

  const qty = parseFloat(val('lot-quantity')) || 50;
  const payload = {
    lot_number: lotNum,
    farmer_id: farmerId,
    procurement_centre_id: centreId,
    variety: val('lot-variety') || 'Red Onion',
    quantity_quintals: qty,
  };
  try {
    await api('/api/v1/lots', { method: 'POST', body: payload });
    toast('Lot created!'); closeModal('modal-lot'); loadLots();
  } catch (e) { toast(e.message, 'error'); }
}

// ── INSPECTIONS ──
async function loadInspections() {
  try {
    const data = await api('/api/v1/inspections?limit=100');
    const arr  = Array.isArray(data) ? data : (data.items || []);
    if (!arr.length) { document.getElementById('inspections-table').innerHTML = '<div class="empty-state">No inspections yet.</div>'; return; }
    const rows = arr.map(i => `<tr>
      <td><code class="mono">${i.inspection_code || short(i.id)}</code></td>
      <td>${short(i.lot_id)}</td>
      <td>${i.sample_size || '—'}</td>
      <td>${fmtDate(i.created_at)}</td>
      <td>${statusBadge(i.status)}</td>
      <td style="display:flex;gap:6px">
        <button class="btn btn-sm btn-outline" onclick="loadGradingForInsp('${i.id}')">Grade</button>
        ${i.status !== 'COMPLETED' ? `<button class="btn btn-sm btn-primary" onclick="finalizeInspection('${i.id}')">Finalize</button>` : ''}
      </td>
    </tr>`).join('');
    document.getElementById('inspections-table').innerHTML =
      `<table class="data-table"><thead><tr><th>ID</th><th>Lot</th><th>Samples</th><th>Date</th><th>Status</th><th>Actions</th></tr></thead><tbody>${rows}</tbody></table>`;
  } catch (e) { document.getElementById('inspections-table').innerHTML = errRow(e); }
}

async function createInspection() {
  const payload = { lot_id: val('insp-lot-id'), sample_size: parseInt(val('insp-sample-size')) || 10, notes: val('insp-notes') };
  if (!payload.lot_id) { toast('Lot ID is required', 'error'); return; }
  try {
    const r = await api('/api/v1/inspections', { method: 'POST', body: payload });
    toast('Inspection created! ID: ' + r.id); closeModal('modal-inspection'); loadInspections();
  } catch (e) { toast(e.message, 'error'); }
}

async function finalizeInspection(id) {
  try {
    await api(`/api/v1/inspections/${id}/finalize`, { method: 'POST', body: {} });
    toast('Inspection finalized & report generated!'); loadInspections(); loadReports();
  } catch (e) { toast(e.message, 'error'); }
}

// ── IMAGE UPLOAD ──
function previewFile(e) {
  const file = e.target.files[0];
  if (!file) return;
  const prev = document.getElementById('image-preview');
  prev.src = URL.createObjectURL(file);
  prev.classList.remove('hidden');
}

// Drag and drop
const dz = document.getElementById('drop-zone');
dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('dragover'); });
dz.addEventListener('dragleave', () => dz.classList.remove('dragover'));
dz.addEventListener('drop', e => {
  e.preventDefault(); dz.classList.remove('dragover');
  const file = e.dataTransfer.files[0];
  if (file) {
    document.getElementById('file-input').files = e.dataTransfer.files;
    const prev = document.getElementById('image-preview');
    prev.src = URL.createObjectURL(file);
    prev.classList.remove('hidden');
  }
});
dz.addEventListener('click', () => document.getElementById('file-input').click());

async function uploadImage() {
  const inspId = val('upload-inspection-id');
  const fileEl = document.getElementById('file-input');
  const resultEl = document.getElementById('upload-result');

  if (!inspId) { toast('Enter an Inspection ID first', 'error'); return; }
  if (!fileEl.files.length) { toast('Select an image first', 'error'); return; }

  const fd = new FormData();
  fd.append('file', fileEl.files[0]);
  fd.append('image_type', 'SAMPLE');

  resultEl.classList.add('hidden');
  try {
    const r = await api(`/api/v1/inspections/${inspId}/upload-image`, { method: 'POST', body: fd });
    resultEl.textContent = JSON.stringify(r, null, 2);
    resultEl.className = 'result-box success';
    resultEl.classList.remove('hidden');
    toast('Image uploaded & analysed!');
  } catch (e) {
    resultEl.textContent = e.message + (e.data ? '\n\n' + JSON.stringify(e.data, null, 2) : '');
    resultEl.className = 'result-box error';
    resultEl.classList.remove('hidden');
    toast(e.message, 'error');
  }
}

// ── GRADING RESULTS ──
function loadGradingForInsp(id) {
  document.getElementById('grade-inspection-id').value = id;
  navigate('grading');
  loadGradingResults();
}

async function loadGradingResults() {
  const id = val('grade-inspection-id');
  const el = document.getElementById('grading-results');
  if (!id) { el.innerHTML = '<div class="empty-state">Enter an Inspection ID to load results.</div>'; return; }
  el.innerHTML = '<div class="loading-row"><span class="spinner"></span> Loading grading results…</div>';

  try {
    const [insp, repData] = await Promise.allSettled([
      api(`/api/v1/inspections/${id}`),
      api(`/api/v1/reports?inspection_id=${id}&limit=1`),
    ]);

    const inspection = getValue(insp, null);
    const reports    = getValue(repData, []);
    const repsArr    = Array.isArray(reports) ? reports : (reports.items || []);
    const report     = repsArr[0] || null;

    if (!inspection) { el.innerHTML = '<div class="empty-state">Inspection not found.</div>'; return; }

    const metrics = report?.summary_metrics || {};
    const gradeA  = metrics.grade_a_percentage ?? '—';
    const urs     = metrics.urs_percentage ?? '—';
    const rej     = metrics.reject_percentage ?? '—';
    const decision = report?.lot_decision || inspection.status || 'PENDING';

    el.innerHTML = `
      <div class="grading-lot-header">
        <div>
          <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">Lot Decision</div>
          <span class="grade-pill ${gradePillClass(decision)}">${decision.replace(/_/g,' ')}</span>
        </div>
        <div>
          <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">Sample Size</div>
          <div style="font-size:20px;font-weight:800;font-family:'JetBrains Mono',monospace">${inspection.sample_size || '—'}</div>
        </div>
        <div>
          <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">Inspection Status</div>
          <div>${statusBadge(inspection.status)}</div>
        </div>
        ${report ? `<div style="margin-left:auto"><a class="btn btn-sm btn-outline" href="${STATE.apiUrl}/api/v1/reports/${report.id}/pdf" target="_blank">⬇ Download PDF</a></div>` : ''}
      </div>
      <div class="pct-bars">
        ${pctBar('Grade A', gradeA, 'var(--green)')}
        ${pctBar('URS', urs, 'var(--yellow)')}
        ${pctBar('Reject', rej, 'var(--red)')}
      </div>
      ${report?.summary_metrics ? `
        <div style="padding:16px 20px;border-top:1px solid var(--border)">
          <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:12px">Report Metrics</div>
          <pre class="result-box">${JSON.stringify(report.summary_metrics, null, 2)}</pre>
        </div>` : ''}
    `;
  } catch (e) {
    el.innerHTML = `<div class="empty-state" style="color:var(--red)">Error: ${e.message}</div>`;
  }
}

function pctBar(label, value, color) {
  const n = typeof value === 'number' ? value : parseFloat(value) || 0;
  return `<div class="pct-bar-row">
    <div class="pct-bar-label">${label}</div>
    <div class="pct-bar-track"><div class="pct-bar-fill" style="width:${Math.min(n,100)}%;background:${color}"></div></div>
    <div class="pct-bar-value" style="color:${color}">${typeof value==='number' ? value.toFixed(1)+'%' : value}</div>
  </div>`;
}

function gradePillClass(d) {
  if (!d) return 'grade-pill-review';
  d = d.toUpperCase();
  if (d.includes('GRADE_A') || d.includes('ACCEPT_GRADE')) return 'grade-pill-a';
  if (d.includes('URS')     || d.includes('ACCEPT_URS'))   return 'grade-pill-urs';
  if (d.includes('REJECT'))    return 'grade-pill-reject';
  return 'grade-pill-review';
}

// ── MANUAL REVIEW ──
async function loadReview() {
  try {
    const data = await api('/api/v1/inspections?status=MANUAL_REVIEW&limit=100');
    const arr  = Array.isArray(data) ? data : (data.items || []);
    if (!arr.length) { document.getElementById('review-table').innerHTML = '<div class="empty-state">✅ No inspections pending manual review.</div>'; return; }
    const rows = arr.map(i => `<tr>
      <td><code class="mono">${short(i.id)}</code></td>
      <td>${short(i.lot_id)}</td>
      <td>${fmtDate(i.created_at)}</td>
      <td>${statusBadge('review')}</td>
      <td><button class="btn btn-sm btn-primary" onclick="loadGradingForInsp('${i.id}')">Review</button></td>
    </tr>`).join('');
    document.getElementById('review-table').innerHTML =
      `<table class="data-table"><thead><tr><th>Inspection ID</th><th>Lot</th><th>Date</th><th>Status</th><th></th></tr></thead><tbody>${rows}</tbody></table>`;
  } catch (e) { document.getElementById('review-table').innerHTML = errRow(e); }
}

// ── REPORTS ──
async function loadReports() {
  try {
    const data = await api('/api/v1/reports?limit=100');
    const arr  = Array.isArray(data) ? data : (data.items || []);
    if (!arr.length) { document.getElementById('reports-table').innerHTML = '<div class="empty-state">No reports yet. Finalize an inspection to generate one.</div>'; return; }
    const rows = arr.map(r => `<tr>
      <td><code class="mono">${r.report_code || short(r.id)}</code></td>
      <td>${short(r.inspection_id)}</td>
      <td>${fmtDate(r.generated_at || r.created_at)}</td>
      <td>${statusBadge(r.lot_decision || 'completed')}</td>
      <td style="display:flex;gap:6px;flex-wrap:wrap">
        <a class="btn btn-sm btn-outline" href="${STATE.apiUrl}/api/v1/reports/${r.id}/pdf" target="_blank">⬇ PDF</a>
        <a class="btn btn-sm btn-outline" href="${STATE.apiUrl}/api/v1/reports/${r.id}/qr" target="_blank">📷 QR</a>
        <button class="btn btn-sm btn-outline" onclick="verifyReport('${r.qr_verification_hash || r.id}')">🔍 Verify</button>
      </td>
    </tr>`).join('');
    document.getElementById('reports-table').innerHTML =
      `<table class="data-table"><thead><tr><th>Report Code</th><th>Inspection</th><th>Date</th><th>Decision</th><th>Actions</th></tr></thead><tbody>${rows}</tbody></table>`;
  } catch (e) { document.getElementById('reports-table').innerHTML = errRow(e); }
}

function verifyReport(hash) {
  document.getElementById('verify-hash').value = hash;
  navigate('verify');
  verifyQR();
}

// ── QR VERIFICATION ──
async function verifyQR() {
  const hash = val('verify-hash');
  const el   = document.getElementById('verify-result');
  if (!hash) { toast('Enter a verification hash', 'error'); return; }
  el.classList.add('hidden');
  try {
    const r = await api(`/api/v1/reports/verify/${hash}`);
    const valid = r.is_valid;
    el.innerHTML = `<div style="margin-bottom:12px;font-size:18px">${valid ? '✅ Certificate Valid' : '❌ Certificate Invalid'}</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px 16px;font-size:12px">
        ${infoRow('Verification Status', r.verification_status)}
        ${infoRow('Report Code', r.report_code)}
        ${infoRow('Lot Decision', r.lot_decision)}
        ${infoRow('Grade A %', r.grade_a_percentage != null ? r.grade_a_percentage + '%' : '—')}
        ${infoRow('URS %', r.urs_percentage != null ? r.urs_percentage + '%' : '—')}
        ${infoRow('Model Version', r.model_version || '—')}
        ${infoRow('Policy Version', r.policy_version || '—')}
        ${infoRow('Source', r.verification_source || '—')}
      </div>`;
    el.className = `result-box ${valid ? 'success' : 'error'}`;
    el.classList.remove('hidden');
  } catch (e) {
    el.textContent = `${e.status === 404 ? '❌ Certificate not found.' : '⚠️ ' + e.message}`;
    el.className = 'result-box error';
    el.classList.remove('hidden');
  }
}

function infoRow(label, value) {
  return `<div><span style="color:var(--text-muted)">${label}</span><br><strong>${value ?? '—'}</strong></div>`;
}

// ── SETTINGS ──
function loadSettings() {
  document.getElementById('settings-api-url').value = STATE.apiUrl;
  const u = STATE.user;
  document.getElementById('settings-user-info').innerHTML = u
    ? `<span>Full Name</span><strong>${u.full_name || '—'}</strong><span>Username</span><strong>${u.username || '—'}</strong><span>Role</span><strong>${u.role || '—'}</strong>`
    : '—';
}

function saveSettings() {
  const url = val('settings-api-url').replace(/\/$/, '');
  STATE.apiUrl = url;
  localStorage.setItem('onion_api_url', url);
  const msg = document.getElementById('settings-msg');
  msg.textContent = '✅ Settings saved!';
  msg.className = 'alert alert-success';
  msg.classList.remove('hidden');
  setTimeout(() => msg.classList.add('hidden'), 2500);
  pingHealth();
}

async function testConnection() {
  const el = document.getElementById('health-result');
  el.innerHTML = '<span class="spinner"></span>';
  try {
    const h = await api('/health');
    el.innerHTML = `<div class="health-ok">✅ Connected — ${h.status} (${h.details?.dialect || 'db'})</div>
      <div style="font-size:11px;color:var(--text-muted);margin-top:4px">${h.timestamp}</div>
      <button class="btn btn-sm btn-outline" style="margin-top:8px" onclick="testConnection()">Re-test</button>`;
  } catch (e) {
    el.innerHTML = `<div class="health-err">❌ Connection failed: ${e.message}</div>
      <button class="btn btn-sm btn-outline" style="margin-top:8px" onclick="testConnection()">Retry</button>`;
  }
}

// ── MODALS ──
function openModal(id) { document.getElementById(id).classList.remove('hidden'); }
function closeModal(id) { document.getElementById(id).classList.add('hidden'); }
document.querySelectorAll('.modal-overlay').forEach(m => {
  m.addEventListener('click', e => { if (e.target === m) closeModal(m.id); });
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') document.querySelectorAll('.modal-overlay:not(.hidden)').forEach(m => closeModal(m.id)); });

// ── TABLE FILTER ──
function filterTable(tableId, searchId) {
  const q = document.getElementById(searchId).value.toLowerCase();
  const wrap = document.getElementById(tableId);
  wrap.querySelectorAll('tr[data-search]').forEach(tr => {
    tr.style.display = tr.dataset.search.includes(q) ? '' : 'none';
  });
}

// ── Helpers ──
function val(id) { const el = document.getElementById(id); return el ? el.value.trim() : ''; }
function short(s) { return s ? s.substring(0, 8) + '…' : '—'; }
function fmtDate(s) { if (!s) return '—'; try { return new Date(s).toLocaleString('en-IN', {dateStyle:'medium',timeStyle:'short'}); } catch { return s; } }
function errRow(e) { return `<div class="empty-state" style="color:var(--red)">⚠️ ${e.message || 'Failed to load data. Is the backend running?'}</div>`; }

function statusBadge(s) {
  if (!s) return '<span class="status status-pending">—</span>';
  const cls = {
    active: 'status-active', COMPLETED: 'status-completed', completed: 'status-completed',
    PENDING: 'status-pending', pending: 'status-pending',
    MANUAL_REVIEW: 'status-review', review: 'status-review',
    ACCEPT_GRADE_A: 'status-grade-a', 'GRADE A': 'status-grade-a',
    ACCEPT_URS: 'status-urs', URS: 'status-urs',
    REJECT_LOT: 'status-reject', REJECTED: 'status-reject', reject: 'status-reject',
  };
  const c = cls[s] || 'status-pending';
  return `<span class="status ${c}">${s.replace(/_/g,' ')}</span>`;
}

// ── Init: auto-login if token exists ──
if (STATE.token) {
  bootApp();
} else {
  const loginScreen = document.getElementById('screen-login');
  const appScreen   = document.getElementById('screen-app');
  if (loginScreen) {
    loginScreen.classList.remove('hidden');
    loginScreen.classList.add('active');
    loginScreen.style.display = 'flex';
  }
  if (appScreen) {
    appScreen.classList.remove('active');
    appScreen.classList.add('hidden');
    appScreen.style.display = 'none';
  }
}
