#!/usr/bin/env python3
"""Move the lineups of the map loaded in CS2 out of walls and onto the floor (data/lineups/<map>.toml).

Lineups taken from workshop maps stand where their marker is: often inside a wall or above the floor. A routine step
that teleports there gets stuck and CS2 unsticks it somewhere else. This asks the running game where a player fits:
the nearest free spot, the eye height after landing there, and aims again at the first help point. Where a teleport
only fits higher up than gen.py starts it (LIFT above the spot), the lineup gets a lift.

CS2 has to run with -condebug. Ingame: kt_set_map_<map>, kt_start, kt_remote. Then:

./fixpos.py [--check] [lineup ...]    --check only reports, without a lineup name all of the map are done
"""
import math, os, re, sys, time, tomllib

import gen

CSGO = gen.CS2 / "game/csgo"
LOG = CSGO / "console.log"
KT = gen.CFG / "kt"
STUCK = "setpos into world"
HEIGHTS = (gen.LIFT, 8, 16, 32)  # teleport heights above the spot to try
DIRS, NEAR, FAR = 16, range(1, 25), range(26, 66, 2)  # search pattern around a lineup stuck at all of them: directions, radii
BATCH, LANDS = 250, 40  # probes and teleports per cfg: 16K of commands overflow CS2's buffer on this way in
DROP, STEP = 0.6, 0.75  # seconds a teleported player gets to land before getpos, and between two teleports
LEDGE = 18  # a moved lineup landing this much higher or lower stepped off its floor: left alone and reported
TOL_XY, TOL_Z = 0.5, 2  # a lineup that lands this close to its pos is fine
ROUNDS = 4


class Game:
    """Runs cfg text in the game exactly once per call and returns what the console logged for it.
    kt_remote makes the game exec kt/remote_cmd.cfg ten times a second; the body goes through an alias that the same
    file disarms, so a second exec of it does nothing. An unknown command tells when the game has read a new
    remote_cmd.cfg: CS2 logs those (not echo), though only after everything else in the file."""

    def __init__(self):
        if not LOG.exists():
            sys.exit(f"{LOG} missing: start CS2 with -condebug")
        self.n = int(time.time()) % 100000 * 1000
        self.pos = LOG.stat().st_size
        try:
            self._step("ent_fire chicken kill")  # they wander into the probes
        except TimeoutError:
            sys.exit("no answer from CS2: load the map with kt_start and type kt_remote")

    def _new(self):
        with open(LOG, "rb") as f:
            f.seek(self.pos)
            return f.read()

    def _write(self, name, text):
        tmp = KT / f"{name}.tmp"
        tmp.write_text(text)
        os.replace(tmp, KT / f"{name}.cfg")  # atomic: the game never reads half a file

    def _step(self, cmds, timeout=3):
        """put cmds and a marker into remote_cmd.cfg and wait until the game ran them"""
        self.n += 1
        mark = f"Unknown command: kt_m{self.n}".encode()
        self.pos = LOG.stat().st_size
        self._write("remote_cmd", f"{cmds}\nkt_m{self.n}\n")
        end = time.time() + timeout
        while mark not in self._new():
            if time.time() > end:
                raise TimeoutError
            time.sleep(0.01)

    def run(self, body, done, timeout):
        """run body once, return the log since then as soon as done(log) holds"""
        self._write("remote_body", body)
        self._step('alias kt_remote_run "exec kt/remote_body"')
        self.pos = LOG.stat().st_size
        self._write("remote_cmd", "kt_remote_run\nalias kt_remote_run kt_noop\n")
        end = time.time() + timeout
        while not done(new := self._new().decode(errors="replace")):
            if time.time() > end or "Command buffer full" in new:
                self._write("remote_cmd", "")
                sys.exit(f"CS2 stopped answering (dead, noclip on, or a map change?). Last lines:\n{new[-400:]}")
            time.sleep(0.01)
        self._write("remote_cmd", "")
        return new

    def close(self):
        self._write("remote_cmd", "ent_fire kt_remote kill")
        time.sleep(0.3)
        self._write("remote_cmd", "")

    def noclip_off(self):
        """the probes toggle noclip twice and expect it off in between"""
        log = self.run("noclip;noclip\n", lambda t: t.count("noclip O") >= 2, 5)
        if log.index("noclip OFF") < log.index("noclip ON"):
            self.run("noclip\n", lambda t: "noclip OFF" in t, 5)

    def stuck(self, points):
        """is a player stuck when teleported with his feet at each of points? All in one frame per BATCH."""
        out = []
        for i in range(0, len(points), BATCH):
            chunk = points[i:i + BATCH]
            # noclip prints through the server like the stuck message does: its two lines close each probe in the log
            log = self.run("".join(f"setpos {x:.2f} {y:.2f} {z:.2f};noclip;noclip\n" for x, y, z in chunk),
                           lambda t: t.count("noclip OFF") >= len(chunk), 10)
            world = False
            for line in log.splitlines():
                if STUCK in line:
                    world = True
                elif "noclip ON" in line:
                    out.append(world)
                    world = False
        if len(out) != len(points):
            sys.exit(f"{len(points)} probes but {len(out)} answers: is noclip on?")
        return out

    def land(self, spots):
        """teleport to each (pos, ang, height above pos) the way a routine step does: [(stuck, eye position after landing)].
        One after the other, DROP seconds each: delayed player outputs feed the commands to kt_remote."""
        out = []
        for i in range(0, len(spots), LANDS):
            chunk, body = spots[i:i + LANDS], ""
            for k, (pos, ang, h) in enumerate(chunk):
                tp = gen.teleport({"pos": pos, "ang": ang}, gen.EYE - h)
                body += (f'ent_fire player AddOutput "OnUser4>kt_remote>Command>{tp}>{0.1 + k * STEP:.2f}>1"\n'
                         f'ent_fire player AddOutput "OnUser4>kt_remote>Command>getpos>{0.1 + k * STEP + DROP:.2f}>1"\n')
            log = self.run(body + "ent_fire player FireUser4\n", lambda t: len(re.findall(r"setpos \S+ \S+ \S+;setang", t)) >= len(chunk),
                           len(chunk) * STEP + 10)
            world = False
            for line in log.splitlines():
                if STUCK in line:
                    world = True
                elif m := re.search(r"setpos (\S+) (\S+) (\S+);setang", line):
                    out.append((world, tuple(float(m.group(j)) for j in (1, 2, 3))))
                    world = False
        return out


