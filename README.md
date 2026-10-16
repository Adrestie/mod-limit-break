# mod-limit-break

A gauge shared by a party or a raid, for AzerothCore 3.3.5a, after Final Fantasy
XIV's Limit Break. Damage dealt, damage taken and healing from every member fill
one common bar; any of them can spend it, and what happens depends on how far the
bar has filled and on which archetype -- healing, physical damage, magic damage,
tank -- that player put in the reached tier's slot. The gauge lives wherever most
of the group actually is: the map, instance, zone and phase holding the largest
number of members, with a floor of four. Nobody outside it fills the bar or
spends it, and no distance is ever measured.

The design is written down in [docs/CAHIER_DES_CHARGES.md](docs/CAHIER_DES_CHARGES.md),
in French; it is the only reference of the module.

## Status: milestone 1, the mechanism

The mechanism is written; the content is not. What is still undecided in the
specification (§16) ships empty or neutral, and is listed below.

Written:

* **Census, election, gauge** (`src/LimitBreak.cpp`), in three phases that never
  overlap, so the module holds no lock (`MapUpdate.Threads = 8`):
  * A, in each map's own thread: the map counts its grouped players by
    container (map, instance, zone, phase) in its own table; the damage and
    healing hooks write only to a counter of each player.
  * B, in `WorldScript::OnUpdate`, while no map runs: the counters are
    harvested, each group elects its container (largest number of members,
    the active container wins a tie, floor `LimitBreak.MinMembers`), the gauge
    pauses without loss below the floor, and the participants are published.
  * C, same pass: the bar of each member is refreshed, at a low fixed rate.
* The gauge belongs to the group, is never stored, and disappears with the
  group. The fourth segment opens while a boss of `mod_limit_break_boss` is
  engaged in the container, and closes at its death or reset, keeping what the
  first three hold.
* PlayerBots fill the gauge through the same hooks and never spend it.
* **Requests** (`src/cs_limit_break.cpp`): `.limitbreak use` carries no
  parameter and the server recomputes everything (group, container, presence,
  tier, chosen spell); `.limitbreak choose <tier> <spell>` is checked again
  (tier, archetype open to the class, out of combat); requests coming too fast
  are dropped before any work.
* **Bar** (`data/lua/LimitBreak`, ALE + AIO): segmented bar, the slot of the
  reached tier's spell, or a button opening the selection when no spell is
  chosen for it (greyed in combat), and a selection window. The module pushes
  the state to the bar as addon messages; the bar's buttons go through AIO to
  the commands above.

Still to decide (§16), shipped neutral or empty:

* the three factors and four thresholds (`conf`: factors 1.0, thresholds
  100/200/300/400 as placeholders);
* what counts: pets, totems and guardians, self-healing, environment damage,
  duels and world PvP (`LimitBreak.Count.*` switches, all on meanwhile);
  training dummies are not told apart;
* the archetypes of each class (`mod_limit_break_class_archetype`, empty);
* the sixteen effects (`mod_limit_break_effect`, empty) and their spells in
  `spell_dbc` (ids 90000-90999);
* the bosses of the fourth segment and their difficulties
  (`mod_limit_break_boss`, empty);
* the cast time of the trigger and whether it can be interrupted (instant
  meanwhile), and whether a dead player may trigger (refused meanwhile);
* the bar of a member outside the elected container, hidden or greyed
  (`LimitBreak.Hud.OutsideDisplay`, greyed meanwhile);
* effect visuals, autobalance and Mythic+ interaction.

## Layout

| Path | Content |
|---|---|
| `src/` | the C++ module |
| `conf/mod-limit-break.conf.dist` | settings, read again by `.reload config` |
| `data/sql/db-world/base/` | archetypes, class archetypes, effects, bosses, texts, command help |
| `data/sql/db-characters/base/` | the four choices of each character |
| `data/lua/LimitBreak/` | the bar: server relay and client side (AIO) |
| `installer.json` | the WoW-mods installer's description |

## Commands

| Command | Level | |
|---|---|---|
| `.limitbreak use` | player | unleash the reached tier's spell |
| `.limitbreak choose <tier> <spell>` | player | choose a tier's spell; 0 clears it |
| `.limitbreak catalog` | player | send the spells open to the class to the bar |
| `.limitbreak info` | player | the group's gauge in the chat |
| `.limitbreak fill <points>` | game master | add points, for tests |

To try the mechanism before the content exists, `data/sql/db-world/base/01_limit_break_world.sql`
ends with commented test rows (game spells as stand-ins).

Original module, GPL-2.0-or-later, the licence of AzerothCore it is compiled
into.
