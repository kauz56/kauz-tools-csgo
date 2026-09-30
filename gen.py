#!/usr/bin/env python3
"""Generate cfg/kt/ from settings.cfg + data/spawns/<map>.toml + data/lineups/<map>.toml + data/routines/<name>.toml.

./gen.py         install into the local CS2 cfg dir
./gen.py --zip   build dist/kauz-tools-csgo.zip (Windows installer included)
"""
import math, os, random, re, shutil, sys, tempfile, tomllib
from pathlib import Path

ROOT = Path(__file__).parent
CS2 = Path(os.environ.get("CS2_DIR", Path.home() / ".local/share/Steam/steamapps/common/Counter-Strike Global Offensive"))
CFG = CS2 / "game/csgo/cfg"
NAME = "kauz-tools-csgo"
HOOK = "// kauz-tools hook: runs kt_onload (no-op unless kt_start armed it)"
# CS2 execs gamemode_<mode>_server.cfg last on every map load (see gamemodes.txt); kt_start forces casual
MODES = ["casual"]
SPOTS = 16  # kt_spot keeps this many recordings
EYE = 64  # routines use getpos coordinates (standing eye position); setpos sets the feet
# kt_routine_help markers: flat unlit world texts facing the player at the help points of a map
HELP_KV = ('"message" "X" "color" "255 0 0" "font_name" "Arial" "font_size" "80" "fullbright" "1" "enabled" "1" '
          '"reorient_mode" "1" "angles" "0 0 90" "justify_horizontal" "1" "justify_vertical" "1"')  # roll 90: upright
HELP_SCALE = 0.0002  # world_units_per_pixel per unit of distance to the step's position: same apparent size for far markers


def num(x):
    return f"{x:.10g}"


def teleport(v, eye=0):
    x, y, z = v["pos"]
    # noclip off moves a stuck player into free space
    return f'setpos {num(x)} {num(y)} {num(z - eye)}; setang {" ".join(map(num, v["ang"]))}; noclip; noclip'


def load(name):
    """spot -> setpos command"""
    spots = {}
    for kind in ("spawns",):  # ("spawns", "spots"): custom spots disabled for now, would override spawns
        f = ROOT / "data" / kind / f"{name}.toml"
        if f.exists():
            spots |= {s: teleport(v) for s, v in tomllib.loads(f.read_text()).items()}
    return spots


def shuffle(m, ss, n=64):
    """kt_go_<team>_random: no RNG in cfg, so cycle through a pre-shuffled spawn sequence."""
    rng, out = random.Random(m), ""
    for team in ("ct", "t"):
        spawns = [s for s in ss if re.fullmatch(rf"{team}_\d+", s)]
        if len(spawns) < 2:
            continue
        seq = [rng.choice(spawns)]
        while len(seq) < n or seq[-1] == seq[0]:
            seq.append(rng.choice([s for s in spawns if s != seq[-1]]))
        out += f"alias kt_go_{team}_random kt_rnd_{team}_0\n" + "".join(
            f'alias kt_rnd_{team}_{i} "kt_go_{s}; alias kt_go_{team}_random kt_rnd_{team}_{(i + 1) % len(seq)}"\n'
            for i, s in enumerate(seq))
    return out


def launch(m):
    # map name inline: an exec inside an alias runs after the rest of the line, so kt_load would still be stale
    return f"exec kt/maps/{m}; alias kt_onload kt_apply; game_type 0; game_mode 0; map {m}"


def markers(points):
    """kt_help_draw: ent_create honors origin but then drops the entity to the floor, and ent_fire only finds
    entities that already exist, so a delayed player output moves each marker to its point."""
    out = "ent_fire kt_help* kill\n"
    for j, (pt, scale) in enumerate(points.items()):
        p = " ".join(map(num, pt))
        out += f'ent_create point_worldtext {{"targetname" "kt_help{j}" "origin" "{p}" "world_units_per_pixel" "{scale:.2g}" {HELP_KV}}}\n' + "".join(
            f'ent_fire player AddOutput "OnUser1>kt_help{j}>SetAbsOrigin>{p}>{d}>1"\n' for d in (0.2, 1.5))  # 1.5: slow spawn
    return out + "ent_fire player FireUser1\n"


