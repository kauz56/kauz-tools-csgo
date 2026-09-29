#!/usr/bin/env python3
"""Generate cfg/kt/ from settings.cfg + data/{spawns,spots}/<map>.toml.

./gen.py         install into the local CS2 cfg dir
./gen.py --zip   build dist/kauz-tools-csgo.zip (Windows installer included)
"""
import os, shutil, sys, tempfile, tomllib
from pathlib import Path

ROOT = Path(__file__).parent
CS2 = Path(os.environ.get("CS2_DIR", Path.home() / ".local/share/Steam/steamapps/common/Counter-Strike Global Offensive"))
CFG = CS2 / "game/csgo/cfg"
NAME = "kauz-tools-csgo"
HOOK = "// kauz-tools hook: runs kt_onload (no-op unless kt_start armed it)"
# CS2 execs gamemode_<mode>_server.cfg last on every map load (see gamemodes.txt)
MODES = ["casual", "competitive", "competitive2v2", "deathmatch", "armsrace", "demolition", "custom", "training",
         "cooperative", "coopmission", "survival"]


def num(x):
    return f"{x:g}"


def load(name):
    spots = {}
    for kind in ("spawns", "spots"):  # spots override spawns
        f = ROOT / "data" / kind / f"{name}.toml"
        if f.exists():
            spots |= tomllib.loads(f.read_text())
    return spots


def build(cfg):
    """Write cfg/kt/ and return (maps, spot names)."""
    maps = sorted({f.stem for f in (ROOT / "data").glob("*/*.toml")})
    spots = {m: load(m) for m in maps}
    names = sorted({s for m in spots.values() for s in m})
    out = cfg / "kt"

    shutil.rmtree(out, ignore_errors=True)
    (out / "maps").mkdir(parents=True)
    shutil.copy(ROOT / "settings.cfg", out / "settings.cfg")
    (out / "reset.cfg").write_text("".join(f'alias kt_go_{s} "echo kt: {s} not set on this map"\n' for s in names))
    for m, ss in spots.items():
        (out / "maps" / f"{m}.cfg").write_text(f"exec kt/reset\nalias kt_load \"map {m}\"\n" + "".join(
            f'alias kt_go_{s} "setpos {" ".join(map(num, v["pos"]))}; setang {" ".join(map(num, v["ang"]))}"\n'
            for s, v in ss.items()))
    (out / "init.cfg").write_text(
        'alias kt_noop ""\n'
        'alias kt_onload kt_noop\n'
        'alias kt_load "echo kt: kt_set_map_<map> first"\n'
        'alias kt_start "alias kt_onload kt_apply; kt_load"\n'
        'alias kt_apply "exec kt/settings"\n'
        + "".join(f'alias kt_set_map_{m} "exec kt/maps/{m}"\n' for m in maps)
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
        for mode in MODES:  # templates; install.ps1 merges them into existing files
            (pkg / "cfg" / f"gamemode_{mode}_server.cfg").write_text(f"{HOOK}\nkt_onload\n")
        for f in ("install.bat", "install.ps1", "README.md"):
            shutil.copy(ROOT / f if f == "README.md" else ROOT / "windows" / f, pkg / f)
        (ROOT / "dist").mkdir(exist_ok=True)
        zip_ = shutil.make_archive(ROOT / "dist" / NAME, "zip", tmp, NAME)
    print(f"{len(maps)} maps, {len(names)} spots -> {zip_}")


if __name__ == "__main__":
    package() if "--zip" in sys.argv[1:] else install()
