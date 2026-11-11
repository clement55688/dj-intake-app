'use strict';
const $ = selector => document.querySelector(selector);
const token = $('meta[name=intake-token]').content;
let state = null;
let tab = 'queue';
let toastTimer;
let renderedState = '';
const active = job => !['successful', 'failed', 'cancelled'].includes(job.status);
const labels = {
  queued: 'Queued', resolving: 'Finding track', downloading: 'Downloading',
  processing: 'Checking & tagging', needs_selection: 'Pick a recording',
  successful: 'Downloaded', failed: 'Failed',
};

async function api(path, body) {
  const response = await fetch('/api/' + path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Intake-Token': token },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const data = await response.json();
  if (!response.ok) throw Error(data.error || 'Action failed');
  return data;
}

function toast(message, action) {
  const box = $('#toast');
  box.replaceChildren(node('span', '', message));
  if (action) {
    const undo = node('button', 'toast-action', action.label);
    undo.onclick = async () => {
      box.hidden = true;
      try { await action.run(); await refresh(); } catch (error) { toast(error.message); }
    };
    box.append(undo);
  }
  box.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { box.hidden = true; }, action ? 9000 : 6500);
}

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = String(text).normalize('NFC');
  return element;
}

function button(label, action, className = 'pill ghost') {
  const element = node('button', className, label);
  element.onclick = async () => {
    element.disabled = true;
    try { await action(); await refresh(); }
    catch (error) { toast(error.message); }
    finally { element.disabled = false; }
  };
  return element;
}

function duration(seconds) {
  if (seconds === null || seconds === undefined) return 'Duration unavailable';
  return Math.floor(seconds / 60) + ':' + String(Math.floor(seconds % 60)).padStart(2, '0');
}

function downloads() {
  const seen = new Set();
  return state.jobs.filter(job => {
    if (job.status !== 'successful' || !job.output || seen.has(job.output)) return false;
    seen.add(job.output);
    return true;
  });
}

function setTab(value, scrollTarget) {
  tab = value;
  document.querySelectorAll('[data-tab]').forEach(element => {
    element.classList.toggle('active', element.dataset.tab === tab);
    if (element.dataset.tab === tab && element.classList.contains('tab')) element.setAttribute('aria-current', 'page');
    else element.removeAttribute('aria-current');
  });
  $('#hero').dataset.mode = tab;
  document.querySelectorAll('[data-view]').forEach(element => { element.hidden = element.dataset.view !== tab; });
  render(true);
  if (scrollTarget) scrollTarget.scrollIntoView({ behavior: 'smooth', block: 'start' });
  else if (window.scrollY > 0) window.scrollTo({ top: 0, behavior: 'smooth' });
}

const stages = [['queued', 'Queued'], ['resolving', 'Finding'], ['downloading', 'Downloading'], ['processing', 'Checking']];
function stageBar(status) {
  const current = stages.findIndex(([key]) => key === status);
  const bar = node('div', 'stages');
  bar.setAttribute('aria-label', 'Progress: ' + (labels[status] || status));
  stages.forEach(([, label], index) => bar.append(node('span', 'stage' + (index < current ? ' done' : index === current ? ' now' : ''), label)));
  return bar;
}

// Plain-language summary for common downloader errors; the raw text stays under "Details".
function friendlyError(text) {
  const t = String(text || '').toLowerCase();
  if (/video unavailable|this video is unavailable|has been removed|no longer available/.test(t)) return 'This track is unavailable — it may have been removed, made private, or blocked where you are. Try another link.';
  if (/private video|this track is private|\bis private\b/.test(t)) return 'This track is private. Try a public link.';
  if (/http error 404|\bnot found\b/.test(t)) return 'That link doesn’t exist anymore. Check the link or try another source.';
  if (/sign in to confirm|confirm your age|age[- ]restricted|inappropriate/.test(t)) return 'The site wants a sign-in or age check for this track, which DJ Intake can’t do. Try another upload.';
  if (/http error 429|too many requests/.test(t)) return 'The site is limiting requests right now. Wait a few minutes, then Retry.';
  if (/timed out|timeout|connection|network|resolve host|temporary failure/.test(t)) return 'Couldn’t reach the site. Check your internet connection, then Retry.';
  if (/ffmpeg|ffprobe|yt-dlp is missing|deno/.test(t)) return 'A required audio tool is missing. Run setup again from the install guide, then Retry.';
  if (/one-hour|too long|duration/.test(t)) return 'This recording is longer than DJ Intake’s one-hour limit. Use Trim to timestamps to take a section.';
  return 'Something went wrong with this request. The details below say why; Retry or remove it.';
}

