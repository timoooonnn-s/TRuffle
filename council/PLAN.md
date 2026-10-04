# Current Plan (Drafter)

## Milestone 1: working tool. DONE (2026-10-02)
1. [x] `tree-li` single file: config, CSV loading, search, sort
2. [x] curses UI matching V-Li: title, command bar, search, table, status line
3. [x] Own key parser (PuTTY `ESC[11~`, xterm `ESC OP`, Linux console `ESC[[A`)
4. [x] Popups: ping (streamed), traceroute/tracepath (streamed), details, help
5. [x] Batch ping: thread pool (64), ESC cancels, `Ping` column, F6 sorts DOWN first
6. [x] Credential dialog, pty ssh relay, handling of auth failures and changed host keys
7. [x] Optional session log (0600, never contains the password)
8. [x] Tests: 36 (logic, ssh relay against `tests/fake_ssh.py` through a pty, tmux UI smoke test); Python 3.8/3.9/3.11/3.14
9. [x] README, `data.example.csv`, `tree-li.conf.example`, `.gitignore`, `.gitattributes`

## Milestone 1b: review fixes + redesign. DONE (2026-10-02)
- [x] All 10 review findings fixed (see code-review), 38 tests
- [x] Redesign per D11; verified in 256 colours, 8 colours and ASCII
- [x] Restored `.gitignore` / `.gitattributes` (missing from the first push!)

## Milestone 1c: brainstorm picks #1 + #2. DONE (2026-10-02)
- [x] Search filters (D12), highlighted in the search line, documented in help + README
- [x] Favourites (Ctrl-F, pinned, `is:fav`) and history (`is:recent`, "Last connected" in details)
- [x] 46 tests

## Milestone 1d: transport without GitHub. DONE (2026-10-02)
- [x] `tools/make-bundle.py` -> one self-extracting text file (checksum, safe paths, keeps data.csv / tree-li.conf, survives CRLF)

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
      that cannot log in makes TRee-Li forget the password

## Milestone 1g: paste safety, latency, failure reasons. DONE (2026-10-04)
- [x] Password lifetime: 10 h **absolute**, one variable (`PASSWORD_LIFETIME_MINUTES`), never
      touches a running session or tmux pane (D28)
- [x] Bracketed paste: a pasted newline can no longer start an ssh session (D28)
- [x] `MS` column: round-trip time, sortable slowest-first, `LC_ALL=C` (D28)
- [x] Why a ssh attempt failed: saved, survives a restart, in details + export (D28)
- [x] `TMUX-SECURITY.md` for the other engineers; switch idle timeout (900 s) recorded as fact
- [x] 102 tests
- [ ] **PuTTY: confirm bracketed paste with Ruffy** - until then it is a Tabby-only win

## Milestone 2: field test (needs the user)
- [x] `./tree-li --check` on the RHEL server: works (2026-10-02)
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
- Change the username mid-session (today: restart TRee-Li)