def free_spot(game, x, y, zf):
    """nearest spot around a stuck (x, y) where a player fits, None if there is none within reach"""
    dirs = [(math.cos(a), math.sin(a)) for a in (2 * math.pi * k / DIRS for k in range(DIRS))]
    for radii in (NEAR, FAR):
        radii = list(radii)
        hits = game.stuck([(x + r * dx, y + r * dy, zf) for r in radii for dx, dy in dirs])
        free = [[not hits[i * DIRS + k] for k in range(DIRS)] for i in range(len(radii))]
        for i, r in enumerate(radii[:-1]):
            ok = [k for k in range(DIRS) if free[i][k] and free[i + 1][k]]  # still free one step further out: not a crack
            if not ok:
                continue
            # middle of the widest run of free directions: straight away from the wall
            runs = []
            for k in ok:
                n = 1
                while n < DIRS and (k + n) % DIRS in ok:
                    n += 1
                runs.append((n, -k, k))
            n, _, k = max(runs)
            a = 2 * math.pi * (k + (n - 1) / 2) / DIRS
            r += (radii[i + 1] - r) / 2
            return x + r * math.cos(a), y + r * math.sin(a)
    return None


def aim(eye, target):
    dx, dy, dz = (t - e for t, e in zip(target, eye))
    return [round(-math.degrees(math.atan2(dz, math.hypot(dx, dy))), 2), round(math.degrees(math.atan2(dy, dx)), 2), 0]