function removeButton(job, label) {
  return button(label, async () => {
    const removed = await api('jobs/remove', { id: job.id });
    toast('Removed “' + (job.title || job.input) + '”.', { label: 'Undo', run: () => api('jobs/restore', removed) });
  }, 'pill ghost danger');
}

function trackCard(job, compact = false) {
  const row = node('article', 'track ' + job.status + (compact ? ' compact' : ''));
  const top = node('div', 'track-top');
  top.append(node('div', 'track-icon', job.status === 'successful' ? '✓' : job.status === 'failed' ? '!' : job.status === 'needs_selection' ? '?' : '♫'));
  const info = node('div', 'track-info');
  const extension = job.output ? job.output.split('.').pop().toUpperCase() : '';
  info.append(
    node('h3', '', job.title || job.input),
    node('div', 'meta', [job.artist, job.source, extension, job.clip_end !== null && job.clip_end !== undefined ? 'Clip '+duration(job.clip_start)+'–'+duration(job.clip_end) : ''].filter(Boolean).join(' · ')),
  );
  top.append(info, node('span', 'status ' + job.status, labels[job.status] || job.status));
  row.append(top);
  const body = node('div', 'track-body');
  row.append(body);
  if (!compact && stages.some(([key]) => key === job.status)) body.append(stageBar(job.status));
  if (job.status === 'failed' && !compact) {
    body.append(node('p', 'track-summary', friendlyError(job.error)));
    if (job.error) {
      const details = node('details', 'track-details');
      details.append(node('summary', '', 'Details'), node('p', 'track-note', job.error));
      body.append(details);
    }
  } else if (job.error && !compact && job.status !== 'needs_selection') {
    body.append(node('p', 'track-note', job.error));
  }

  if (job.status === 'needs_selection') {
    const choices = node('div', 'candidates');
    choices.append(node('div', 'eyebrow', 'Choose the recording to download'));
    for (const candidate of JSON.parse(job.candidates || '[]')) {
      const choice = node('div', 'candidate');
      const description = node('div');
      description.append(
        node('p', '', candidate.title),
        node('div', 'meta', [candidate.artist, duration(candidate.duration)].filter(Boolean).join(' · ')),
      );
      const actions = node('div', 'find-choice-actions');
      const preview = node('a', 'pill ghost', 'Preview ↗');
      preview.href = candidate.url;
      preview.target = '_blank';
      preview.rel = 'noopener noreferrer';
      actions.append(preview, button('Choose', () => api('choose', { id: job.id, url: candidate.url }), 'pill primary'));
      choice.append(description, actions);
      choices.append(choice);
    }
    body.append(choices);
    const actions = node('div', 'track-actions');
    actions.append(node('span', 'meta', 'None of these?'), removeButton(job, 'Remove request'));
    body.append(actions);
  }

  if (job.status === 'queued' && !compact) {
    const actions = node('div', 'track-actions');
    actions.append(removeButton(job, 'Cancel'));
    body.append(actions);
  }

  if (['successful', 'failed'].includes(job.status)) {
    const actions = node('div', 'track-actions');
    if (job.status === 'successful') {
      if (!compact) body.append(node('p', 'track-note path', job.output));
      actions.append(button('Show in Finder ↗', () => api('reveal', { id: job.id })));
    } else {
      actions.append(button('Retry ↻', () => api('retry', { id: job.id }), 'pill primary'), removeButton(job, 'Remove'));
    }
    (compact ? top : body).append(actions);
  }
  return row;
}

