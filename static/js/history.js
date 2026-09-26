let historyEvents = [];
let filter = 'all';
let historyBusy = false;
let historyPage = 1;
let historyPageSize = Number($('history-page-size')?.value || 10);
let historyMeta = { total: 0, page: 1, pages: 1, has_prev: false, has_next: false };

function renderHistory() {
  const visible = historyEvents;
  $('history-list').innerHTML = visible.length ? visible.map(event => `<article class="history-item"><div class="event-icon">${event.kind === 'feeding' ? '↧' : '◷'}</div><div class="event-body"><h3>${escapeHtml(event.kind === 'feeding' ? event.portion : 'System update')}</h3><p>${escapeHtml(event.message)}</p><div class="event-meta"><time datetime="${escapeHtml(event.timestamp)}">${formatDate(event.timestamp)}</time><span>${escapeHtml(event.trigger || 'System')}</span></div></div><span class="badge ${event.status === 'Successful' ? 'good' : event.status === 'Failed' ? 'bad' : event.status === 'Warning' ? 'warn' : 'neutral'}">${escapeHtml(event.status)}</span></article>`).join('') : `<div class="empty">${historyEvents.length ? 'No matching events in the loaded history. Load older history to see more.' : 'Your activity starts here. Feeding events and system alerts will appear as they happen.'}</div>`;
}

function renderPagination() {
  const summary = $('history-summary');
  const pageLabel = $('history-page-label');
  const prevButton = $('history-prev');
  const nextButton = $('history-next');
  if (!summary || !pageLabel || !prevButton || !nextButton) return;

  const total = historyMeta.total;
  const page = historyMeta.page;
  const pages = historyMeta.pages;
  const firstEntry = total ? (page - 1) * historyPageSize + 1 : 0;
  const lastEntry = total ? Math.min(page * historyPageSize, total) : 0;
  summary.textContent = total ? `Showing ${firstEntry}-${lastEntry} of ${total} entries` : 'Showing 0 entries';
  pageLabel.textContent = `Page ${page} of ${pages}`;
  prevButton.disabled = !historyMeta.has_prev;
  nextButton.disabled = !historyMeta.has_next;
}

async function loadHistory(page = historyPage) {
  if (historyBusy) return;
  historyBusy = true;
  $('history-prev').disabled = true;
  $('history-next').disabled = true;
  try {
    const query = new URLSearchParams({ page: String(page), limit: String(historyPageSize) });
    if (filter !== 'all') query.set('kind', filter);
    const data = await api(`/api/history?${query}`);
    historyEvents = data.events || [];
    historyMeta = {
      total: Number(data.total || 0),
      page: Number(data.page || page),
      pages: Number(data.pages || 1),
      has_prev: Boolean(data.has_prev),
      has_next: Boolean(data.has_next),
    };
    historyPage = historyMeta.page;
    renderPagination();
    renderHistory();
  } catch (error) {
    notice('Could not load history. ' + error.message, true);
  } finally {
    historyBusy = false;
    renderPagination();
  }
}

document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {
  filter = button.dataset.filter;
  document.querySelectorAll('[data-filter]').forEach(tab => tab.classList.toggle('selected', tab === button));
  historyPage = 1;
  loadHistory(historyPage);
}));

$('history-page-size')?.addEventListener('change', event => {
  historyPageSize = Number(event.target.value);
  historyPage = 1;
  loadHistory(historyPage);
});

$('history-prev')?.addEventListener('click', () => {
  if (historyMeta.has_prev) loadHistory(historyPage - 1);
});

$('history-next')?.addEventListener('click', () => {
  if (historyMeta.has_next) loadHistory(historyPage + 1);
});

$('supply-button').addEventListener('click', () => $('supply-dialog').showModal());
$('close-supply').addEventListener('click', () => $('supply-dialog').close());
loadHistory(historyPage);

function onMonitor(data) {
  if (data.level !== null && data.level < 20) $('supply-title').textContent = `Feed is low (${data.level}%). Time to restock.`;
}
function onMonitorError() {}

refresh();
