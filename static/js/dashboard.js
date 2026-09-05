function countdown() {
  if (!$('countdown')) return;
  if (!monitor?.next) {
    $('countdown').textContent = 'Paused';
    return;
  }
  const seconds = Math.max(0, Math.floor((new Date(monitor.next.at) - new Date()) / 1000));
  const hours = Math.floor(seconds / 3600);
  $('countdown').textContent = `${String(hours).padStart(2,'0')}:${String(Math.floor(seconds / 60) % 60).padStart(2,'0')}:${String(seconds % 60).padStart(2,'0')}`;
}
function renderDashboard(data) {
  $('operation').textContent = data.operation === 'Dispensing' ? 'Dispensing' : !data.connected ? 'Device disconnected' : data.operation;
  $('operation-detail').textContent = !data.connected ? 'Connect your Arduino to resume monitoring and feeding.' : data.operation === 'Failed' ? 'The last feeding needs attention. Check the activity log.' : data.operation === 'Dispensing' ? 'Your feeder is dispensing a portion. The stop command follows automatically.' : 'Your feeder is connected. A healthy routine starts here.';
  $('next-feeding').textContent = data.next ? `${formatDate(data.next.at)} · ${data.next.name}` : 'No automatic feeding scheduled';
  $('next-portion').textContent = data.next ? data.next.portion : 'Enable automation in Feeder Control';
  $('level').textContent = data.level ?? '—';
  $('level-bar').style.width = `${data.level ?? 0}%`;
  $('level-bar').style.background = data.level !== null && data.level < 20 ? '#dba348' : '#39a27d';
  if (data.level !== null) $('level-meter').setAttribute('aria-valuenow', data.level);
  else $('level-meter').removeAttribute('aria-valuenow');
  $('level-label').textContent = data.level === null ? (data.settings.calibrated ? 'Sensor reading unavailable' : 'Calibrate hopper in Feeder Control') : `${data.level < 20 ? 'Low · Refill soon' : data.level < 70 ? 'Medium · Supply available' : 'Full · Supply available'} (estimated)`;
  $('distance').textContent = data.distance === null ? '—' : data.distance.toFixed(1);
  $('sensor-status').textContent = data.distance === null ? 'No valid sensor response' : 'Live reading from controller';
  $('valve').textContent = data.valve;
  $('schedule-snapshot').innerHTML = data.settings.slots.length ? [...data.settings.slots].sort((a,b) => a.time.localeCompare(b.time)).map(slot => `<div class="schedule-row"><div class="slot-icon">${Number(slot.time.slice(0,2)) < 17 ? '☼' : '☾'}</div><div class="row-info"><strong>${escapeHtml(slot.name)}</strong><p>${escapeHtml(slot.portion)}</p></div><div class="schedule-time">${formatTime(slot.time)}<small>${slot.enabled && data.settings.automation ? 'Automatic' : 'Paused'}</small></div></div>`).join('') : '<div class="empty">No feeding times yet. Add one in Feeder Control.</div>';
  $('alerts').innerHTML = data.alerts.length ? data.alerts.map(alert => `<div class="alert ${alert.status === 'Warning' ? 'warning' : ''}"><span class="alert-symbol">${alert.status === 'Warning' ? '!' : '○'}</span><div><p>${escapeHtml(alert.message)}</p><small>${formatDate(alert.timestamp)}</small></div></div>`).join('') : '<div class="empty">No system alerts recorded yet.</div>';
  countdown();
}

function onMonitor(data, stale) {
  renderDashboard(stale ? {...data, connected:false, distance:null, level:null, valve:'Unknown'} : data);
}
function onMonitorError() {
  $('operation').textContent = 'Connection unknown';
  $('operation-detail').textContent = 'The server is unavailable. Reconnecting automatically.';
  $('distance').textContent = '--';
  $('level').textContent = '--';
  $('level-bar').style.width = '0%';
  $('level-meter').removeAttribute('aria-valuenow');
  $('level-label').textContent = 'Live reading unavailable';
  $('sensor-status').textContent = 'Live reading unavailable';
  $('valve').textContent = 'Unknown';
}
setInterval(countdown, 1000);

refresh();