let findEdit = null;
function editFind(find, mode) {
  findEdit = { identity: find.identity, mode };
  const rename = mode === 'rename';
  $('#find-editor-title').textContent = rename ? 'Edit track name' : 'Queue a track link';
  $('#find-label').textContent = rename ? 'Artist — Title' : 'Track URL';
  const field = $('#find-value');
  field.maxLength = rename ? 240 : 2000;
  field.value = rename ? find.name : '';
  field.placeholder = rename ? 'Artist — Track (Remix)' : 'https://…';
  $('#find-help').textContent = rename
    ? 'This updates your saved list and the next search. Existing downloads keep their file names.'
    : 'Paste an individual YouTube, SoundCloud, or Bandcamp track. It will use your current download preferences.';
  $('#find-submit').textContent = rename ? 'Save name' : 'Queue download';
  $('#find-error').hidden = true;
  $('#find-editor').showModal();
  field.focus();
  if (rename) field.select();
}

function findCard(find, job) {
  const card = node('article', 'track find-track');
  const top = node('div', 'track-top');
  const info = node('div', 'track-info');
  const isSearch = job?.source === 'Search';
  const busy = job && ['queued', 'resolving', 'downloading', 'processing'].includes(job.status);
  const summary = ['Spotted ' + new Date(find.found_at * 1000).toLocaleString()];
  if (job) summary.push(isSearch && busy ? 'Searching for versions…' : labels[job.status]);
  info.append(node('h3', '', find.name), node('div', 'meta', summary.join(' · ')));
  const controls = node('div', 'find-controls');
  controls.append(button('Edit name', () => editFind(find, 'rename')));
  const remove = button('Delete', async () => {
    const removed = await api('finds/delete', { identity: find.identity });
    toast('Removed “' + removed.name + '” from Saved finds.', {
      label: 'Undo',
      run: () => api('finds/restore', { identity: removed.identity, name: removed.name, found_at: removed.found_at }),
    });
  }, 'pill ghost danger');
  remove.setAttribute('aria-label', 'Delete ' + find.name + ' from Saved finds');
  if (!busy) {
    controls.append(button('Use a link', () => editFind(find, 'download')));
    if (job?.status !== 'needs_selection' || job.input !== find.name) {
      controls.append(button('Find versions', () => api('finds/search', { identity: find.identity }), 'pill primary'));
    }
  }
  controls.append(remove);
  top.append(node('div', 'track-icon', '◉'), info, controls);
  const body = node('div', 'track-body');
  card.append(top, body);
  if (busy && !isSearch) body.append(stageBar(job.status));
  if (job?.status === 'needs_selection') {
    const choices = node('div', 'candidates');
    choices.append(node('div', 'eyebrow', 'YouTube matches'));
    if (job.input !== find.name) choices.append(node('p', 'meta', 'Results for: ' + job.input));
    for (const result of JSON.parse(job.candidates || '[]')) {
      const row = node('div', 'candidate');
      const description = node('div');
      description.append(node('p', '', result.title), node('div', 'meta', [result.artist, duration(result.duration)].filter(Boolean).join(' · ')));
      const actions = node('div', 'find-choice-actions');
      const preview = node('a', 'pill ghost', 'Preview ↗');
      preview.href = result.url;
      preview.target = '_blank';
      preview.rel = 'noopener noreferrer';
      actions.append(preview, button('Queue download', async () => {
        await api('choose', { id: job.id, url: result.url });
        toast('Download queued. Follow it in Queue.');
      }, 'pill primary'));
      row.append(description, actions);
      choices.append(row);
    }
    body.append(choices);
  } else if (job?.status === 'successful') {
    const actions = node('div', 'track-actions');
    actions.append(button('Show in Finder ↗', () => api('reveal', { id: job.id })));
    body.append(actions);
  } else if (job?.status === 'failed') {
    card.classList.add('failed');
    body.append(node('p', 'track-note', job.error));
    if (!isSearch) {
      const actions = node('div', 'track-actions');
      actions.append(button('Retry download ↻', () => api('retry', { id: job.id }), 'pill primary'));
      body.append(actions);
    }
  }
  return card;
}

