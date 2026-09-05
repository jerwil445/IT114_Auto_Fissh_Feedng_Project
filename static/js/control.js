let loadedSettings = false;
let slots = [];
function renderSlots() {
  $('schedule-editor').innerHTML = slots.length ? slots.map((slot, index) => `<div class="editor-row" data-index="${index}"><label class="switch"><input type="checkbox" data-field="enabled" ${slot.enabled ? 'checked' : ''} aria-label="Enable ${escapeHtml(slot.name)}"><span></span></label><div><label for="name-${index}">Feeding name</label><input id="name-${index}" data-field="name" value="${escapeHtml(slot.name)}" maxlength="80" required></div><div><label for="time-${index}">Time</label><input id="time-${index}" type="time" data-field="time" value="${escapeHtml(slot.time)}" required></div><div><label for="portion-${index}">Portion / feed type</label><input id="portion-${index}" data-field="portion" value="${escapeHtml(slot.portion)}" maxlength="80" required></div><button type="button" class="delete" data-delete="${index}" aria-label="Delete ${escapeHtml(slot.name)}">Delete</button></div>`).join('') : '<div class="empty">No feeding times. Add a time to build your routine.</div>';
  $('add-slot').disabled = slots.length >= 12;
}
function fillSettings(data) {
  const settings = data.settings;
  $('automation').checked = settings.automation;
  $('angle').value = settings.angle;
  $('angle-value').textContent = `${settings.angle}°`;
  $('duration').value = settings.duration;
  $('full-distance').value = settings.full_distance;
  $('empty-distance').value = settings.empty_distance;
  $('calibrated').checked = settings.calibrated;
  $('angle-note').textContent = data.angle_supported ? 'The saved angle is sent to your controller before dispensing.' : 'Angle is saved as a preference. Your current firmware interface uses its own servo angle; an angle command must be configured to apply this setting.';
  slots = structuredClone(settings.slots);
  renderSlots();
  loadedSettings = true;
}
$('settings-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (!loadedSettings) return notice('Wait for settings to load before saving.', true);
    const data = {automation:$('automation').checked, angle:Number($('angle').value), duration:Number($('duration').value), full_distance:Number($('full-distance').value), empty_distance:Number($('empty-distance').value), calibrated:$('calibrated').checked, slots};
    $('save').disabled = true;
    try {
      await api('/api/settings', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
      notice('Schedule saved. Your feeding settings are up to date.');
    } catch (error) { notice(error.message, true); }
    finally { $('save').disabled = false; }
  });
  $('angle').addEventListener('input', () => $('angle-value').textContent = `${$('angle').value}°`);
  $('schedule-editor').addEventListener('input', event => {
    const field = event.target.dataset.field;
    if (!field) return;
    slots[Number(event.target.closest('.editor-row').dataset.index)][field] = field === 'enabled' ? event.target.checked : event.target.value;
  });
  $('schedule-editor').addEventListener('click', event => {
    if (event.target.dataset.delete === undefined) return;
    slots.splice(Number(event.target.dataset.delete), 1);
    renderSlots();
  });
  $('add-slot').addEventListener('click', () => {
    if (!loadedSettings || slots.length >= 12) return;
    slots.push({id:crypto.randomUUID(), name:'Extra feeding', time:'', portion:'Fish feed', enabled:true});
    renderSlots();
    $('schedule-editor').querySelector('.editor-row:last-child input[data-field="name"]').focus();
  });
  $('feed-now').addEventListener('click', async () => {
    $('feed-now').disabled = true;
    try { notice((await api('/api/feed', {method:'POST'})).message); }
    catch (error) { notice(error.message, true); }
  });

function onMonitor(data, stale) {
  if (!loadedSettings) fillSettings(data);
  $('feed-now').disabled = stale || !data.connected || data.operation === 'Dispensing' || data.diagnostics.running;
  $('feed-now').textContent = data.operation === 'Dispensing' ? 'Dispensing...' : 'Feed Now';
}
function onMonitorError() { $('feed-now').disabled = true; }

refresh();