def lineup(st, cache={}):
    """step with its lineup (data/lineups/<map>.toml) filled in, the throw appended to the title"""
    if "lineup" not in st:
        return st
    if st["map"] not in cache:
        cache[st["map"]] = tomllib.loads((ROOT / "data/lineups" / f"{st['map']}.toml").read_text())
    st = {"title": st["lineup"].replace("_", " ")} | cache[st["map"]][st["lineup"]] | st
    throw = ", ".join(t for t in ("crouch" * st.get("crouch", False), st.get("throw")) if t)
    return st | {"title": st["title"] + f" ({throw})" * bool(throw)}


def routine(name, steps):
    """kt_set_routine_<name>: step list with a map-load step whenever the map changes."""
    seq, cur = [], None
    for st in steps:
        if st["map"] != cur:
            cur = st["map"]
            seq.append((cur, None, f"loading {cur}, kt_routine_next when ingame"))
        if "spawn" in st:  # extracted map spawn (feet)
            action = load(cur)[st["spawn"]]
        else:  # pos/ang from getpos (eye)
            action = teleport(st, EYE - st.get("lift", 0))
        seq.append((cur, action, st["title"]))
    n, rs = len(seq), f"kt_rs_{name}_"
    out = f'alias {rs}{n} "say routine done"\nalias {rs}-1 "say routine start"\n'
    for i, (m, action, title) in enumerate(seq):
        nxt, prev = i + 1, i - 1
        if action is None:
            action, prev = launch(m), f"b{i + 1}" if i else -1
        elif seq[i - 1][1] is None and i > 1:  # back across a map boundary: reload the previous map first
            prev = f"b{i}"
            out += (f'alias {rs}b{i} "alias kt_routine_next {rs}{i - 2}; alias kt_routine_prev {rs}{i - 2}; alias kt_routine_repos {rs}b{i}; '
                    f'say loading {seq[i - 2][0]}, kt_routine_next when ingame; {launch(seq[i - 2][0])}"\n')
        elif i == 1:
            prev = -1
        out += (f'alias {rs}{i} "alias kt_routine_next {rs}{nxt}; alias kt_routine_prev {rs}{prev}; alias kt_routine_repos {rs}{i}; '
                f'say [{i + 1}/{n}] {title}; {action}"\n')  # action last: map changes may drop the rest
    return out