// The small glass card in the hero: what is happening right now.
function liveCard(queue, finds, completed) {
  const card = $('#live-card');
  const working = queue.find(job => job.status !== 'queued' && job.status !== 'needs_selection') || queue[0];
  const latestFind = [...finds].sort((a, b) => b.found_at - a.found_at)[0];
  let content = null;
  if (tab === 'finds' && latestFind) content = ['Last identified', latestFind.name, 'Spotted ' + new Date(latestFind.found_at * 1000).toLocaleString()];
  else if (tab === 'successful' && completed[0]) content = ['Latest download', completed[0].title || completed[0].input, [completed[0].artist, completed[0].output?.split('.').pop().toUpperCase()].filter(Boolean).join(' · ')];
  else if (tab === 'queue' && working) content = [working.status === 'needs_selection' ? 'Your turn' : 'Now in the queue', working.title || working.input, (labels[working.status] || working.status) + (queue.length > 1 ? ' · ' + (queue.length - 1) + ' more waiting' : '')];
  else if (tab === 'queue' && completed[0]) content = ['Last finished', completed[0].title || completed[0].input, 'Ready in your staging folder'];
  card.hidden = !content;
  if (!content) return;
  card.classList.toggle('idle', !(tab === 'queue' && working && working.status !== 'needs_selection'));
  $('#live-label').textContent = content[0];
  $('#live-title').textContent = content[1];
  $('#live-detail').textContent = content[2];
}

function render(force = false) {
  if (!state) return;
  const signature = JSON.stringify([state, tab]);
  if (!force && signature === renderedState) return;
  renderedState = signature;
  const completed = downloads();
  const isFindSearch = job => job.find_identity && job.source === 'Search';
  const queue = state.jobs.filter(job => active(job) && !isFindSearch(job));
  const failed = state.jobs.filter(job => job.status === 'failed' && !isFindSearch(job));
  const finds = state.finds || [];
  const counts = { queue: queue.length, successful: completed.length, failed: failed.length, finds: finds.length };
  document.querySelectorAll('[data-count]').forEach(element => { element.textContent = counts[element.dataset.count]; });
  document.querySelectorAll('.tab-failed, .stat-failed').forEach(element => element.classList.toggle('alert', failed.length > 0));
  if (state.version) $('#version').textContent = 'v' + state.version;
  $('#update-open').hidden = !state.update;
  if (state.update) $('#update-label').textContent = 'Update to ' + state.update.version;
  liveCard(queue, finds, completed);
  $('#clear-failed').hidden = tab !== 'failed' || failed.length < 2;
  const nudge = $('#failed-nudge');
  nudge.hidden = tab === 'failed' || !failed.length;
  nudge.textContent = failed.length + (failed.length === 1 ? ' request needs' : ' requests need') + ' another try — see why and retry →';

  const recent = $('#recent-downloads');
  recent.hidden = tab !== 'queue' || !completed.length;
  $('#recent-list').replaceChildren(...completed.slice(0, 3).map(job => trackCard(job, true)));
  $('#download-total').textContent = completed.length + ' saved';

  const jobs = tab === 'queue' ? queue : tab === 'successful' ? completed : tab === 'finds' ? finds : failed;
  const headings = {
    queue: ['Queue', 'In the queue', 'Requests being found, downloaded, checked, or waiting for your choice.'],
    successful: ['Library', 'Your downloads', 'Saved on your Mac. Use Show in Finder to locate each file.'],
    finds: ['Identify', 'Saved finds', 'Edit a name, compare versions, then queue the recording you want.'],
    failed: ['Failed', 'Needs another try', 'Each request keeps its reason and a retry action.'],
  };
  $('#list-eyebrow').textContent = headings[tab][0];
  $('#list-title').textContent = headings[tab][1];
  $('#list-subtitle').textContent = headings[tab][2];
  $('#total').textContent = jobs.length + (tab === 'finds' ? ' find' : ' track') + (jobs.length === 1 ? '' : 's');
  const list = $('#list');
  list.replaceChildren();
  if (!jobs.length) {
    const empty = $('#empty-template').content.cloneNode(true);
    empty.querySelector('.empty').classList.toggle('has-downloads', tab === 'queue' && completed.length > 0);
    empty.querySelector('h3').textContent = {
      queue: completed.length ? 'All caught up.' : 'A clean slate. A fresh set.',
      successful: 'Your next favorite is on its way.', finds: 'No songs identified yet.', failed: 'Nothing to fix here.',
    }[tab];
    empty.querySelector('p').textContent = {
      queue: completed.length ? 'Your finished music is saved above. Add another link whenever you’re ready.' : 'Add a track above. Its progress and recording choices will appear here.',
      successful: 'Completed downloads will appear here and on the Queue page.',
      finds: 'Play a song out loud on your speakers or nearby, then click Identify song. Shazam does the listening.',
      failed: 'If a request fails, its details and retry action will appear here.',
    }[tab];
    list.append(empty);
  }
  const linked = new Map();
  for (const job of state.jobs) {
    if (job.find_identity && job.status !== 'cancelled' && !linked.has(job.find_identity)) linked.set(job.find_identity, job);
  }
  jobs.forEach(item => list.append(tab === 'finds' ? findCard(item, linked.get(item.identity)) : trackCard(item)));
  const missing = Object.entries(state.tools).filter(([, available]) => !available).map(([name]) => name);
  $('#tools-warning').hidden = !missing.length;
  $('#tools-warning').textContent = 'Setup needed: ' + missing.join(', ') + '. Run setup.command in the scripts folder, then retry.';
}

