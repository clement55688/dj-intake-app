# Naming rules

New outputs use `Artist_Song (Version).ext`. No hash, request ID, or source ID is added to the filename.

Example: `AFROJACK & Martin Garrix_Turn Up The Speakers (Julian Jordan Remix).mp3`.

- Use one underscore between artist and song; keep ordinary spaces within both names.
- Keep meaningful remix/edit/version labels and Clean/Dirty labels. Remove explicit bracketed promotional labels and promotional suffixes such as `(Official Music Video)`, `[Official Audio]`, and `- Official Video`.
- Remove a repeated `Artist - ` prefix when it exactly matches the known artist tag. Never guess the artist from the upload channel. Use `Unknown Artist` if no artist is available.
- Normalize Unicode NFC; preserve native scripts, accents, capitalization and meaningful punctuation.
- Replace reserved path characters and controls with spaces; collapse whitespace; strip leading/trailing spaces and dots.
- Limit the descriptive stem to 160 UTF-8 bytes, keeping whole characters. Use the actual output extension.
- If a different file already has the same name, use a simple numeric suffix: `Artist_Song (2).mp3`. Never overwrite another recording. Identical content reuses the existing path, including during interrupted publication recovery.
- Clips add a readable time range before the extension: `Artist_Song (00m50s-02m30s).mp3`. Different ranges remain distinct.
- Keep checksums and internal request IDs in the catalog/manifests only. Retain acquired originals and source metadata separately.
- MP3/AIFF copies get known artist/title tags; original-format mode preserves existing tags.
- Keep filenames stable after Serato/rekordbox import. `scripts/rename_staged.py` can update existing app-managed staging names while the app is stopped; it backs up the database, records old/new paths, and updates all referring requests/manifests without changing audio bytes.
