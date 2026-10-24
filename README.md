# mod-limit-break

**WORK IN PROGRESS**

A gauge shared by a party or a raid, for AzerothCore 3.3.5a, after Final Fantasy XIV's Limit Break: the whole group fills one bar, and any member can spend it.

## Key features

- Damage dealt, damage taken and healing of every member fill one common bar.
- Four tiers; the fourth opens only against a raid boss (every WotLK raid boss by default).
- Each player picks, for each tier, a spell of an archetype open to the class: healing, physical damage, magic damage, tank.
- Sixteen effects, scaled on the caster's power.
- The gauge follows where most of the group is, with a floor of four members; nobody outside fills or spends it.
- Playerbots fill the gauge but never spend it.

## Dependencies

| Dependency | For |
|---|---|
| [AzerothCore](https://github.com/azerothcore/azerothcore-wotlk) (WotLK 3.3.5a) | the server |
| [mod-ale](https://github.com/azerothcore/mod-ale) | runs the bar's server script; without it the gauge still fills, but nobody sees it |
| [AIO](https://github.com/Rochet2/AIO) | the bar: `AIO_Server` in `lua_scripts`, and the `AIO_Client` addon on every client |
| [WarcraftXL](https://github.com/WarcraftXL/wxl-core) and its Modern M2 plugin | the effects' modern models, which the client draws as they are |

## How to install

1. Download `installer.exe` from the [WoW-mods-installer releases](https://github.com/Adrestie/WoW-mods-installer/releases).
2. Stop the worldserver and close the game.
3. Run `installer.exe`, give it this folder and the folders it asks for, click **Check**, then **Install**.
4. Rebuild the worldserver. On its next start, the core applies the module's SQL.
5. The installer writes the game files into `Data\patch-Z.MPQ`: give that archive to the other players.

## How to update

Same steps with the new version's folder, choosing **Update** instead of **Install**. Each player's tier choices and your `mod-limit-break.conf` settings are kept. Rebuild the worldserver.

## How to uninstall

Same steps, choosing **Remove**. Everything goes, database included. Rebuild the worldserver.

## Configuration

`mod-limit-break.conf` sets:

- the module on or off, and in battlegrounds;
- how much healing, damage taken and damage done fill the bar, and the four tier thresholds;
- what counts: self-healing, environment damage, PvP, pets;
- the minimum members, update interval and request cooldown;
- whether the bar shows outside the elected container and while paused.

## Commands

| Command | |
|---|---|
| `/limitbreak` | the bar's selection window (also `/limite`) |
| `.limitbreak use` | unleashes the reached tier's spell |
| `.limitbreak choose <tier> <spell>` | chooses a tier's spell; 0 clears it |
| `.limitbreak catalog` | sends the spells open to the class to the bar |
| `.limitbreak info` | the group's gauge in the chat |
| `.limitbreak fill <points>` | game master: adds points |
| `.limitbreak debug` | game master: what the module sees for a player |
