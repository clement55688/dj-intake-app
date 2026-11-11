# DJ Intake

A local Mac app for turning track requests into an organized staging library. Paste URLs or song names, watch the queue, choose recordings when searching, and keep downloads and failed requests in separate lists. No AI service or API key is needed to execute downloads.

[Install and use DJ Intake](TUTORIAL.md) · [Downloads](https://github.com/clement55688/dj-intake-app/releases/latest) · [Feedback](https://github.com/clement55688/dj-intake-app/issues/new/choose)

## Start

Requires macOS and Python 3.10+. Double-click **Launch DJ Intake.command**. First launch creates a Python environment and installs yt-dlp. FFmpeg must be installed; setup can install it with Homebrew. A compatible existing Stacher FFmpeg can be used as a fallback.

```sh
./scripts/setup.command
./'Launch DJ Intake.command'
```

Double-click the Desktop app to open the webpage and keep a record icon in the macOS menu bar. Click that record icon to paste a URL or song name and add it to the queue without opening the webpage. **Open library** shows the full queue; **Quit menu bar** exits the shortcut while leaving the worker running. Use Preferences → Quit app in the webpage to stop the worker. The menu-bar app does not start automatically at login. Building the native app requires Xcode Command Line Tools (Swift); running the built app does not.

The interface opens at `http://127.0.0.1:8765` and runs entirely on your Mac. Closing the browser tab does not stop the worker. Use Preferences → Quit app to stop it. The Mac must stay awake to process tracks. The Desktop app is a locally signed native macOS menu-bar app with a quick-add popover. The full library interface runs locally in your browser. No cloud queue, Google Drive sync, or login-item service is enabled by this app.

Build the Mac launcher with `python3 scripts/build_app.py`; open `outputs/DJ Intake.app`. Use `python3 scripts/build_app.py --desktop` to put a link to it on the Desktop (a link, not a copy, so rebuilding and in-app updates never need permission to change the Desktop). It launches this checkout, so keep the project folder in place. Rebuild the launcher if you move the project.

## Requests

- **YouTube / YouTube Music:** paste an individual video URL. Tracking parameters are removed for duplicate detection.
- **SoundCloud:** paste a track URL (including shared short URLs).
- **Bandcamp:** paste a track URL. Available public audio is not necessarily the purchased lossless master.
- **Song names:** search YouTube, then choose one of up to five recordings. Include remix/edit names in the search. Results display title, uploader and duration; the uploader is not automatically treated as the performing artist.
- **Spotify:** look up the track title, then offer separate YouTube recording candidates. Spotify audio is not downloaded. If title lookup is insufficient, enter Artist - Title instead.

The Queue screen keeps the three most recent completed files visible in Recently downloaded. The Downloads tab lists all completed files, grouped by saved path so duplicate requests do not create duplicate library cards. New completions show a notification in the app.

You can paste a YouTube address-bar URL containing both `v=` and `list=` (including radio mixes): the app takes only the current video ID and drops playlist/radio parameters. A playlist-only URL without `v=` needs a specific song link; the Share button is optional for ordinary watch URLs.

The worker selects source routes automatically through yt-dlp and runs one job at a time. Successful means a file downloaded, decoded without errors and was copied to staging; it does not certify source quality or the exact recording. Audition and analyze in Serato/rekordbox before playing live. Sites can require authentication or change their behavior; failures remain visible with the reason and Retry. This version does not import browser cookies or bypass DRM/paywalls. Use downloads you are entitled to obtain.

## Timestamp clips

Check **Trim to timestamps** to reveal **Start** and **End** fields below the URL, for example `00:50` → `02:30`. This produces a 1:40 clip. Unchecked means the full track, including when old times remain in hidden fields. Both blank also means the full track; an end with no start means start at 00:00. Supported formats: seconds, MM:SS, or HH:MM:SS, optionally with milliseconds. The same range applies to all requests in a pasted batch and stays attached while you choose a search result.

The acquired source is kept intact; FFmpeg decodes and cuts the selected interval. This first version downloads the source before cutting, rather than fetching only that time range. The existing one-hour recording limit still applies. Clips are re-encoded for precise boundaries. MP3/AIFF use the selected performance profile; **Original** mode exports clips as 24-bit PCM WAV, preserving the acquired compressed source separately. This does not restore any quality lost in the source.

Clip filenames include their range: `Artist_Song (00m50s-02m30s).mp3`. No hashes or IDs. The queue and Downloads cards display the selected range. Requests are deduplicated by recording, range and output profile, so a clip cannot silently reuse a full track. Invalid/reversed ranges are rejected; an end beyond the recording moves the request to Failed with an explanation.

## Files and quality

Default staging: `~/Music/DJ Intake Staging`. Change it in Preferences. Queue/catalog, per-request acquired audio, metadata, logs, and checksum manifests live in `~/Library/Application Support/DJ Intake/`. Existing Serato and rekordbox databases and the organized library are not modified.

Profiles apply to **new** requests:

- **MP3:** copy existing MP3 audio without re-encoding; otherwise make a 320 kbps / 44.1 kHz copy. Write artist/title tags from source metadata. No automatic denoising, loudness changes, trimming or remastering.
- **AIFF:** make a 16-bit / 44.1 kHz PCM copy with artist/title tags. Verify actual player compatibility before venue use.
- **Original:** preserve the acquired file's format and tags; only organize its filename.

Lossy-to-lossless or higher-bitrate conversion cannot recover missing information. Acquired audio is kept separately so you can reprocess later. There is no automatic original-file cleanup in v0.1: watch disk space.

Files use `Artist_Song (Version).ext` with no hash or request ID. Only different recordings sharing a filename get a numeric `(2)` suffix. Never overwrite another output. Repeated canonical URLs reuse a queue entry; different URLs for the same provider recording reuse a successful file when its checksum is intact. Cross-provider fingerprint deduplication is not implemented. An interrupted active job requeues on restart; publication recovery reuses an identical already-published file. Failed jobs retain metadata and logs.

## Update

Close the running app, then run `scripts/update.command`. It runs `git pull --ff-only` and refreshes dependencies; uncommitted conflicts stop the update. Personal settings, music, and history are outside the checkout. The code never automatically executes downloaded software updates. If a website stops working, update yt-dlp first by rerunning setup.

To apply the naming rules to existing app-managed staging files, quit DJ Intake and run `.venv/bin/python scripts/rename_staged.py`. This makes a database backup and rename journal and updates the catalog/manifests while preserving file bytes.

## Development

Native shortcut: AppKit status item + WebKit popover (`native/MenuBarApp.swift`), sharing the local authenticated queue API. Both quick-add and the webpage use `00:00 → 00:00` placeholders and hide timestamp fields until checked. Native resize/open/quit messages accept only the main frame on the local app origin.

Backend: Python standard library HTTP server, SQLite, single background worker. Frontend: plain HTML/CSS/JavaScript, no build step or remote fonts. Downloader: maintained yt-dlp CLI, FFmpeg/ffprobe. Bound to loopback with host checks, session token, same-origin mutation checks and no remote access. Only fixed source hosts are accepted; this local-only prototype is not hardened as a public multi-user server.

```sh
.venv/bin/python -m unittest discover -s tests -v
node --check dj_intake/static/app.js
.venv/bin/python -m dj_intake.server --no-browser
```

Source layout: `dj_intake/core.py` handles queue/routing/audio, `dj_intake/server.py` handles local APIs, `dj_intake/static/` holds the interface. `NAMING_RULES.md` defines filenames. Legacy `mac/` sync utilities predate this app and are not enabled or needed; their local account configuration is deliberately excluded from this repository.

Future work: recording preview, editable metadata review, richer progress, optional shared request inbox, fingerprint deduplication, import/export of catalog backups and notarized distribution packaging.
