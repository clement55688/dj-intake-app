# Identify a song and save it for later

DJ Intake can run a dedicated macOS shortcut on demand. It saves the returned artist and title in **Saved finds**. Search a saved song later to find a downloadable source.

## From a saved find to a download

1. Open the **Identify** tab. Choose **Edit name** to correct the artist or title or add a remix name. Edits change future searches; previously downloaded files keep their names.
2. Choose **Find versions** to see YouTube matches with their uploader and duration. Use **Preview** to verify the version, then click **Queue download** on that result. Recognition and search alone do not download anything.
3. If you already have an individual YouTube, SoundCloud, or Bandcamp track URL, use **Use a link** instead. Watch **Add** for progress, **Library** for finished files, and **Failed** for any download that needs another try.

## One-time setup on each Mac

1. In DJ Intake, open **Identify** or the menu-bar panel and click **Set up recognition**.
2. Apple Shortcuts opens the bundled shortcut. Click **Add Shortcut** if prompted. If the shortcut is already installed, the button opens it in the editor.
3. Return to DJ Intake, play a song and click **Identify song**. If macOS asks for microphone access, choose **Allow** to enable recognition.
4. Open **Saved finds** to see the match.

The shortcut uses Apple’s Recognize Music action and returns its result as text. You can edit the returned name in Saved finds. To check its output in Terminal, run:

```bash
shortcuts run 'DJ Intake Recognize' --output-type public.plain-text --output-path -
```

Recognition happens only when you click Identify song. DJ Intake stores the returned text and time on your Mac. Apple’s recognition service handles the audio. Matches depend on what the Mac can hear and what Shazam can identify. Play the song out loud through speakers: recognition listens with the microphone and can’t hear audio that only plays in headphones. If Shortcuts says “Try again when network conditions improve”, that usually means it heard silence. A mix, mashup, or heavily altered edit may return no match or a different version of the song.