async function refresh() {
  try {
    const updated = await api('state');
    if (state) {
      const previous = new Map(state.jobs.map(job => [job.id, job.status]));
      for (const job of updated.jobs) {
        if (job.status === 'successful' && previous.has(job.id) && previous.get(job.id) !== 'successful') {
          toast('Downloaded: ' + (job.title || job.input) + ' — see Recently downloaded or Downloads.');
        }
      }
    }
    state = updated;
    $('#connection').textContent = 'Connected to your Mac';
    render();
  } catch (error) {
    $('#connection').textContent = updating ? 'Updating DJ Intake…' : 'App disconnected — reopen DJ Intake';
  }
}

for (const element of document.querySelectorAll('[data-tab]')) {
  element.onclick = () => setTab(element.dataset.tab, element.classList.contains('stat') ? $('#list').parentElement : null);
}
$('#failed-nudge').onclick = () => setTab('failed');
$('#clear-failed').onclick = async () => {
  try {
    const { ids } = await api('jobs/clear-failed', {});
    await refresh();
    toast('Cleared ' + ids.length + ' failed request' + (ids.length === 1 ? '' : 's') + '.', {
      label: 'Undo',
      run: () => Promise.all(ids.map(id => api('jobs/restore', { id, status: 'failed' }))),
    });
  } catch (error) { toast(error.message); }
};
$('#hero-library').onclick = () => setTab('successful');
const topbar = $('#topbar');
const onScroll = () => topbar.classList.toggle('scrolled', window.scrollY > 24);
window.addEventListener('scroll', onScroll, { passive: true });
onScroll();
$('#hero-identify').onclick = () => { setTab('finds'); $('#identify-song').click(); };
$('#trim-enabled').onchange = () => { $('#clip-fields').hidden = !$('#trim-enabled').checked; };

