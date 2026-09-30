#!/usr/bin/env python3
"""Print a spot saved by kt_spot (where you stood and what you looked at) as a lineup for data/lineups/<map>.toml.

./spot.py [name] [n]    n = 1 for the latest recording (default), 2 for the one before, ...
"""
import re, sys

from extract import CS2

EYE = 64  # pos is the standing eye position, like getpos


def main(name="spot", n="1"):
    files = sorted((CS2 / "game/csgo/annotations/local").glob("kt_spot*/kt_spot*.txt"), key=lambda f: f.stat().st_mtime, reverse=True)
    text = files[int(n) - 1].read_text()
    nodes = {}  # (type, subtype) -> {Position, Angles}
    for block in re.split(r"MapAnnotationNode\d+ =", text)[1:]:
        node = dict(re.findall(r"^\t\t(\w+) = (.+)$", block, flags=re.M))
        vecs = {k: [float(x) for x in node[k].strip("[] ").split(",")] for k in ("Position", "Angles")}
        nodes[node["Type"].strip('"'), node["SubType"].strip('"')] = vecs
    x, y, z = nodes["grenade", "main"]["Position"]  # feet
    pitch, yaw, _ = nodes["grenade", "aim_target"]["Angles"]
    help_ = nodes.get(("text", "main"), nodes["grenade", "aim_target"])["Position"]  # no surface hit: point on the view ray
    print(f"# {re.search(r'MapName = \"(.*)\"', text).group(1)}\n[{name}]\npos = [{x:.2f}, {y:.2f}, {z + EYE:.2f}]\n"
          f"ang = [{pitch:.2f}, {yaw:.2f}, 0]\nhelp = [[{', '.join(f'{c:.2f}' for c in help_)}]]")


if __name__ == "__main__":
    main(*sys.argv[1:3])
