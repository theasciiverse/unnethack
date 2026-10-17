"""Records UnNetHack's catalog preview (hub/RECORDING.md): a Valkyrie
explores the Dungeons of Doom, fights what she meets, picks things up and
goes down the stairs, then saves. Usage, from the repo root after
asciiverse/build.sh (which leaves unnethack and nhdat in out/), with pyte
installed:

    python3 asciiverse/record/unnethack.py

The game runs under `asciinema rec` in a 100x30 pseudo-terminal, by name
from out/ on PATH so the cast's header holds no local path, started in a
copy of its archive's files as av would start it, with a throwaway home
whose data folder holds the options file (unnethackrc) that picks the
character. The screen is read through pyte.

    python3 asciiverse/record/unnethack.py --play SECONDS [--bin DIR]

plays without recording, for as long as asked, with the binary (and nhdat)
from DIR: the way an AddressSanitizer build is put through its paces.
Several takes are recorded and the liveliest kept (score()).
"""
import argparse, json, os, pty, random, re, select, shutil, struct, sys
import tempfile, termios, fcntl, time
from collections import deque

import pyte

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COLS, ROWS = 100, 30
# the tty interface keeps 80x24 and is centred: column 10, row 3 on 100x30;
# its row 0 is the message line, rows 1 to 21 the map, 22 and 23 the status
X0, Y0 = (COLS - 80) // 2, (ROWS - 24) // 2
OPTIONS = """OPTIONS=role:Valkyrie,race:human,gender:female,align:neutral
OPTIONS=name:Freya,pettype:cat,!autopickup,time
"""


class Screen(pyte.Screen):
    """Answers the terminal's own questions as a terminal would: UnNetHack
    asks where the cursor is to find out whether UTF-8 works."""
    fd = None

    def write_process_input(self, data):
        if self.fd is not None:
            os.write(self.fd, data.encode())


class Session:
    def __init__(self, record=True, bindir=None, title="UnNetHack", home=None):
        self.keep_home = home is not None
        self.home = home or tempfile.mkdtemp(prefix="unnethack-rec-")
        data = os.path.join(self.home, "data", "unnethack")
        os.makedirs(data, exist_ok=True)
        if not os.path.exists(os.path.join(data, "unnethackrc")):
            with open(os.path.join(data, "unnethackrc"), "w") as f:
                f.write(OPTIONS)
        bindir = bindir or os.path.join(ROOT, "out")
        # the install folder av would start the game in
        self.install = tempfile.mkdtemp(prefix="unnethack-install-")
        shutil.copy(os.path.join(bindir, "nhdat"), self.install)
        shutil.copy(os.path.join(ROOT, "dat", "license"), self.install)
        env = {
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "HOME": self.home,
            "USER": "player",
            "LOGNAME": "player",
            "XDG_DATA_HOME": os.path.join(self.home, "data"),
            "TERM": "xterm-256color",
            "COLORTERM": "truecolor",
            "LANG": "C.UTF-8",
        }
        for k in ("ASAN_OPTIONS", "UBSAN_OPTIONS"):
            if k in os.environ:
                env[k] = os.environ[k]
        self.cast = os.path.join(ROOT, "asciiverse", "casts", "unnethack.cast")
        self.screen = Screen(COLS, ROWS)
        self.stream = pyte.ByteStream(self.screen)
        self.pid, self.fd = pty.fork()
        self.screen.fd = self.fd
        if self.pid == 0:
            os.chdir(self.install)
            if record:
                os.execvpe("asciinema", ["asciinema", "rec", "--overwrite", "-q",
                    "--idle-time-limit", "2", "--window-size", f"{COLS}x{ROWS}",
                    "--capture-env", "TERM,COLORTERM,LANG", "--title", title,
                    "--command", "unnethack", self.cast], env)
            else:
                os.execvpe("unnethack", ["unnethack"], env)
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
        self.start = time.time()

    def pump(self, t):
        end = time.time() + t
        while True:
            left = end - time.time()
            r, _, _ = select.select([self.fd], [], [], max(0.0, min(0.02, left)))
            if r:
                try:
                    data = os.read(self.fd, 65536)
                except OSError:
                    return False
                if not data:
                    return False
                self.stream.feed(data)
            if left <= 0:
                return True

    def key(self, k, wait=0.15):
        os.write(self.fd, k.encode() if isinstance(k, str) else k)
        self.pump(wait)

    def text(self):
        return "\n".join(self.screen.display)

    def wait_for(self, s, timeout=5.0):
        end = time.time() + timeout
        while time.time() < end:
            if s in self.text():
                return True
            self.pump(0.05)
        return False

    def elapsed(self):
        return time.time() - self.start

    def alive(self):
        if hasattr(self, "exit_status"):
            return False
        done, status = os.waitpid(self.pid, os.WNOHANG)
        if done:
            self.exit_status = status
        return done == 0

    def finish(self, grace=5.0):
        end = time.time() + grace
        while time.time() < end and not hasattr(self, "exit_status"):
            if not self.pump(0.1):
                break
            done, status = os.waitpid(self.pid, os.WNOHANG)
            if done:
                self.exit_status = status
                break
        if not hasattr(self, "exit_status"):
            done, status = os.waitpid(self.pid, os.WNOHANG)
            if not done:
                print("game did not exit; stopping it", file=sys.stderr)
                os.kill(self.pid, 15)
                done, status = os.waitpid(self.pid, 0)
            self.exit_status = status
        if not self.keep_home:
            shutil.rmtree(self.home, ignore_errors=True)
        shutil.rmtree(self.install, ignore_errors=True)

    # the game's own screen, without the margins
    def line(self, y):
        return self.screen.display[Y0 + y][X0:X0 + 80]

    def grid(self):
        return [self.line(1 + i) for i in range(21)]

    def status(self):
        return self.line(22) + "\n" + self.line(23)


