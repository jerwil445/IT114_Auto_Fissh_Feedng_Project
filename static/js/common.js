const $ = id => document.getElementById(id);
let monitor = null;
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const formatDate = value => new Date(value).toLocaleString('en-US', {timeZone: monitor?.timezone || 'Asia/Manila', month:'short', day:'numeric', hour:'numeric', minute:'2-digit'});
const formatTime = value => {
  const [hour, minute] = value.split(':').map(Number);
  return `${hour % 12 || 12}:${String(minute).padStart(2,'0')} ${hour >= 12 ? 'PM' : 'AM'}`;
};
function notice(message, error = false) {
  $('notice').textContent = message;
  $('notice').className = 'notice' + (error ? ' error' : '');
  $('notice').hidden = false;
}
async function api(path, options = {}) {
  const response = await fetch(path, {cache:'no-store', signal:AbortSignal.timeout(12000), ...options});
  const data = await response.json();
  if (!response.ok) throw new Error(data.message || 'The request could not be completed.');
  return data;
}
async function refresh() {
  try {
    const data = await api('/api/monitor');
    monitor = data;
    const stale = !data.updated_at || Date.now() - new Date(data.updated_at).getTime() > 15000;
    $('connection').textContent = stale ? 'Waiting for device update' : data.connected ? `Device connected · ${data.port}` : 'Device disconnected';
    $('connection').className = 'badge ' + (stale ? 'neutral' : data.connected ? 'good' : 'bad');
    $('last-update').textContent = data.updated_at ? `Last update ${formatDate(data.updated_at)}` : 'Waiting for device reading';
    document.querySelectorAll('.timezone').forEach(el => el.textContent = data.timezone);
    onMonitor(data, stale);
  } catch (error) {
    $('connection').textContent = 'Server unavailable';
    $('connection').className = 'badge bad';
    $('last-update').textContent = 'Live updates unavailable · retrying';
    onMonitorError();
  } finally {
    setTimeout(refresh, 3000);
  }
}
$('today').textContent = new Date().toLocaleDateString('en-US', {timeZone:'Asia/Manila', weekday:'short', month:'short', day:'numeric', year:'numeric'});