def main(args):
    check = "--check" in args
    names = [a for a in args if a != "--check"]
    maps = re.findall(r"Spawn Server: (\w+)", LOG.read_text(errors="replace")) if LOG.exists() else []
    path = gen.ROOT / "data/lineups" / f"{maps[-1] if maps else '?'}.toml"
    if not path.exists():
        sys.exit(f"no {path.name}: CS2 has to be on a map with lineups (and run with -condebug)")
    text = path.read_text()
    data = tomllib.loads(text)
    names = names or [k for k, v in data.items() if "pos" in v]
    if bad := [n for n in names if "pos" not in data.get(n, {})]:
        sys.exit(f"no lineup with a pos in {path.name}: {' '.join(bad)}")
    game = Game()
    try:
        game.noclip_off()
        # self test on a map spawn: free there, stuck 40 below it
        x, y, z = next(iter(tomllib.loads((gen.ROOT / "data/spawns" / path.name).read_text()).values()))["pos"]
        if game.stuck([(x, y, z + gen.LIFT), (x, y, z - 40)]) != [False, True]:
            sys.exit("self test failed: be alive on the map, noclip off, sv_cheats 1")
        # per round: probe, search around the stuck ones, teleport like a routine step and see where the player ends up.
        # A lineup is done once it lands on its own pos; a changed one gets another round with its new pos.
        cur, lift = {n: tuple(data[n]["pos"]) for n in names}, {n: data[n].get("lift", 0) for n in names}
        todo, report = list(names), {}
        for _ in range(ROUNDS):
            hits = game.stuck([(x, y, z - gen.EYE + h) for x, y, z in (cur[n] for n in todo) for h in HEIGHTS])
            height = {}
            for i, n in enumerate(todo[:]):
                x, y, z = cur[n]
                if free := [h for h, hit in zip(HEIGHTS, hits[i * len(HEIGHTS):]) if not hit]:
                    height[n] = free[0]
                elif spot := free_spot(game, x, y, z - gen.EYE + 8):  # in a wall
                    cur[n], height[n] = (round(spot[0], 2), round(spot[1], 2), z), None
                else:
                    report[n] = "no free spot nearby: fix by hand"
                    todo.remove(n)
            again = []
            for n, (world, eye) in zip(todo, game.land([(cur[n], data[n]["ang"], height[n] or 8) for n in todo])):
                if world:  # the next round searches on from here
                    again.append(n)
                elif not height[n] or math.dist(eye[:2], cur[n][:2]) > TOL_XY or abs(eye[2] - cur[n][2]) > TOL_Z:
                    cur[n] = tuple(round(c, 2) for c in eye)  # a moved one always gets its teleport height in the next round
                    again.append(n)
                else:
                    lift[n] = height[n] - gen.LIFT
            todo = again
            if not todo:
                break
        new = {}
        for n in names:
            old = data[n]["pos"]
            moved, dz = math.dist(cur[n][:2], old[:2]), cur[n][2] - old[2]
            if n in report:
                continue
            if n in todo:
                report[n] = f"does not come to rest after {ROUNDS} rounds: fix by hand"
            elif moved and abs(dz) > LEDGE:
                report[n] = f"moved {moved:.1f} and landed {dz:+.1f}: off its floor, fix by hand"
            elif cur[n] != tuple(old) or lift[n] != data[n].get("lift", 0):
                new[n] = cur[n]
                report[n] = f"moved {moved:.1f}, z {dz:+.1f}" + f", lift {lift[n]}" * bool(lift[n])
        for n, pos in new.items():
            block = re.search(rf"^\[{re.escape(n)}\]\n.*?(?=^\[|\Z)", text, flags=re.M | re.S)
            b = re.sub(r"^pos = .*$", f"pos = [{', '.join(f'{c:.2f}' for c in pos)}]", block.group(0), flags=re.M)
            if data[n].get("help"):
                ang = aim(pos, data[n]["help"][0])
                b = re.sub(r"^ang = .*$", f"ang = [{ang[0]:.2f}, {ang[1]:.2f}, 0]", b, flags=re.M)
            b = re.sub(r"^lift = .*\n", "", b, flags=re.M)
            if lift[n]:
                b = re.sub(r"^(ang = .*\n)", rf"\1lift = {lift[n]}\n", b, flags=re.M)
            text = text[:block.start()] + b + text[block.end():]
        tomllib.loads(text)
    finally:
        game.close()
    for n in names:
        print(f"{n:28} {report.get(n, 'ok')}")
    failed = sum("hand" in r for r in report.values())
    print(f"{path.name}: {len(names)} lineups, {len(new)} {'to move' if check else 'moved'}, {failed} need a look")
    if new and not check:
        path.write_text(text)
    return 1 if failed or (check and new) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
