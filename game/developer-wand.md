# Developer's Wand

The desktop development launcher enables a modeless ClassicUO testing toolbox.
Single-click the wand in the Avatar's backpack to see its name; double-click to
open it. The wand is a presentation-only shortcut: it adds no native weight,
cannot be equipped or dropped, and is recreated when reconnecting or loading.

The tools change the original U7 world. Created supplies, creatures, equipment,
stats and weather use native engine operations; ordinary spellcasting still
checks the original learned spells, reagents, mana and eligibility.

## Controls

- **Supplies:** create a bag with 30 of each of the eight original reagents, add
  a fully learned spellbook, or refill a selected living actor's HP and mana.
- **Items / Creatures:** search original names and categories, inspect available
  UO artwork, and create an item or a fresh generic actor. Unmapped art remains
  identifiable in the catalog rather than being mistaken for an absent U7 object.
- **Duplicate:** select a source, then its destination. Supported containers copy
  their contents; spellbooks preserve learned spells and bookmarks; virtue stones
  preserve their marked destination. Avatar, companions, story NPCs and opaque
  internal objects cannot be duplicated.
- **Inspect / Stats:** target an actor or object to read native properties and
  mapping details. Copy Details produces text suitable for a bug report. Actor
  stat edits are absolute values; experience editing does not award training.
- **Conditions:** apply or remove supported native conditions. Resurrection uses
  a valid native corpse; setting HP is not a replacement for resurrection.
- **World:** set native time, weather, teleport destination, or save the current
  run. Time changes affect NPC schedules. Advanced weather types indicate where
  their UO presentation is not implemented.
- **Cleanup:** remove surviving tool-created objects from this session. Loading
  clears this history. Containers or actors holding untracked possessions cannot
  be removed through cleanup.

Escape or right-click cancels targeting. A native dialogue or spell prompt takes
priority over debug targeting. The toolbox does not pause the world.

## Saves and launch options

Run `Play Ultima Offline 7.cmd` for the normal development save. Add `--no-debug`
to hide the wand and disable native debug commands for that launch.

Use `--test-copy <new-run>` to create a separate run from the source run's latest
saved checkpoint. `--run <source-run>` selects the source; without it, the normal
development run is used. Existing destination runs are never overwritten.
Resume an existing test copy with `--run <test-run>`.

From PowerShell in the repository:

```powershell
& '.\Play Ultima Offline 7.cmd' --test-copy wand-spells
& '.\Play Ultima Offline 7.cmd' --run wand-spells
& '.\Play Ultima Offline 7.cmd' --no-debug
```

Save World uses the same native operation as F5. The wand itself needs no save
format change; objects and changes made with it are saved as ordinary U7 state.

## Limits

Recursive copying is bounded to 16 levels and 512 objects. Unsupported descendants
cause the entire copy to be refused. Placement or allocation failure rolls back
new objects and leaves the source intact.

Creature copies keep explicit base attributes and equipment, with fresh identities,
conditions and AI. Ground placement checks native support and collision; targeting
furniture uses its native top elevation. Targeting a living actor places an item in
that actor's inventory.

Created specimens are persistent native objects. Dead created actors are protected
from cleanup until resurrected, so their corpses cannot refer to a reused identity.

The stat editor distinguishes base attributes from effective native values.
Strength/combat allow 1–127; dexterity/intelligence 1–30; magic 0–30; training
0–255; food 0–31; experience 0–999999. Current HP and mana cannot exceed their
editor maxima, and reducing maxima clamps current values. Derived values,
story identity and quest flags are read-only.

This is a desktop development tool, not a replacement for native gameplay or a
global lighting/weather-renderer rewrite. Automated audit capabilities remain
separate from the development capability.
