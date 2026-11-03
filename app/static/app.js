const state = { map: null, route: null, selectedEdge: null, toastTimer: null };
const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail;
    const message = typeof detail === 'string' ? detail : detail?.message || JSON.stringify(detail || payload);
    const error = new Error(message || `Request failed (${response.status})`);
    error.payload = payload;
    error.status = response.status;
    throw error;
  }
  return payload;
}

function toast(message, kind = 'success') {
  const el = $('toast');
  el.textContent = message;
  el.className = `toast ${kind === 'error' ? 'error' : kind === 'warning' ? 'warning' : ''}`;
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => el.classList.add('hidden'), 3600);
}

function setFeedback(id, message, isError = false) {
  const el = $(id);
  el.textContent = message;
  el.classList.toggle('error', isError);
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]);
}

function labelForNode(id) {
  return state.map?.nodes.find((node) => node.id === id)?.name || id;
}

function labelForEdge(edge) {
  return `${labelForNode(edge.source)} ↔ ${labelForNode(edge.target)} · ${edge.type} (${edge.distance_m} m)`;
}

function selectedRouteEdgeIds() {
  return new Set((state.route?.edges || []).map((edge) => edge.id));
}

function populateSelectors() {
  const { nodes, profiles, facilities, edges } = state.map;
  $('startSelect').innerHTML = nodes.map((n) => `<option value="${n.id}">${escapeHtml(n.name)} · ${escapeHtml(n.floor)}</option>`).join('');
  $('destinationSelect').innerHTML = nodes.map((n) => `<option value="${n.id}">${escapeHtml(n.name)} · ${escapeHtml(n.floor)}</option>`).join('');
  $('startSelect').value = 'GATE';
  $('destinationSelect').value = 'CS_DEPT';
  $('profileSelect').innerHTML = Object.entries(profiles).map(([key, p]) => `<option value="${key}">${escapeHtml(p.label)}</option>`).join('');
  $('profileSelect').value = 'wheelchair';
  $('facilitySelect').innerHTML = facilities.map((f) => `<option value="${f.id}">${escapeHtml(f.name)}</option>`).join('');
  $('edgeSelect').innerHTML = edges.map((e) => `<option value="${e.id}">${escapeHtml(labelForEdge(e))}</option>`).join('');
  $('reportTarget').innerHTML = `<optgroup label="Route segments">${edges.map((e) => `<option value="edge:${e.id}">${escapeHtml(labelForEdge(e))}</option>`).join('')}</optgroup><optgroup label="Facilities">${facilities.map((f) => `<option value="facility:${f.id}">${escapeHtml(f.name)}</option>`).join('')}</optgroup>`;
  $('reportTarget').value = 'facility:E1';
  updateProfileExplainer();
}

function updateProfileExplainer() {
  const profile = state.map?.profiles[$('profileSelect').value];
  $('profileExplainer').textContent = profile ? profile.description : '';
}