WALLS = set("│─┌┐└┘├┤┬┴┼|-")
ITEMS = set(")[%?!/=*\"$(¶`+0")
DIRS = {(-1, 0): "h", (1, 0): "l", (0, -1): "k", (0, 1): "j",
        (-1, -1): "y", (1, -1): "u", (-1, 1): "b", (1, 1): "n"}


def find(grid, ch):
    for y, row in enumerate(grid):
        x = row.find(ch)
        if x >= 0:
            return (x, y)
    return None


def passable(ch):
    return ch != " " and ch not in WALLS


def doorway(grid, c):
    """Doors are entered and left straight, never diagonally: a cell with
    wall on both sides of it is one (the @ hides the door itself)."""
    x, y = c
    if grid[y][x] in "+▒":
        return True
    v = 0 < y < 20 and grid[y - 1][x] in WALLS and grid[y + 1][x] in WALLS
    h = 0 < x < 79 and grid[y][x - 1] in WALLS and grid[y][x + 1] in WALLS
    return v or h


def step(grid, me, want, monster, avoid, target=None):
    """A move: attack a monster next to us, else take the first step of the
    shortest path to the nearest cell want() likes; while the cell aimed
    at last time (target) is still wanted, keep going there instead of
    turning to whatever is nearest now. Returns (key, cell aimed at)."""
    for (dx, dy), k in DIRS.items():
        x, y = me[0] + dx, me[1] + dy
        if 0 <= y < 21 and 0 <= x < 80 and monster(grid[y][x], (x, y)):
            if dx and dy and (doorway(grid, me) or doorway(grid, (x, y))):
                continue
            return k, None
    if target is not None and target != me and want(target):
        aim = lambda c: c == target
    else:
        aim = want
    seen = {me: None}
    q = deque([me])
    goal = None
    while q:
        cur = q.popleft()
        if cur != me and aim(cur):
            goal = cur
            break
        for (dx, dy) in DIRS:
            x, y = cur[0] + dx, cur[1] + dy
            if not (0 <= y < 21 and 0 <= x < 80) or (x, y) in seen or (x, y) in avoid:
                continue
            if not passable(grid[y][x]):
                continue
            if dx and dy and (doorway(grid, cur) or doorway(grid, (x, y))):
                continue
            seen[(x, y)] = cur
            q.append((x, y))
    if goal is None:
        if aim is not want:
            return step(grid, me, want, monster, avoid)
        return None, None
    aimed = goal
    while seen[goal] != me:
        goal = seen[goal]
    return DIRS[(goal[0] - me[0], goal[1] - me[1])], aimed


