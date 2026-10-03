#!/usr/bin/env python3
"""Generate cfg/kt/ from settings.cfg + data/spawns/<map>.toml + data/{nades,lineups}/<map>.toml + data/routines/<name>.toml.

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
CBUF = 32768  # CS2's command buffer: an exec'd cfg beyond this size loses its tail ("Command buffer full")
EYE = 64  # routines use getpos coordinates (standing eye position); setpos sets the feet
LIFT = 4  # and start this far above the spot: right at the floor setpos gets stuck on slopes
# help markers: flat unlit world texts facing the player at the help points of a map
HELP_KV = ('"message" "X" "color" "255 0 0" "font_name" "Arial" "font_size" "80" "fullbright" "1" "enabled" "1" '
          '"reorient_mode" "1" "angles" "0 0 90" "justify_horizontal" "1" "justify_vertical" "1"')  # roll 90: upright
HELP_SCALE = 0.0002  # world_units_per_pixel per unit of distance to the step's position: same apparent size for far markers
HELP_PULL = 0.012  # markers move this fraction of the distance along the line of sight towards the step's position
NADE_WORDS = {"molotov": ("molotov", "molly", "incendiary"), "flash": ("flash", "pop")}  # lineup nade -> words naming it in a title


def num(x):
    return f"{x:.10g}"


def teleport(v, eye=0):
    x, y, z = v["pos"]
    return f'setpos {num(x)} {num(y)} {num(z - eye)}; setang {" ".join(map(num, v["ang"]))}'


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
    for j, (pt, scale) in enumerate(points.values()):
        p = " ".join(map(num, pt))
        out += f'ent_create point_worldtext {{"targetname" "kt_help{j}" "origin" "{p}" "world_units_per_pixel" "{scale:.2g}" {HELP_KV}}}\n' + "".join(
            f'ent_fire player AddOutput "OnUser1>kt_help{j}>SetAbsOrigin>{p}>{d}>1"\n' for d in (0.2, 1.5))  # 1.5: slow spawn
    return out + "ent_fire player FireUser1\n"


def lineup(st, cache={}):
    """step with its lineup (data/nades or data/lineups/<map>.toml) filled in, nade (unless the title names it) and throw appended to the title"""
    if "lineup" not in st:
        return st
    if st["map"] not in cache:  # csnades.gg nades (fetch_nades.py), own lineups win
        cache[st["map"]] = {k: v for kind in ("nades", "lineups") if (f := ROOT / "data" / kind / f"{st['map']}.toml").exists()
                            for k, v in tomllib.loads(f.read_text()).items()}
    st = {"title": st["lineup"].replace("_", " ")} | cache[st["map"]][st["lineup"]] | st
    nade = st.get("nade", "") * all(w not in st["title"].lower() for w in NADE_WORDS.get(st.get("nade"), (st.get("nade"),)))
    throw = ", ".join(t for t in (nade, "crouch" * (st.get("crouch", False) and "crouch" not in st.get("throw", "")), st.get("throw")) if t)
    return st | {"title": st["title"] + f" ({throw})" * bool(throw)}


def expand(name, seen=()):
    """steps of a routine; include = ["a", "b"] puts the steps of those routines first (composite routines)"""
    if name in seen:
        sys.exit(f"routine include loop: {' -> '.join(seen + (name,))}")
    data = tomllib.loads((ROOT / "data/routines" / f"{name}.toml").read_text())
    return [st for inc in data.get("include", []) for st in expand(inc, seen + (name,))] + data.get("step", [])


def routine(name, steps):
    """kt_set_routine_<name>: step list with a map-load step whenever the map changes. Returns the cfg and per map a cfg with
    the teleports of its steps, exec'd by its load step: all in one cfg overflows CS2's command buffer."""
    seq, cur, part = [], None, {}  # part: load step -> number of its teleport cfg
    for st in steps:
        if st["map"] != cur:
            cur = st["map"]
            part[len(seq)] = len(part)
            seq.append((cur, None, f"load {cur} (kt_routine_next when ingame)"))
        if "spawn" in st:  # extracted map spawn (feet)
            v, eye = tomllib.loads((ROOT / "data/spawns" / f"{cur}.toml").read_text())[st["spawn"]], 0
        else:  # pos/ang from getpos (eye)
            v, eye = st, EYE - LIFT - st.get("lift", 0)
        seq.append((cur, (v, eye), st["title"]))
    n, rs = len(seq), f"kt_rs_{name}_"
    out = (f'alias {rs}{n} "say routine done"\nalias {rs}-1 "say routine start"\n')
    parts = []
    for i, (m, tp, title) in enumerate(seq):
        if tp is None:
            parts.append("")
            continue
        # {rs}<i>t: teleport and redraw the markers, a map load removes them
        parts[-1] += f'alias {rs}{i}t "{teleport(*tp)}; kt_help_draw"\n'
        seq[i] = (m, f"{rs}{i}t", title)
    for i, (m, action, title) in enumerate(seq):
        nxt, prev = i + 1, i - 1
        if action is None:
            action, prev = f"exec kt/routines/{name}_{part[i]}; {launch(m)}", f"b{i + 1}" if i else -1
            # {rs}<i>s: the load step reached back from its map, which is loaded already
            out += (f'alias {rs}{i}s "alias kt_routine_next {rs}{nxt}; alias kt_routine_prev {rs}{prev}; alias kt_routine_repos {rs}{i}s; '
                    f'say [{i + 1}/{n}] load {m}"\n')
        elif seq[i - 1][1] is None:
            prev = f"{i - 1}s"
            if i > 1:  # back from the load step: reload the previous map first
                out += (f'alias {rs}b{i} "alias kt_routine_next {rs}{i - 2}; alias kt_routine_prev {rs}{i - 2}; alias kt_routine_repos {rs}b{i}; '
                        f'echo load {seq[i - 2][0]} (kt_routine_next when ingame); exec kt/routines/{name}_{part[i - 1] - 1}; {launch(seq[i - 2][0])}"\n')
        out += (f'alias {rs}{i} "alias kt_routine_next {rs}{nxt}; alias kt_routine_prev {rs}{prev}; alias kt_routine_repos {rs}{i}; '
                f'say [{i + 1}/{n}] {title}; {action}"\n')  # action last: map changes may drop the rest
    return out, {str(k): t for k, t in enumerate(parts)}


def build(cfg):
    """Write cfg/kt/ and return (maps, spot names)."""
    maps = sorted({f.stem for kind in ("spawns",) for f in (ROOT / "data" / kind).glob("*.toml")})  # + "spots"
    routines = {f.stem: [lineup(st) for st in expand(f.stem)] for f in sorted((ROOT / "data" / "routines").glob("*.toml"))}
    points = {}  # map -> {help point: (marker position, size)} of all routine steps on it
    for st in (st for steps in routines.values() for st in steps):
        if "pos" in st:
            eye = st["pos"]
        else:
            x, y, z = tomllib.loads((ROOT / "data/spawns" / f"{st['map']}.toml").read_text())[st["spawn"]]["pos"]
            eye = (x, y, z + EYE)
        for pt in st.get("help", []):
            dist = math.dist(pt, eye)
            # help points sit on surfaces: pull the marker a bit towards the player so the wall doesn't swallow it
            k = min(0.5, max(4, HELP_PULL * dist) / dist) if dist else 0
            at = tuple(round(p + (e - p) * k, 2) for p, e in zip(pt, eye))
            points.setdefault(st["map"], {}).setdefault(tuple(pt), (at, max(0.01, HELP_SCALE * dist)))
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
    (out / "routines").mkdir()
    for name, steps in list(routines.items()):
        text, files = routine(name, steps)
        if (size := max(len(text), *map(len, files.values()))) > CBUF:
            print(f"skipping routine {name}: {size} bytes don't fit CS2's command buffer ({CBUF})")
            del routines[name]
            continue
        (out / "routines" / f"{name}.cfg").write_text(text)
        for part, t in files.items():
            (out / "routines" / f"{name}_{part}.cfg").write_text(t)
    usage = [
        "kauz-tools commands",
        "  kt_set_map_<map>        pick a map, then kt_start",
        "  kt_set_routine_<name>   pick a routine, then kt_start",
        "  kt_start                load the map with practice settings",
        "  kt_go_ct_<n>, kt_go_t_<n>, kt_go_ct_random, kt_go_t_random   teleport to a spawn",
        "  kt_clear                remove all grenades, smokes and fires",
        "  kt_routine_next / kt_routine_prev / kt_routine_repos   step through a routine",
        "  kt_get                  print setpos/setang of where you stand and look (pos/ang of a lineup)",
        "maps: " + " ".join(maps),
        "routines: " + " ".join(routines),
    ]
    (out / "usage.cfg").write_text("".join(f'echo "{line}"\n' for line in usage))
    (out / "init.cfg").write_text(
        'alias kt_help "exec kt/usage"\n'
        'alias kt_noop ""\n'
        'alias kt_onload kt_noop\n'
        'alias kt_load "echo kt: kt_set_map_<map> first"\n'
        'alias kt_clear "ent_fire smokegrenade_projectile kill; ent_fire molotov_projectile kill; ent_fire inferno kill; '
        'ent_fire flashbang_projectile kill; ent_fire hegrenade_projectile kill; ent_fire decoy_projectile kill"\n'
        # kt_set_* only set flags; kt_start runs kt_begin (plain map load or routine start)
        'alias kt_launch "alias kt_onload kt_apply; game_type 0; game_mode 0; kt_load"\n'
        'alias kt_begin kt_launch\n'
        'alias kt_start kt_begin\n'
        'alias kt_apply "exec kt/settings"\n'
        'alias kt_get getpos\n'
        + "".join(f'alias kt_set_map_{m} "exec kt/maps/{m}; alias kt_begin kt_launch"\n' for m in maps)
        + 'alias kt_routine_next "echo kt: kt_set_routine_<name> first"\nalias kt_routine_prev kt_routine_next\nalias kt_routine_repos kt_routine_next\n'
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
