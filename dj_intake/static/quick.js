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
// Same check as the library: say whether DJ Intake can use what was pasted.
function describeInput(raw) {
  const lines = raw.split('\n').map(line => line.trim()).filter(Boolean);
  if (!lines.length) return null;
  if (lines.length > 1) return ['ok', lines.length + ' tracks — each line is added separately'];
  let text = lines[0];
  if (!text.includes('://') && /^(www\.|youtube\.com\/|youtu\.be\/|soundcloud\.com\/|open\.spotify\.com\/|[a-z0-9-]+\.bandcamp\.com\/)/i.test(text)) text = 'https://' + text;
  if (!text.includes('://')) return ['ok', 'Song name — DJ Intake searches YouTube and you pick the recording'];
  let url;
  try { url = new URL(text); } catch { return ['warn', 'That doesn’t look like a complete link.']; }
  const host = url.hostname.toLowerCase();
  if (['youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtu.be'].includes(host)) {
    const id = host === 'youtu.be' ? url.pathname.slice(1) : url.searchParams.get('v') || (url.pathname.match(/^\/(shorts|embed)\/([^/]+)/) || [])[2];
    if (id && /^[\w-]{11}$/.test(id)) return ['ok', '✓ YouTube track' + (url.searchParams.has('list') ? ' — only this song, not the playlist' : '')];
    return ['warn', 'That’s a YouTube playlist or channel. Paste a single video link.'];
  }
  if (['soundcloud.com', 'www.soundcloud.com', 'on.soundcloud.com'].includes(host)) {
    return /\/sets\//.test(url.pathname) ? ['warn', 'That’s a SoundCloud playlist. Paste a single track link.'] : ['ok', '✓ SoundCloud track'];
  }
  if (host === 'open.spotify.com') {
    return /\/track\//.test(url.pathname) ? ['ok', 'Spotify track — DJ Intake finds it on YouTube and you pick the recording'] : ['warn', 'Paste a single Spotify track link, not an album or playlist.'];
  }
  if (host.endsWith('.bandcamp.com')) {
    return url.pathname.startsWith('/track/') ? ['ok', '✓ Bandcamp track'] : ['warn', 'Paste a single Bandcamp track link (…/track/…), not an album.'];
  }
  return ['warn', 'That site isn’t supported. Use YouTube, SoundCloud, Bandcamp, a Spotify track, or type the song name.'];
}
function showKind() {
  const kind = describeInput($('#quick-input').value);
  const line = $('#quick-kind');
  line.hidden = !kind;
  if (kind) { line.className = 'input-kind ' + kind[0]; line.textContent = kind[1]; }
  resize();
}
$('#quick-input').addEventListener('input', showKind);
$('#quick-input').addEventListener('keydown', event => {
  if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) { event.preventDefault(); $('#quick-form').requestSubmit(); }
});
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
    showKind();
    $('#quick-fields').hidden = true;
    $('#quick-input').focus();
  } catch (error) {
    status.className = 'error';
    status.textContent = error.message;
  } finally { $('#quick-submit').disabled = false; resize(); }
};
$('#quick-open').onclick = () => native('open');
$('#quick-update').onclick = () => native('open');
// Show a quiet line when a newer release exists; the library handles the update itself.
fetch('/api/state', { headers: { 'X-Intake-Token': token } })
  .then(response => response.ok ? response.json() : null)
  .then(state => {
    if (!state?.update) return;
    $('#quick-update').textContent = '● Update to ' + state.update.version + ' available — open the library to install';
    $('#quick-update').hidden = false;
    resize();
  })
  .catch(() => {});
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