def build(cfg):
    """Write cfg/kt/ and return (maps, spot names)."""
    maps = sorted({f.stem for kind in ("spawns",) for f in (ROOT / "data" / kind).glob("*.toml")})  # + "spots"
    routines = {f.stem: [lineup(st) for st in tomllib.loads(f.read_text())["step"]] for f in sorted((ROOT / "data" / "routines").glob("*.toml"))}
    points = {}  # map -> {help point: size} of all routine steps on it
    for st in (st for steps in routines.values() for st in steps):
        x, y, z = st["pos"] if "pos" in st else tomllib.loads((ROOT / "data/spawns" / f"{st['map']}.toml").read_text())[st["spawn"]]["pos"]
        for pt in st.get("help", []):
            points.setdefault(st["map"], {}).setdefault(tuple(pt), max(0.01, HELP_SCALE * math.dist(pt, (x, y, z))))
    spots = {m: load(m) for m in maps}
    names = sorted({s for m in spots.values() for s in m})
    out = cfg / "kt"

    shutil.rmtree(out, ignore_errors=True)
    (out / "maps").mkdir(parents=True)
    shutil.copy(ROOT / "settings.cfg", out / "settings.cfg")
    (out / "reset.cfg").write_text("".join(f'alias kt_go_{s} "echo kt: {s} not set on this map"\n' for s in names + ["ct_random", "t_random"])
                                   + 'alias kt_help_draw "echo kt: no help on this map"\n')
    (out / "help").mkdir()
    for m, ss in spots.items():
        (out / "maps" / f"{m}.cfg").write_text(f"exec kt/reset\nalias kt_load \"map {m}\"\n" + "".join(
            f'alias kt_go_{s} "{v}"\n' for s, v in ss.items()) + shuffle(m, ss)
            + (f'alias kt_help_draw "exec kt/help/{m}"\n' if m in points else ""))
        if m in points:
            (out / "help" / f"{m}.cfg").write_text(markers(points[m]))
    # kt_spot: a grenade annotation holds stand position and view angles, a surface text the point looked at; spot.py reads the file
    for i in range(SPOTS):  # rotating slots, spot.py picks them by age
        (out / f"spot_{i}.cfg").write_text('annotation_clear\nannotation_create grenade smoke "kt"\nannotation_create text "kt" "" surface\n'
                                           f'annotation_save kt_spot_{i}\nannotation_clear\n')
    (out / "routines").mkdir()
    for name, steps in routines.items():
        (out / "routines" / f"{name}.cfg").write_text(routine(name, steps))
    (out / "init.cfg").write_text(
        'alias kt_noop ""\n'
        'alias kt_onload kt_noop\n'
        'alias kt_load "echo kt: kt_set_map_<map> first"\n'
        'alias kt_clear "ent_fire smokegrenade_projectile kill; ent_fire molotov_projectile kill; ent_fire inferno kill; '
        'ent_fire flashbang_projectile kill; ent_fire hegrenade_projectile kill; ent_fire decoy_projectile kill"\n'
        # kt_set_* only set flags; kt_start runs kt_begin (plain map load or routine start)
        'alias kt_launch "alias kt_onload kt_apply; game_type 0; game_mode 0; kt_load"\n'
        'alias kt_begin kt_launch\n'
        'alias kt_start kt_begin\n'
        'alias kt_apply "exec kt/settings; alias kt_routine_help kt_help_on"\n'  # a map load removes the markers
        'alias kt_spot kt_sp_0\n'
        + "".join(f'alias kt_sp_{i} "exec kt/spot_{i}; alias kt_spot kt_sp_{(i + 1) % SPOTS}"\n' for i in range(SPOTS))
        + "".join(f'alias kt_set_map_{m} "exec kt/maps/{m}; alias kt_begin kt_launch"\n' for m in maps)
        + 'alias kt_routine_next "echo kt: kt_set_routine_<name> first"\nalias kt_routine_prev kt_routine_next\nalias kt_routine_repos kt_routine_next\n'
        # kt_routine_help toggles the markers of the current map
        + 'alias kt_help_on "kt_help_draw; alias kt_routine_help kt_help_off"\n'
        + 'alias kt_help_off "ent_fire kt_help* kill; alias kt_routine_help kt_help_on"\n'
        + 'alias kt_routine_help kt_help_on\n'
        + "".join(f'alias kt_set_routine_{r} "exec kt/routines/{r}; alias kt_begin kt_rs_{r}_0"\n' for r in routines)
        + "exec kt/reset\n")
    return maps, names


def append_line(f, line, header=None):
    text = f.read_text() if f.exists() else (header + "\n" if header else "")
    if line not in text.splitlines():
        f.write_text(text + ("\n" if text and not text.endswith("\n") else "") + line + "\n")


def install():
    maps, names = build(CFG)
    for mode in MODES:
        append_line(CFG / f"gamemode_{mode}_server.cfg", "kt_onload", HOOK)
    append_line(CFG / "autoexec.cfg", "exec kt/init")
    print(f"{len(maps)} maps, {len(names)} spots -> {CFG / 'kt'}")


def package():
    with tempfile.TemporaryDirectory() as tmp:
        pkg = Path(tmp) / NAME
        maps, names = build(pkg / "cfg")
        for mode in MODES:  # templates; install.bat merges them into existing files
            (pkg / "cfg" / f"gamemode_{mode}_server.cfg").write_text(f"{HOOK}\nkt_onload\n")
        shutil.copy(ROOT / "windows" / "install.bat", pkg)
        shutil.copy(ROOT / "README.md", pkg)
        (ROOT / "dist").mkdir(exist_ok=True)
        zip_ = shutil.make_archive(ROOT / "dist" / NAME, "zip", tmp, NAME)
    print(f"{len(maps)} maps, {len(names)} spots -> {zip_}")


if __name__ == "__main__":
    package() if "--zip" in sys.argv[1:] else install()
