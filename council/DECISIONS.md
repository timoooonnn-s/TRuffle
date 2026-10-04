# Decisions

Each entry records who proposed it, who objected, and the outcome.

## D1: Name: **TRee-Li** (2026-10-02)
Spelled **TRee-Li**: T + R for Timmy and Ruffy. "Tree" fits a network tool, and "-Li" keeps the V-Li family name.
The command is `tree-li` (`tree` already exists on Linux, so the hyphenated name doesn't collide).

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
- When a stored key has changed (device replaced), TRee-Li asks y/N and then runs `ssh-keygen -R`. It never removes a key silently (*Warden*).

## D5: After disconnect, return to the menu
- After a normal logout the main screen comes back immediately.
- When ssh itself fails (exit code 255: timeout, refused, unreachable), the error stays on screen until a key is pressed (*Operator*).
- `ServerAliveInterval` makes dead sessions come back on their own.

## D6: UI follows V-Li
- Same order of elements: title, command bar, search, table, status line.
- Same commands: `ssh · ping · traceroute · batch ping · details · help · exit`. Same keys.
- `traceroute` runs `traceroute` if it's installed, otherwise `tracepath` (the server only has tracepath).
- `batch ping` writes UP/DOWN into a `Ping` column, which is sortable.
- *Critic/Operator:* TRee-Li parses escape sequences itself, so F1–F6 work in PuTTY's default mode too. `Tab` cycles the sort column as a backup.
- Only ASCII is used for the UI chrome. PuTTY line-drawing characters break with UTF-8, so there are none.

## D7: Data & config
- Same CSV format as V-Li. The delimiter is auto-detected. UTF-8 (including a BOM) is accepted, with a fallback to cp1252 (Excel on Windows).
- The data path is resolved relative to the config file or the script, **never the CWD** (V-Li bug).
- Shared defaults live in `tree-li.conf` next to the script. Personal overrides go in `~/.config/tree-li/tree-li.conf`.
- Visible columns are configurable, so future CSV columns (e.g. location) can be added without code changes.

## D8: Session logging: optional, off by default
- Turned on with the `--log` flag or `session_log = yes`.
- Logs are per user, in `~/.local/state/tree-li/logs`, with modes 0700/0600. Never in the shared directory (*Warden*).

## D9: Normal logout vs. failure (Operator + Critic, 2026-10-02)
- Many switches end the session with ssh exit code 255 ("closed by remote host"), so the exit code alone can't tell a normal logout from a failure.
- Rule: if the user typed anything after the login, it was a session. TRee-Li returns to the menu immediately and shows "Disconnected".
- If the user never typed anything and the exit code is non-zero, it was a connection failure. TRee-Li waits for a key so the error stays readable, and also shows it in the status line.

## D10: Repository hygiene (Warden)
- `data.csv` and `tree-li.conf` are git-ignored. The real inventory never goes to GitHub; `data.example.csv` and `tree-li.conf.example` are shipped instead.
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
- Stored per user in `~/.local/state/tree-li/{favorites,recent}`: mode 0600, atomic writes, re-read before every write (two TRee-Li windows of the same user don't overwrite each other), history capped at 200. Only successful logins are recorded (*Warden*).

## D13: Dialog windows and the TRee-Li palette (user request, 2026-10-02)
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
- **SSH check (user's choice: separate column, inside batch ping):** TCP connect to `ssh_port` (22) and wait for the server's `SSH-` greeting. If the server waits for the client, TRee-Li sends its own greeting first. Results: `open`, `closed` (refused), `no answer` (timeout, unreachable, no SSH greeting). No login, no password (*Warden*); the switch only logs a short connection.
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
- **Saved check results:** `~/.local/state/tree-li/status`, merged per host (newest wins), restored at startup with a hint. `wait` is never saved.
- **Mouse** (stdlib curses, on by default, `mouse = no` to switch off):
  - click selects, double-click runs (300 ms window), a header click sorts, the wheel scrolls
  - switched off during ssh sessions
  - *Operator:* text selection then needs Shift; documented in the README troubleshooting table
  - wheel-down needs ncurses mouse v2 (RHEL 8+); older builds only scroll up

## D18: traceroute removed (user, 2026-10-03)
- The command, `trace_command` and the `--check` line are gone. An old `tree-li.conf` that still sets `trace_command` keeps working: the option is silently ignored (`OBSOLETE`).

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
- From the handover security review, the parts that apply to TRee-Li as it is: **no core dumps** (`RLIMIT_CORE=0`), and on Linux **`PR_SET_DUMPABLE=0`**, so other processes of the same user can't attach or read `/proc/<pid>/mem`, where the stored password lives. Root still can. ssh and ping children are unaffected, because exec resets this.
- The **tmux pane feature is NOT built.** It's parked in `council/ideas/tmux-panes.md` with option 1, the hardening and the Warden's concern about forgotten background sessions.
- Credit **"by Timmy & Ruffy"**: small, in Steel, bottom right of the footer (when no batch progress is shown there) and on the help screen.

## D22: Review round 4 - fixes, --check as a gate, version discipline (2026-10-03)
- **Crash fix (*Architect*):** the batch-ping rate limiter could call `time.sleep()` with a negative value when a worker was descheduled between the loop condition and the argument. The `ValueError` killed the thread, printed a traceback over the curses screen and left hosts stuck in `wait`. Reproduced deterministically, now `max(0.0, ...)`.
- **`user_typed` simplified (*Critic*):** it used to be set only when a password had already been sent. If the prompt was never recognised and the user typed the password by hand, a normal logout (exit 255 on most switches) was then reported as a failure. Any keystroke now counts, which is both simpler and correct.
- **Prompt-not-recognised hint:** `SessionResult.prompt_missed` is true when a password was stored, the switch answered, and no prompt was ever matched. TRee-Li now says so instead of silently doing nothing. It stays false for connection failures, where no prompt could appear. This is the Universal 4300 failure shape made visible.
- **`--check` is a gate (*Operator*):** exit 0 = fine, 1 = data warnings, 2 = cannot run. It also lists obsolete options from an old config, which were silently ignored before, and prints the state directory.
- **Version discipline (*Warden*):** `VERSION` is 1.1.0 and must be bumped per bundle. `make-bundle.py` refuses to overwrite an existing bundle with different contents (`--force` overrides), and the extractor refuses to downgrade without a confirmation. Previously every bundle was called `tree-li-bundle-1.0.0.py`.
- **Help page is data (`help_sections`)**, rendered by `show_help` and checked by tests: every command must be documented and no removed feature may still be advertised. The stale "ping + SSH check" line got through exactly because nothing tested this.
- **Cleanup:** dead `delimiter` parameter on `read_table`, the double refilter in `connect()`, the defensive `getattr(args, "debug")` (the test helper now mirrors the real parser), the `--debug` help text that hardcoded the state path, and stray blank lines.
- **Session logging stays** (user's call) - it is the only feature with no demonstrated user, revisit later.

## D23: tmux panes built on the `tmux-version` branch (2026-10-03)
- Not merged. The user wants to try it before deciding; `main` is untouched.
- **Mark with `Tab`** (right-click too), `+` in the list, "N marked" in the top bar. With 2+ marked, ssh opens one tmux session with one pane per switch (max 9), all logging in at once - the user's call: a mistyped password is their problem, as when using tmux by hand.
- **Back out:** `Ctrl-b d`. **Back in:** `Ctrl-T`. Logging out of the last pane ends the session and TRee-Li picks the results up by itself.
- **Handover (option 1)** with all the hardening from the idea doc: private 0700 directory, 0600 socket, kernel uid *and* pid check, one-time ticket bound to the pane tmux started, 15 s lifetime, socket deleted once the logins are out.
- **Results go through the status file, not the socket** - simpler, survives long sessions, and lets the socket close early. The DONE protocol is gone.
- *Warden:* `N tmux` in the top bar while sessions live, and they are named again on exit. `synchronize-panes` is forced off so one command can never go to every switch.
- Works on Linux (`SO_PEERCRED`) and macOS (`LOCAL_PEERCRED` / `LOCAL_PEERPID`), both verified.
- 14 security tests in `tests/test_handover.py`; 80 tests overall on Python 3.8 / 3.9 / 3.14.

## D24: tmux hardening after the first real use (2026-10-03)
User feedback: "Ctrl-T is a bit buggy" and "Ctrl-b & does not close the session for me (Swiss German layout)".
- **Ctrl-T had four faults**, all now fixed: it trusted a session list cached for up to 3 s (so it could attach to a session that had just ended), `attach_session` returned an exception object nobody looked at, a failed attach left curses and came straight back with no message, and a successful switch inside tmux said nothing at all. It now asks tmux for the live list, checks the session exists, reports every outcome, and names the sessions still running.
- **Closing without a tmux key:** `Ctrl-K` in TRee-Li closes the sessions after a y/n window. Keyboard layouts make `Ctrl-b &` unreliable, and binding a tmux key ourselves would change the user's global tmux config, so the action belongs in TRee-Li. The tmux status bar now advertises `exit` per pane instead of `&`.
- **Handover: one thread per connection.** The accept loop was serial with a 5 s timeout, so a single client that connected and said nothing blocked every other pane from fetching its login - measured: the second pane timed out completely. The `parent_pid()` lookup (which runs `ps` on macOS) also no longer happens while holding the lock. Single use is still exact, re-checked under the lock.
- **Session names could collide** inside one second (`tree-li-HHMMSS`); `free_session_name()` now suffixes.
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
  `pip install` is a ticket, and TRee-Li's promise is "copy one file".
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
- **A tmux pane's login failure never reached TRee-Li (*Warden*).** `ideas/tmux-panes.md` step 5 promised the
  stored password is wiped on a login failure; D23 moved results to the status file and the wipe was quietly
  lost with the DONE protocol. So one mistyped password was spent on up to 9 panes **and then kept**, costing
  another failed auth on the next single ssh - exactly the TACACS+/RADIUS lockout D3 exists to prevent.
  Panes now report it through the state directory (`authfail`, 0600), TRee-Li picks it up within 3 s while the
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
- **`Ctrl-K` / `Ctrl-T` could touch another TRee-Li window's sessions (*Warden*).** The fallback to "any
  `tree-li-*` session" stays - it is how an orphaned session is recovered - but both now say so and ask first.
- **Idle password timeout built (*Warden*, the condition from `ideas/tmux-panes.md` risk 5).** Background tmux
  sessions exist on this branch, so the "mandatory if" is met. `password_timeout = 15` minutes, `0` = never.
  Idle means no keypress in TRee-Li; a switch session and a return from tmux both count as use, and tmux panes
  running in the background deliberately do **not**.
- **Help page and README named the wrong `ESC` chain** (the marks step was missing). D22 made the help page
  data so this drift gets caught, but the test only checked commands - it now checks the `ESC` entry itself.
- **Observations fixed:** a pane faster than tmux's pane-pid report is waited for instead of refused
  (`BIND_GRACE`, still never answering an unbound ticket); `--ascii` is passed on to panes; two exports in the
  same second no longer collide (`-2`, `-3`); `Ctrl-C` saves finished ping results instead of dropping them;
  a bare `ping:` / `ssh:` now means "not checked", consistent with an empty `location:`; and with `tmux = no`
  the refusal explains what marks still do (limit batch ping) instead of being a dead end.
- **New end-to-end tests:** two marked switches really do share one login through the handover (and no pane
  command line carries the password), and a pane that cannot log in really does make TRee-Li forget it.
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
- **One variable:** `PASSWORD_LIFETIME_MINUTES` at the top of `tree-li`, with the reasoning next to it, is
  the single place to change if the team argues for longer or shorter. The config option defaults to it.
- **Expiry only deletes the password inside TRee-Li** (user's explicit requirement). A switch session you
  are sitting in is never interrupted - the check only runs while TRee-Li has the screen - and tmux panes
  keep running and stay logged in. Nothing in the workspace is touched.
- `password_timeout` goes into `OBSOLETE`, so a config written in the last two days keeps working.
- *Warden:* accepted. With a 900 s switch timeout and per-user accounts, the residual case this covers is
  narrow (TRee-Li parked inside tmux for days), and the cost is near zero. Honest limit: Python cannot wipe
  a string from memory, so this shrinks the usable window, not the theoretical one.

### Bracketed paste (idea B, built)
Terminals paste by *typing* at the application, so a copied switch name with its trailing newline arrived
as `ENTER` - which ran `ssh` on whatever row the filter happened to put first. Now TRee-Li enables
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
  still written with 4 - so an older TRee-Li sharing the state directory keeps reading what it can instead
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
