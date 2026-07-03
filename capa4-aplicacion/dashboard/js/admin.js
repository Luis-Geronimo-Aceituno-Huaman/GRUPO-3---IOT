/*
 * admin.js — Pestaña de administración (solo rol admin).
 *
 *   - Usuarios: crear / cambiar rol / activar-desactivar / resetear contraseña.
 *   - Detector: editar los parámetros de visión (detector_params) con validación
 *     de rango; el gateway los recarga al inicio de CADA análisis (hot-reload).
 *   - Riesgo: pesos y umbrales del motor risk.py (system_config['risk']).
 *
 * Toda acción queda en la tabla events (auditoría) — lo registra el backend.
 */

async function renderAdminTab() {
  if (!CURRENT_USER || CURRENT_USER.role !== 'admin') return;
  await Promise.all([_renderUsers(), _renderDetectorParams(), _renderRiskConfig()]);
}

/* ------------------------------- usuarios -------------------------------- */
async function _renderUsers() {
  const box = document.getElementById('adminUsers');
  if (!box) return;
  try {
    const users = await fetchJSON('/api/users');
    box.innerHTML = `
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr><th>Usuario</th><th>Rol</th><th>Nombre</th><th>Activo</th>
                     <th>Último ingreso</th><th>Acciones</th></tr></thead>
          <tbody>
            ${users.map(u => `
              <tr class="${u.active ? '' : 'row-dim'}">
                <td><b>${u.username}</b></td>
                <td><span class="role-tag ${u.role}">${u.role}</span></td>
                <td>${u.full_name || '<span class="muted">—</span>'}</td>
                <td>${u.active ? '✅' : '⛔'}</td>
                <td class="muted small">${u.last_login ? new Date(u.last_login).toLocaleString('es-PE') : 'nunca'}</td>
                <td class="actions">
                  <button class="btn-sm" onclick="adminToggleRole(${u.id}, '${u.role}')">↔ rol</button>
                  <button class="btn-sm" onclick="adminResetPass(${u.id}, '${u.username}')">🔑 clave</button>
                  ${u.active
                    ? `<button class="btn-sm danger" onclick="adminDeactivate(${u.id}, '${u.username}')">desactivar</button>`
                    : `<button class="btn-sm" onclick="adminReactivate(${u.id})">reactivar</button>`}
                </td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>
      <div class="admin-new-user">
        <input id="nuUsername" class="form-input" placeholder="usuario nuevo" />
        <input id="nuPassword" class="form-input" type="password" placeholder="contraseña (mín. 6)" />
        <select id="nuRole" class="form-input">
          <option value="operador">operador</option>
          <option value="admin">admin</option>
        </select>
        <input id="nuFullname" class="form-input" placeholder="nombre completo (opcional)" />
        <button class="btn accent" onclick="adminCreateUser()">+ Crear usuario</button>
      </div>`;
  } catch (e) {
    box.innerHTML = `<div class="banner-info">No se pudieron cargar los usuarios: ${e.message}</div>`;
  }
}

async function adminCreateUser() {
  try {
    await fetchJSON('/api/users', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: document.getElementById('nuUsername').value.trim(),
        password: document.getElementById('nuPassword').value,
        role: document.getElementById('nuRole').value,
        full_name: document.getElementById('nuFullname').value.trim() || null,
      }),
    });
    toast('Usuario creado ✓');
    _renderUsers();
  } catch (e) { toast('Error: ' + e.message, true); }
}

async function adminToggleRole(uid, current) {
  const nuevo = current === 'admin' ? 'operador' : 'admin';
  if (!confirm(`¿Cambiar rol a '${nuevo}'?`)) return;
  try {
    await fetchJSON(`/api/users/${uid}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role: nuevo }),
    });
    toast('Rol actualizado ✓'); _renderUsers();
  } catch (e) { toast('Error: ' + e.message, true); }
}