def hp(s):
    m = re.search(r"HP:(\d+)\((\d+)\)", s.status())
    return (int(m.group(1)), int(m.group(2))) if m else (1, 1)


def play(s, seconds, log=None):
    """Plays until `seconds` have passed or the game is over. Returns what
    happened, for choosing the best take."""
    stats = {"kills": 0, "levels": 1, "picked": 0, "died": False}
    visited, bad = set(), set()
    pet = None
    known_down = target = None
    last_top = ""
    no_food = prayed = False
    stuck, descend_at = 0, 16
    last_level_time = s.elapsed()
    while s.elapsed() < seconds:
        if not s.alive():
            break
        t = s.text()
        top = s.line(0)
        if ("You kill" in top or "You destroy" in top) and top != last_top:
            stats["kills"] += 1
        last_top = top
        if "Do you want your possessions identified" in t or "DYWYPI" in t:
            stats["died"] = True
            s.key("q", 0.5)
            continue
        if "--More--" in t or "--End--" in t:
            s.key(" ", 0.25)
            continue
        if "(end)" in t or re.search(r"\(\d+ of \d+\)", t):
            s.key("\x1b", 0.25)
            continue
        if "Really attack" in t:
            s.key("n", 0.25)    # a peaceful in the way: leave it be
            continue
        if "What do you want to eat?" in t:
            m = re.search(r"eat\? \[([a-zA-Z])", t)
            s.key(m.group(1) if m else "\x1b", 0.4)
            continue
        if re.search(r"\[yn[aq]*\]|\[ynq\]|\(y/n\)", top):
            s.key("n", 0.25)
            continue
        if "?" in top and ("What do you want" in top or "In what direction" in top
                           or "Call " in top):
            s.key("\x1b", 0.25)
            continue
        grid = s.grid()
        me = find(grid, "@")
        if me is None:
            s.key("\x1b", 0.2)
            continue
        visited.add(me)
        if pet is None:
            pet = find(grid, "f")
        st = s.status()
        if "anything to eat" in top:
            no_food = True
        if ("Hungry" in st or "Weak" in st) and not no_food:
            s.key("e", 0.4)
            continue
        if ("Weak" in st or "Fainting" in st) and not prayed:
            prayed = True           # the gods feed the faithful, once
            s.key("#pray\r", 0.6)
            if "Are you sure you want to pray" in s.text():
                s.key("y", 0.6)
            continue
        cur, mx = hp(s)

        def monster(ch, c):
            return ch.isalpha() and ch not in "fI" or (ch == "f" and pet is None)

        adjacent = any(monster(grid[me[1] + dy][me[0] + dx], None)
                       for (dx, dy) in DIRS
                       if 0 <= me[1] + dy < 21 and 0 <= me[0] + dx < 80)
        if cur * 3 < mx and not adjacent:
            s.key("20s", 0.6)       # rest and search while hurt
            continue
        want_down = s.elapsed() - last_level_time > descend_at

        stairs = find(grid, ">")
        if stairs:
            known_down = stairs

        def want(c):
            ch = grid[c[1]][c[0]]
            if c in bad:
                return False
            if want_down and stairs:
                return ch == ">"
            if ch in ITEMS and c not in visited:
                return True
            if want_down and ch == ">":
                return True
            if c in visited:
                return False
            if ch in "·#.":
                for (dx, dy) in DIRS:
                    x, y = c[0] + dx, c[1] + dy
                    if 0 <= y < 21 and 0 <= x < 80 and grid[y][x] == " ":
                        return True
            return False

        if want_down and (me == known_down or "staircase down here" in s.text()):
            s.key(">", 0.8)
            stats["levels"] += 1
            visited.clear(); bad.clear()
            known_down = target = None
            pet = None
            last_level_time = s.elapsed()
            continue
        k, target = step(grid, me, want, monster, set(), target)
        if k is None or stuck >= 3:
            if want_down or k is None:
                # nothing left to see here, or stuck: search for hidden ways
                s.key("10s" if k is None and stuck < 6 else random.choice(list(DIRS.values())), 0.4)
                if k is None:
                    last_level_time -= 4
                stuck = 0 if stuck >= 6 else stuck + 1
                continue
            k = random.choice(list(DIRS.values()))
            stuck = 0
        before = grid
        s.key(k, 0.2)
        after = s.grid()
        if after == before and "You" not in s.line(0):
            stuck += 1
            if stuck >= 2:
                dx, dy = [d for d, v in DIRS.items() if v == k][0]
                bad.add((me[0] + dx, me[1] + dy))
        else:
            stuck = 0
        top = s.line(0)
        heavy = re.search(r"corpse|chest|large box|statue|boulder|ice box", top)
        if ("You see here" in top and not heavy) or "There are several" in top \
                or "Things that are here" in s.text():
            s.key(",", 0.4)
            if "Pick up what" in s.text():
                s.key(",", 0.2)
                s.key("\r", 0.4)
            stats["picked"] += 1
        if log:
            log.write(s.text() + "\n----\n")
    return stats


