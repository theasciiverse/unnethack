#!/bin/sh
# Builds UnNetHack's terminal game, tty and curses interfaces only, into
# out/: the binary, unnethack, and its data library, nhdat, which holds
# the help texts, the Lua scripts and the compiled levels. The compiler,
# flags and Lua come from the environment, so one script serves every
# target (see .github/workflows/release.yml):
#
#   asciiverse/build.sh                        # Debian, Ubuntu
#   LDFLAGS=-static LUA_INCLUDE=-I/usr/include/lua5.4 \
#     LUA_LIB="-L/usr/lib/lua5.4 -llua" asciiverse/build.sh   # Alpine, static
#   LUA_INCLUDE=-I$LUA/include LUA_LIB=$LUA/lib/liblua.a \
#     asciiverse/build.sh                      # macOS, Lua built static
#
# Needs a C compiler, make, flex, bison, ncurses and Lua 5.4 with its
# headers (Debian and Ubuntu: build-essential flex bison libncurses-dev
# liblua5.4-dev). configure wants col for the Guidebook, which is not
# built here, so where there is none (Alpine) it is told col exists.
#
# configure and make run in a copy of the tree, out/build, since
# UnNetHack's build writes into its source folders. ASCIIVERSE switches
# on our own changes: the playground in the player's data folder and the
# data read from beside the binary (sys/unix/unixmain.c), and the tty
# screen centred on bigger terminals. Seduction by
# succubi and incubi is left out (--disable-seduce): no sex content in
# the Asciiverse catalog. No compression (--with-compression=no): saved
# games would otherwise go through the bzip2 found at build time, which a
# player's machine may not have.
set -eu
cd "$(dirname "$0")/.."
OUT="$PWD/out"
B="$OUT/build"
rm -rf "$B" && mkdir -p "$B"
tar --exclude=./.git --exclude=./out --exclude=./dist --exclude=./stage -cf - . | (cd "$B" && tar -xf -)
cd "$B"

CFLAGS="${CFLAGS:--O2} -DASCIIVERSE"
# config1.h defines _GNU_SOURCE, but the curses interface includes
# <curses.h> first, which Alpine's fortified headers do not survive
case "$(uname -s)" in Linux) CFLAGS="$CFLAGS -D_GNU_SOURCE" ;; esac
LDFLAGS="${LDFLAGS:-}"
command -v col >/dev/null 2>&1 || export HAVE_COL=yes

set -- --disable-file-areas --enable-tty-graphics --enable-curses-graphics \
  --enable-data-librarian --disable-seduce --with-compression=no \
  --with-owner=no --with-group=no \
  CC="${CC:-cc}" CFLAGS="$CFLAGS"
[ -n "${LUA_INCLUDE:-}" ] && set -- "$@" LUA_INCLUDE="$LUA_INCLUDE"
[ -n "${LUA_LIB:-}" ] && set -- "$@" LUA_LIB="$LUA_LIB"
./configure "$@" > configure.log 2>&1 || { tail -20 configure.log; exit 1; }

# the game two jobs at a time (JOBS to change it), then the level
# compilers and the data library one at a time (their yacc steps race
# under -j); LFLAGS is what the Makefiles link with
make -j"${JOBS:-2}" unnethack LFLAGS="$LDFLAGS" > make.log 2>&1 || { tail -30 make.log; exit 1; }
make all LFLAGS="$LDFLAGS" >> make.log 2>&1 || { tail -30 make.log; exit 1; }

cp src/unnethack dat/nhdat "$OUT/"
chmod 644 "$OUT/nhdat"
echo "built unnethack"