function renderMap() {
  if (!state.map) return;
  const svg = $('campusMap');
  const nodes = state.map.nodes;
  const edgeById = new Map(state.map.edges.map((edge) => [edge.id, edge]));
  const routeIds = selectedRouteEdgeIds();
  let html = `
    <rect x="10" y="20" width="920" height="95" rx="12" class="floor-band" />
    <rect x="10" y="132" width="920" height="205" rx="12" class="floor-band" />
    <rect x="10" y="345" width="920" height="70" rx="12" class="floor-band" />
    <text x="27" y="40" class="floor-label">FIRST FLOOR</text>
    <text x="27" y="152" class="floor-label">GROUND FLOOR</text>
    <text x="27" y="366" class="floor-label">OUTDOOR APPROACH</text>`;
  for (const edge of state.map.edges) {
    const a = nodes.find((n) => n.id === edge.source);
    const b = nodes.find((n) => n.id === edge.target);
    if (!a || !b) continue;
    const classes = ['edge-line'];
    if (routeIds.has(edge.id)) classes.push('route-active');
    if (edge.status !== 'open') classes.push('edge-blocked');
    const selected = state.selectedEdge === edge.id;
    const title = `${labelForEdge(edge)} | ${edge.status}`;
    html += `<line class="${classes.join(' ')}" data-edge-id="${edge.id}" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke-width="${selected ? 7 : 3}" opacity="${selected ? 1 : .95}"><title>${escapeHtml(title)}</title></line>`;
  }
  const routeNodeIds = new Set(state.route?.node_ids || []);
  for (const node of nodes) {
    const classNames = ['node-circle'];
    if (routeNodeIds.has(node.id)) classNames.push('route-node');
    if (state.route?.start === node.id) classNames.push('start-node');
    if (state.route?.destination === node.id) classNames.push('destination-node');
    const labelClass = node.name.length > 20 ? 'node-label small' : 'node-label';
    html += `<g data-node-id="${node.id}"><circle class="${classNames.join(' ')}" cx="${node.x}" cy="${node.y}" r="7"><title>${escapeHtml(node.name)} · ${escapeHtml(node.floor)}</title></circle><text class="${labelClass}" x="${node.x + (node.dx || 0)}" y="${node.y + (node.dy || -13)}" text-anchor="middle">${escapeHtml(node.name)}</text></g>`;
  }
  svg.innerHTML = html;
  svg.querySelectorAll('[data-edge-id]').forEach((line) => {
    line.addEventListener('click', () => {
      state.selectedEdge = line.dataset.edgeId;
      $('edgeSelect').value = state.selectedEdge;
      renderMap();
    });
  });
  svg.querySelectorAll('[data-node-id]').forEach((group) => {
    group.style.cursor = 'pointer';
    group.addEventListener('click', () => {
      const nodeId = group.dataset.nodeId;
      const targetField = state.nextMapClickTarget || (document.activeElement === $('destinationSelect') ? 'destination' : 'start');
      $(targetField === 'destination' ? 'destinationSelect' : 'startSelect').value = nodeId;
      state.nextMapClickTarget = null;
      toast(`${labelForNode(nodeId)} selected as ${targetField}.`);
      calculateRoute(false);
    });
  });
  renderFacilityChips();
}

function renderFacilityChips() {
  const facilities = state.map.facilities;
  $('floorStatus').innerHTML = facilities.map((f) => `<span class="facility-chip ${f.status === 'unavailable' ? 'unavailable' : ''}">${f.status === 'available' ? '●' : '✕'} ${escapeHtml(f.name)}: <strong>${escapeHtml(f.status)}</strong></span>`).join('');
  const unavailableEdges = state.map.edges.filter((e) => e.status !== 'open').length;
  $('campusStatus').textContent = unavailableEdges ? `${unavailableEdges} route segment${unavailableEdges === 1 ? '' : 's'} unavailable` : 'All mapped segments open';
  const latest = [...facilities.map((f) => f.updated_at), ...state.map.edges.map((e) => e.updated_at)].filter(Boolean).sort().at(-1);
  $('campusUpdated').textContent = latest ? `Latest status update: ${new Date(latest).toLocaleString()}` : 'No recent status update';
}

function renderRoute() {
  const route = state.route;
  $('routeError').classList.add('hidden');
  if (!route) {
    $('routeEmpty').classList.remove('hidden');
    $('routeResult').classList.add('hidden');
    $('routeBadge').className = 'badge neutral';
    $('routeBadge').textContent = 'Not calculated';
    renderMap();
    return;
  }
  $('routeEmpty').classList.add('hidden');
  $('routeResult').classList.remove('hidden');
  $('routeBadge').className = 'badge good';
  $('routeBadge').textContent = 'Feasible route';
  $('distanceMetric').textContent = route.distance_m;
  $('segmentsMetric').textContent = route.edges.length;
  $('facilityMetric').textContent = route.edges.filter((e) => ['elevator', 'stairs'].includes(e.type)).length;
  $('routeMessage').textContent = route.message;
  const steps = [];
  route.nodes.forEach((node, index) => {
    const edge = route.edges[index];
    steps.push(`<li><strong>${escapeHtml(node.name)}</strong><span>${escapeHtml(node.floor)}${edge ? ` · next: ${escapeHtml(edge.type)} · ${edge.distance_m} m` : ' · destination'}</span></li>`);
  });
  $('routeSteps').innerHTML = steps.join('');
  renderMap();
}

