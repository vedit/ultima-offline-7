# Desktop U7 Options

Open **Options** on the Avatar's paperdoll.

- **Save world / Load last save:** F5 and F9 use the active save slot.
- **Saved worlds:** ten original U7 slots, editable titles, overwrite/load confirmation. An asterisk marks the active slot. The development launcher resumes that slot on the next launch. The Developer's Wand also saves to it.
- **Music, sound and speech:** independent switches and 0–100 volume controls. Sound effects control both original native effects and the mapped ClassicUO effects.
- **Exult music folder:** Browse to your own installed Exult `music` folder, or paste its path and select **Use folder**. The original U7 track number selects `00bg.ogg` through `59bg.ogg`. Missing or unreadable tracks fall back to native synthesis. **Use native music** clears the folder selection. Recordings are neither copied nor bundled.
- **Display/movement:** nearby-wall transparency, Ctrl+wheel zoom, and Always run.
- **Advanced client settings:** the existing ClassicUO settings.
- **Quit:** confirmation before exiting; it does not automatically save.

Preferences are stored in the existing per-run ClassicUO profile. World saves remain original U7 files; `active-slot.txt` is launcher metadata beside them. `--test-copy <new-run>` copies the active checkpoint into slot 1 of a new, independent run and refuses an existing destination. Scripted qualification sessions remain silent; the normal desktop launcher explicitly enables native audio output.

The original native music sequencer owns track starts, queued special tunes, stops, and returns to interrupted music. The client observes actual song starts and uses the local recording until the native cue stops or changes. Volume changes affect output, not the native song clock, fade counters, quest state, or randomness. Native synthesis uses the installed original game data; optional recordings are Simon Quinn's MT-32 performances distributed by the Exult project. This is recording playback, not MT-32 emulation in the client.

## Credits

The in-game credits acknowledge Dana Glover; additional music by Raymond Benson, Herman Miller, David Watson, Kathleen Jones, and Kirk Winterrowd; and Origin Systems. See the [transcription of the original Black Gate credits](https://www.wiki.ultimacodex.com/wiki/Credits_(Ultima_VII)). Optional MT-32 recordings are credited to **Simon Quinn** and the **Exult project**, as identified by the installed music pack's readme and [Exult documentation](https://exult.info/docs.html).

## Qualification

`game/qualification/audio-options.py` exercises native switches, exact mute, gain restoration, validation, deduplication, save slots, load resynchronization, active-slot restart, and independent test-copy. Its `--client` mode captures the UO panels and checks recording playback, missing-track fallback, native acknowledgments, typing isolation, reconnect, save/load, and quit cancellation. Existing inventory, companion, spellbook, spell-effect and U7-options checks remain separate regressions.

This change is for the desktop build. Browser audio and browser file selection require their own playback integration; this does not qualify them.