def score(cast, stats):
    lines = open(cast).read().splitlines()
    idle = json.loads(lines[0]).get("idle_time_limit") or 2
    length = sum(min(json.loads(l)[0], idle) for l in lines[1:])
    if length < 35 or stats["died"]:
        return -1
    return 4 * stats["kills"] + 2 * stats["picked"] + 6 * (stats["levels"] - 1)


def take():
    s = Session(record=True)
    s.wait_for("welcome", 8)
    stats = play(s, 50)
    if s.alive() and not stats["died"]:
        for _ in range(4):
            if "--More--" in s.text():
                s.key(" ", 0.3)
        s.key("S", 0.6)          # save, which ends the game quietly
        s.wait_for("Really save", 2)
        s.key("y", 1.0)
    s.finish()
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--play", type=float, help="play this many seconds, no recording")
    ap.add_argument("--bin", help="folder holding unnethack and nhdat")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--log", help="write every screen to this file")
    ap.add_argument("--home", help="keep the home folder here, to restore the save next time")
    a = ap.parse_args()
    if a.seed is not None:
        random.seed(a.seed)
    if a.play:
        if a.home:
            os.makedirs(a.home, exist_ok=True)
        s = Session(record=False, bindir=a.bin and os.path.abspath(a.bin),
                    home=a.home and os.path.abspath(a.home))
        s.wait_for("welcome", 8)
        log = open(a.log, "w") if a.log else None
        stats = play(s, a.play, log)
        print("before save:", stats, file=sys.stderr)
        print(s.text(), file=sys.stderr)
        if s.alive():
            s.key("\x1b", 0.3)
            s.key("S", 0.6)
            s.key("y", 1.5)
        s.finish()
        print("exit status", getattr(s, "exit_status", None), file=sys.stderr)
        return
    best = None
    cast = os.path.join(ROOT, "asciiverse", "casts", "unnethack.cast")
    for attempt in range(6):
        stats = take()
        sc = score(cast, stats)
        print(f"take {attempt + 1}: {stats}, score {sc}", file=sys.stderr)
        if best is None or sc > best[0]:
            best = (sc, open(cast).read())
        if sc >= 30:
            break
    with open(cast, "w") as f:
        f.write(best[1])


if __name__ == "__main__":
    main()