// Tell people, as they type, whether DJ Intake can use what they pasted.
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
function showInputKind() {
  const kind = describeInput($('#input').value);
  const line = $('#input-kind');
  line.hidden = !kind;
  if (kind) { line.className = 'input-kind ' + kind[0]; line.textContent = kind[1]; }
}
$('#input').addEventListener('input', showInputKind);
$('#input').addEventListener('keydown', event => {
  if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) { event.preventDefault(); $('#add-form').requestSubmit(); }
});
$('#paste').onclick = async () => {
  try {
    const text = await navigator.clipboard.readText();
    if (!text.trim()) { toast('Your clipboard is empty. Copy a track link first.'); return; }
    const box = $('#input');
    box.value = box.value.trim() ? box.value.trimEnd() + '\n' + text.trim() : text.trim();
    showInputKind();
    box.focus();
  } catch {
    $('#input').focus();
    toast('Press ⌘V to paste into the box.');
  }
};
$('#composer-help').onclick = () => openTutorial();
$('#view-downloads').onclick = () => setTab('successful');
$('#find-cancel').onclick = () => $('#find-editor').close();
$('#find-form').onsubmit = async event => {
  event.preventDefault();
  const { identity, mode } = findEdit;
  const submit = $('#find-submit');
  const error = $('#find-error');
  const value = $('#find-value').value.trim();
  submit.disabled = true;
  error.hidden = true;
  try {
    await api('finds/' + mode, { identity, [mode === 'rename' ? 'name' : 'url']: value });
    $('#find-editor').close();
    toast(mode === 'rename' ? 'Track name saved.' : 'Download queued. Follow it in Queue.');
    await refresh();
  } catch (failure) {
    error.textContent = failure.message;
    error.hidden = false;
  } finally { submit.disabled = false; }
};
$('#add-form').onsubmit = async event => {
  event.preventDefault();
  $('#add').disabled = true;
  try {
    const result = await api('jobs', { input: $('#input').value, clip_start: $('#trim-enabled').checked ? $('#clip-start').value : '', clip_end: $('#trim-enabled').checked ? $('#clip-end').value : '' });
    if (result.errors.length) {
      $('#input').value = result.errors.map(item => item.input).join('\n');
      toast(result.errors.map(item => item.error).join(' '));
    } else {
      $('#input').value = '';
      showInputKind();
      $('#clip-start').value = '';
      $('#clip-end').value = '';
      $('#trim-enabled').checked = false;
      $('#clip-fields').hidden = true;
      const count = result.added.length;
      const needsPick = result.added.some(job => job.source === 'Search' || job.source === 'Spotify lookup');
      toast((count === 1 ? 'Added to your queue.' : count + ' tracks added to your queue.') + (needsPick ? ' You’ll pick the recording below.' : ''));
    }
    setTab('queue');
    await refresh();
  } catch (error) { toast(error.message); }
  finally { $('#add').disabled = false; }
};
$('#folder').onclick = () => api('folder', {}).catch(error => toast(error.message));
$('#settings-open').onclick = () => {
  if (!state) return;
  $('#output-dir').value = state.settings.output_dir;
  $('#profile').value = state.settings.profile;
  $('#update-check').checked = state.update_check !== false;
  $('#settings').showModal();
};
$('#pick-folder').onclick = async () => {
  try {
    const result = await api('pick-folder', {});
    if (!result.cancelled) {
      $('#output-dir').value = result.output_dir;
      toast('Default folder saved');
      await refresh();
    }
  } catch (error) { toast(error.message); }
};
$('#settings-close').onclick = () => $('#settings').close();
$('#settings-form').onsubmit = async event => {
  event.preventDefault();
  try {
    await api('settings', { output_dir: $('#output-dir').value, profile: $('#profile').value, update_check: $('#update-check').checked });
    $('#settings').close();
    toast('Preferences saved for new requests');
    await refresh();
  } catch (error) { toast(error.message); }
};
$('#quit-app').onclick = async () => {
  try {
    await api('quit', {});
    $('#settings').close();
    toast('DJ Intake stopped. Reopen the app to continue.');
  } catch (error) { toast(error.message); }
};
refresh();
setInterval(refresh, 2500);

