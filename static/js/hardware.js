let testRequestPending = false;
function renderHardware(data, stale) {
  const tests = data.diagnostics;
  const busy = tests.running || data.operation === 'Dispensing' || testRequestPending;
  document.querySelectorAll('[data-test]').forEach(button => {
    button.disabled = busy || stale || !data.connected;
  });
  $('cancel-tests').disabled = !tests.running;
  $('test-progress').textContent = tests.running
    ? `Testing ${tests.current || 'hardware'}... Off/stop commands run automatically.`
    : data.operation === 'Dispensing' ? 'A feeding is in progress. Tests will be available when it finishes.'
    : stale || !data.connected ? 'Connect the Arduino and wait for a device update to enable tests.'
    : Object.keys(tests.results).length ? 'Test run finished. Review the results below.'
    : 'Device connected. Choose a component or run all tests.';
  for (const [key, result] of Object.entries(tests.results)) {
    const badge = $('test-status-' + key);
    if (!badge) continue;
    badge.textContent = result.status;
    badge.className = 'badge ' + (result.status === 'Acknowledged' ? 'good' : result.status === 'Failed' ? 'bad' : 'neutral');
    $('test-result-' + key).textContent = result.message;
  }
}
document.querySelectorAll('[data-test]').forEach(button => button.addEventListener('click', async () => {
    testRequestPending = true;
    document.querySelectorAll('[data-test]').forEach(control => control.disabled = true);
    try {
      const data = await api('/api/hardware-test/' + button.dataset.test, {method:'POST'});
      notice(data.message);
      renderHardware(await api('/api/monitor'), false);
    } catch (error) { notice(error.message, true); }
    finally { testRequestPending = false; }
  }));
  $('cancel-tests').addEventListener('click', async () => {
    $('cancel-tests').disabled = true;
    try { notice((await api('/api/hardware-test-cancel', {method:'POST'})).message); }
    catch (error) { notice(error.message, true); $('cancel-tests').disabled = false; }
  });

function onMonitor(data, stale) { renderHardware(data, stale); }
function onMonitorError() {
  document.querySelectorAll('[data-test]').forEach(button => button.disabled = true);
  $('test-progress').textContent = 'Server unavailable. Test progress is unknown; reconnecting automatically.';
}

refresh();
