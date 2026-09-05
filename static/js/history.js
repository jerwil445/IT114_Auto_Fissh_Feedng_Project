let historyEvents = [];
let filter = 'all';
let historyBusy = false;
function renderHistory() {
  const visible = historyEvents.filter(event => filter === 'all' || event.kind === filter);
  $('history-list').innerHTML = visible.length ? visible.map(event => `<article class="history-item"><div class="event-icon">${event.kind === 'feeding' ? '↧' : '◷'}</div><div class="event-body"><h3>${escapeHtml(event.kind === 'feeding' ? event.portion : 'System update')}</h3><p>${escapeHtml(event.message)}</p><div class="event-meta"><time datetime="${escapeHtml(event.timestamp)}">${formatDate(event.timestamp)}</time><span>${escapeHtml(event.trigger || 'System')}</span></div></div><span class="badge ${event.status === 'Successful' ? 'good' : event.status === 'Failed' ? 'bad' : event.status === 'Warning' ? 'warn' : 'neutral'}">${escapeHtml(event.status)}</span></article>`).join('') : `<div class="empty">${historyEvents.length ? 'No matching events in the loaded history. Load older history to see more.' : 'Your activity starts here. Feeding events and system alerts will appear as they happen.'}</div>`;
}
async function loadHistory(reset = false) {
  if (historyBusy) return;
  historyBusy = true;
  $('load-more').disabled = true;
  try {
    const before = !reset && historyEvents.length ? `?before=${historyEvents.at(-1).id}` : '';
    const data = await api('/api/history' + before);
    historyEvents = reset ? data.events : historyEvents.concat(data.events);
    renderHistory();
    $('load-more').hidden = !data.has_more;
  } catch (error) { notice('Could not load history. ' + error.message, true); }
  finally { historyBusy = false; $('load-more').disabled = false; }
}
document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {
    filter = button.dataset.filter;
    document.querySelectorAll('[data-filter]').forEach(tab => tab.classList.toggle('selected', tab === button));
    renderHistory();
  }));
  $('load-more').addEventListener('click', () => loadHistory());
  $('supply-button').addEventListener('click', () => $('supply-dialog').showModal());
  $('close-supply').addEventListener('click', () => $('supply-dialog').close());
  loadHistory(true);

function onMonitor(data) {
  if (data.level !== null && data.level < 20) $('supply-title').textContent = `Feed is low (${data.level}%). Time to restock.`;
}
function onMonitorError() {}

refresh();
