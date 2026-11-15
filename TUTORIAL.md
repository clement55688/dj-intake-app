# DJ Intake: install, download, and update

1. Download the installer ZIP from [GitHub Releases](https://github.com/clement55688/dj-intake-app/releases/latest). Unzip it and run **Install DJ Intake.command**. If Finder declines to launch the script, you can inspect it and run `bash ` followed by the script path in Terminal.
2. The installer needs Git, Python 3.10 or newer, and Apple's Command Line Tools. FFmpeg and ffprobe are required for processing. Setup uses Homebrew to install FFmpeg if available; otherwise install the tools before rerunning setup. For YouTube, install Deno; setup can also install it with Homebrew. It installs source into `~/Library/Application Support/DJ Intake Source` and builds the Desktop app locally. No GitHub login is required to install.
3. Double-click **DJ Intake.app** on your Desktop. The library opens in your browser and a record icon appears in the Mac menu bar. Click the icon to paste a URL and queue it without opening the full library.
4. Use **Settings → Choose folder…** in either view to set the default download location. Picking a folder saves it immediately. Previously downloaded files stay where they are.
5. Enable **Trim to timestamps** to cut a section. For example, enter `00:50` and `02:30` for a 1:40 clip. Leave it off for the whole track.
6. Open **Library → Show in Finder** to locate a finished file. Song-name searches may need you to select a recording in the full library.
7. To name a song you hear, open **Identify** and click **Set up recognition** once. Apple Shortcuts opens; click **Add Shortcut**. Then play a song on your Mac or nearby and click **Identify song** — Shazam, through Apple Shortcuts, names it and DJ Intake saves it to Saved finds. The first time, macOS asks to use the microphone; choose **Allow**. Nothing downloads until you pick a version. See [RECOGNITION.md](RECOGNITION.md).
8. Paste a YouTube playlist, SoundCloud set or Bandcamp album to see its tracks and tick the ones you want. Tracks you already have are unticked.
9. Before downloading, DJ Intake checks your Music folder and download folder. If you already have the song, it asks before downloading it again. If a site only offers a locked track or a 30-second preview, it shows the same song on YouTube for you to pick, plus Beatport and Bandcamp links to buy a high-quality copy. The Library tab flags files that are only about 30 seconds long.
10. Using Serato? Turn on **Add new downloads to a "DJ Intake" crate** (Library tab or Preferences). DJ Intake updates that one crate while Serato is closed, and the tracks appear the next time you open Serato.
11. **Send from iPhone:** click **Send from iPhone** under the add box, turn it on and choose **Allow** when macOS asks about iCloud Drive. On your iPhone, open Files › iCloud Drive › Shortcuts, tap **Send to DJ Intake** and add it. Then share any track link to **Send to DJ Intake**; it lands in your queue while DJ Intake is open.

Use sources you're entitled to download. Keep the Mac awake while the queue is working.

## Updates

Let current jobs finish. Quit the menu-bar shortcut and use **Preferences → Quit app** in the webpage. Run the update script in Terminal:

```bash
bash "$HOME/Library/Application Support/DJ Intake Source/scripts/update.command"
```

It pulls the newest changes from GitHub, refreshes dependencies, and rebuilds the app. It preserves your existing settings and queue. Open the Desktop app again when it finishes.

From version 0.4.2 on, you don't need Terminal: when a new version is published, an **Update to …** button appears in the library's top bar (and a notice in the menu-bar panel). Click it, then **Update now** — DJ Intake closes, updates and reopens by itself. DJ Intake checks GitHub for the latest version number a few times a day; turn this off in **Preferences**.

From 0.4.4, the Desktop icon is a shortcut (it has a small arrow) to the app inside DJ Intake's own folder, so updates never need permission to change your Desktop. The first update to 0.4.4 may still ask once.

## Feedback

Open [GitHub Issues](https://github.com/clement55688/dj-intake-app/issues/new/choose) and choose **Report a bug** or **Suggest an improvement**. Issues are public; omit private URLs, personal paths and logs with account information.