// Update available: one click closes the app, runs the update script and reopens it.
let updating = false;
$('#update-open').onclick = () => {
  const update = state?.update;
  if (!update) return;
  $('#update-version').textContent = update.version;
  $('#update-from').textContent = 'You have ' + update.current + '.';
  $('#update-notes').href = update.url;
  $('#update-auto').hidden = !state.can_update;
  $('#update-manual').hidden = state.can_update;
  $('#update-now').hidden = !state.can_update;
  $('#update-status').hidden = true;
  $('#update-dialog').showModal();
};
$('#update-later').onclick = () => $('#update-dialog').close();
$('#update-now').onclick = async () => {
  const status = $('#update-status');
  $('#update-now').disabled = true;
  status.hidden = false;
  status.textContent = 'Updating… this page reconnects by itself when DJ Intake reopens.';
  try {
    await api('update/install', {});
    updating = true;
    // The server restarts with a new session, so reload once it answers again.
    const started = Date.now();
    const wait = setInterval(async () => {
      try {
        const page = await fetch('/', { cache: 'no-store' });
        if (page.ok && Date.now() - started > 8000) { clearInterval(wait); location.reload(); }
      } catch { /* still updating */ }
      if (Date.now() - started > 600000) { clearInterval(wait); status.textContent = 'Still updating. Reopen DJ Intake from your Desktop if this page doesn’t come back.'; }
    }, 3000);
  } catch (error) {
    status.textContent = error.message;
    $('#update-now').disabled = false;
  }
};

// First-run tutorial. "Seen" is remembered in this browser only; the How to use button reopens it.
const TUTORIAL_KEY = 'djintake.tutorial.v1';
const tutorialSteps = [...document.querySelectorAll('.tutorial-step')];
let tutorialStep = 0;
function showTutorialStep(index) {
  tutorialStep = index;
  tutorialSteps.forEach((step, i) => { step.hidden = i !== index; });
  document.querySelectorAll('#tutorial .dots i').forEach((dot, i) => dot.classList.toggle('on', i === index));
  $('#tutorial-count').textContent = (index + 1) + ' of ' + tutorialSteps.length;
  $('#tutorial-back').hidden = index === 0;
  $('#tutorial-next').textContent = index === tutorialSteps.length - 1 ? 'Start using DJ Intake' : 'Next';
}
function openTutorial() { showTutorialStep(0); $('#tutorial').showModal(); }
function closeTutorial() {
  $('#tutorial').close();
  try { localStorage.setItem(TUTORIAL_KEY, '1'); } catch { /* private mode: show again next time */ }
}
$('#help-open').onclick = openTutorial;
$('#tutorial-skip').onclick = closeTutorial;
$('#tutorial-back').onclick = () => showTutorialStep(Math.max(0, tutorialStep - 1));
$('#tutorial-next').onclick = () => (tutorialStep === tutorialSteps.length - 1 ? closeTutorial() : showTutorialStep(tutorialStep + 1));
$('#tutorial').addEventListener('cancel', () => { try { localStorage.setItem(TUTORIAL_KEY, '1'); } catch { /* ignore */ } });
let seenTutorial = false;
try { seenTutorial = localStorage.getItem(TUTORIAL_KEY) === '1'; } catch { /* ignore */ }
if (!seenTutorial || new URLSearchParams(location.search).has('tour')) openTutorial();
else $('#input').focus();
$('#tutorial').addEventListener('close', () => { if (tab === 'queue') $('#input').focus(); });


$('#identify-song').onclick = async () => {
  const trigger = $('#identify-song');
  const status = $('#recognition-status');
  trigger.disabled = true;
  trigger.classList.add('listening');
  status.hidden = false;
  status.textContent = 'Listening with Shazam… keep the music playing.';
  try {
    const match = await api('identify', {});
    status.textContent = 'Saved: ' + match.name + '. Find versions below when you’re ready.';
    await refresh();
    if (tab !== 'finds') setTab('finds');
  } catch (error) {
    status.textContent = error.message;
  } finally {
    trigger.disabled = false;
    trigger.classList.remove('listening');
  }
};

$('#recognition-setup').onclick = async () => {
  const trigger = $('#recognition-setup');
  const status = $('#recognition-status');
  trigger.disabled = true;
  status.hidden = false;
  status.textContent = 'Opening Apple Shortcuts…';
  try {
    const { installed } = await api('recognition/setup', {});
    status.textContent = installed
      ? 'Recognition is set up. Play a song and click Identify song. If macOS asks for microphone access, choose Allow.'
      : 'In Apple Shortcuts, click Add Shortcut. Then come back, play a song, and click Identify song.';
  } catch (error) {
    status.textContent = error.message;
  } finally {
    trigger.disabled = false;
  }
};
