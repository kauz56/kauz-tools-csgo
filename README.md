# kauz-tools-csgo

Practice setup for CS2 built purely from console configs — no custom maps, no plugins, no server.

## Install

**Windows:** unzip the release, run `install.bat`. Rerun it with a newer zip to update.
If CS2 isn't found automatically, it asks for the path to `...\game\csgo\cfg`.

**Linux:** `./gen.py` (Python 3.11+) installs straight into the Steam CS2 dir (override with `CS2_DIR`).

**Required:** add `+exec autoexec` to the CS2 launch options (Steam → right-click CS2 → Properties → General → Launch Options).
Without it the `kt_*` commands don't exist until you type `exec autoexec` in the console.

## Usage

From the main menu or ingame:

```
kt_set_map_de_mirage   pick the map
kt_start               load it with practice settings
kt_go_ct_1             teleport to CT spawn 1 (kt_go_t_1 for T)
kt_go_ct_random        teleport to a random CT spawn (kt_go_t_random for T)
kt_clear               remove all grenades, smokes and fires
```

Practice settings (`settings.cfg`): cheats on, no bots, endless round, no freezetime/warmup,
$65535 + buy anywhere, no per-match weapon limits, infinite ammo & utility (all nades except decoy),
grenade trajectory preview. Switch teams with the native team menu (`M`).

Spawn numbering follows the map's entity order; maps with more than 5 spawns get more `kt_go_*` commands.

## Routines

`data/routines/<name>.toml` becomes `kt_set_routine_<name>` (then `kt_start`): a list of positions across maps, stepped through with
`kt_routine_next` / `kt_routine_prev` (`kt_routine_repos` repeats the current step,
`kt_routine_help` toggles red markers at the `help` points of all steps on the current map). Each step teleports you and posts its title in chat.
Copy `pos`/`ang` from `getpos` while standing (`gen.py` subtracts the 64u eye height),
or use `spawn = "ct_1"` for an exact map spawn. `lift = 20` raises the teleport if you get stuck in the floor. When the map changes,
a load step is inserted; press `kt_routine_next` again once you're ingame.

```toml
[[step]]
map = "de_ancient"
title = "red smoke"
pos = [-1188.536499, -1134.898071, 59.460468]
ang = [-0.92391, 110.507843, 0]
help = [[-911.27, -637.09, 102.27]]  # optional: world points to mark, e.g. where to aim
```

### Lineups

A step can take its position from `data/lineups/<map>.toml` instead: `lineup = "redroom_smoke4"` fills in `pos`/`ang`/`help`
and appends the throw to the title (`title` is optional then, keys set in the step win).

```toml
[redroom_smoke4]
pos = [-1231.22, -1036.58, 75.33]
ang = [-3.01, 51.31, 0]
help = [[-911.27, -637.09, 102.27]]
nade = "smoke"
throw = "jumpthrow"
```

`./extract_lineups.py <workshop id or .vpk> <map>` generates that file from a practice workshop map (built like the Astralis utility maps).
For your own spots, stand at the spot, look at the aim point and run `kt_spot` ingame, then `./spot.py <name>` prints the lineup.

<!-- custom spots disabled for now
## Custom spots

Add `data/spots/<map>.toml`, each table becomes a `kt_go_<name>` command (overrides spawns of the same name):

```toml
[a_smoke]
pos = [-300.0, -1500.0, -160.0]
ang = [-20.0, 45.0, 0.0]
```

`pos` is the feet position, as used by `setpos`.
-->

## Development

- `./gen.py` — generate and install locally
- `./gen.py --zip` — build `dist/kauz-tools-csgo.zip` (cfgs + Windows installer)
- `./extract.py` — refresh `data/spawns/` from the map VPKs after map updates;
  needs [Source2Viewer-CLI](https://github.com/ValveResourceFormat/ValveResourceFormat/releases) in `.tools/s2v/`
- `./extract_lineups.py`, `./spot.py` — see Lineups

## How it works

`kt_start` loads the map in casual mode, and CS2 runs `gamemode_casual_server.cfg` last on every map load. The installer adds `kt_onload` there,
which does nothing until `kt_start` arms it to exec `kt/settings.cfg`. All other files live in `cfg/kt/`.
