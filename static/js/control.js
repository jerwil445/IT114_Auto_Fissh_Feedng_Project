// Generate UUID v4 - works in all browsers
function generateUUID() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // Fallback for older browsers
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    const r = Math.random() * 16 | 0;
    const v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

// Get time range based on feeding name
function getTimeRange(name) {
  const lower = name.toLowerCase();
  if (lower.includes('morning')) return { min: '05:00', max: '11:59', label: 'Morning (5 AM - 12 PM)' };
  if (lower.includes('afternoon')) return { min: '12:00', max: '17:59', label: 'Afternoon (12 PM - 6 PM)' };
  if (lower.includes('evening') || lower.includes('night')) return { min: '18:00', max: '23:59', label: 'Evening (6 PM - 12 AM)' };
  return { min: '00:00', max: '23:59', label: 'Any time' };
}

let loadedSettings = false;
let slots = [];

function addErrorMessage(input, message) {
  const id = `${input.id}-error`;
  let error = $(id);
  if (!error) {
    error = document.createElement('small');
    error.id = id;
    error.className = 'error-text';
    error.setAttribute('aria-live', 'polite');
    const anchor = input.closest('.input-unit') || input;
    anchor.insertAdjacentElement('afterend', error);
    const descriptions = new Set((input.getAttribute('aria-describedby') || '').split(' ').filter(Boolean));
    descriptions.add(id);
    input.setAttribute('aria-describedby', [...descriptions].join(' '));
  }
  error.textContent = message || '';
  error.hidden = !message;
  input.classList.toggle('error', Boolean(message));
  input.setAttribute('aria-invalid', String(Boolean(message)));
  return !message;
}

function validateSlot(row) {
  const name = row.querySelector('[data-field="name"]');
  const time = row.querySelector('[data-field="time"]');
  const portion = row.querySelector('[data-field="portion"]');
  let valid = addErrorMessage(name, name.value.trim() ? '' : 'Feeding name is required.');
  const duplicate = slots.some((slot, index) => index !== Number(row.dataset.index) && slot.time === time.value);
  const timeError = !time.value ? 'Feeding time is required.'
    : validateTimeForName(time.value, name.value) || (duplicate ? 'Choose a different time; another feeding uses this time.' : '');
  valid = addErrorMessage(time, timeError) && valid;
  valid = addErrorMessage(portion, portion.value.trim() ? '' : 'Portion / feed type is required.') && valid;
  return valid;
}

function validateSlots() {
  let valid = true;
  $('schedule-editor').querySelectorAll('.editor-row').forEach(row => { valid = validateSlot(row) && valid; });
  return valid;
}

function validateNumber(id, label) {
  const input = $(id);
  let message = '';
  if (input.validity.badInput) message = `Enter a valid number for ${label.toLowerCase()}.`;
  else if (input.value.trim() === '') message = `${label} is required.`;
  else if (!Number.isFinite(input.valueAsNumber)) message = 'Enter a valid number.';
  else if (input.validity.rangeUnderflow || input.validity.rangeOverflow) message = `Use a value between ${input.min} and ${input.max}.`;
  else if (input.validity.stepMismatch) message = `Use increments of ${input.step}.`;
  return addErrorMessage(input, message);
}

function validateDistances() {
  const fullValid = validateNumber('full-distance', 'Full hopper distance');
  const emptyValid = validateNumber('empty-distance', 'Empty hopper distance');
  if (fullValid && emptyValid && $('empty-distance').valueAsNumber <= $('full-distance').valueAsNumber) {
    return addErrorMessage($('empty-distance'), 'Empty distance must be greater than full distance.');
  }
  return fullValid && emptyValid;
}

function validateTimeForName(timeValue, name) {
  if (!timeValue) return null;
  const [hours, minutes] = timeValue.split(':').map(Number);
  const time = hours * 60 + minutes;
  const lower = name.toLowerCase();
  
  if (lower.includes('morning')) {
    if (time < 5 * 60 || time > 11 * 60 + 59) return 'Morning must be 5:00 AM - 11:59 AM';
  } else if (lower.includes('afternoon')) {
    if (time < 12 * 60 || time > 17 * 60 + 59) return 'Afternoon must be 12:00 PM - 5:59 PM';
  } else if (lower.includes('evening') || lower.includes('night')) {
    if (time < 18 * 60 || time > 23 * 60 + 59) return 'Evening must be 6:00 PM - 11:59 PM';
  }
  return null;
}

function getSlotStatus(slot) {
  const automation = $('automation') ? $('automation').checked : true;
  if (slot.completed_today) {
    return { text: '✓ Completed', type: 'complete' };
  }
  if (!slot.enabled || !automation) {
    return { text: 'Paused', type: 'paused' };
  }
  return { text: 'Automatic', type: 'automatic' };
}

function updateSlotStatus(index) {
  const pill = $(`slot-status-${index}`);
  if (!pill || !slots[index]) return;
  const status = getSlotStatus(slots[index]);
  pill.textContent = status.text;
  pill.className = `slot-status-pill status-${status.type}`;
}

