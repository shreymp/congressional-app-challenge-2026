Human controls were fetched directly from the [official LibriSpeech test-clean archive](https://www.openslr.org/resources/12/test-clean.tar.gz). [OpenSLR's corpus documentation](https://www.openslr.org/12/) and [corpus description](https://www.openslr.org/resources/12/about.html) identify LibriSpeech as 16 kHz read English speech derived from LibriVox audiobooks. This is trustworthy human-speech provenance; the unrelated local transcript fixture WAVs were not used as human controls.

Selection was fixed before inference: stream the official archive, take the first two encountered speakers, collect their first archive-order utterances until at least 40 seconds, concatenate and crop each to exactly 40 seconds. Archive order is nonchronological, so these controls contain utterance joins and are not natural conversations. Official `SPEAKERS.TXT` identifies both speakers as male: `6930` (Nolan Fout) and `1320` (number6). Both belong to test-clean.

The resulting two mono 16 kHz PCM16 WAVs are under `audio/human_controls/`. Their hashes, exact source member names, individual FLAC hashes, durations, and archive HTTP headers are in `human_control_provenance.json`. The source FLACs and resulting WAVs occupy approximately 4 MB. The downloader stops reading the archive after it has both controls, rather than saving the 346,663,984-byte archive.

Reproduce from the project root:

```sh
.venv/bin/python 'model teseting/fetch_human_controls.py'
```

This needs network access to `www.openslr.org`; the evaluation itself remains local. The downloader writes only public dataset controls and provenance, and does not read or transmit the user's recording. Official corpus README, speaker table, license (CC BY 4.0), and downloaded documentation pages are preserved beside this note.

Two male audiobook readers are convenience controls. They do not establish broad human false-positive performance, generalization to phone calls, or independence from the detector's unknown training corpus. Concatenations, crops, repeats, and transformed versions remain related observations.
