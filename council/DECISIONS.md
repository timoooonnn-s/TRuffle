# Decisions

Each entry records who proposed it, who objected, and the outcome.

## D1: Name: **TRee-Li** (2026-10-02) - SUPERSEDED by D31
Spelled **TRee-Li**: T + R for Timmy and Ruffy. "Tree" fits a network tool, and "-Li" keeps the V-Li family name.
The command was `tree-li` (`tree` already exists on Linux, so the hyphenated name didn't collide).

*Left as it was written, because a decision log that gets rewritten is worth nothing. The project
was renamed to **TRuffle** on 2026-10-05; see [D31](#d31-renamed-to-truffle-user-2026-10-05).*

## D2: Python 3, standard library only, one executable file
- Target: RHEL with Python 3.11. Tested with Python 3.8, 3.9, 3.11 and 3.14. RHEL 9's default `python3` is 3.9, so 3.8+ compatibility is required.
- No pip, no venv. To install, copy one file.
- Rejected: Bash + whiptail (no live search table, no password injection), Go (needs libraries and a toolchain).

## D3: SSH through the system `ssh` binary in a pseudo-terminal (`pty`)
- The tool watches for the password prompt and types the password once. After that it relays I/O transparently.
- The password lives only in process memory. It never goes to disk, argv or env, and it's gone when the tool exits.
- Credentials are asked lazily, on the first `ssh` of a session. The username is pre-filled with the Linux user and can be edited.
- Leaving the password empty means the tool never types it, and ssh asks as usual (key users, testing).
- *Warden:* `passphrase` prompts (SSH key) and MFA/other prompts are **never** auto-answered.
- *Warden:* `NumberOfPasswordPrompts=1`. If a second password prompt appears, the attempt is aborted, the stored password is wiped and the user is asked again. This prevents locking out a TACACS/RADIUS account across 700 switches.

## D4: Host keys
- `StrictHostKeyChecking=accept-new`: new switches are accepted silently.
- When a stored key has changed (device replaced), TRuffle asks y/N and then runs `ssh-keygen -R`. It never removes a key silently (*Warden*).

## D5: After disconnect, return to the menu
- After a normal logout the main screen comes back immediately.
- When ssh itself fails (exit code 255: timeout, refused, unreachable), the error stays on screen until a key is pressed (*Operator*).
- `ServerAliveInterval` makes dead sessions come back on their own.

## D6: UI follows V-Li
- Same order of elements: title, command bar, search, table, status line.
- Same commands: `ssh · ping · traceroute · batch ping · details · help · exit`. Same keys.
- `traceroute` runs `traceroute` if it's installed, otherwise `tracepath` (the server only has tracepath).
- `batch ping` writes UP/DOWN into a `Ping` column, which is sortable.
- *Critic/Operator:* TRuffle parses escape sequences itself, so F1–F6 work in PuTTY's default mode too. `Tab` cycles the sort column as a backup.
- Only ASCII is used for the UI chrome. PuTTY line-drawing characters break with UTF-8, so there are none.

## D7: Data & config
- Same CSV format as V-Li. The delimiter is auto-detected. UTF-8 (including a BOM) is accepted, with a fallback to cp1252 (Excel on Windows).
- The data path is resolved relative to the config file or the script, **never the CWD** (V-Li bug).
- Shared defaults live in `truffle.conf` next to the script. Personal overrides go in `~/.config/truffle/truffle.conf`.
- Visible columns are configurable, so future CSV columns (e.g. location) can be added without code changes.

## D8: Session logging: optional, off by default
- Turned on with the `--log` flag or `session_log = yes`.
- Logs are per user, in `~/.local/state/truffle/logs`, with modes 0700/0600. Never in the shared directory (*Warden*).

## D9: Normal logout vs. failure (Operator + Critic, 2026-10-02)
- Many switches end the session with ssh exit code 255 ("closed by remote host"), so the exit code alone can't tell a normal logout from a failure.
- Rule: if the user typed anything after the login, it was a session. TRuffle returns to the menu immediately and shows "Disconnected".
- If the user never typed anything and the exit code is non-zero, it was a connection failure. TRuffle waits for a key so the error stays readable, and also shows it in the status line.

## D10: Repository hygiene (Warden)
- `data.csv` and `truffle.conf` are git-ignored. The real inventory never goes to GitHub; `data.example.csv` and `truffle.conf.example` are shipped instead.
- `.gitattributes` forces LF line endings, because the repo travels through Windows and a CRLF shebang breaks.

## D11: Visual redesign (user choices, 2026-10-02)
- **Layout:** slim top bar (brand left, user and count right), thin rules, command **tabs** (the active tab has a blue background), a `›` search prompt, an uppercase table header with its own rule, and a footer with key hints. Messages replace the hints for a few seconds.
- **Colours:** a broad range of blues (256-colour palette: 17-117). The terminal's own foreground is used for body text, so light terminal themes still work. 8-colour fallback for PuTTY's default `TERM=xterm`; attributes only without colour.
- **Popups:** full screen, same top bar and footer frame. ping/traceroute show a running / done / exit status.
- **Switch list:** `● up` / `● down` coloured dots, a `▌` selection marker, a scrollbar for long lists.
- *Critic:* Unicode only for characters in common Windows fonts, and an automatic ASCII fallback (`charset`, `--ascii`). Python's C-locale coercion reports UTF-8 even under `LANG=C`, so the manual switch is the real escape hatch.
- *Operator:* the login dialog draws its own block cursor instead of relying on the terminal cursor (PuTTY often hides that).

## D12: Search syntax, favourites, history (2026-10-02)
- Search terms: `word`, `field:value` (any CSV column or table label, `field:` = empty), `ping:up|down|wait|none`, `is:fav`, `is:recent`, and `-term` to negate. Unknown `x:y` is treated as plain text, so IPv6 addresses (`fe80::1`) keep working (*Critic*).
- The favourite key is **Ctrl-F**, not `*`: every printable key belongs to the search (*Operator*).
- Without a chosen sort column, favourites are pinned on top and `is:recent` orders newest first. Choosing a sort column (F1-F6) always wins, because otherwise "sort by Ping" would be confusing (*Operator*).
- Stored per user in `~/.local/state/truffle/{favorites,recent}`: mode 0600, atomic writes, re-read before every write (two TRuffle windows of the same user don't overwrite each other), history capped at 200. Only successful logins are recorded (*Warden*).

## D13: Dialog windows and the TRuffle palette (user request, 2026-10-02)
- First version (dark navy panel, strong grey-out, drop shadow) was rejected as too dark.
- Now: the screen behind a dialog only **fades a bit** (grey 246), there is **no shadow**, and the window is a **lighter mid-blue panel** with a thin rounded **frame** that carries the title (`╭─ Login · asked once per session ─╮`). The input fields are pale blue, and the active one is the lightest.
- The whole UI uses one blue palette with several shades (the user's choice), defined in `STYLE.md`. Light shades carry text on dark terminals; strong shades are backgrounds (tab, selection bar, panel).
- Small, obvious highlights stay bright and off-palette on purpose: the favourite star is orange (214) and ping status is green/red.
- `draw_window()` is generic, so future dialogs look the same.
- 8 colours: blue panel, cyan frame, white hint text, white/cyan input fields, background faded to bright blue.
- Rule: no third-party brand names in the project.

## D14: Sorting can be switched off (user feedback, 2026-10-02)
- Problem: once sorted, there was no way back. The list was re-sorted in place, so the CSV order was lost.
- Now: the same F-key cycles ascending ▲ → descending ▼ → off. `Tab`/`Shift-Tab` go through all columns and then "off". `ESC` with an empty search also switches sorting off. "Off" shows the CSV order again, favourites pinned on top (*Operator*).
- The loaded CSV order is kept separately (`App.loaded`), so "off" is exact, not "whatever the last sort left behind" (*Critic*).

## D15: Second review round (2026-10-02)
- **Kept on purpose (user):** `←` on "ssh" wraps around to "exit". The user sees it as a feature.
- **ESC order** is now search → batch ping → sort, so clearing a search never kills a running batch ping. The footer only offers "ESC cancels" while the search is empty, and hides the batch counter once cancelled.
- A fresh login shows up in `is:recent` at once. A ping result (single or batch) re-sorts a Ping-sorted list and updates `ping:` searches (`ping_changed()`).
- A ping closed early still counts as "up" if a reply already came back.
- Consolidated: ping states are stored as the words shown and searched (`up`/`down`/`wait`; the three translation tables are gone); stdlib `textwrap` replaces the hand-written word wrapper; the hidden search aliases (`is:favs`, `is:star`, `is:history`, ...) are gone. Only the documented `is:fav` / `is:recent` remain.

## D16: Fuzzy search and SSH check (user request, 2026-10-02)
- **Fuzzy search, fzf-style (user's choice):** plain words match when their letters appear in order within one visible column. A substring always outranks a scattered match; word starts and adjacent letters score higher. Without a sort column, the best matches come first (favourites win ties). Matched letters are underlined.
  - `'word` forces an exact match.
  - Excludes (`-word`), `field:value` and status filters stay exact. A fuzzy exclude would hide far too much (*Critic*).
- **SSH check (user's choice: separate column, inside batch ping):** TCP connect to `ssh_port` (22) and wait for the server's `SSH-` greeting. If the server waits for the client, TRuffle sends its own greeting first. Results: `open`, `closed` (refused), `no answer` (timeout, unreachable, no SSH greeting). No login, no password (*Warden*); the switch only logs a short connection.
  - Ping and SSH run as separate tasks in the same worker pool, so a host with ICMP filtered can still show `ssh open`.
  - `ssh:no` matches "no answer" but not unchecked hosts (`none`), because status filters treat `none` specially (*Critic*).
- Sorting by PING/SSH puts problems first.

## D17: Review round 3 + data check, export, saved results, mouse (2026-10-02)
- **Fixes:**
  - Single ping: a finished ping counts by its exit code, and runs with `LC_ALL=C`. On a German server " bytes from " didn't match, so every ping showed "down".
  - SSH check: accepts pre-banner lines (RFC 4253) and uses one overall deadline, including a time-limited DNS lookup.
  - The SSH port comes from `ssh -G` (`ssh_options`, `~/.ssh/config`).
  - A cancelled batch restores earlier results and doesn't block a new batch. Without `ping`, the batch checks SSH only.
  - A lone `'` or `-` while typing is ignored.
  - The state is `no-answer`, one word, so it's searchable.
  - Highlighting is skipped when lower-casing changes a cell's length. Dead `BatchCheck.hosts` removed.
- **Bundle (*Warden*):** only git-tracked files are packed. Untracked files are listed and never shipped. Without git, an allow-list is used.
- **Data check:** field-count mismatches with line numbers, duplicate names and IPs, missing or invalid IPs, leading zeros. Shown in `--check`, plus a hint at startup.
- **Export (`Ctrl-E`):** the current view with all CSV columns plus Ping/SSH and their times, to a new file (0600, UTF-8 with BOM for Excel, the list's own delimiter) in `export_dir` (default `~`).
- **Saved check results:** `~/.local/state/truffle/status`, merged per host (newest wins), restored at startup with a hint. `wait` is never saved.
- **Mouse** (stdlib curses, on by default, `mouse = no` to switch off):
  - click selects, double-click runs (300 ms window), a header click sorts, the wheel scrolls
  - switched off during ssh sessions
  - *Operator:* text selection then needs Shift; documented in the README troubleshooting table
  - wheel-down needs ncurses mouse v2 (RHEL 8+); older builds only scroll up

## D18: traceroute removed (user, 2026-10-03)
- The command, `trace_command` and the `--check` line are gone. An old `truffle.conf` that still sets `trace_command` keeps working: the option is silently ignored (`OBSOLETE`).

## D19: Slimmed down + --debug (user, 2026-10-03)
- **Removed:** Tab/Shift-Tab sorting (F-keys, ESC and header clicks cover it), `TREELI_DATA`, `--user`, and the `delimiter` / `host_column` / `name_column` settings (auto-detection covers them). Old configs that still set these keep working (`OBSOLETE`).
- **`--debug`** appends one report per login to `state_dir/debug.log` (0600): the command, the prompts seen, typed/not typed, exit code, last line, and the output before the login. Never the password or the session. Built for field problems like the Universal 4300 case.
- **Bundle:** `council/` is never shipped. It stays in this workspace only. A checkout that got it from an older bundle loses it on the next update.

## D20: SSH test removed, batch ping made quiet (user, 2026-10-03)
- The active SSH test is gone: it caused noise that the network monitoring noticed. That removes `ssh_check`, the DNS helper, `ssh -G` port detection, the `ssh_port` / `ssh_check_timeout` settings and their tests.
- The **SSH column stays**, now passive: it records the outcome of your **real** ssh attempts (`ok` / `failed`, the reason in details, saved with time). Zero extra traffic. `ssh:failed` search, sortable, exported.
- **Batch ping (ICMP only)** is rate-limited: at most `ping_rate` (20) pings started per second, replacing `ping_workers`. 700 switches take about 35 s (before: about 2 s at about 320/s). Cancel restores earlier results, including pings that were waiting for their slot.
- The removed settings are listed in `OBSOLETE`, so old config files keep working.

## D21: Process hardening + credit (2026-10-03)
- From the handover security review, the parts that apply to TRuffle as it is: **no core dumps** (`RLIMIT_CORE=0`), and on Linux **`PR_SET_DUMPABLE=0`**, so other processes of the same user can't attach or read `/proc/<pid>/mem`, where the stored password lives. Root still can. ssh and ping children are unaffected, because exec resets this.
- The **tmux pane feature is NOT built.** It's parked in `council/ideas/tmux-panes.md` with option 1, the hardening and the Warden's concern about forgotten background sessions.
- Credit **"by Timmy & Ruffy"**: small, in Steel, bottom right of the footer (when no batch progress is shown there) and on the help screen.

## D22: Review round 4 - fixes, --check as a gate, version discipline (2026-10-03)
- **Crash fix (*Architect*):** the batch-ping rate limiter could call `time.sleep()` with a negative value when a worker was descheduled between the loop condition and the argument. The `ValueError` killed the thread, printed a traceback over the curses screen and left hosts stuck in `wait`. Reproduced deterministically, now `max(0.0, ...)`.
- **`user_typed` simplified (*Critic*):** it used to be set only when a password had already been sent. If the prompt was never recognised and the user typed the password by hand, a normal logout (exit 255 on most switches) was then reported as a failure. Any keystroke now counts, which is both simpler and correct.
- **Prompt-not-recognised hint:** `SessionResult.prompt_missed` is true when a password was stored, the switch answered, and no prompt was ever matched. TRuffle now says so instead of silently doing nothing. It stays false for connection failures, where no prompt could appear. This is the Universal 4300 failure shape made visible.
- **`--check` is a gate (*Operator*):** exit 0 = fine, 1 = data warnings, 2 = cannot run. It also lists obsolete options from an old config, which were silently ignored before, and prints the state directory.
- **Version discipline (*Warden*):** `VERSION` is 1.1.0 and must be bumped per bundle. `make-bundle.py` refuses to overwrite an existing bundle with different contents (`--force` overrides), and the extractor refuses to downgrade without a confirmation. Previously every bundle was called `truffle-bundle-1.0.0.py`.
- **Help page is data (`help_sections`)**, rendered by `show_help` and checked by tests: every command must be documented and no removed feature may still be advertised. The stale "ping + SSH check" line got through exactly because nothing tested this.
- **Cleanup:** dead `delimiter` parameter on `read_table`, the double refilter in `connect()`, the defensive `getattr(args, "debug")` (the test helper now mirrors the real parser), the `--debug` help text that hardcoded the state path, and stray blank lines.
- **Session logging stays** (user's call) - it is the only feature with no demonstrated user, revisit later.

## D23: tmux panes built on the `tmux-version` branch (2026-10-03)
- Not merged. The user wants to try it before deciding; `main` is untouched.
- **Mark with `Tab`** (right-click too), `+` in the list, "N marked" in the top bar. With 2+ marked, ssh opens one tmux session with one pane per switch (max 9), all logging in at once - the user's call: a mistyped password is their problem, as when using tmux by hand.
- **Back out:** `Ctrl-b d`. **Back in:** `Ctrl-T`. Logging out of the last pane ends the session and TRuffle picks the results up by itself.
- **Handover (option 1)** with all the hardening from the idea doc: private 0700 directory, 0600 socket, kernel uid *and* pid check, one-time ticket bound to the pane tmux started, 15 s lifetime, socket deleted once the logins are out.
- **Results go through the status file, not the socket** - simpler, survives long sessions, and lets the socket close early. The DONE protocol is gone.
- *Warden:* `N tmux` in the top bar while sessions live, and they are named again on exit. `synchronize-panes` is forced off so one command can never go to every switch.
- Works on Linux (`SO_PEERCRED`) and macOS (`LOCAL_PEERCRED` / `LOCAL_PEERPID`), both verified.
- 14 security tests in `tests/test_handover.py`; 80 tests overall on Python 3.8 / 3.9 / 3.14.

## D24: tmux hardening after the first real use (2026-10-03)
User feedback: "Ctrl-T is a bit buggy" and "Ctrl-b & does not close the session for me (Swiss German layout)".
- **Ctrl-T had four faults**, all now fixed: it trusted a session list cached for up to 3 s (so it could attach to a session that had just ended), `attach_session` returned an exception object nobody looked at, a failed attach left curses and came straight back with no message, and a successful switch inside tmux said nothing at all. It now asks tmux for the live list, checks the session exists, reports every outcome, and names the sessions still running.
- **Closing without a tmux key:** `Ctrl-K` in TRuffle closes the sessions after a y/n window. Keyboard layouts make `Ctrl-b &` unreliable, and binding a tmux key ourselves would change the user's global tmux config, so the action belongs in TRuffle. The tmux status bar now advertises `exit` per pane instead of `&`.
- **Handover: one thread per connection.** The accept loop was serial with a 5 s timeout, so a single client that connected and said nothing blocked every other pane from fetching its login - measured: the second pane timed out completely. The `parent_pid()` lookup (which runs `ps` on macOS) also no longer happens while holding the lock. Single use is still exact, re-checked under the lock.
- **Session names could collide** inside one second (`truffle-HHMMSS`); `free_session_name()` now suffixes.
- **A half-built session is killed** if a `split-window` fails, instead of being left behind.
- Sessions are created with the real terminal size, not tmux's detached default of 80x24.
- **`win_text` did not exist** in the palette and only crashed when the new confirm window opened. `TestTheme` now checks every `th.<name>` in the source, the dynamically built status styles and the MONO fallback against the palette - that class of bug must not reach a user again.

## D25: Standing rules written down: dependencies and target platform (user, 2026-10-04)
The user stated two rules that had been implicit since D2. They now live in
[COUNCIL.md](COUNCIL.md#standing-rules) as **R1** and **R2**, so every future proposal is measured against them
instead of re-arguing them:
- **R1 - as few dependencies as possible.** Standard library first, then a tool already on the server, then a
  vendored file we own, then (only with a named benefit) an external package. "Easier, more secure, or another
  clear benefit" is the test; "nicer" is not. The cost side is concrete: on a locked-down RHEL box every
  `pip install` is a ticket, and TRuffle's promise is "copy one file".
- **R2 - RHEL Linux is the target, macOS is only a test bench.** Local testing happens on macOS, so macOS
  support is a convenience and never the yardstick. Platform-split code states both paths, Linux first; the
  supported Pythons are the ones RHEL ships (3.8/3.9 up, RHEL 9's `python3` is 3.9); a macOS-only feature is
  not built.

## D26: Review round 5 - crash, the unreported pane login failure, honest counters (2026-10-04)
Seven findings and six smaller observations from a full review of the `tmux-version` branch. 92 tests.
- **Crash (*Architect*):** `UserState.save_status` walked the live ping dict while a cancelled batch ping's
  worker threads were deleting hosts from that same dict (`BatchPing._restore`), so a single ping right after
  an `ESC` could raise `RuntimeError: dictionary changed size during iteration` over the curses screen. Same
  class as the D22 rate-limiter crash. Now iterates a snapshot. Reproduced deterministically and kept as a
  threaded regression test.
- **A tmux pane's login failure never reached TRuffle (*Warden*).** `ideas/tmux-panes.md` step 5 promised the
  stored password is wiped on a login failure; D23 moved results to the status file and the wipe was quietly
  lost with the DONE protocol. So one mistyped password was spent on up to 9 panes **and then kept**, costing
  another failed auth on the next single ssh - exactly the TACACS+/RADIUS lockout D3 exists to prevent.
  Panes now report it through the state directory (`authfail`, 0600), TRuffle picks it up within 3 s while the
  sessions are still running, drops the password and says so. Sub-second timestamps: a pane can fail inside
  the same second the password was typed, and a whole-second stamp looked *older* than the password it
  belonged to - found by the end-to-end test, not by reading.
- **"N marked" lied (*Operator*).** The top bar counted every mark; `ssh` and `batch ping` act only on marks
  in the current view. Mark 3, search so one stays visible, and the bar said "3 marked" while `ssh` opened a
  single session to the *selected* row, which need not be marked at all. The bar now shows what will be used:
  `1 marked (+2 hidden)`.
- **A bad IP on the selected row blocked a multi-switch ssh.** The `valid_host` gate ran before the single/
  multi decision. The marked switches are now handled first; the selected row only has to be usable when it
  is the one being connected to.
- **`Ctrl-K` / `Ctrl-T` could touch another TRuffle window's sessions (*Warden*).** The fallback to "any
  `truffle-*` session" stays - it is how an orphaned session is recovered - but both now say so and ask first.
- **Idle password timeout built (*Warden*, the condition from `ideas/tmux-panes.md` risk 5).** Background tmux
  sessions exist on this branch, so the "mandatory if" is met. `password_timeout = 15` minutes, `0` = never.
  Idle means no keypress in TRuffle; a switch session and a return from tmux both count as use, and tmux panes
  running in the background deliberately do **not**.
- **Help page and README named the wrong `ESC` chain** (the marks step was missing). D22 made the help page
  data so this drift gets caught, but the test only checked commands - it now checks the `ESC` entry itself.
- **Observations fixed:** a pane faster than tmux's pane-pid report is waited for instead of refused
  (`BIND_GRACE`, still never answering an unbound ticket); `--ascii` is passed on to panes; two exports in the
  same second no longer collide (`-2`, `-3`); `Ctrl-C` saves finished ping results instead of dropping them;
  a bare `ping:` / `ssh:` now means "not checked", consistent with an empty `location:`; and with `tmux = no`
  the refusal explains what marks still do (limit batch ping) instead of being a dead end.
- **New end-to-end tests:** two marked switches really do share one login through the handover (and no pane
  command line carries the password), and a pane that cannot log in really does make TRuffle forget it.
- **The dropped-password notice leads its line.** `connect_many`'s closing message used to overwrite it, and
  once both were in one message the right-hand truncation cut off the half that mattered. Per D22's version
  discipline, `VERSION` is now **1.2.1-tmux**.

## D27: PuTTY and Tabby field-tested (user + Ruffy, 2026-10-04)
Milestone 2's open client test is done: **Tabby** tested by the user, **PuTTY** tested and approved by Ruffy,
the second engineer. Both fine, so the D6/D11 bets (own escape-sequence parser for PuTTY's `ESC[11~` F-keys,
ASCII-only chrome, 8-colour fallback, the dialog drawing its own block cursor) hold up against real clients.
Still open: the batch ping and the ssh pass over the **full ~700-switch inventory**, which needs the inventory.

## D28: Password lifetime, bracketed paste, latency, failure reasons (user, 2026-10-04)

### Password: 10 hours, absolute, and it never touches a session
The 15-minute idle timeout from D26 was wrong for this team and is replaced. The user's input:
devices are secured, no engineer uses another's machine, and the **switches themselves drop an idle
session after 900 s** (now in [KNOWLEDGE.md](KNOWLEDGE.md) section 6). A tight timeout priced in a threat
that does not exist here.
- **`password_lifetime = 600` (10 hours), measured from when the password was TYPED**, not from the last
  keypress. Idle time was the wrong clock: a window someone pokes once a morning would keep a live
  credential alive for weeks, while an absolute lifetime always expires and costs at most one re-entry
  per day. `0` = never.
- **One variable:** `PASSWORD_LIFETIME_MINUTES` at the top of `truffle`, with the reasoning next to it, is
  the single place to change if the team argues for longer or shorter. The config option defaults to it.
- **Expiry only deletes the password inside TRuffle** (user's explicit requirement). A switch session you
  are sitting in is never interrupted - the check only runs while TRuffle has the screen - and tmux panes
  keep running and stay logged in. Nothing in the workspace is touched.
- `password_timeout` goes into `OBSOLETE`, so a config written in the last two days keeps working.
- *Warden:* accepted. With a 900 s switch timeout and per-user accounts, the residual case this covers is
  narrow (TRuffle parked inside tmux for days), and the cost is near zero. Honest limit: Python cannot wipe
  a string from memory, so this shrinks the usable window, not the theoretical one.

### Bracketed paste (idea B, built)
Terminals paste by *typing* at the application, so a copied switch name with its trailing newline arrived
as `ENTER` - which ran `ssh` on whatever row the filter happened to put first. Now TRuffle enables
bracketed paste (`ESC[?2004h`), and everything between the terminal's `ESC[200~`/`ESC[201~` markers is
treated as text: control characters are dropped, so a pasted tab cannot mark a switch and a pasted newline
cannot start a connection. Line breaks become spaces in the search (all terms must match, so a pasted list
visibly matches nothing); in the login dialog only the first line is taken, so a pasted password gets no
newline. The mode is switched off before the terminal is handed to ssh or tmux and on again afterwards.
*Critic:* timing-based paste detection was rejected - over a laggy link it misfires both ways. A terminal
that does not support the mode never sends the markers, so nothing changes there. **Open:** PuTTY support
still to be confirmed by Ruffy; until then this is a Tabby-only improvement.

### Latency (idea D, built)
`ping_once` threw its output away and kept only the exit code. It now runs with **`LC_ALL=C`** (the single
ping already did - without it, D17's German-server bug returns) and parses `time=`. The value gets its
**own 6-wide sortable `MS` column**, because the point is finding the outlier in 700 rows, which sorting
inside the PING column could never do. Sorting it puts the **slowest first**, consistent with the state
columns putting problems first; unknown values go last. Batch ping also reports the measured range.
Stated plainly in help and README: one packet is one number, **not** packet loss and not jitter - getting
loss would mean 4x the traffic and fight D20's quietness.

### Why a ssh attempt failed (idea F, built)
`ssh_reason` was an in-memory dict, filled only by `connect()`, shown only in `details`, lost on exit and
never written by panes. "failed" alone is useless in a report: `Connection timed out`, `Permission denied`
and `no matching key exchange method` are three different tickets. The reason is now saved with the result,
so it survives a restart, panes contribute theirs, `details` shows it (wrapped onto its own line rather
than clipped at the screen edge), and `Ctrl-E` exports an "SSH reason" column - so `ssh:failed` + `Ctrl-E`
produces a list someone else can act on.
- **Status file:** `host TAB kind TAB state TAB time` gains an optional **5th** detail field (the ms for a
  ping, the reason for a ssh attempt). `load_status` accepts **4 or 5**, and a result with no detail is
  still written with 4 - so an older TRuffle sharing the state directory keeps reading what it can instead
  of dropping the whole file. A second file was rejected: one file already merges by time.

### Also
- The `MS` column makes sorting `F1`-`F8`; `TestSearchSort` now derives its indices from `STATUS_KINDS`
  instead of hardcoding them, so adding a column can never again make a test silently sort the wrong one.
- **[TMUX-SECURITY.md](../TMUX-SECURITY.md)** written for the other engineers: the handover explained from
  first principles (what a Unix socket is, why `/run/user/<uid>` is private, why the kernel's peer check
  cannot be faked, why the ticket in `ps` is deliberately not the secret), the attacker table, the honest
  limits, and the fact that background sessions - bounded by the 900 s switch timeout - were always the
  bigger exposure than the password. It ships with the tool, unlike `council/`.
- `VERSION` 1.2.2-tmux. 102 tests.

## D29: Review round 6 - mouse out, settings page in, 11 findings fixed (2026-10-04)
A full review of the 695 lines added in round 5. Eleven findings, four of them bugs in code written
that same day. 108 tests.

### The two that mattered
- **An oversized paste put the newlines back (*Architect*).** `read_paste` stopped consuming at its
  cap **without draining to the `ESC[201~` end marker**, so everything past 1024 characters stayed in
  the input queue and was read as ordinary keys. Measured on a 200-line paste: **87 leaked `ENTER`
  presses**, each running ssh on the selected switch. Strictly worse than having no bracketed paste,
  because the user now trusts pasting. The cap now limits what is **kept**, never what is consumed,
  with a hard `HUGE_PASTE` stop so a terminal that never ends a paste cannot hang us.
- **The terminal kept our paste mode after exit.** `bracketed_paste(False)` existed only in the
  ssh/tmux hand-off; neither `run()` nor `main()` ever switched it off, so quitting left DECSET 2004
  enabled and later pastes in an unaware shell arrived wrapped in literal `200~`. Now switched off at
  the end of `run()` **and** in a `finally` around `curses.wrapper`, so a failed startup cannot leak it.

### Data correctness
- **Stale latency survived a host going down.** `save_status` copied `self.detail` and only overwrote
  the hosts still in `self.rtt`, so a switch that stopped answering kept yesterday's ms and showed
  `● down  1.20` after a restart - and the export said the same. One `App.save_detail()` now rebuilds
  the ping details from `self.rtt`, which removes a duplicated three-line block at the same time.
- **A 0.0 ms reading sorted as "never measured".** `sort_devices` split rows on truthiness, and `0.0`
  is falsy, so a real measurement landed with the unmeasured hosts while `draw()` still printed it.
  Now `!= ""`. *Tester:* the first regression test for this **passed on the broken code too** - with
  only one other measured host the two orders coincide. The test now puts an unmeasured host first in
  CSV order, which is what actually tells the behaviours apart. A test that cannot fail is worse than
  no test.

### Mouse support removed (user, 2026-10-04)
Reversing D17's mouse decision. It was the one feature that **made something done constantly worse in
exchange for something done rarely**: while TRuffle held the mouse, PuTTY and Tabby needed Shift to
select text, so copying an IP out of the list - the most common action in the tool - got worse, in
exchange for clicking a row instead of pressing a key that is already under your finger. Gone with it:
`mousemask`/`mouseinterval`, the `MOUSE` dict and button constants, `App.click()`, the whole `spans`
bookkeeping threaded through `draw()`, the wheel handling in `show_text`, the `mouse` option and the
README troubleshooting row that existed only to explain the damage. The user: "haven't used it that
much."

### Settings page: Ctrl-G (user request)
Every setting was judged on one question: *would you want to flip this in the middle of a day?* Five
were: **session log**, **debug log**, **tmux mode**, **screen symbols**, and "forget the password
now". Those are the settings page. Columns, ping rate, paths and the password lifetime are set once
in `truffle.conf` and stay there.
- **Session-only on purpose.** Writing them back would rewrite `truffle.conf` with configparser and
  destroy its comments, and "just for now" is the whole point of the screen. It says so on screen.
- ***Operator:* `Ctrl-G`, not `Ctrl-O`.** `Ctrl-O` was built first and silently did nothing: `^O` is
  the tty **discard** character (`VDISCARD`), which the terminal driver eats before curses sees it,
  because `cbreak()` clears `ICANON` but not `IEXTEN`. `^U`/`^W`/`^R` are `ICANON`-only, which is why
  those have always worked. Caught by driving the real UI, not by reading the code. Recorded in
  [KNOWLEDGE.md](KNOWLEDGE.md).

### Cut, and why
- **Old-config back-compat (`OBSOLETE`) deleted** (user: "No need to keep stuff for old configs").
  The tool has only ever run on one or two test machines and `truffle.conf` is git-ignored, so the
  entire population of old config files is those machines. A retired option is now a hard startup
  error that names itself, which `--check` also reports - a ten-second fix instead of a permanent
  carrying cost. **Kept** on purpose: `load_status` still accepts 4 **or** 5 fields, because that is
  tolerant parsing of files the test machines already have, not back-compat theatre.
- **`BIND_GRACE` deleted** - my own over-engineering from D26. The race it closed was theoretical
  (Python startup is ~50 ms, `bind()` lands microseconds after `tmux_run` returns), the fallback was
  already graceful, and the 2 s wait widened the window in which anything could ask while pushing
  macOS towards the client's 5 s timeout. An unbound ticket is refused at once again.
- **`parent_pid` no longer runs on every handover request:** `expected not in (pid, parent_pid(pid))`
  built the tuple eagerly, forking `ps` on macOS even when the pid already matched.

### Smaller
- `set_or_clear()` replaces four copies of "store it unless it is empty". Not used for `self.rtt`,
  where `0.0` is a real value and only `None` clears - the same trap as the sort bug.
- One `App.results()` now maps kind to dict; `column_results()` (drawing/sorting, STATUS_COLUMNS
  order) and `word_results()` (what the status file saves) derive from it, so adding a column cannot
  make `reload_status` raise. The old `status()`/`states()` pair was a mix-up waiting to happen.
- `minutes_text()`: `password_lifetime = 90` used to report "typed 2 h ago".
- The `MS` column and its header are right-aligned, so magnitudes line up without sorting.
- `VERSION` 1.3.0-tmux (mouse removed and the config contract changed - not a patch release).

## D30: The column label decides the job (user's Infoblox export, 2026-10-05)
The first real inventory export arrived - an Infoblox network export - and TRuffle showed a single
column with the **subnet** address in it. Two separate causes, one of them a silent data bug:
- `columns` defaults to `Name, IP, subnet, aliases:Alias, comment`. In that export the only header
  that matched anything was `SUBNET`, so the table had one column showing the network address
  (`198.51.100.0`), not the host address (`192.0.2.98`, which sits in `ADDRESS`).
- Worse: the switch **name** fell back to `headers[0]` **silently**, which in this export is `SUBNET`.
  Two switches in one subnet therefore shared an identity - so favourites, history and the duplicate
  check were all keyed on the subnet. The export has exactly that case (`cd-34-s56-r1` and
  `cd-34-s56-r2` are both in `198.51.100.0`).

**Decision: the label in `columns` picks the column.** The column labelled `Name` is the switch name,
the one labelled `IP` is the ssh target; the old header-name search stays as the fallback. So the
user's whole setup is one config line and no code change:

```ini
columns = PRIMARY_DN_CODE:Name, ADDRESS:IP
```

- *Architect:* this reuses something that already exists instead of adding an option. **D19 removed
  `name_column` / `host_column`** on the grounds that auto-detection covered them; this export proves
  it does not, but re-adding two options would reverse D19 for a case the labels already express.
- *Critic:* the label must win over a same-named header, otherwise you could never point TRuffle at a
  different column in a list that happens to have its own `Name`. Tested.
- *Operator:* the silent fallback is the real fault. It now **warns and names the fix**
  (`no 'Name' column: using 'SUBNET' as the switch name - set it with columns = <header>:Name`), and
  `--check` prints `switch name` and `ssh target` outright - the one thing you could not see from the
  table was which column was doing which job.
- The other twelve Infoblox columns are left in the file on purpose: they are searchable
  (`vlan_id:2301`), listed by **details**, and ready for the location and comment EAs the user says
  are coming, which then only need adding to `columns`.
- `build_devices` returns a 4th value (`picked`) so `--check` can report it. 111 tests.
- Not built, offered: a data check that the hostname matches the site pattern `xx-xx-sxx-xx`. Waiting
  for the user - it is easy to add and easy to get wrong if the pattern has exceptions.

## D31: Renamed to **TRuffle** (user, 2026-10-05)
The user's call, no debate needed. **TRee-Li → TRuffle**, and the command is now `truffle`.
The name still carries the **T** and **R** of Timmy and Ruffy that D1 was built on - and "Ruffy"
sits inside "TRuffle" - so the origin survives the rename. `CREDIT` ("by Timmy & Ruffy") is unchanged.

**What moved:**
- `tree-li` → `truffle`, `tree-li.conf` → `truffle.conf`, config section `[tree-li]` → `[truffle]`
- state and logs: `~/.local/state/tree-li` → `~/.local/state/truffle`, personal config
  `~/.config/tree-li/` → `~/.config/truffle/`
- tmux sessions `tree-li-HHMMSS` → `truffle-HHMMSS`; the handover directory prefix with them
- exports `tree-li-export-*.csv` → `truffle-export-*.csv`; bundles `truffle-bundle-<version>.py`;
  the bundle manifest `.tree-li-files` → `.truffle-files`
- `tests/test_tree_li.py` → `tests/test_truffle.py`; `tree_li_sessions()` → `truffle_sessions()`
- the palette colour **TRee Blue** → **Truffle Blue** (`STYLE.md`, and the CSS variables
  `--treeli-*` → `--truffle-*`)
- a new 5-row ASCII banner reading TRuffle, generated in the same figlet style; the README shows
  the exact same art the help screen draws, so the two cannot drift

**Deliberately NOT renamed:**
- **`V-Li`** - that is the separate, real reference tool (seismicindustries/switch-manager), not us.
- **`TREELI_DATA`** in D19 - an environment variable that was *removed*. Renaming it would make that
  decision record describe something that never existed.
- **D1 itself**, restored to what it actually said and marked superseded. A log that is rewritten to
  match the present is not a log.

**What this breaks, on purpose** (D28's reasoning: the tool has only ever run on one or two test
machines, so a loud break is cheaper than carrying compatibility):
- an existing `tree-li.conf` is not read any more - rename it to `truffle.conf` and change the
  section header to `[truffle]`. A wrong section name is a clear startup error.
- favourites, history and saved ping/SSH results live under the old state directory. Either
  `mv ~/.local/state/tree-li ~/.local/state/truffle` or let them be re-created empty.
- tmux sessions started by the old binary keep their `tree-li-` names until they end; the new one
  neither lists nor closes them. `tmux ls` and `tmux kill-session` still reach them by hand.

**Also in this round:** every trace of the user's real inventory was removed from the repository -
no company name, no real hostnames, no real internal subnets. The Infoblox examples in `README.md`,
`council/` and the tests now use invented names in the same `xx-xx-sxx-xx` shape and RFC 5737
documentation addresses (`192.0.2.x`, `198.51.100.x`), so the tests still prove exactly what they did
(including two switches sharing one subnet). `data.csv` stays git-ignored.

**One thing to check before rollout (*Researcher*):** a `truffle` command already exists in the wild
(the Ethereum/Solidity development framework, installed via npm). It is very unlikely to be on a
RHEL switch-management server, but `command -v truffle` on the target box is a five-second check that
D1 explicitly did for `tree`, and is worth repeating here.

## D32: Two field bugs: cancelled ping, and a list whose columns don't fit (user, 2026-10-05)

### A cancelled ping reported the switch as DOWN
Reported from the field: pressing `ESC` while a ping ran recorded **down** although replies were
on the screen. Reproduced in one run (two replies received, verdict `down`).
Cause: `ESC` makes `show_text` call `ProcStream.stop()`, which SIGTERMs ping, so `returncode` is
`-15` and `stream.done` becomes true. The `stream.done` branch then decided by exit code and the
"a reply already came back" rule from **D15** - which sat in the `elif` below it - was never reached.

While reproducing it, a **second, older bug** in the same test surfaced: a router answering
*Destination Net Unreachable* makes ping print `76 bytes from <router>: ...`, so the `" bytes from "`
test used since D17 read an ICMP **error** as a successful reply. On macOS that ping even exits **0**,
so neither the text nor the exit code is proof. An unreachable host was reported **up**.

**Decision: the parsed round-trip time is the only proof of a reply.** Only a real echo reply carries
`time=`, which `parse_rtt` already reads (and `LC_ALL=C` already guarantees). New pure function
`ping_verdict(ms, done, killed, started)`:
- a time -> **up**, whatever the exit code says (so a cancelled-but-answered ping is up, and `0.0 ms`
  counts - it is a measurement, not a missing value);
- no time, and the ping **ran to the end by itself** -> **down**;
- anything else - cancelled before a reply, or ping could not start at all -> **no verdict**, and the
  previous result is left untouched. "ping is not installed" is not a statement about a switch.
- `ProcStream` gained `killed` (we signalled it) and `started` (it never ran), because the exit code
  alone cannot distinguish those.
- `ping_once` now returns **the ms or None** instead of `(bool, ms)` - the two were redundant, and the
  bool was the thing that was wrong. Batch ping follows the same rule, which also fixes the
  unreachable-host-reported-up case there.
- *Tester:* all four single-ping outcomes plus the ICMP-error text are tested, and the tests were
  checked to fail against the old logic.

### A list whose columns don't fit showed only subnets
Also reported: with the real Infoblox export the table showed **only** network addresses, and in
another attempt the NAME column was recognised but **empty**. Two different causes, both now handled
rather than guessed at:
- **Only one configured column existed.** The default `columns` line matched just `subnet` in that
  export, so the table was one column of *network* addresses. Fewer than two resolved columns now
  falls back to the switch **name and its address** with a warning, because a table that cannot show
  what you connect to is not worth drawing. *Critic:* this does override an explicit one-column
  `columns` line; accepted, because the warning says so and a deliberate single-column table is not a
  real use case.
- **Rows with an empty name column.** `d.name` falls back to the IP, but the NAME *cell* comes from
  `columns`, so the row looked half-broken with nothing explaining it. `data_issues` now reports
  "N row(s) have nothing in the name column 'X' (lines ...)".
- **`--check` now prints `headers found` and the first switch's resolved name and ssh target.** The
  whole confusion existed because that mapping was invisible; one command now answers it.
- Deliberately **not** done: adding `primary_dn_code` to the header auto-detection. It would make this
  one vendor's export work with no config, but the cause of the user's report is not yet confirmed and
  a vendor field name in a generic tool is a poor trade on a guess. Offered if they want it.

`VERSION` 1.3.2-tmux. 120 tests.

## D33: The empty NAME column was a renamed header (user's server, 2026-10-05)
`truffle --check` on the real 843-switch export answered D32's open question in one command:

```
headers found: SUBNET, MASK, VLAN_ID, PRIMARY_DN_CODE, CREATION_DATE, Default-GW, Name,
               WINS-Server, BootP_NextServer, BootP_BootFile, MAC_ADDRESS, RFC_MAC_ADDRESS, IP
first switch : name ''  ssh to '...'
```

Two headers had been renamed in the CSV: `ADDRESS` -> `IP` (correct, and it worked) and
**`Name-Server` -> `Name`** (wrong). `Name-Server` is Infoblox's DNS-name-server field and is empty in
this export; the hostname only ever lives in `PRIMARY_DN_CODE`. So `Name` resolved perfectly and was
empty for all 843 rows, and every switch fell back to its IP. Nothing was broken in TRuffle.

- **The diagnostics from D32 did their job** - `headers found`, `first switch : name ''` and the
  nameless-rows warning together made it obvious. Worth noting as evidence that spending code on
  *making a failure legible* beats spending it on guessing.
- **But "it is empty" was not enough.** The warning now names the likely column: *"Columns that do have
  a value here: PRIMARY_DN_CODE. Point 'Name' at the right one: columns = PRIMARY_DN_CODE:Name"*.
  Candidates are the headers that are filled in, contain no space and are not IP-like, so the mask, the
  VLAN and the creation date are not offered. That turns a round trip into a copy-paste.
- **Standing rule (*Operator*, now in [KNOWLEDGE.md](KNOWLEDGE.md)): do not rename headers in the
  export.** It is regenerated from Infoblox each time, so every rename is manual work that must be
  repeated and can be got wrong - as it was. The mapping belongs in `columns`, in one place, where
  `--check` prints it.
- **The default `columns` line was left alone.** Pointing it at Infoblox headers would make
  `data.example.csv` - a hand-written example in the generic shape - stop matching its own tool, so the
  site-specific mapping stays a config file (D7's design). Offered to the user as an alternative, with
  the example file updated to match, if they would rather have zero config per machine.

`VERSION` 1.3.3-tmux. 121 tests.

## D34: Patterns, OR in the search, and marks that survive a search (user, 2026-10-05)
Three things asked for while working the real 843-switch list. All three built.

### Patterns: `*` and `?`
A word containing `*` or `?` is a shell-style pattern matched against a **whole** visible column.
Whole-value matching is the point: the site scheme is `xx-xx-sxx-ROLE`, and `*-l1` finds
`ab-12-s34-l1` while **not** matching `ab-12-s34-l11` - something neither fuzzy nor substring
matching can do. `??-??-s??-w3` checks the whole pattern. Patterns work in `field:value` too
(`name:*-l1`).
- **Names are FQDNs, so the part before the first dot is tried as well.** Without that, every role
  filter would have to be written `*-l1.*`. Addresses are deliberately *not* split that way, or
  `19?` would match `192.0.2.98` through its leading octet - tested.
- *Honest correction:* the first prototype shown to the user claimed `*-l1*` excludes `l11`. It does
  not - the trailing `*` swallows `1.example.net`. The annotation was wrong, the output in the same
  message already showed `l11` in the result, and it was only caught when the test was written.
  Patterns are documented with the short form `*-l1`, and a test asserts that `*-l1*` *does* catch
  `l11` so the documentation cannot drift back into the wrong claim.
- No highlighting for pattern matches (the underline stays a fuzzy-match feature); a pattern match
  is all-or-nothing, so there is nothing partial to point at.

### OR inside one term: `a|b`
The user would have written `w3 w4` and expected "either". **Space has to stay AND** - it is what
makes narrowing an 843-row list work (`ab-* s34 -ping:down`) - so OR is written inside a single
term: `w3|w4`, `*-w3|*-w4`, `ping:up|wait`.
- An alternative with no `field:` prefix **inherits the first one's**, so `ping:up|wait` means
  up-or-wait and not "ping:up, or the word wait somewhere". Same for `name:*-w4|*-l1`.
- A negated group excludes every alternative: `-*-w3|*-w4` = NOT (w3 OR w4).
- Excluded plain words stay exact (D16 still holds); a *pattern* stays a pattern even when negated,
  because it is already precise.
- With several fuzzy alternatives the best-scoring one supplies the ranking and the underline.
- Half-typed terms (`|`, `w3|`, `|w3`, `'`, `-`) filter nothing, so the list does not flash empty
  while typing.

### Marks survive a new search (*reverses part of D26*)
"Search, select two, search again, select two more - I want to connect to four."
`marked_devices()` filtered by the current view, so only the visible marks were used. It now returns
**every** marked switch, in the order you marked them, and `self.marked` became an ordered dict
because that order decides the pane order.
- **This supersedes D26's "N marked (+N hidden)" counter.** That fix made the *counter* honest about
  the behaviour; the user's report says the *behaviour* was wrong. With nothing excluded any more the
  counter is just "4 marked", and `marked_label()` is deleted along with its test. Worth recording:
  the review finding was right that the two disagreed, and wrong about which one to change.
- **`is:marked`** added, because a selection you cannot see is a selection you cannot trust - it is
  the way to review what you have collected across several searches.
- `ESC` (empty search) still clears the marks; `batch ping` still prefers the marks when there are
  any, and now means all of them.

`VERSION` 1.4.0-tmux (new search syntax and a changed selection behaviour). 127 tests.

## D35: ping and batch ping merged, CSV export removed (user, 2026-10-05)

### One ping command
`batch ping` is gone from the command bar. **`ping`** now does the obvious thing:
- **nothing marked** -> `ping -c 4` on the selected switch, live output, as before;
- **2 or more marked** -> all of them at once, no live output, straight into the PING / MS columns.

The user's framing, which settled the design: *"It's just to check if the connection to one or
multiple devices fails, to check if they actually still are reachable."* So the sweep follows the
**marks**, and the old "ping every switch in the current filtered list" is gone with it - watching the
whole fleet is a different tool's job and never was TRuffle's.
- *Rejected after the user corrected me:* a `Ctrl-A` "mark everything in this search" key. I added it
  on the assumption that a 843-switch sweep still had to be reachable in two keystrokes. It does not,
  so the key was removed again. Noted because it is the second time an assumption about scale, not a
  request, drove a feature.
- **ESC order changed: search -> running ping -> marks -> sort.** With marks now required for a sweep,
  the marks are *always* set while one runs, so clearing them first made the footer's "ESC cancels"
  a promise that took two presses to keep - reproduced live, the sweep sat at 0% while the message
  said "Marks cleared". The cancel branch also tests `not cancelled`, matching the footer: workers can
  sit in an in-flight ping for `ping_timeout + 5` seconds after a cancel, and ESC must not be stuck on
  that branch meanwhile.

### CSV export removed
`Ctrl-E`, `export_csv()`, `free_path()`, `App.export()`, the `export_dir` option, the README section
and the tests are gone. Not needed.
- The help page test now refuses to let "batch ping", "ctrl-e" or "export" reappear in the help, the
  same guard D22 added after a stale "ping + SSH check" line survived a removal.
- *Consequence worth recording:* the persisted ssh failure reason (D32) was justified largely by
  "search `ssh:failed`, press `Ctrl-E`, hand someone the list with reasons". It now only shows one
  switch at a time in **details**. Still useful, but narrower than what it was built for - raised with
  the user rather than silently kept.

`VERSION` 1.5.0-tmux (a command removed and another's behaviour changed). 124 tests.

## D36: MS column, rate limiting and other leftovers removed (user, 2026-10-05)
Review round 7, after D35 narrowed ping to "do these switches still answer".

### The MS column is gone
With ping defined as a reachability check and fleet watching handed to another tool, a latency column
had no job left. Removed: the column, `App.rtt`, `format_rtt()`, `parse_float()`, the round-trip detail
in the status file, `App.save_detail()`, and the numeric branches in `draw()` and `sort_devices()`.
- **`parse_rtt` was NOT removed** - it is load-bearing. The `time=` field is still the only proof that a
  real echo reply came back (D32: a router's *Destination Net Unreachable* also prints "bytes from" and
  on macOS exits 0). It is now `ping_replied(text) -> bool`, which is all anyone needed, and
  `ping_verdict` takes that bool instead of a number.
- `ping_once` returns a plain bool again. It returned the ms and every caller only tested
  `is None` - the exact "value nobody reads" that round 6 flagged elsewhere.
- With no numeric column, `STATUS_COLUMNS` loses its `numeric` flag, `STATE_KINDS` collapses into
  `STATUS_KINDS`, and `word_results()` collapses into `results()`.

### Rate limiting removed (finding 3)
`ping_rate`, the rate-limit sleep loop and the worker-pool sizing derived from it existed to keep a
700-switch sweep quiet (D20). The sweep is now the handful you marked, so there was nothing to spread
out - 9 hosts at 20/s was 0.45 s of pointless spacing, and the "about N s" estimate was always 1.
One thread per host (capped at 16), and the estimate is gone from the message.
- The cancel check moved to **after** the ping and under the lock, so a ping already in flight restores
  the previous result instead of overwriting it. The test now uses a slow fake ping so it actually
  exercises that, which the old timing-based test no longer could.

### Fixes
- **ping decided on raw marks, ssh on resolved ones** (finding 2). Both now use the marks that resolve
  to a switch with a usable address, so a mark left over from a switch that has left the list cannot
  send a single ping down the several-at-once path. `start_batch(devices)` takes the resolved list
  instead of re-deriving it.
- **`Tab` now refilters when the query contains `is:marked`** (finding 5). The list *is* the marks
  there, so an unmarked row has to leave it; the next row slides up under the cursor, which is what you
  want when pruning a selection. Outside such a search nothing changes.
- **The ssh failure reason stays persisted** (finding 6). The export it was partly built for is gone,
  but surviving a restart is the whole point of the passive SSH column, and tmux panes still report
  their reason that way. What *was* removed is the ms half of the detail plumbing, so the 5th status
  field now carries one thing only.

### Process note, worth more than the code
The crash this round was mine and the **119 tests did not catch it**. My edit helper is all-or-nothing:
one batch aborted on its last block, so two fixes were silently never written while a third was - and
`execute()` called `start_batch()` with the wrong arity. Nothing failed, because no test can reach
`execute()` without curses. Only driving the real UI found it.
Two lessons: a "FAIL: 0 occurrences" line means *the whole batch was discarded*, and the UI path has no
automated coverage below the tmux end-to-end tests. The end-to-end run is the only thing standing
between `execute()` and a traceback over the user's screen.

`VERSION` 1.6.0-tmux. 119 tests.

## D37: A ping line left behind in the switch list (user, 2026-10-05)
Reported: cancelling a single-switch ping after ~3 replies leaves a line of the ping output stuck in
the switch list.

**Not reproducible here.** Six variations were tried - reachable and unreachable host, 60x12 / 84x16 /
200x50, cancelling at 1.2 s and 2.6 s, closing with `ESC` and with `q` - and every screen came back
clean. Ruled out by reading the code as well: ping's output goes to a pty
(`stdout=slave, stderr=slave`) and never to the real terminal, so a stray line cannot be the ping
writing past us.

**What the evidence points at instead.** `tmux capture-pane` shows what *curses believes* the screen
is, so an artifact that survives there would be a drawing bug - and none did. An artifact only the user
sees is the terminal and curses disagreeing, which is what happens when an update is dropped or mangled
on a laggy link: curses sends only the *difference*, so it never rewrites a cell it thinks is already
correct. `Ctrl-L` is the standing cure, which fits "stuck".

**The asymmetry that makes this specific to popups.** Coming back from an ssh session force-clears
(`resume_curses` -> `sync_size` -> `scr.clear()`). Closing a full-screen view (ping / details / help)
did not - it left the next frame to the diff. So the one path with no full repaint is exactly the one
the user reported. `show_text` now ends with `scr.clear()`, doing automatically what `Ctrl-L` does by
hand. One repaint when a popup closes; nothing else changes.

**Confirmed by the user (2026-10-05):** `Ctrl-L` does clear it, on **macOS**. And the **RHEL** build -
older, still has `batch ping` - does **not** show the bug at all. So the mechanism is settled: the
terminal and curses disagree, and forcing the repaint is the cure. `show_text` now makes exactly the
call `Ctrl-L` makes, at the moment the problem happens.

**The one thing this does NOT prove.** The RHEL build differs from the current one in *two* ways at
once - older code **and** a different platform - so "RHEL is fine" does not clear the newer code. What
tips it towards the platform: almost nothing changed in the popup drawing path between those versions
(the mouse wheel branch went, that is all), while the curses libraries differ by five years -
macOS here is **ncurses 6.0 (20150808)**, RHEL 9 ships a newer 6.x.
The test that would disentangle it is free: when RHEL is finally updated, watch whether the line ever
appears there. If it does, the cause is in our code after all and the repaint is only hiding it.

**Stakes, so nobody over-invests later:** R2 - RHEL is the target, macOS is the test bench. This bug
lives only on the bench. The fix is one call and makes popup-close consistent with ssh-return, which
already cleared, so it is worth having either way.

`VERSION` 1.6.1-tmux.

## D38: Cut-down review - dead code and doubled logic out (user, 2026-10-07)
The user asked whether lines could go without losing a feature, a security fix or anything still
needed, and approved every item per category. `truffle` 3,536 -> 3,469 lines (about 2.5% of the
code), tests -18 lines. The comments were left alone on purpose (they carry the D-numbers and the
"why"); only comments that were wrong were fixed. Each cut was first applied alone to a fresh copy
and run against the whole suite.

### Dead code (removing it changes nothing)
- the `coding: utf-8` line (Python 3 reads source as UTF-8); `App.headers` / `App.delimiter`, only
  ever read by the CSV export that D35 removed; `except InterruptedError` in `_write_all`, which
  Python has not raised since 3.5 (PEP 475 retries `os.write` itself - checked with a signal);
  `tmux_run`'s `**kw`, which no caller passed; the "is now newer than the stamp" test in
  `note_auth_failure`, always true unless the clock runs backwards; a second `select-layout tiled`
  right after the loop that already tiles.
- *Researcher:* `bracketed_paste(False)` at the end of `run()` is gone. D29 put it there **and** in a
  `finally` around `curses.wrapper`; the `finally` already covers every way out, including the normal one.

### Doubled logic, now in one place
- `App.sessions` was a copy of `App.my_sessions`, pruned in the same two places. Only `my_sessions` is left.
- `run_session` re-implemented `clean_output()` to find the last line (equal on 200,000 random outputs).
- `filter_devices` built the same `exact_term(...)` call three times; the known-field and excluded-word
  branches did the same thing and are merged, branch order unchanged.
- the login dialog had four copies of `if field == 0: user ... else: pw ...`; it edits `entry[field]` now.
- `main()` hardened the process and set the locale twice (pane and normal path); once now, after `--check`.
- smaller: `show_help`'s two single-use inner helpers, the batch dedup loop (`dict.fromkeys`), the
  `kept` counter in `read_paste` (always `len(out)`), `BatchPing.done` (always the sum of `counts`),
  `ping_verdict`'s two-step "down" test, and `connect()` building the host-key reason by hand although
  `ssh_failure_reason()` returns exactly that string.
- *Warden:* `Handover.close` uses `shutil.rmtree` on its private 0700 directory instead of removing
  the socket and the directory one by one. Only our uid can write there, so the two are the same.
  The D29 paste drain and the paste reset in the login dialog are untouched.

### One behaviour change (*Critic*, accepted)
`execute()` checked the marks twice, for ping before "is a row selected?" and for ssh after it. So:
mark two switches, type a search that matches nothing, press Enter on ssh -> "No switch selected",
while ping in the same state worked. Both now use one check before the selected row is looked at,
which is what D26 meant ("the selected row only has to be usable when it is the one being connected
to"). *Tester:* new end-to-end test, checked to FAIL on the old code.

### A security line that did nothing (*Warden*)
`pane_main` set `password = None` after the login, but the same password stayed in `login` (the parsed
reply) and `answer` (the raw one). A pane waiting at "Press any key to close this pane" held it the whole
time. All three are dropped now. Same honest limit as before: Python cannot wipe the bytes.

### Same length, cleaner
`str()` conversions and a comment left over from the MS column (D36); `refilter()` / `start_batch()` use
`App.results()` and `draw()` uses `known_field()` instead of repeating them; stale comments (the "ping
rate" setting, the footer sketch, the `*-l1*` docstring form D34 found misleading); `default_user()`'s
`$USER` fallback, which `getpass.getuser()` had already tried.

### Looked at and kept
macOS paths (R2), the 4-or-5-field status lines (D29), the latin-1 CSV fallback (cp1252 cannot decode
five byte values - checked), the paste reset in the login dialog (else a pasted password outlives a
forgotten one), `attach_session`'s existence check (D24), `device_key()` (the seam between identity and
display name - D30 was an identity bug), the attribute list in `__init__`.

### Tests, tool, docs
Duplicated helpers and one duplicated session test merged, `contextlib.redirect_stdout` instead of
swapping stdout by hand, stale test names and docstrings fixed; `make-bundle.py` hashes once. README:
four lines that described removed things (mouse, ping rate, ignored old options, a garbled sentence)
now match the code. `VERSION` 1.6.2-tmux. 119 tests.
