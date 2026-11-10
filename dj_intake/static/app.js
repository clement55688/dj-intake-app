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

function button(label, action, className = 'button subtle') {
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

function setTab(value) {
  tab = value;
  document.querySelectorAll('[data-tab]').forEach(element => {
    element.classList.toggle('active', element.dataset.tab === tab);
  });
  render(true);
}

function trackCard(job, compact = false) {
  const row = node('article', 'track ' + job.status + (compact ? ' compact' : ''));
  const top = node('div', 'track-top');
  top.append(node('div', 'track-icon', job.status === 'successful' ? '✓' : job.status === 'failed' ? '!' : '♫'));
  const info = node('div', 'track-info');
  const extension = job.output ? job.output.split('.').pop().toUpperCase() : '';
  info.append(
    node('h3', '', job.title || job.input),
    node('div', 'meta', [job.artist, job.source, extension, job.clip_end !== null && job.clip_end !== undefined ? 'Clip '+duration(job.clip_start)+'–'+duration(job.clip_end) : ''].filter(Boolean).join(' · ')),
  );
  top.append(info, node('span', 'status ' + job.status, labels[job.status] || job.status));
  row.append(top);
  if (job.error && !compact) row.append(node('p', 'track-note', job.error));

  if (job.status === 'needs_selection') {
    const choices = node('div', 'candidates');
    for (const candidate of JSON.parse(job.candidates || '[]')) {
      const choice = node('div', 'candidate');
      const description = node('div');
      description.append(
        node('p', '', candidate.title),
        node('div', 'meta', [candidate.artist, duration(candidate.duration)].filter(Boolean).join(' · ')),
      );
      choice.append(description, button('Choose ↗', () => api('choose', { id: job.id, url: candidate.url })));
      choices.append(choice);
    }
    row.append(choices);
  }

  if (['successful', 'failed'].includes(job.status)) {
    const actions = node('div', 'track-actions');
    if (job.status === 'successful') {
      if (!compact) row.append(node('p', 'track-note', job.output));
      actions.append(button('Show in Finder ↗', () => api('reveal', { id: job.id })));
    } else {
      actions.append(button('Retry request ↻', () => api('retry', { id: job.id })));
    }
    row.append(actions);
  }
  return row;
}

function render(force = false) {
  if (!state) return;
  const signature = JSON.stringify([state, tab]);
  if (!force && signature === renderedState) return;
  renderedState = signature;
  const completed = downloads();
  const queue = state.jobs.filter(active);
  const failed = state.jobs.filter(job => job.status === 'failed');
  $('#count-queue').textContent = queue.length;
  $('#count-successful').textContent = completed.length;
  $('#count-failed').textContent = failed.length;

  const recent = $('#recent-downloads');
  recent.hidden = tab !== 'queue' || !completed.length;
  $('#recent-list').replaceChildren(...completed.slice(0, 3).map(job => trackCard(job, true)));
  $('#download-total').textContent = completed.length + ' SAVED';

  const jobs = tab === 'queue' ? queue : tab === 'successful' ? completed : failed;
  const headings = {
    queue: ['In the queue', 'Requests being resolved, downloaded, or waiting for your choice.'],
    successful: ['Your downloads', 'Saved on your Mac. Use Show in Finder to locate each file.'],
    failed: ['Needs another try', 'Your requests stay here with the reason and a retry action.'],
  };
  $('#list-title').textContent = headings[tab][0];
  $('#list-subtitle').textContent = headings[tab][1];
  $('#crumb').textContent = tab === 'successful' ? 'DOWNLOADS' : tab.toUpperCase();
  $('#total').textContent = jobs.length + ' TRACK' + (jobs.length === 1 ? '' : 'S');
  const list = $('#list');
  list.replaceChildren();
  if (!jobs.length) {
    const empty = $('#empty-template').content.cloneNode(true);
    empty.querySelector('.empty').classList.toggle('has-downloads', tab === 'queue' && completed.length > 0);
    empty.querySelector('h3').textContent = {
      queue: completed.length ? 'All caught up.' : 'A clean slate. A fresh set.',
      successful: 'Your next favorite is on its way.', failed: 'Nothing to fix here.',
    }[tab];
    empty.querySelector('p').textContent = {
      queue: completed.length ? 'Your finished music is saved above. Add another link whenever you’re ready.' : 'Add a track above. Its progress and recording choices will appear here.',
      successful: 'Completed downloads will appear here and on the Queue page.',
      failed: 'If a request fails, its details and retry action will appear here.',
    }[tab];
    list.append(empty);
  }
  jobs.forEach(job => list.append(trackCard(job)));
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
  element.onclick = () => setTab(element.dataset.tab);
}
$('#trim-enabled').onchange = () => { $('#clip-fields').hidden = !$('#trim-enabled').checked; };
$('#view-downloads').onclick = () => setTab('successful');
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