function renderSlots() {
  $('schedule-editor').innerHTML = slots.length ? slots.map((slot, index) => {
    const timeRange = getTimeRange(slot.name);
    const status = getSlotStatus(slot);
    return `<div class="editor-row" data-index="${index}"><label class="switch"><input type="checkbox" data-field="enabled" ${slot.enabled ? 'checked' : ''} aria-label="Enable ${escapeHtml(slot.name)}"><span></span></label><div><div class="field-header"><label for="name-${index}">Feeding name</label><span class="slot-status-pill status-${status.type}" id="slot-status-${index}">${status.text}</span></div><input id="name-${index}" data-field="name" value="${escapeHtml(slot.name)}" maxlength="80"></div><div><label for="time-${index}">Time <small>${timeRange.label}</small></label><input id="time-${index}" type="time" data-field="time" value="${escapeHtml(slot.time)}"></div><div><label for="portion-${index}">Portion / feed type</label><input id="portion-${index}" data-field="portion" value="${escapeHtml(slot.portion)}" maxlength="80"></div><button type="button" class="delete" data-delete="${index}" aria-label="Delete ${escapeHtml(slot.name)}">Delete</button></div>`;
  }).join('') : '<div class="empty">No feeding times. Add a time to build your routine.</div>';
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
  $('angle-note').textContent = data.angle_supported ? 'The saved angle is sent to your controller before dispensing.' : 'Angle is saved as a preference. Your current firmware interface uses its own servo angle; an angle command must be configured to apply this setting.';
  slots = structuredClone(settings.slots);
  slots.forEach(slot => {
    slot._originalTime = slot.time;
    slot._originalCompleted = Boolean(slot.completed_today);
  });
  renderSlots();
  loadedSettings = true;
}
$('settings-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (!loadedSettings) return notice('Wait for settings to load before saving.', true);
    $('notice').hidden = true;
    const scheduleValid = validateSlots();
    const distancesValid = validateDistances();
    const durationValid = validateNumber('duration', 'Dispensing duration');
    const angleValid = validateNumber('angle', 'Servo opening angle');
    if (!scheduleValid || !distancesValid || !durationValid || !angleValid) {
      $('settings-form').querySelector('[aria-invalid="true"]')?.focus();
      return;
    }
    const data = {automation:$('automation').checked, angle:Number($('angle').value), duration:Number($('duration').value), full_distance:Number($('full-distance').value), empty_distance:Number($('empty-distance').value), calibrated:true, slots};
    $('save').disabled = true;
    try {
      await api('/api/settings', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
      slots.forEach(slot => {
        slot._originalTime = slot.time;
        slot._originalCompleted = Boolean(slot.completed_today);
      });
      showToast('Settings saved successfully.');
    } catch (error) { notice(error.message, true); }
    finally { $('save').disabled = false; }
  });
  ['full-distance', 'empty-distance'].forEach(id => $(id).addEventListener('input', validateDistances));
  $('duration').addEventListener('input', () => validateNumber('duration', 'Dispensing duration'));
  $('angle').addEventListener('input' , () => $('angle-value').textContent = `${$('angle').value}°`);
  $('automation').addEventListener('change', () => {
    slots.forEach((_, index) => updateSlotStatus(index));
  });
  $('schedule-editor').addEventListener('input', event => {
    const field = event.target.dataset.field;
    if (!field) return;
    const index = Number(event.target.closest('.editor-row').dataset.index);
    slots[index][field] = field === 'enabled' ? event.target.checked : event.target.value;
    const row = event.target.closest('.editor-row');
    if (field === 'name') row.querySelector(`label[for="time-${index}"] small`).textContent = getTimeRange(event.target.value).label;
    if (field === 'time') {
      if (slots[index]._originalTime && slots[index].time !== slots[index]._originalTime) {
        slots[index].completed_today = false;
      } else if (slots[index]._originalTime && slots[index].time === slots[index]._originalTime) {
        slots[index].completed_today = Boolean(slots[index]._originalCompleted);
      }
      updateSlotStatus(index);
    }
    if (field === 'enabled') {
      updateSlotStatus(index);
    }
    validateSlots();
  });
  $('schedule-editor').addEventListener('change', event => {
    const field = event.target.dataset.field;
    if (field === 'enabled') {
      const index = Number(event.target.closest('.editor-row').dataset.index);
      slots[index].enabled = event.target.checked;
      updateSlotStatus(index);
    }
  });
  $('schedule-editor').addEventListener('click', event => {
    if (event.target.dataset.delete === undefined) return;
    slots.splice(Number(event.target.dataset.delete), 1);
    renderSlots();
  });
  $('add-slot').addEventListener('click', () => {
    if (!loadedSettings || slots.length >= 12) return;
    slots.push({id:generateUUID(), name:'Extra feeding', time:'12:00', portion:'Fish feed', enabled:true, completed_today:false, _originalTime:'12:00', _originalCompleted:false});
    renderSlots();
    $('schedule-editor').querySelector('.editor-row:last-child input[data-field="name"]').focus();
  });
  $('feed-now').addEventListener('click', async () => {
    $('feed-now').disabled = true;
    try { notice((await api('/api/feed', {method:'POST'})).message); }
    catch (error) { notice(error.message, true); }
  });

function onMonitor(data, stale) {
  $('calibration-status').textContent = stale || !data.connected
    ? 'Controller disconnected. Saved calibration will be sent when it reconnects.'
    : data.calibration_synced
      ? 'Saved distance calibration confirmed by the Arduino.'
      : 'Arduino calibration not confirmed. Upload the updated arduino_code.c++ sketch; hardware warnings may still use the previous distances.';
  if (!loadedSettings) fillSettings(data);
  $('feed-now').disabled = stale || !data.connected || data.operation === 'Dispensing' || data.diagnostics.running;
  $('feed-now').textContent = data.operation === 'Dispensing' ? 'Dispensing...' : 'Feed Now';
}
function onMonitorError() { $('feed-now').disabled = true; }

refresh();
