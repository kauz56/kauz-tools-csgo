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
kt_get                 print setpos/setang of where you stand and look
kt_help                list all commands, maps and routines
```

Practice settings (`settings.cfg`): cheats on, no bots, endless round, no freezetime/warmup,
$65535 + buy anywhere, no per-match weapon limits, infinite ammo & utility (all nades except decoy),
grenade trajectory preview. Switch teams with the native team menu (`M`).

Type the commands one by one: CS2 expands all aliases of a line before it runs any of it,
so `kt_set_map_de_mirage; kt_start` would still start the map picked before.

Spawn numbering follows the map's entity order; maps with more than 5 spawns get more `kt_go_*` commands.

## Routines

`kt_set_routine_<name>` (then `kt_start`) steps through a list of lineups across maps: `kt_routine_next` / `kt_routine_prev`,
`kt_routine_repos` repeats the current step. Each step teleports you onto the spot with the exact aim and says its title in chat.
When the map changes, a load step is inserted; press `kt_routine_next` again once you're ingame.

Shipped routines: one per premier map (`kt_set_routine_mirage`, ...) with every nade [csnades.gg](https://csnades.gg) recommends there,
and `all` with all of them.

Known issues:
- A local server only gets your inventory a few seconds after you join, so you spawn with the default knife and gloves until you die once.

### Writing routines

`data/routines/<name>.toml` becomes `kt_set_routine_<name>`:

```toml
recommended = "de_mirage"         # optional: csnades' recommended nades of that map first
include = ["dust2"]               # optional: then the steps of these routines

[[step]]
map = "de_mirage"
lineup = "stairs-from-t-spawn"    # pos/ang/nade/throw from a lineup, title optional

[[step]]
map = "de_ancient"
title = "red smoke"
pos = [-1188.54, -1134.90, 59.46] # getpos / kt_get while standing (eye position)
ang = [-0.92, 110.51, 0]
help = [[-911.27, -637.09, 102.27]]  # optional: world points to mark red, e.g. where to aim
lift = 20                         # optional: teleport higher if you get stuck in the floor (default 4u)
```

`spawn = "ct_1"` instead of `pos`/`ang` uses an exact map spawn.

Lineups come from `data/nades/<map>.toml` (all non-community nades of the premier maps from csnades.gg, refreshed with
`./fetch_nades.py [map ...]`; key = slug of the csnades URL, `molotov-`/`flash-`/`he-` prefix for non-smokes) and your own
`data/lineups/<map>.toml` (same keys as a step: `pos`, `ang`, optional `help`, `nade`, `throw`; wins on equal names).
The title gets nade and throw appended unless it names them.

## Development

- `./gen.py` — generate and install locally
- `./gen.py --zip` — build `dist/kauz-tools-csgo.zip` (cfgs + Windows installer)
- `./extract.py` — refresh `data/spawns/` from the map VPKs after map updates;
  needs [Source2Viewer-CLI](https://github.com/ValveResourceFormat/ValveResourceFormat/releases) in `.tools/s2v/`
- `./fetch_nades.py` — refresh `data/nades/` from csnades.gg

## How it works

`kt_start` loads the map in casual mode, and CS2 runs `gamemode_casual_server.cfg` last on every map load. The installer adds `kt_onload` there,
which does nothing until `kt_start` arms it to exec `kt/settings.cfg`. All other files live in `cfg/kt/`.
