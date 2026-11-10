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
// Short how-to: open on the first visit, then only when asked.
const HELP_KEY = 'djintake.quickhelp.v1';
function setHelp(open) {
  $('#quick-help').hidden = !open;
  $('#quick-help-toggle').setAttribute('aria-expanded', String(open));
  $('#quick-help-toggle').textContent = open ? 'Hide tips' : 'How it works';
  resize();
}
$('#quick-help-toggle').onclick = () => {
  setHelp($('#quick-help').hidden);
  try { localStorage.setItem(HELP_KEY, '1'); } catch { /* ignore */ }
};
$('#quick-tour').onclick = () => native('open', { path: '/?tour' });
let helpSeen = false;
try { helpSeen = localStorage.getItem(HELP_KEY) === '1'; } catch { /* ignore */ }
if (!helpSeen) {
  setHelp(true);
  try { localStorage.setItem(HELP_KEY, '1'); } catch { /* ignore */ }
}
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
  $('.quick-listen').hidden = !panel.hidden;
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


$('#quick-identify').onclick = async () => {
  const trigger = $('#quick-identify');
  const status = $('#quick-recognition-status');
  trigger.disabled = true;
  trigger.classList.add('listening');
  status.textContent = 'Listening with Shazam…';
  resize();
  try {
    const match = await folderApi('identify', 'POST');
    status.textContent = 'Saved to Saved finds: ' + match.name;
  } catch (error) {
    status.textContent = error.message;
  } finally {
    trigger.disabled = false;
    trigger.classList.remove('listening');
    resize();
  }
};

$('#quick-recognition-setup').onclick = async () => {
  const trigger = $('#quick-recognition-setup');
  const status = $('#quick-recognition-status');
  trigger.disabled = true;
  status.textContent = 'Opening Apple Shortcuts…';
  resize();
  try {
    const { installed } = await folderApi('recognition/setup', 'POST');
    status.textContent = installed
      ? 'Shortcut is installed. Play a song and click Identify song.'
      : 'Click Add Shortcut in Shortcuts, then come back and click Identify song.';
  } catch (error) {
    status.textContent = error.message;
  } finally {
    trigger.disabled = false;
    resize();
  }
};
