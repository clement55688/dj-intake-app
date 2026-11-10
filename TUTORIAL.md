# DJ Intake: install, download, and update

1. Download the installer ZIP from [GitHub Releases](https://github.com/clement55688/dj-intake-app/releases/latest). Unzip it and run **Install DJ Intake.command**. If Finder declines to launch the script, you can inspect it and run `bash ` followed by the script path in Terminal.
2. The installer needs Git, Python 3.10 or newer, and Apple's Command Line Tools. FFmpeg and ffprobe are required for processing. Setup uses Homebrew to install FFmpeg if available; otherwise install the tools before rerunning setup. For YouTube, install Deno; setup can also install it with Homebrew. It installs source into `~/Library/Application Support/DJ Intake Source` and builds the Desktop app locally. No GitHub login is required to install.
3. Double-click **DJ Intake.app** on your Desktop. The library opens in your browser and a record icon appears in the Mac menu bar. Click the icon to paste a URL and queue it without opening the full library.
4. Use **Settings → Choose folder…** in either view to set the default download location. Picking a folder saves it immediately. Previously downloaded files stay where they are.
5. Enable **Trim to timestamps** to cut a section. For example, enter `00:50` and `02:30` for a 1:40 clip. Leave it off for the whole track.
6. Open **Downloads → Show in Finder** to locate a finished file. Song-name searches may need you to select a recording in the full library.

Use sources you're entitled to download. Keep the Mac awake while the queue is working.

## Updates

Let current jobs finish. Quit the menu-bar shortcut and use **Preferences → Quit app** in the webpage. Run the update script in Terminal:

```bash
bash "$HOME/Library/Application Support/DJ Intake Source/scripts/update.command"
```

It pulls the newest changes from GitHub, refreshes dependencies, and rebuilds the Desktop app. It preserves your existing settings and queue. Open the Desktop app again when it finishes. Updates are manual.

## Feedback

Open [GitHub Issues](https://github.com/clement55688/dj-intake-app/issues/new/choose) and choose **Report a bug** or **Suggest an improvement**. Issues are public; omit private URLs, personal paths and logs with account information.
