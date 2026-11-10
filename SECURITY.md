# Security notes

DJ Intake is a single-user Mac app. Keep its HTTP service on loopback. Requests that change state require a per-session token and reject foreign browser origins. The server validates JSON input and sets a timeout for socket reads. The folder picker only runs after an authenticated local request and runs a fixed system dialog.

Download requests are limited to supported source URLs. yt-dlp ignores user config, disables plugin directories and limits its extractors. The app does not provide a full network sandbox for downloader or media parser processes. Keep yt-dlp, Python and FFmpeg current. A localhost token does not protect the app from another program already running under your Mac account.

Personal download files, catalog, settings and logs are outside the public repository. Release archives contain source and setup scripts, not installed dependencies or personal data.

Use GitHub Issues for ordinary bugs. For a suspected security issue, open a report without publishing credentials, sensitive paths, or exploit details; ask the maintainer for a private contact channel.
