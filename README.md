# kauz-tools-csgo

Practice setup for CS2 built purely from console configs — no custom maps, no plugins, no server.

## Install

**Windows:** unzip the release, run `install.bat`. Rerun it with a newer zip to update.
If CS2 isn't found automatically, it asks for the path to `...\game\csgo\cfg`.

**Linux:** `./gen.py` (Python 3.11+) installs straight into the Steam CS2 dir (override with `CS2_DIR`).

Then set the CS2 launch option `+exec autoexec` (or type `exec autoexec` once per game start).

## Usage

From the main menu or ingame:

```
kt_set_map_de_mirage   pick the map
kt_start               load it with practice settings
kt_go_ct_1             teleport to CT spawn 1 (kt_go_t_1 for T)
```

Practice settings (`settings.cfg`): cheats on, no bots, endless round, no freezetime/warmup,
$65535 + buy anywhere, no per-match weapon limits, infinite ammo & utility (all nades except decoy),
grenade trajectory preview. Switch teams with the native team menu (`M`).

Spawn numbering follows the map's entity order; maps with more than 5 spawns get more `kt_go_*` commands.

## Custom spots

Add `data/spots/<map>.toml`, each table becomes a `kt_go_<name>` command (overrides spawns of the same name):

```toml
[a_smoke]
pos = [-300.0, -1500.0, -160.0]
ang = [-20.0, 45.0, 0.0]
```

Get the values ingame with `getpos`.

## Development

- `./gen.py` — generate and install locally
- `./gen.py --zip` — build `dist/kauz-tools-csgo.zip` (cfgs + Windows installer)
- `./extract.py` — refresh `data/spawns/` from the map VPKs after map updates;
  needs [Source2Viewer-CLI](https://github.com/ValveResourceFormat/ValveResourceFormat/releases) in `.tools/s2v/`

## How it works

CS2 runs `gamemode_<mode>_server.cfg` last on every map load. The installer adds `kt_onload` there,
which does nothing until `kt_start` arms it to exec `kt/settings.cfg`. All other files live in `cfg/kt/`.
