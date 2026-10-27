# Changes from upstream

This is the Asciiverse packaging of UnNetHack, the NetHack variant by
Patric Mueller and contributors. Branch `asciiverse` starts from
upstream's `master` at `c4db5abfc31d4cea9e392d174c12d7f51c159359`
(2026-10-07), three build fixes after the commit that set the version
to 6.0.16 (`7618459ee`, 2026-09-16). Upstream stopped tagging after the
6.0.4 pre-releases of 2022 and marks each release by a "Bump version
number" commit instead; nixpkgs packages 6.0.16 from that commit. The
full history is here, with github.com/UnNetHack/UnNetHack as the
`upstream` remote. Everything after `c4db5abfc` is ours.

Why `master` and not 6.0.4: 6.0.16 carries four and a half years of
fixes over the last tag (418 commits, among them crash fixes such as
buying an unpaid container), and it is what upstream releases now. It
needs Lua 5.4, which 6.0.4 did not; Lua is linked in statically.

Licence: the NetHack General Public License, `dat/license` (SPDX
`NGPL`), shipped in the archive. Its section 2a asks that changed files
say so, with the date: every file we changed carries a "Changed for the
Asciiverse, 2026-10-17" notice beside the change.

Distribution packaging checked on 2026-10-17 (Repology): nixpkgs
(6.0.16; one patch, removing configure's `col` check for its macOS
sandbox), Homebrew (5.3.2 with two upstream backports, both already in
`master`), the AUR (setgid install tweaks), SlackBuilds and FreeBSD
(older versions, no source patches), Debian none. Nothing to take: the
`col` check is met by the runners and skipped in Alpine by our build
script.

## Build

- `asciiverse/build.sh` configures and builds in a copy of the tree,
  `out/build`, since UnNetHack's build writes into its source folders
  and does not build out of tree; it leaves `out/unnethack` and
  `out/nhdat`. tty and curses interfaces only (no X11, no tiles), the
  data library on, `--disable-file-areas`, `-DASCIIVERSE` for our
  changes below, `-D_GNU_SOURCE` on Linux (the curses interface includes
  `<curses.h>` before `config1.h` defines it, which Alpine's fortified
  headers do not survive). Two jobs at a time for the game, then the
  level compilers and the data library serially: their yacc steps race
  under `-j`. In Alpine, where there is no `col`, configure is told it
  exists (`HAVE_COL=yes`; it only formats the Guidebook, not built).
- `--disable-seduce`: no sex content in the Asciiverse catalog, so the
  succubus and incubus seduction scene is built out, as upstream's own
  configure option allows. A nymph still "seduces you and you start
  taking off" your armour to steal it, the classic NetHack line; left
  as it is.
- `--with-compression=no`: saved games would otherwise go through the
  `bzip2` found at build time, which a player's machine may lack.
- `asciiverse/package.sh` packs `dist/unnethack-<target>.tar.gz` from
  `asciiverse/archive/unnethack.txt` (the binary, `nhdat`, `license`);
  `.github/workflows/asciiverse-release.yml` builds static Linux in
  Alpine (x86_64, aarch64; ncurses and Lua linked in) and macOS (x86_64,
  arm64; system ncurses, Lua 5.4.8 built static in the job from lua.org,
  sha256 pinned). Upstream's own CI, `unnethack.yml`, is left as it is.
- `.gitignore`: `out/`, `dist/`, `stage/`.

## Source

- `configure`, `sys/autoconf/configure.ac`: the tty and curses check
  used bash's `[[ ... == ... ]]`, which autoconf turns into a single
  `[`; under a POSIX sh (BusyBox ash, or dash when configure does not
  re-execute itself in bash) that ran the command `yes == yes` for
  ever. Now three plain `test`s.
- Files (`sys/unix/unixmain.c`, `include/unixconf.h`, `src/files.c`):
  no setgid playground. The playground is `unnethack` under
  `$XDG_DATA_HOME` (else `~/.local/share`), made on the first run with
  its `save` folder and the empty `record`, `logfile`, `xlogfile` and
  `perm` files that the game locks by linking to them. `nhdat` and
  `license` are read from the folder the binary is in
  (`/proc/self/exe`, `_NSGetExecutablePath`, else `argv[0]`), else from
  the folder the game was started in, through the data file prefix;
  `PREFIXES_IN_USE` is turned on for that directly, since
  `NOCWD_ASSUMPTIONS`, which `decl.h` ties it to, does not build on
  Unix. `HACKDIR`, `NETHACKDIR` and `-d` still choose another
  playground. Options: without `~/.unnethackrc`, `unnethackrc` in the
  data folder is read, before upstream's `~/.nethackrc` fallback.
- Centred (`include/tcap.h`, `sys/share/ioctl.c`, `win/tty/termcap.c`,
  `win/tty/wintty.c`, `win/tty/topl.c`): on a terminal bigger than
  80x24 the tty interface keeps 80x24 and is drawn in the middle.
  `getwindowsz()` works out the offset, `cmov()` adds it to every
  absolute move, and `nocmov()`, `home()`, `tty_curs()` and the message
  line's line breaks move absolutely while there is an offset, since a
  newline, carriage return or home would land in the margin. A resize
  that only moves the screen redraws it from a cleared screen and sends
  the remembered map again (`redraw_map()`), which `docrt()` skips when
  the resize comes during its own `--More--`; the next key then shows
  everything. The curses interface, chosen with
  `OPTIONS=windowtype:curses`, lays itself out on the whole terminal as
  before.
- Saves (`include/global.h`): with no external compressor UnNetHack
  uses its own compression, and its zero-run compression (`ZEROCOMP`)
  writes saves that do not restore ("Read 0 instead of 4 bytes.",
  "Error restoring old game.", and the save is gone). With `ASCIIVERSE`
  only the run-length compression of the level map (`RLECOMP`) stays
  on. An upstream bug, to report.

## Verification

- Run under AddressSanitizer and UndefinedBehaviorSanitizer (glibc
  build in Debian trixie): scripted games of two minutes each going
  down to the third level, fighting and picking things up, saving and
  restoring across levels, starving to death through the end-of-game
  flow (record and xlogfile written), the curses interface, the help
  menu and the licence. No reports.
- `asciiverse/record/unnethack.py` plays the preview,
  `asciiverse/casts/unnethack.cast` (100x30, asciicast v3), and with
  `--play SECONDS --bin DIR [--home DIR]` puts a build through its paces
  without recording.

## Ours

- **How to play it, at the top of README.** A short note on installing and
  starting it with av, or from a release archive; the original text follows
  unchanged.
