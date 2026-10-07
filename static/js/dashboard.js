function renderHopper(level) {
  const hopperLevel = Number.isFinite(level) ? Math.max(0, Math.min(100, level)) : null;
  const meter = $('level-meter');
  $('level').textContent = hopperLevel === null ? '--' : Number(hopperLevel.toFixed(1));
  $('level-bar').style.height = `${hopperLevel ?? 0}%`;
  meter.classList.toggle('hopper-low', hopperLevel !== null && hopperLevel < 20);
  meter.classList.toggle('hopper-unavailable', hopperLevel === null);
  if (hopperLevel !== null) {
    meter.setAttribute('aria-valuenow', hopperLevel);
    meter.setAttribute('aria-valuetext', `${hopperLevel}% full`);
  } else {
    meter.removeAttribute('aria-valuenow');
    meter.setAttribute('aria-valuetext', 'Sensor reading unavailable');
  }
}

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
  renderHopper(data.level);
  $('valve').textContent = data.valve;
  if (data.connected && data.hopper_empty) {
    $('operation').textContent = 'FEED EMPTY - PLEASE REFILL';
    $('operation-detail').textContent = data.alarm_confirmed
      ? 'Red LED and buzzer commands acknowledged. Automatic warnings take priority over hardware tests.'
      : 'Hopper is empty. Alarm commands are not confirmed yet; retrying automatically.';
  }
  $('schedule-enabled-count').textContent = `${data.settings.slots.filter(slot => slot.enabled && data.settings.automation).length} enabled`;
  $('schedule-snapshot').innerHTML = data.settings.slots.length ? [...data.settings.slots].sort((a,b) => a.time.localeCompare(b.time)).map(slot => `<div class="schedule-row ${slot.completed_today ? 'completed' : ''}"><div class="slot-icon">${Number(slot.time.slice(0,2)) < 17 ? '☼' : '☾'}</div><div class="row-info"><strong>${escapeHtml(slot.name)}</strong><p>${escapeHtml(slot.portion)}</p></div><div class="schedule-time">${formatTime(slot.time)}<small>${slot.completed_today ? '✓ Completed' : slot.enabled && data.settings.automation ? 'Automatic' : 'Paused'}</small></div></div>`).join('') : '<div class="empty">No feeding times yet. Add one in Feeder Control.</div>';
  $('alerts').innerHTML = data.alerts.length ? data.alerts.map(alert => `<div class="alert ${alert.status === 'Warning' ? 'warning' : ''}"><span class="alert-symbol">${alert.status === 'Warning' ? '!' : '○'}</span><div><p>${escapeHtml(alert.message)}</p><small>${formatDate(alert.timestamp)}</small></div></div>`).join('') : '<div class="empty">No system alerts recorded yet.</div>';
  countdown();
}

let dashboardFeedPending = false;
$('dashboard-feed-now').addEventListener('click', async () => {
  dashboardFeedPending = true;
  $('dashboard-feed-now').disabled = true;
  $('dashboard-feed-now').textContent = 'Starting...';
  try {
    const result = await api('/api/feed', {method:'POST'});
    notice(result.message);
  } catch (error) {
    notice(error.message, true);
  } finally {
    dashboardFeedPending = false;
    // The next status update determines whether feeding can be started again.
  }
});

function onMonitor(data, stale) {
  const feeding = data.operation === 'Dispensing';
  $('dashboard-feed-now').disabled = dashboardFeedPending || stale || !data.connected || feeding || data.diagnostics.running;
  $('dashboard-feed-now').textContent = dashboardFeedPending ? 'Starting...' : feeding ? 'Dispensing...' : 'Feed Now';
  renderDashboard(stale ? {...data, connected:false, distance:null, level:null, hopper_empty:null, valve:'Unknown'} : data);
}
function onMonitorError() {
  $('dashboard-feed-now').disabled = true;
  $('dashboard-feed-now').textContent = 'Feed Now';
  $('operation').textContent = 'Connection unknown';
  $('operation-detail').textContent = 'The server is unavailable. Reconnecting automatically.';
  renderHopper(null);
  $('valve').textContent = 'Unknown';
}
setInterval(countdown, 1000);

refresh();

// Independent, lightweight sensor updates; no smoothing that could hide an empty reading.
let sensorSnapshot = null;
let sensorReceivedAt = 0;
function renderSensor() {
  const sample = sensorSnapshot;
  const elapsed = (performance.now() - sensorReceivedAt) / 1000;
  const age = sample && Number.isFinite(sample.age_seconds) ? sample.age_seconds + elapsed : null;
  const live = sample?.status === 'live' && age !== null && age <= 5 && Number.isFinite(sample.distance);
  $('distance').textContent = live ? sample.distance.toFixed(1) : '--';
  const messages = {waiting:'Waiting for first sensor reading', disconnected:'Device disconnected',
    no_echo:'No valid echo - check the sensor', stale:'Reading expired - waiting for an update',
    unavailable:'Sensor updates unavailable - reconnecting'};
  $('sensor-status').textContent = live
    ? `Live reading - ${age < 1 ? 'just now' : `${Math.floor(age)}s ago`}`
    : messages[sample?.status === 'live' ? 'stale' : sample?.status || 'waiting'];
}
async function refreshSensor() {
  if (!document.hidden) {
    try {
      const response = await fetch('/api/sensor', {cache:'no-store', signal:AbortSignal.timeout(4000)});
      if (!response.ok) throw new Error('Sensor unavailable');
      sensorSnapshot = await response.json();
      sensorReceivedAt = performance.now();
    } catch (error) {
      sensorSnapshot = {status:'unavailable', distance:null};
    }
    renderSensor();
  }
  setTimeout(refreshSensor, 1000);
}
setInterval(renderSensor, 500); // Expire old readings even while a network request is pending.
document.addEventListener('visibilitychange', renderSensor);
refreshSensor();
