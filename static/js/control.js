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

function validateSlots() {
  let isValid = true;
  $('schedule-editor').querySelectorAll('.editor-row').forEach((row, index) => {
    const nameInput = row.querySelector('input[data-field="name"]');
    const timeInput = row.querySelector('input[data-field="time"]');
    const portionInput = row.querySelector('input[data-field="portion"]');
    
    // Clear previous errors
    row.querySelectorAll('.error-text').forEach(el => el.remove());
    row.querySelectorAll('input').forEach(el => el.classList.remove('error'));
    
    // Validate name
    if (!nameInput.value.trim()) {
      addErrorMessage(nameInput, 'Feeding name is required');
      isValid = false;
    }
    
    // Validate time
    if (!timeInput.value) {
      addErrorMessage(timeInput, 'Time is required');
      isValid = false;
    } else {
      const timeError = validateTimeForName(timeInput.value, nameInput.value);
      if (timeError) {
        addTimeErrorMessage(timeInput, nameInput, timeError);
        isValid = false;
      }
    }
    
    // Validate portion
    if (!portionInput.value.trim()) {
      addErrorMessage(portionInput, 'Portion type is required');
      isValid = false;
    }
  });
  return isValid;
}

function addErrorMessage(input, message) {
  input.classList.add('error');
  // Remove existing error message
  const existingError = input.parentElement.querySelector('.error-text');
  if (existingError) existingError.remove();
  if (message) {
    const errorEl = document.createElement('small');
    errorEl.className = 'error-text';
    errorEl.textContent = message;
    input.parentElement.appendChild(errorEl);
  }
}

function addTimeErrorMessage(timeInput, nameInput, message) {
  timeInput.classList.add('error');
  // Remove existing error message
  const existingError = nameInput.parentElement.querySelector('.error-text');
  if (existingError) existingError.remove();
  if (message) {
    const errorEl = document.createElement('small');
    errorEl.className = 'error-text';
    errorEl.textContent = message;
    nameInput.parentElement.appendChild(errorEl);
  }
}

function clearTimeError(timeInput, nameInput) {
  timeInput.classList.remove('error');
  const errorEl = nameInput.parentElement.querySelector('.error-text');
  if (errorEl) errorEl.remove();
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

function renderSlots() {
  $('schedule-editor').innerHTML = slots.length ? slots.map((slot, index) => {
    const timeRange = getTimeRange(slot.name);
    return `<div class="editor-row" data-index="${index}"><label class="switch"><input type="checkbox" data-field="enabled" ${slot.enabled ? 'checked' : ''} aria-label="Enable ${escapeHtml(slot.name)}"><span></span></label><div><label for="name-${index}">Feeding name</label><input id="name-${index}" data-field="name" value="${escapeHtml(slot.name)}" maxlength="80"></div><div><label for="time-${index}">Time <small>${timeRange.label}</small></label><input id="time-${index}" type="time" data-field="time" value="${escapeHtml(slot.time)}"></div><div><label for="portion-${index}">Portion / feed type</label><input id="portion-${index}" data-field="portion" value="${escapeHtml(slot.portion)}" maxlength="80"></div><button type="button" class="delete" data-delete="${index}" aria-label="Delete ${escapeHtml(slot.name)}">Delete</button></div>`;
  }).join('') : '<div class="empty">No feeding times. Add a time to build your routine.</div>';
  $('add-slot').disabled = slots.length >= 12;
  
  // Add event listeners for real-time validation
  $('schedule-editor').querySelectorAll('.editor-row').forEach((row, index) => {
    const timeInput = row.querySelector('input[data-field="time"]');
    const nameInput = row.querySelector('input[data-field="name"]');
    
    timeInput?.addEventListener('input', () => {
      const error = validateTimeForName(timeInput.value, nameInput.value);
      if (error) {
        addTimeErrorMessage(timeInput, nameInput, error);
      } else {
        clearTimeError(timeInput, nameInput);
      }
    });
    
    nameInput?.addEventListener('input', () => {
      if (timeInput.value) {
        const error = validateTimeForName(timeInput.value, nameInput.value);
        if (error) {
          addTimeErrorMessage(timeInput, nameInput, error);
        } else {
          clearTimeError(timeInput, nameInput);
        }
      }
      const label = row.querySelector('label[for="time-' + index + '"] small');
      if (label) {
        const timeRange = getTimeRange(nameInput.value);
        label.textContent = timeRange.label;
      }
    });
  });
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
  renderSlots();
  loadedSettings = true;
}
$('settings-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (!loadedSettings) return notice('Wait for settings to load before saving.', true);
    if (!validateSlots()) return notice('Please fill in all required fields.', true);
    const data = {automation:$('automation').checked, angle:Number($('angle').value), duration:Number($('duration').value), full_distance:Number($('full-distance').value), empty_distance:Number($('empty-distance').value), calibrated:true, slots};
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
    const index = Number(event.target.closest('.editor-row').dataset.index);
    slots[index][field] = field === 'enabled' ? event.target.checked : event.target.value;
  });
  $('schedule-editor').addEventListener('click', event => {
    if (event.target.dataset.delete === undefined) return;
    slots.splice(Number(event.target.dataset.delete), 1);
    renderSlots();
  });
  $('add-slot').addEventListener('click', () => {
    if (!loadedSettings || slots.length >= 12) return;
    slots.push({id:generateUUID(), name:'Extra feeding', time:'12:00', portion:'Fish feed', enabled:true});
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
