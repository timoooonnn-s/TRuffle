# Current Plan (Drafter)

## Milestone 1: working tool. DONE (2026-10-02)
1. [x] `truffle` single file: config, CSV loading, search, sort
2. [x] curses UI matching V-Li: title, command bar, search, table, status line
3. [x] Own key parser (PuTTY `ESC[11~`, xterm `ESC OP`, Linux console `ESC[[A`)
4. [x] Popups: ping (streamed), traceroute/tracepath (streamed), details, help
5. [x] Batch ping: thread pool (64), ESC cancels, `Ping` column, F6 sorts DOWN first
6. [x] Credential dialog, pty ssh relay, handling of auth failures and changed host keys
7. [x] Optional session log (0600, never contains the password)
8. [x] Tests: 36 (logic, ssh relay against `tests/fake_ssh.py` through a pty, tmux UI smoke test); Python 3.8/3.9/3.11/3.14
9. [x] README, `data.example.csv`, `truffle.conf.example`, `.gitignore`, `.gitattributes`

## Milestone 1b: review fixes + redesign. DONE (2026-10-02)
- [x] All 10 review findings fixed (see code-review), 38 tests
- [x] Redesign per D11; verified in 256 colours, 8 colours and ASCII
- [x] Restored `.gitignore` / `.gitattributes` (missing from the first push!)

## Milestone 1c: brainstorm picks #1 + #2. DONE (2026-10-02)
- [x] Search filters (D12), highlighted in the search line, documented in help + README
- [x] Favourites (Ctrl-F, pinned, `is:fav`) and history (`is:recent`, "Last connected" in details)
- [x] 46 tests

## Milestone 1d: transport without GitHub. DONE (2026-10-02)
- [x] `tools/make-bundle.py` -> one self-extracting text file (checksum, safe paths, keeps data.csv / truffle.conf, survives CRLF)

## Milestone 1e: review round 3 + data check, export, saved results, mouse. DONE (2026-10-02)

## Milestone 1f: review round 5 + the idle timeout. DONE (2026-10-04)
- [x] Standing rules written down: R1 (as few dependencies as possible), R2 (RHEL is the target,
      macOS is only a test bench) - see [COUNCIL.md](COUNCIL.md#standing-rules), D25
- [x] All 7 findings and 6 observations fixed (D26): the save_status crash, the unreported pane
      login failure, the lying "N marked" counter, the blocked multi-ssh, Ctrl-K/Ctrl-T on foreign
      sessions, the wrong ESC chain in help + README
- [x] Idle password timeout built (`password_timeout`, 15 min) - the Warden's condition for
      background tmux sessions is finally met
- [x] 92 tests, incl. two tmux end-to-end runs: two marked switches share one login, and a pane
      that cannot log in makes TRuffle forget the password

## Milestone 1g: paste safety, latency, failure reasons. DONE (2026-10-04)
- [x] Password lifetime: 10 h **absolute**, one variable (`PASSWORD_LIFETIME_MINUTES`), never
      touches a running session or tmux pane (D28)
- [x] Bracketed paste: a pasted newline can no longer start an ssh session (D28)
- [x] `MS` column: round-trip time, sortable slowest-first, `LC_ALL=C` (D28)
- [x] Why a ssh attempt failed: saved, survives a restart, in details + export (D28)
- [x] `TMUX-SECURITY.md` for the other engineers; switch idle timeout (900 s) recorded as fact
- [x] 102 tests
- [ ] **PuTTY: confirm bracketed paste with Ruffy** - until then it is a Tabby-only win

## Milestone 1h: review round 6. DONE (2026-10-04)
- [x] 11 findings fixed, incl. two in the paste feature built the same day: an oversized paste
      leaked 87 Enter presses, and the terminal kept our paste mode after exit (D29)
- [x] Stale latency on a down host, and 0.0 ms sorting as "never measured" - both with
      regression tests that were checked to FAIL on the old code
- [x] **Mouse support removed** (user): it cost Shift-to-select every day for a rarely used click
- [x] **Settings page on `Ctrl-G`**: session log, debug log, tmux, symbols, forget password now.
      `Ctrl-O` was built first and silently did nothing - `^O` is the tty discard character
- [x] Old-config back-compat (`OBSOLETE`) and `BIND_GRACE` deleted
- [x] 108 tests, VERSION 1.3.0-tmux

## Milestone 1i: Infoblox export + renamed to TRuffle. DONE (2026-10-05)
- [x] The column **label** decides the job: `columns = PRIMARY_DN_CODE:Name, ADDRESS:IP` makes the
      real Infoblox export work with no code change (D30). `--check` prints which column it picked
- [x] The silent "first column is the name" fallback warns now - it was making every switch in a
      subnet share one identity
- [x] **Renamed TRee-Li → TRuffle** (D31): script, config, config section, state dir, tmux session
      names, exports, bundles, tests, banner
- [x] Every trace of the real inventory removed from the repo (no company name, no real hostnames,
      no real subnets); examples use the same shape with documentation addresses
- [x] 111 tests, bundle builds and self-extracts under the new name, VERSION 1.3.1-tmux
- [ ] **On the server:** rename `tree-li.conf` → `truffle.conf` with `[truffle]`, and move
      `~/.local/state/tree-li` → `~/.local/state/truffle` (or let it start empty)
- [ ] `command -v truffle` on the target box - an npm tool of that name exists

## Milestone 2: field test (needs the user)
- [x] `./truffle --check` on the RHEL server: works (2026-10-02)
- [x] ssh into a real Extreme Fabric Engine switch: password prompt detected, logout returns to the menu
- [x] Wrong password: one attempt only, then asked again
- [x] Dead host: ssh gives up after `connect_timeout`, then back in the menu (user likes it)
- [x] Tabby: tested by the user, works (2026-10-04)
- [x] PuTTY: tested and approved by Ruffy, the second engineer (2026-10-04)
- [ ] Batch ping + ssh over all ~700 switches: still waiting for the full inventory.
      **The last open item of this milestone.**

## Ideas
All open ideas, including the parked tmux pane feature: [ideas/README.md](ideas/README.md).

## Backlog (only if asked)
- Extra CSV columns (location, ...): configure `columns`, no code change needed
- Change the username mid-session (today: restart TRuffle)