function renderReports() {
  const reports = state.map.reports || [];
  if (!reports.length) {
    $('reportsQueue').innerHTML = '<div class="queue-empty">No reports yet. Submit a barrier report above to test the review workflow.</div>';
    return;
  }
  $('reportsQueue').innerHTML = reports.map((r) => {
    const target = r.edge_id ? labelForEdge(state.map.edges.find((e) => e.id === r.edge_id) || { source: r.edge_id, target: '', type: 'segment', distance_m: '' }) : (state.map.facilities.find((f) => f.id === r.facility_id)?.name || r.facility_id);
    const safeTarget = escapeHtml(target);
    const actions = r.status === 'verified'
      ? `<button class="mini-btn resolve" data-review="resolve" data-id="${r.id}">Resolve</button>`
      : ['resolved', 'rejected'].includes(r.status)
        ? ''
        : `<button class="mini-btn verify" data-review="verify" data-id="${r.id}">Verify & apply</button><button class="mini-btn" data-review="under_review" data-id="${r.id}">Under review</button><button class="mini-btn" data-review="reject" data-id="${r.id}">Reject</button>`;
    return `<article class="report-card"><div><div class="report-title-row"><strong>#${r.id} · ${escapeHtml(r.barrier_type)}</strong><span class="report-state ${r.status}">${escapeHtml(r.status.replace('_', ' '))}</span></div><div class="report-meta">${safeTarget} · By ${escapeHtml(r.reporter_alias)} · ${new Date(r.created_at).toLocaleString()}</div><div class="report-desc">${escapeHtml(r.description)}${r.review_note ? `<br><em>Review note: ${escapeHtml(r.review_note)}</em>` : ''}</div></div><div class="report-actions">${actions}</div></article>`;
  }).join('');
  $('reportsQueue').querySelectorAll('[data-review]').forEach((button) => {
    button.addEventListener('click', async () => {
      const decision = button.dataset.review;
      const note = decision === 'verify' ? 'Verified in the demo admin console.' : decision === 'resolve' ? 'Barrier confirmed resolved in the demo.' : '';
      try {
        await api(`/api/reports/${button.dataset.id}/review`, { method: 'POST', body: JSON.stringify({ decision, review_note: note }) });
        toast(decision === 'verify' ? 'Report verified; routing state updated.' : `Report marked ${decision.replace('_', ' ')}.`);
        await refreshState({ keepRoute: true });
        await calculateRoute(false);
      } catch (err) { toast(err.message, 'error'); }
    });
  });
}

async function refreshState({ keepRoute = true } = {}) {
  state.map = await api('/api/map');
  if (!state.selectedEdge || !state.map.edges.some((e) => e.id === state.selectedEdge)) state.selectedEdge = state.map.edges[0]?.id;
  const previousStart = $('startSelect').value;
  const previousDestination = $('destinationSelect').value;
  const previousProfile = $('profileSelect').value;
  const previousFacility = $('facilitySelect').value;
  const previousReportTarget = $('reportTarget').value;
  populateSelectors();
  if (state.map.nodes.some((n) => n.id === previousStart)) $('startSelect').value = previousStart;
  if (state.map.nodes.some((n) => n.id === previousDestination)) $('destinationSelect').value = previousDestination;
  if (state.map.profiles[previousProfile]) $('profileSelect').value = previousProfile;
  $('edgeSelect').value = state.selectedEdge;
  if (state.map.facilities.some((f) => f.id === previousFacility)) $('facilitySelect').value = previousFacility;
  if ([...$('reportTarget').options].some((option) => option.value === previousReportTarget)) {
    $('reportTarget').value = previousReportTarget;
  }
  const facility = state.map.facilities.find((f) => f.id === $('facilitySelect').value);
  if (facility) $('facilityStatusSelect').value = facility.manual_status;
  const selectedEdge = state.map.edges.find((e) => e.id === $('edgeSelect').value);
  if (selectedEdge) $('edgeStatusSelect').value = selectedEdge.direct_status;
  updateProfileExplainer();
  renderMap();
  renderReports();
  if (!keepRoute) state.route = null;
  renderRoute();
}

async function calculateRoute(showToast = true) {
  try {
    const route = await api('/api/route', {
      method: 'POST',
      body: JSON.stringify({ start: $('startSelect').value, destination: $('destinationSelect').value, profile: $('profileSelect').value }),
    });
    state.route = route;
    renderRoute();
    if (showToast) toast(`Route calculated: ${route.distance_m} m across ${route.edges.length} segments.`);
    return true;
  } catch (err) {
    state.route = null;
    renderRoute();
    $('routeError').classList.remove('hidden');
    $('routeBadge').className = 'badge bad';
    $('routeBadge').textContent = 'No feasible route';
    $('routeEmpty').classList.add('hidden');
    $('routeError').textContent = err.message;
    renderMap();
    if (showToast) toast(err.message, 'error');
    return false;
  }
}

