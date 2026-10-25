# Feature review (2026-10-25)

**Status: CLOSED (2026-10-25) - decided and built as D50, see [the discussion](#discussion).** Decisions taken in the discussion go into
[DECISIONS.md](DECISIONS.md) and are marked here as `-> D5x`. Anything listed under
[Settled](#settled---do-not-reopen) is not discussed again unless new evidence shows up.

## The council for this review

| Seat | Role here |
|---|---|
| **Drafter** (chair) | runs the review, writes this file, closes each point |
| **Operator** | the admin at 3 a.m. in PuTTY: keystrokes, surprises, error texts |
| **Critic** | challenges every "keep": what does it cost, who uses it |
| **Warden** | security: credentials, the shared CSV, what a feature exposes |
| **Newcomer** *(added for this review)* | one of the two engineers who are "learning into it": what is confusing, what a new user trips over |
| Tester, Platform | observers - this is a feature review, not a code review |

## The evidence (user, 2026-10-25)

- **Users:** Timon and Ruffy daily; two younger engineers experimenting.
- **Used:** ssh, search, ping, tmux, session logging, terminal servers, `truffle.conf`. Bracketed paste
  confirmed in PuTTY; the terminal-server login "worked great"; `truffle` as a command works.
- **Never used:** favourites.
- **Real use that the design did not expect:** "I pinged most of the inventory and had a great first look
  of how many dead hosts our IPAM actually carries." D35 built ping-with-marks for "the handful you
  marked" and removed a mark-all key because a sweep was "not TRuffle's job". The use says otherwise.
- **The list:** a full IPAM export, ~900 devices, not only switches (terminal servers and other devices),
  many columns per device.

---

## Part 1: the existing features, ranked

Four tiers, most critical first. Each line says why, and where a seat disagrees it says so.

### D. Cut candidates - remove unless someone argues them back

| # | Feature | Why it should go | Dissent |
|---|---|---|---|
| D1 | **Favourites** (`Ctrl-F`, the `*` column, "favourites pinned on top", `is:fav`, the `favorites` state file) | Never used by either daily user in three weeks. It is not free: a key, a marker column on every row, an ordering rule ("pinned first, only win ties during a search") that makes the list order harder to predict, a state file and a README section. `is:recent` already gives "my usual switches" without any effort. | *Operator:* about 30 lines; the newcomers might like it. *Newcomer:* "a star I never set but whose rule changes the order is the confusing kind of feature." **Drafter: cut.** |
| D2 | **`Ctrl-G` `t`: tmux on/off for this session** | Nobody turns tmux off for an hour. If tmux is unwanted, `tmux = no` is set once in the config. It is a settings row that only exists because the settings window existed. | none |
| D3 | **`Ctrl-G` `c`: cycle screen symbols** | `charset = auto` detects it, `--ascii` / `charset = ascii` fix it for good. Cycling mid-session is a debugging toy. | *Operator:* the one quick fix when a PuTTY font garbles mid-session. *Critic:* a restart with `--ascii` takes three seconds. **Open.** |
| D4 | **The single-file bundle** (`tools/make-bundle.py`, 249 lines: self-extract, checksum, `.truffle-files`, downgrade guard) | Built for "no git on the server" (Milestone 1d). If the server has git - **question to the user** - it is dead weight, and it has a known hole since 2.0: an old bundle over a 2.0 install cannot warn about the downgrade (D45). | *Operator:* it is the only way to mail TRuffle to a box without git. Keep only if that box exists. |

### C. Questionable - keep for now, but the question is real

| # | Feature | The question |
|---|---|---|
| C1 | **`is:recent` and "Last connected"** | Unknown whether anyone uses it. If favourites go (D1), this becomes the "my switches" feature - then it should be **taught** (help, README Quick start), not just exist. |
| C2 | **`truffle --logs`** | The third way to find the logs (`Ctrl-G` `f`, the list at exit, `--logs`). *Critic:* one too many. *Operator:* the only way from a second shell while TRuffle runs in tmux. Keep, but nothing more in this direction. |
| C3 | **`--check` exit codes "for cron or a pipeline"** | Nobody runs TRuffle from cron. Harmless and cheap, so it stays, but it should not be sold in the README as a use case nobody has. |
| C4 | **The search power features: `'exact`, exact excludes, `-*-w4`, `a\|b` with inherited field prefixes, empty `field:`** | Every one is justified (D16, D34, D39, D49), but together they are a language. *Newcomer:* "the README search section is longer than the rest of the quick start." Nothing to cut - but the help page and README should teach **four things first** (word, `*` pattern, `field:value`, `ping:down`) and leave the rest as "more". |
| C5 | **Session log for tmux panes that are already running** (D41: `pipe-pane`, the hidden `--log-sink`) | Session logging is used now (the "no demonstrated user" note of D22 is out of date). Whether the *running-pane* variant is used is unknown. It works and is tested, so it stays - but it is the most intricate logging path, and nothing should be built on top of it without a user asking. |
| C6 | **The tmux login handover** (one password for all panes over a private Unix socket, 187 lines + the 327-line `TMUX-SECURITY.md`) | tmux is used daily, so this stays. *Warden:* it is still the largest attack surface in TRuffle, and the company-policy question from the tmux-panes idea (risk 6) was never answered. *Critic:* with the newcomers in, "may we do this" deserves a yes from someone outside the two of you. |

### B. Keep - but each needs a tweak

| # | Feature | The tweak |
|---|---|---|
| B1 | **Ping with marks** | Built for "a handful", used for the whole inventory. Marking 900 rows by hand is the gap - see **M1** (mark all) and **M2** (export). The batch summary ("Ping done: 412 up, 488 down") also disappears after 20 seconds; for a sweep that number *is* the result. |
| B2 | **Sorting with `F1` ... `F12`** | The PING and SSH columns are always the **last** two. With 11 or more columns in `columns`, PING is beyond `F12` and **cannot be sorted at all** - and with a full IPAM export, many columns is exactly what happens. Status sorting needs a key that does not depend on the column count. **Question:** how many columns does your `columns` line have? |
| B3 | **"Switch" everywhere** (title "Switch Manager", "29/29 switches", "Switch list reloaded", "No switch matches") | The list now holds terminal servers and other devices. "device" in the UI texts; the name can stay. |
| B4 | **Session logging: no cleanup** | Daily use means a file per session, forever, in `~/.local/state/truffle/logs` - and `debug.log` only grows. A `log_keep_days` (default e.g. 90) that deletes TRuffle's own old logs at start. *Warden:* old session logs with `show running-config` in them are a liability, not an archive. |
| B5 | **The `ESC` chain** (search -> running ping -> marks -> sort) | Clever and documented, but invisible: you have to know which layer is next. *Newcomer:* "ESC cleared my marks, I wanted to clear the sort." Tweak: the footer says what the next `ESC` will do ("ESC: clear 12 marks"). |
| B6 | **Terminal servers** | Works, keep. One tweak worth asking about: the remembered line is **one per terminal server**, so with two switches on the same terminal server the suggestion flips back and forth. Showing the last 2-3 lines used there would cost little. The bigger step is **M3**. |
| B7 | **The plan and the ideas index are stale** | PLAN.md still has open boxes that are done (Milestone 2 "batch ping over all switches", 1g "confirm bracketed paste in PuTTY", "batch ping" wording); the ideas index still calls terminal servers "not yet tried" and session logging "no demonstrated user". Housekeeping, but stale docs are how we end up re-discussing settled things. |

### A. Core - keep as it is

Each of these is used, proven, and not up for discussion:

- **ssh in a pty, password typed once, back to the list after logout** (D3, D5) - the whole point.
- **Search:** fuzzy words split at separators, `*` / `?` patterns, `field:value` with short names, `ping:` / `ssh:` / `is:marked`, AND by space, OR with `|`.
- **Marks** that survive a new search (`Tab`, `is:marked`).
- **tmux panes** with `Ctrl-T` / `Ctrl-K` (used daily; the handover is C6).
- **Terminal servers:** line dialog, RADIUS to the terminal server, radius / local / manual for the switch, `Ctrl-Q`.
- **PING / SSH columns with their age**, saved across restarts and windows, honest SSH results (D44/D45), saved on a hang-up (D48).
- **details**, **help**, **`Ctrl-R`** reload.
- **`truffle.conf`** in three layers, **the column label decides the job** (D30), CSV delimiter / BOM / comment handling.
- **`--check`** with the data check and the session-detection self-test.
- **Session logging** and the **debug log** (used; their tweaks are B4).
- **Security basics:** memory-only password, 10-hour absolute lifetime, process hardening, host-key change handling, CSV never through a shell, bracketed paste.
- **Keyboard-only**, resize handling, 256 / 8 / no-colour and ASCII fallbacks.

---

## Part 2: what is missing

**The use case today:** two daily users and two learners on a RHEL jump host via PuTTY / Tabby, a
~900-device IPAM export with switches, terminal servers and other devices. The daily loop is: find a
device -> ssh; several switches side by side in tmux; record change windows; console when a switch is
down; and - new - **sweeps that turned out to be an IPAM clean-up tool**.

Ranked by value for that use case.

| # | Missing | Why | Size | Seats |
|---|---|---|---|---|
| **M1** | **Mark everything in the current view** (and unmark all) | The sweep the user already did. Without it a 900-device ping means holding `Tab`, and re-pinging only `ping:down` is impossible in practice. *Reverses part of D35*, which removed exactly this key on a scale *assumption* - this time it is real use. | small | *Warden:* cap it, or ask before marking more than N, so one key cannot open 900 tmux panes (the 9-pane cap already protects ssh) |
| **M2** | **Export the current view with its results** (CSV: the visible columns + PING / SSH with time and reason) | "How many dead hosts our IPAM carries" is only useful when the list reaches the IPAM owners. D35 removed the export as "not needed", and noted that the saved ssh failure reason lost its main use with it. The need is here now. | small | *Critic:* the help-page test that bans the word "export" (D35) has to go with it. One format, one key, no options. |
| **M3** | **From a down switch to its console - without inventory work** | The site is in the name (`ab-12-s34-w4` -> site `ab-12`), and so are the terminal servers (`ab-12-ts1-01`). On a switch, a **console** step can offer that site's terminal servers by name; you still type the line. No mapping column, which is why option C was rejected (D42). | medium | **Question:** is the site always the first two segments? |
| **M4** | **Log cleanup** (`log_keep_days`) | See B4. Listed here too because nothing like it exists yet. | small | *Warden:* yes |
| **M5** | **Quick connect from the shell: `truffle bc01`** | In the ideas list since the start. One match connects at once; several open TRuffle with that search. For two daily users it saves the start-up and the search, every time. | small | *Operator:* yes. *Critic:* only if it uses exactly the same search, not a second one. |
| **M6** | **Per-device ssh options / user** (the parked ssh-profiles idea) | Parked when the list held only Extreme switches. "A lot more other devices" may need old crypto, another user or a jump host. **Question:** does any device in the new list fail with plain ssh today? If not, it stays parked. | small | *Warden:* only a profile **name** in the CSV, never options (ssh-profiles.md) |
| M7 | **"Down since"** instead of only "down 3h" | For an IPAM clean-up, *how long* a host has been dead matters more than when it was last checked. Keep the time of the first `down` in a row next to the last check. | small | *Critic:* only after M2 shows people act on the list |
| M8 | **Copy the IP / name to the clipboard** (OSC 52) | Tickets and chats need the IP all day. Works in Tabby, partly in PuTTY. | small | *Platform:* test PuTTY first |
| M9 | **Read-only show commands on many switches** | The natural next big feature, in the ideas list. Not now: big, the Warden's heaviest topic (credentials over many parallel logins), and M1 + tmux cover the manual version. | big | parked on purpose |

### Not missing - checked and rejected again

- A live monitor / repeated sweeps: the network has monitoring (ideas list, D20's noise concern).
- An active SSH reachability test: rejected in D20, still right.
- Team-shared results (Ruffy sees your pings): *Warden:* a file everyone can write is the shared-CSV problem again. Not without a real need.

---

## Settled - do not reopen

These came up before and were decided; they are listed so the discussion does not circle back to them.

| Topic | Decision |
|---|---|
| Mouse support | removed (D29): it cost Shift-to-select every day |
| Latency / `MS` column | removed (D36): ping is a reachability check |
| traceroute | removed (D18) |
| Active SSH probing | rejected (D20) |
| Free-form ssh options in the CSV | never (ssh-profiles.md): command execution for anyone who can write the CSV |
| Switch-to-console mapping in the inventory | rejected (D42, option A): too much inventory work, lines move. M3 is the name-based alternative |
| Terminal server login | always RADIUS, not a choice (D47) |
| Delivery format | the folder, started with `python3 truffle`; the package layout stays (D45) |
| Dependencies / platform | R1 standard library only, R2 RHEL first (COUNCIL.md) |

## Questions for the user

1. **D4:** does the server have git, or is the bundle still how TRuffle gets there?
2. **B2:** how many columns are in your `columns` line? (11+ means PING can no longer be sorted)
3. **M1:** how did you mark most of the inventory for the sweep - holding `Tab`?
4. **M3:** is the site always the first two parts of the name (`ab-12` in `ab-12-s34-w4` and `ab-12-ts1-01`)?
5. **M6:** does any of the new non-switch devices fail with plain ssh?
6. **D1:** favourites - cut?

---

## Discussion

### Round 1 (user, 2026-10-25)

**Decided:**

| Point | Decision |
|---|---|
| D1 favourites | **cut** |
| D2 / D3 `Ctrl-G` `t` and `c` | **cut** - tmux and the symbols are set in the config only |
| D4 bundle | **kept**: the server has git, but only to the internal git, not this GitHub. Big changes travel as a bundle, and the bundle created the server's install. At the least a bundle *creator* stays |
| C4 search language | **README only**, no code change: teach the four basics first |
| C6 tmux login handover | **fine as it is** |
| B2 sorting beyond `F12` | not a problem today (7 columns) - **parked in the ideas list** |
| B3 "switch" everywhere | **rebrand** - wording to be agreed |
| B5 the `ESC` chain hint | **wanted** |
| B7 PLAN.md | **update it, or drop it if it has no job left** - the Drafter's call |
| M1 mark everything | **wanted** (the sweep was done by holding `Tab`) |
| M2 export | **wanted back** |
| M5 `truffle bc01` | **not needed** |
| M6 per-device ssh options | **not needed now**; parked as **device-group settings**, for load balancers and other device types if they come (ssh-profiles.md) |

**Answers:** 7 columns in `columns`; the site is always the first two parts of the name; the only
non-switch devices today are the terminal servers.

**Open - discussed next, nothing is built before:**
- C1 `is:recent`: explained again, keep or cut?
- M3 from a down switch to its console: brainstorm
- M4 / B4 log cleanup: how, and what makes sense
- the wording of the rebrand, and the details of mark-all and export

### Round 2 (user, 2026-10-25) - closed, built as D50

| Point | Decision |
|---|---|
| C1 `is:recent` | **kept** - now taught in the Quick start and its own README section |
| M3 console from a down switch | **dropped**: below 10 locations have console servers, mostly in the data centre, where the first two name blocks hardly vary |
| M4 / B4 log cleanup | **by age**, `log_keep_days = 180` (0 = never); `debug.log` rotates at 1 MB |
| B3 rebrand | **"TRuffle: Device Manager"**, "devices" in the texts |
| M1 / M2 / B5 | `Ctrl-A`, `Ctrl-E` to `~/truffle-export-<date>-<time>.csv`, the ESC hint - as proposed |
| B7 PLAN.md | cut down to what is open |

Not decided, so unchanged: C3 (the `--check` exit codes stay documented), M7 "down since", M8 clipboard -
both listed under "Next" in PLAN.md as candidates.