async function adminResetPass(uid, username) {
  const p = prompt(`Nueva contraseña para '${username}' (mín. 6):`);
  if (!p) return;
  try {
    await fetchJSON(`/api/users/${uid}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: p }),
    });
    toast('Contraseña actualizada ✓');
  } catch (e) { toast('Error: ' + e.message, true); }
}

async function adminDeactivate(uid, username) {
  if (!confirm(`¿Desactivar a '${username}'? (soft-delete: su historial se conserva)`)) return;
  try {
    await fetchJSON(`/api/users/${uid}`, { method: 'DELETE' });
    toast('Usuario desactivado'); _renderUsers();
  } catch (e) { toast('Error: ' + e.message, true); }
}

async function adminReactivate(uid) {
  try {
    await fetchJSON(`/api/users/${uid}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active: true }),
    });
    toast('Usuario reactivado ✓'); _renderUsers();
  } catch (e) { toast('Error: ' + e.message, true); }
}

/* --------------------------- parámetros detector -------------------------- */
async function _renderDetectorParams() {
  const box = document.getElementById('adminDetector');
  if (!box) return;
  try {
    const params = await fetchJSON('/api/config/detector');
    box.innerHTML = `
      <p class="muted small">El gateway relee estos valores al inicio de cada análisis de clip
        (no hace falta reiniciar nada). Rango permitido entre corchetes.</p>
      <div class="param-grid">
        ${params.map(p => `
          <label class="param-row" title="${p.description || ''}">
            <span class="param-key">${p.key}
              <span class="muted small">[${p.min_num ?? '−∞'} … ${p.max_num ?? '∞'}]</span></span>
            <input class="form-input param-input" data-key="${p.key}"
                   type="number" step="any" value="${p.value_num}" />
          </label>`).join('')}
      </div>
      <div class="modal-actions">
        <button class="btn accent" onclick="adminSaveDetector()">Guardar parámetros</button>
      </div>`;
  } catch (e) {
    box.innerHTML = `<div class="banner-info">No se pudo cargar la configuración: ${e.message}</div>`;
  }
}

async function adminSaveDetector() {
  const body = {};
  document.querySelectorAll('#adminDetector .param-input').forEach(inp => {
    body[inp.dataset.key] = parseFloat(inp.value);
  });
  try {
    const r = await fetchJSON('/api/config/detector', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const errs = Object.entries(r.errores || {});
    toast(errs.length
      ? `Aplicados ${Object.keys(r.aplicados).length}; errores: ` +
        errs.map(([k, v]) => `${k}: ${v}`).join(', ')
      : 'Parámetros del detector guardados ✓', errs.length > 0);
  } catch (e) { toast('Error: ' + e.message, true); }
}

/* ----------------------------- config riesgo ------------------------------ */
async function _renderRiskConfig() {
  const box = document.getElementById('adminRisk');
  if (!box) return;
  try {
    const cfg = await fetchJSON('/api/config/risk');
    box.innerHTML = `
      <p class="muted small">Pesos por factor (se renormalizan con los sensores presentes)
        y umbrales de nivel. El job de riesgo lo aplica en ≤5 min.</p>
      <div class="param-grid">
        ${Object.entries(cfg.pesos).map(([k, v]) => `
          <label class="param-row"><span class="param-key">peso · ${k}</span>
            <input class="form-input risk-peso" data-key="${k}" type="number"
                   step="0.05" min="0" max="1" value="${v}" /></label>`).join('')}
        ${Object.entries(cfg.umbrales_nivel).map(([k, v]) => `
          <label class="param-row"><span class="param-key">umbral · ${k} ${RISK_EMOJI[k] || ''}</span>
            <input class="form-input risk-umbral" data-key="${k}" type="number"
                   min="0" max="100" value="${v}" /></label>`).join('')}
      </div>
      <div class="modal-actions">
        <button class="btn accent" onclick="adminSaveRisk()">Guardar riesgo</button>
      </div>`;
  } catch (e) {
    box.innerHTML = `<div class="banner-info">No se pudo cargar la configuración: ${e.message}</div>`;
  }
}

async function adminSaveRisk() {
  const pesos = {}, umbrales = {};
  document.querySelectorAll('#adminRisk .risk-peso').forEach(i => {
    pesos[i.dataset.key] = parseFloat(i.value);
  });
  document.querySelectorAll('#adminRisk .risk-umbral').forEach(i => {
    umbrales[i.dataset.key] = parseFloat(i.value);
  });
  try {
    await fetchJSON('/api/config/risk', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pesos, umbrales_nivel: umbrales }),
    });
    toast('Configuración de riesgo guardada ✓');
  } catch (e) { toast('Error: ' + e.message, true); }
}
