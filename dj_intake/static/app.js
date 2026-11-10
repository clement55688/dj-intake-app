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

function toast(message) {
  $('#toast').textContent = message;
  $('#toast').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $('#toast').hidden = true; }, 6500);
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
  if (job.error && !compact) body.append(node('p', 'track-note', job.error));

  if (job.status === 'needs_selection') {
    const choices = node('div', 'candidates');
    for (const candidate of JSON.parse(job.candidates || '[]')) {
      const choice = node('div', 'candidate');
      const description = node('div');
      description.append(
        node('p', '', candidate.title),
        node('div', 'meta', [candidate.artist, duration(candidate.duration)].filter(Boolean).join(' · ')),
      );
      choice.append(description, button('Choose ↗', () => api('choose', { id: job.id, url: candidate.url }), 'pill primary'));
      choices.append(choice);
    }
    body.append(choices);
  }

  if (['successful', 'failed'].includes(job.status)) {
    const actions = node('div', 'track-actions');
    if (job.status === 'successful') {
      if (!compact) body.append(node('p', 'track-note path', job.output));
      actions.append(button('Show in Finder ↗', () => api('reveal', { id: job.id })));
    } else {
      actions.append(button('Retry request ↻', () => api('retry', { id: job.id }), 'pill primary'));
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
  if (!busy) {
    controls.append(button('Use a link', () => editFind(find, 'download')));
    if (job?.status !== 'needs_selection' || job.input !== find.name) {
      controls.append(button('Find versions', () => api('finds/search', { identity: find.identity }), 'pill primary'));
    }
  }
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
  liveCard(queue, finds, completed);
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
      finds: 'Play a song on your Mac or nearby, then click Identify song. Shazam does the listening.',
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
    $('#connection').textContent = 'App disconnected — reopen DJ Intake';
  }
}

for (const element of document.querySelectorAll('[data-tab]')) {
  element.onclick = () => setTab(element.dataset.tab, element.classList.contains('stat') ? $('#list').parentElement : null);
}
$('#failed-nudge').onclick = () => setTab('failed');
$('#hero-library').onclick = () => setTab('successful');
const topbar = $('#topbar');
const onScroll = () => topbar.classList.toggle('scrolled', window.scrollY > 24);
window.addEventListener('scroll', onScroll, { passive: true });
onScroll();
$('#hero-identify').onclick = () => { setTab('finds'); $('#identify-song').click(); };
$('#trim-enabled').onchange = () => { $('#clip-fields').hidden = !$('#trim-enabled').checked; };
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
      $('#clip-start').value = '';
      $('#clip-end').value = '';
      $('#trim-enabled').checked = false;
      $('#clip-fields').hidden = true;
      toast(result.added.length + ' request(s) added');
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
    await api('settings', { output_dir: $('#output-dir').value, profile: $('#profile').value });
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
