const $ = id => document.getElementById(id);
let monitor = null;
const THEME_STORAGE_KEY = 'aquafeed-theme';
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const formatDate = value => new Date(value).toLocaleString('en-US', {timeZone: monitor?.timezone || 'Asia/Manila', month:'short', day:'numeric', hour:'numeric', minute:'2-digit'});
const formatTime = value => {
  const [hour, minute] = value.split(':').map(Number);
  return `${hour % 12 || 12}:${String(minute).padStart(2,'0')} ${hour >= 12 ? 'PM' : 'AM'}`;
};
function applyTheme(theme) {
  const normalized = theme === 'dark' ? 'dark' : 'light';
  document.documentElement.dataset.theme = normalized;
  document.body.dataset.theme = normalized;
  const button = $('theme-toggle');
  if (button) {
    button.textContent = normalized === 'dark' ? '☀️ Light mode' : '🌙 Dark mode';
    button.setAttribute('aria-pressed', String(normalized === 'dark'));
  }
  try {
    localStorage.setItem(THEME_STORAGE_KEY, normalized);
  } catch (error) {
    // Ignore storage errors in restricted contexts.
  }
}
function initialiseTheme() {
  try {
    const savedTheme = localStorage.getItem(THEME_STORAGE_KEY);
    const preferredDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    applyTheme(savedTheme || (preferredDark ? 'dark' : 'light'));
  } catch (error) {
    applyTheme('light');
  }
  const media = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)');
  media?.addEventListener?.('change', event => {
    if (!localStorage.getItem(THEME_STORAGE_KEY)) applyTheme(event.matches ? 'dark' : 'light');
  });
}
function notice(message, error = false) {
  $('notice').textContent = message;
  $('notice').className = 'notice' + (error ? ' error' : '');
  $('notice').hidden = false;
}
let toastTimer;
function showToast(message, error = false) {
  let toast = $('app-toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'app-toast';
    toast.setAttribute('role', 'status');
    toast.setAttribute('aria-live', 'polite');
    document.body.append(toast);
  }
  toast.textContent = message;
  toast.className = `app-toast${error ? ' error' : ''} visible`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toast.classList.remove('visible');
  }, 4000);
}
async function api(path, options = {}) {
  const headers = new Headers(options.headers);
  headers.set('X-CSRF-Token', document.querySelector('meta[name="csrf-token"]')?.content || '');
  const response = await fetch(path, {cache:'no-store', signal:AbortSignal.timeout(12000), ...options, headers});
  if (response.status === 401) { window.location.assign('/?auth=login'); throw new Error('Please log in again.'); }
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
initialiseTheme();

$('theme-toggle')?.addEventListener('click', () => {
  const nextTheme = document.body.dataset.theme === 'dark' ? 'light' : 'dark';
  applyTheme(nextTheme);
});

$('today').textContent = new Date().toLocaleDateString('en-US', {timeZone:'Asia/Manila', weekday:'short', month:'short', day:'numeric', year:'numeric'});

$('logout-button')?.addEventListener('click', async event => {
  event.currentTarget.disabled = true;
  try { await api('/api/auth/logout', {method:'POST'}); window.location.assign('/'); }
  catch (error) { notice(error.message, true); $('logout-button').disabled = false; }
});