$('findRouteBtn').addEventListener('click', () => calculateRoute(true));
$('profileSelect').addEventListener('change', () => { updateProfileExplainer(); calculateRoute(false); });
$('startSelect').addEventListener('change', () => calculateRoute(false));
$('destinationSelect').addEventListener('change', () => calculateRoute(false));
$('refreshBtn').addEventListener('click', async () => {
  try { await refreshState(); await calculateRoute(false); toast('Infrastructure state refreshed.'); }
  catch (err) { toast(err.message, 'error'); }
});
$('refreshReportsBtn').addEventListener('click', async () => {
  try { await refreshState(); await calculateRoute(false); toast('Report queue and route refreshed.'); } catch (err) { toast(err.message, 'error'); }
});
$('facilitySelect').addEventListener('change', () => {
  const facility = state.map.facilities.find((f) => f.id === $('facilitySelect').value);
  if (facility) $('facilityStatusSelect').value = facility.manual_status;
});
$('edgeSelect').addEventListener('change', () => {
  state.selectedEdge = $('edgeSelect').value;
  const edge = state.map.edges.find((e) => e.id === state.selectedEdge);
  if (edge) $('edgeStatusSelect').value = edge.direct_status;
  renderMap();
});
$('applyFacilityBtn').addEventListener('click', async () => {
  const id = $('facilitySelect').value;
  const status = $('facilityStatusSelect').value;
  try {
    const result = await api(`/api/admin/facilities/${id}/status`, { method: 'POST', body: JSON.stringify({ status, note: 'Changed in demo controls.' }) });
    setFeedback('adminFeedback', `${id} admin status set to ${result.manual_status}; effective routing status is ${result.status}. Recalculating the route.`);
    await refreshState();
    await calculateRoute(false);
    toast(`${id} routing status is ${result.status}.`);
  } catch (err) { setFeedback('adminFeedback', err.message, true); toast(err.message, 'error'); }
});
$('applyEdgeBtn').addEventListener('click', async () => {
  const id = $('edgeSelect').value;
  const status = $('edgeStatusSelect').value;
  try {
    const result = await api(`/api/admin/edges/${id}/status`, { method: 'POST', body: JSON.stringify({ status, note: 'Changed in demo controls.' }) });
    setFeedback('adminFeedback', `${id} admin status set to ${result.manual_status}; effective routing status is ${result.status}. Recalculating the route.`);
    await refreshState();
    await calculateRoute(false);
    toast(`Selected segment routing status is ${result.status}.`);
  } catch (err) { setFeedback('adminFeedback', err.message, true); toast(err.message, 'error'); }
});
$('reportForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const target = $('reportTarget').value;
  const [kind, id] = target.split(':');
  const payload = {
    ...(kind === 'edge' ? { edge_id: id } : { facility_id: id }),
    barrier_type: $('barrierType').value,
    description: $('reportDescription').value.trim(),
    reporter_alias: $('reporterAlias').value.trim() || 'Anonymous',
  };
  try {
    const result = await api('/api/reports', { method: 'POST', body: JSON.stringify(payload) });
    setFeedback('reportFeedback', `Report #${result.report.id} submitted as pending. It will not change routing until verified.`);
    $('reportDescription').value = '';
    await refreshState();
    toast(`Barrier report #${result.report.id} submitted.`);
  } catch (err) { setFeedback('reportFeedback', err.message, true); toast(err.message, 'error'); }
});

// Clicking a mapped node defaults to changing the origin. Focus the destination selector before clicking a node to set destination.
$('destinationSelect').addEventListener('focus', () => { state.nextMapClickTarget = 'destination'; });
$('startSelect').addEventListener('focus', () => { state.nextMapClickTarget = 'start'; });

(async function boot() {
  try {
    await refreshState({ keepRoute: false });
    await calculateRoute(false);
  } catch (err) {
    $('campusStatus').textContent = 'API not connected';
    $('campusUpdated').textContent = 'Start the FastAPI server and refresh this page.';
    toast(`Could not load AccessPath: ${err.message}`, 'error');
  }
})();
