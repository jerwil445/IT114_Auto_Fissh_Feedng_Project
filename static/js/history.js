let historyEvents = [];
let filter = 'all';
let historyPage = 1;
let historyPageSize = 10;
let historyMeta = {total:0, page:1, pages:1, has_prev:false, has_next:false};
const tabFilters = Object.fromEntries(['all','feeding','system'].map(kind => [kind, {start:'',end:'',status:'',trigger:'',search:'',limit:10}]));
let historyRequest = 0;
let historyController = null;
let searchTimer = null;

function renderHistory() {
  const visible = historyEvents;
  $('history-list').innerHTML = visible.length ? visible.map(event => `<article class="history-item"><div class="event-icon">${event.kind === 'feeding' ? '↧' : '◷'}</div><div class="event-body"><h3>${escapeHtml(event.kind === 'feeding' ? event.portion : 'System update')}</h3><p>${escapeHtml(event.message)}</p><div class="event-meta"><time datetime="${escapeHtml(event.timestamp)}">${formatDate(event.timestamp)}</time><span>${escapeHtml(event.trigger || 'System')}</span></div></div><span class="badge ${event.status === 'Successful' ? 'good' : event.status === 'Failed' ? 'bad' : event.status === 'Warning' ? 'warn' : 'neutral'}">${escapeHtml(event.status)}</span></article>`).join('') : `<div class="empty">${historyEvents.length ? 'No matching events in the loaded history. Load older history to see more.' : 'No events match these filters. Try changing the dates or clearing filters.'}</div>`;
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

function saveFilters() {
  Object.assign(tabFilters[filter], {start:$('filter-start').value, end:$('filter-end').value,
    status:$('filter-status').value, trigger:filter === 'feeding' ? $('filter-method').value : '',
    search:filter === 'feeding' ? '' : $('filter-search').value.trim(), limit:Number($('history-page-size').value)});
}
function showFilters() {
  const selected = tabFilters[filter];
  const statuses = filter === 'feeding' ? ['Successful','Failed'] : filter === 'system' ? ['Info','Warning','Failed'] : ['Successful','Failed','Info','Warning'];
  $('filter-status-label').textContent = filter === 'feeding' ? 'Feeding result' : filter === 'system' ? 'Severity' : 'Status';
  $('filter-status').innerHTML = '<option value="">All statuses</option>' + statuses.map(status => `<option>${status}</option>`).join('');
  $('filter-start').value = selected.start;
  $('filter-end').value = selected.end;
  $('filter-status').value = selected.status;
  $('filter-method').value = selected.trigger;
  $('filter-search').value = selected.search;
  $('history-page-size').value = selected.limit;
  $('filter-method-field').hidden = filter !== 'feeding';
  $('filter-search-field').hidden = filter === 'feeding';
  $('filter-search').placeholder = filter === 'system' ? 'Search system messages' : 'Search messages or feed types';
  document.querySelectorAll('[data-filter]').forEach(tab => {
    const active = tab.dataset.filter === filter;
    tab.classList.toggle('selected', active);
    tab.setAttribute('aria-pressed', String(active));
  });
}
async function loadHistory(page = 1) {
  const request = ++historyRequest;
  historyController?.abort();
  historyController = new AbortController();
  saveFilters();
  const selected = {...tabFilters[filter]};
  const invalid = selected.start && selected.end && selected.start > selected.end;
  $('history-filter-error').hidden = !invalid;
  $('history-filter-error').textContent = invalid ? 'To date must be on or after From date.' : '';
  if (invalid) {
    $('history-list').textContent = 'Choose a valid date range to view history.';
    $('history-prev').disabled = true;
    $('history-next').disabled = true;
    $('history-summary').textContent = 'Invalid date range';
    return;
  }
  $('history-prev').disabled = true;
  $('history-next').disabled = true;
  $('history-list').setAttribute('aria-busy','true');
  try {
    const query = new URLSearchParams({page:String(page),limit:String(selected.limit)});
    if (filter !== 'all') query.set('kind',filter);
    for (const name of ['start','end','status','trigger','search']) if (selected[name]) query.set(name,selected[name]);
    const data = await api(`/api/history?${query}`, {signal:historyController.signal});
    if (request !== historyRequest) return;
    historyPageSize = selected.limit;
    historyEvents = data.events || [];
    historyMeta = {total:Number(data.total || 0),page:Number(data.page || page),pages:Number(data.pages || 1),has_prev:Boolean(data.has_prev),has_next:Boolean(data.has_next)};
    historyPage = historyMeta.page;
    renderHistory();
    renderPagination();
  } catch (error) {
    if (request !== historyRequest || error.name === 'AbortError') return;
    $('history-filter-error').textContent = 'Could not load history. ' + error.message;
    $('history-filter-error').hidden = false;
    $('history-list').textContent = 'History unavailable. Change or reset filters to retry.';
  } finally {
    if (request === historyRequest) $('history-list').setAttribute('aria-busy','false');
  }
}
document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {
  clearTimeout(searchTimer);
  saveFilters();
  filter = button.dataset.filter;
  showFilters();
  loadHistory(1);
}));
for (const id of ['filter-start','filter-end','filter-status','filter-method','history-page-size']) {
  $(id).addEventListener('change', () => { clearTimeout(searchTimer); loadHistory(1); });
}
$('filter-search').addEventListener('input', () => {
  clearTimeout(searchTimer);
  // Invalidate pending results immediately while waiting for typing to pause.
  historyRequest++;
  historyController?.abort();
  searchTimer = setTimeout(() => loadHistory(1), 300);
});
$('filter-reset').addEventListener('click', () => {
  clearTimeout(searchTimer);
  tabFilters[filter] = {start:'',end:'',status:'',trigger:'',search:'',limit:10};
  showFilters(); loadHistory(1);
});
$('history-prev').addEventListener('click', () => {if (historyMeta.has_prev) loadHistory(historyPage - 1);});
$('history-next').addEventListener('click', () => {if (historyMeta.has_next) loadHistory(historyPage + 1);});
$('supply-button').addEventListener('click', () => $('supply-dialog').showModal());
$('close-supply').addEventListener('click', () => $('supply-dialog').close());
showFilters();
loadHistory(1);
function onMonitor(data) {
  $('supply-title').textContent = data.level !== null && data.level < 20 ? `Feed is low (${data.level}%). Time to restock.` : 'Keep your feed supply topped up';
}
function onMonitorError() {}
refresh();
