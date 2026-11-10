'use strict';
const $ = selector => document.querySelector(selector);
const token = $('meta[name=intake-token]').content;
function native(action, extra = {}) {
  if (window.webkit?.messageHandlers?.intake) {
    window.webkit.messageHandlers.intake.postMessage({ action, ...extra });
  } else if (action === 'open') { location.href = '/'; }
}
function resize() {
  requestAnimationFrame(() => native('resize', { height: $('.quick-main').scrollHeight + 4 }));
}
$('#quick-trim').onchange = () => {
  $('#quick-fields').hidden = !$('#quick-trim').checked;
  resize();
  if ($('#quick-trim').checked) $('#quick-start').focus();
};
$('#quick-form').onsubmit = async event => {
  event.preventDefault();
  $('#quick-submit').disabled = true;
  const status = $('#quick-status');
  status.hidden = false;
  status.className = '';
  status.textContent = 'Adding to your queue…';
  resize();
  try {
    const response = await fetch('/api/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Intake-Token': token },
      body: JSON.stringify({
        input: $('#quick-input').value,
        clip_start: $('#quick-trim').checked ? $('#quick-start').value : '',
        clip_end: $('#quick-trim').checked ? $('#quick-end').value : '',
      }),
    });
    const result = await response.json();
    if (!response.ok) throw Error(result.error || 'Could not add the request.');
    if (result.errors?.length) throw Error(result.errors.map(item => item.error).join(' '));
    const existing = result.added.some(job => job.status === 'successful');
    const needsChoice = result.added.some(job => job.source === 'Search' || job.source === 'Spotify lookup');
    status.textContent = existing ? 'Already downloaded. Open your library to find it.' : needsChoice ? 'Added. Open your library to choose a recording.' : 'Added to queue. We’ll take it from here.';
    status.className = 'success';
    $('#quick-form').reset();
    $('#quick-fields').hidden = true;
    $('#quick-input').focus();
  } catch (error) {
    status.className = 'error';
    status.textContent = error.message;
  } finally { $('#quick-submit').disabled = false; resize(); }
};
$('#quick-open').onclick = () => native('open');
$('#quick-quit').onclick = () => native('quit');
new ResizeObserver(resize).observe($('.quick-main'));
resize();

async function folderApi(path, method) {
  const response = await fetch('/api/' + path, {
    method, headers: {'Content-Type':'application/json','X-Intake-Token':token},
    ...(method === 'POST' ? {body:'{}'} : {}),
  });
  const result = await response.json();
  if (!response.ok) throw Error(result.error);
  return result;
}
$('#quick-settings').onclick = async () => {
  const panel = $('#quick-preferences');
  panel.hidden = !panel.hidden;
  $('#quick-form').hidden = !panel.hidden;
  $('#quick-settings').setAttribute('aria-expanded', String(!panel.hidden));
  if (!panel.hidden) {
    try { $('#quick-path').textContent = (await folderApi('settings','GET')).output_dir; }
    catch (error) { $('#folder-status').textContent = error.message; }
  }
  resize();
};
$('#quick-pick').onclick = async () => {
  $('#quick-pick').disabled = true;
  try {
    const result = await folderApi('pick-folder','POST');
    if (!result.cancelled) {
      $('#quick-path').textContent = result.output_dir;
      $('#folder-status').textContent = 'Default folder saved.';
    }
  } catch (error) { $('#folder-status').textContent = error.message; }
  finally { $('#quick-pick').disabled = false; resize(); }
};
