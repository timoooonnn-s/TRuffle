# TRuffle: Switch Manager

```
 _____  ____           __   __  _
|_   _||  _ \  _   _  / _| / _|| |  ___
  | |  | |_) || | | || |_ | |_ | | / _ \
  | |  |  _ < | |_| ||  _||  _|| ||  __/
  |_|  |_| \_\ \__,_||_|  |_|  |_| \___|
```

*by Timmy & Ruffy*

Search your switch list, ssh into a switch, log out, and you're back in the list,
all inside the terminal of a Linux server you reach over SSH (PuTTY, Tabby, ...).

- **One folder, Python 3 standard library only.** No pip, no venv, no root. Sent around as [one bundle file](#single-file-bundle).
- **Password asked once per session.** It stays in memory only and is forgotten when TRuffle exits.
- **After you log out of a switch, you're back in TRuffle.**

Inspired by [V-Li: Switch Manager](https://github.com/seismicindustries/switch-manager).
TRuffle keeps its menu, but runs ssh inside your terminal instead of a new desktop window.

**[Quick start](#quick-start)**: up and running in five minutes.
**[Reference](#reference)**: everything in detail.

---

# Quick start

### 1. Check the requirements

On the server: Linux, **Python 3.8 or newer** (`python3 --version`), the OpenSSH client and `ping`.

### 2. Get TRuffle

```bash
git clone <repo-url> ~/truffle
```

Any directory works, for example a [shared team folder](#team-setup).
No git on the server? Use the [single-file bundle](#single-file-bundle) instead.

### 3. Add your switches

```bash
cd ~/truffle
cp data.example.csv data.csv
```

Then put your switches into `data.csv`: one line per switch, at least `Name` and `IP`
([format](#switch-list-datacsv)). Check it, including a [data check](#data-check) for duplicates and typos:

```bash
./truffle --check
```

### 4. Start it

```bash
./truffle
```

To start it from anywhere with just `truffle`, add an alias:

```bash
echo "alias truffle='$HOME/truffle/truffle'" >> ~/.bashrc
```

### 5. Use it

1. **Type** to filter the list. A few letters are enough: `bc01` finds `ber-core-01`.
2. Pick a switch with **↑ ↓**. **ssh** is already selected, so press **Enter**.
3. Enter your username and password **once**. TRuffle logs you in, now and for every following switch.
4. **Log out** of the switch, and you're back in the list.
5. **← →** selects the other commands (ping, details, help, exit).
6. Several switches at once: **`Tab`** marks them (`+`), and marks are kept while you search for more.
   With two or more marked, **ssh** opens one [tmux pane per switch](#several-switches-at-once-tmux).
7. A **terminal server** (a name like `ab-12-ts1-01`): **Enter** asks for the line, then TRuffle logs
   you into the [console](#terminal-servers-console) of the switch behind it. **`Ctrl-Q`** brings you back.

Filtering by a naming scheme — all the `-l1` switches, or the `w3` and `w4` ones — is what
[patterns and `|`](#search) are for: `*-l1`, `w3|w4`.

All keys: [Keys](#keys) or the **help** command inside TRuffle. If something looks wrong, see [Troubleshooting](#troubleshooting).

---

# Reference

- [Screen](#screen)
- [Keys](#keys)
- [Commands](#commands)
- [Search](#search)
- [Several switches at once (tmux)](#several-switches-at-once-tmux)
- [Terminal servers (console)](#terminal-servers-console)
- [Settings](#settings)
- [Favourites and recent switches](#favourites-and-recent-switches)
- [Saved check results](#saved-check-results)
- [Data check](#data-check)
- [Switch list (`data.csv`)](#switch-list-datacsv)
- [Configuration](#configuration)
- [Team setup](#team-setup)
- [Single-file bundle](#single-file-bundle)
- [Session logging](#session-logging)
- [Debug log](#debug-log)
- [Where the log files are](#where-the-log-files-are)
- [Colours and symbols](#colours-and-symbols)
- [Security](#security)
- [Troubleshooting](#troubleshooting)
- [Development](#development)

## Screen

```
  TRuffle  Switch Manager                                    2 marked · timmy · 2/29 switches
───────────────────────────────────────────────────────────────────────────────────────────────

   ssh   ping   details   help   exit

  ›  ber core

     NAME          IP            SUBNET    ALIAS                COMMENT    PING ▲      SSH
     ─────────────────────────────────────────────────────────────────────────────────────────
 ▌*+ ber-core-01   192.0.2.1     ber       Core switch Berlin   5520       ● down now  ● failed 2h
   + ber-core-02   192.0.2.7     ber       Core switch Berlin   VSP7400    ● up 5m     ● ok 3d

───────────────────────────────────────────────────────────────────────────────────────────────
  Enter run  ←→ command  Tab mark  ^F favourite  F1-F7 sort  ^G settings  ^C quit
```

From top to bottom:
- **Top bar:** your login user once you've connected, how many switches are shown, and — when there
  are any — how many switches you've [marked](#several-switches-at-once-tmux), how many
  [tmux sessions](#several-switches-at-once-tmux) are still running, and `local: <user>` while a
  switch's [local account](#terminal-servers-console) is stored.
- **Command tabs.**
- **Search line.**
- **Table:**
  - `▌` marks the selected row.
  - `*` marks a [favourite](#favourites-and-recent-switches).
  - `+` marks a switch you picked with `Tab` for [several at once](#several-switches-at-once-tmux).
    Marks are kept when you search for something else, so you can collect them from several searches.
  - `▲`/`▼` shows the sorted column.
  - **PING** shows the last ping result. A ping that could not run at all (not allowed, unknown host)
    changes nothing - TRuffle says so instead of calling the switch `down`.
  - **SSH** shows how your last real ssh attempt went: `ok` only when ssh actually got you logged in,
    otherwise `failed` - also when you stopped a hanging connect with `Ctrl-C`, or the password was refused.
  - **Both say how old they are:** `now`, `5m`, `2h` (up to two days), then `3d`. A result older than
    a day is **faded** — `down` from three days ago says little about today, ping again. The exact time
    is in **details**. In a narrow window the age is left out before the word is cut.
    TRuffle never tests SSH on its own, so there's no extra traffic. When it failed, **details**
    tells you *why* — `Connection timed out` is a different job from `Permission denied`.
  - Letters matching the [search](#search) are underlined.
- **Footer:** key hints, or a message for a few seconds.

## Keys

| Key | Action |
|---|---|
| `↑` `↓` `PgUp` `PgDn` `Home` `End` | select a switch |
| `←` `→` | select a command |
| `Enter` | run the selected command on the selected switch |
| just type | [search](#search) |
| `Backspace` / `Ctrl-W` / `Ctrl-U` | delete a character / a word / the whole search |
| paste | pasted text goes into the search as **text** — a newline in it no longer runs `ssh` |
| `ESC` | step by step: 1. clears the search, 2. cancels a running ping, 3. clears the marks, 4. clears the sort |
| `F1` … `F7` | sort by that column: ▲ ascending → ▼ descending → original order |
| `Ctrl-F` | mark / unmark the selected switch as a [favourite](#favourites-and-recent-switches) |
| `Tab` / `Shift-Tab` | mark / unmark a switch for [several at once](#several-switches-at-once-tmux) (`+`). Marks survive a new search; `is:marked` lists them |
| `Ctrl-T` | back into the running [tmux session](#several-switches-at-once-tmux) |
| `Ctrl-K` | close the running tmux sessions (asks first) |
| `Ctrl-G` | [settings](#settings) for this session: session log, debug log, tmux, symbols, forget password, log files |
| `Ctrl-R` | reload the switch list |
| `Ctrl-L` | redraw the screen |
| `Ctrl-C` | quit |
| `Ctrl-Q` | in a [terminal server](#terminal-servers-console) session: back to TRuffle (log out of the switch first) |

In full-screen output (ping, details, help, log files): `↑` `↓` `PgUp` `PgDn` scroll, and `ESC` / `Enter` / `q` closes.

**No mouse.** TRuffle is keyboard-only on purpose, so selecting text in PuTTY or Tabby works
normally — no Shift needed.

## Commands

| Command | What it does |
|---|---|
| **ssh** | Connects to the selected switch. The first time, TRuffle asks for username and password (see [Security](#security)). Log out to come back; `~.` at the start of a line force-closes a hanging session. On a [terminal server](#terminal-servers-console) it asks for the line first. |
| **ping** | Checks whether the switches you're working with still answer. **One switch** (nothing marked): `ping -c 4` with live output. **Two or more marked**: all of them at once, no live output, straight into the PING column — you can keep working while it runs, and `ESC` (with an empty search) cancels it. `ESC` during a live ping keeps the replies that already arrived; stopping before any reply leaves the old result alone. |
| **details** | All CSV fields of the switch, plus ping/SSH result with time, favourite and last connection. |
| **help** | Keys, search syntax, and the file paths in use. |
| **exit** | Quits and forgets the password. |

## Search

Case doesn't matter, and **every term separated by a space must match** — that's what narrows a long list
down (`ab-* s34 -ping:down`). For "either/or", put the alternatives in **one** term with `|` (`w3|w4`).

A plain word is found **anywhere in a column when you write it together**. It may be split **only at the
separators** `-` `.` `_` (also `/` `:` `@`), so `bc01` still finds `ber-core-01` (**b**er-**c**ore-**01**) while `w4` finds
`xx-xx-sxx-w4` and **not** `wx-x4-sxx-xx`, where the `4` is buried inside a segment. The best matches come
first and the matched letters are underlined. To match a **whole** name instead — a role, a position in
your naming scheme — use a **pattern** with `*` and `?`.

| You type | Shows |
|---|---|
| `w4`, `ber core` | a word written together, anywhere in a column. `s34` finds `ab-12-s34-w4` |
| `bc01` | split **only at `-` `.` `_` `/` `:` `@`**: `bc01` finds `ber-core-01`, `ab12` finds `ab-12-s34-w4`. A jump inside a segment never matches, so `w4` does not find `wx-x4-sxx-xx` and `a4` does not find `ab-12-s34-w4` |
| `'10.1.2` | exactly this text (a leading `'` also switches the splitting off) |
| `*-l1`, `??-??-s??-w3` | **pattern:** `*` = anything, `?` = one character, matched against a **whole** column. This is how you filter by role: `*-l1` finds `ab-12-s34-l1` and **not** `...-l11`, which a plain word can't tell apart. A name like `sw1.example.net` also matches on just `sw1`, so you don't have to write `*-l1.*` |
| `w3\|w4` | **either one.** Space stays AND, so OR goes inside one term: `ab-* w3\|w4` = site `ab` **and** (`w3` **or** `w4`). Works with fields too: `ping:up\|wait` |
| `type:core` | the CSV column `type` contains "core", or matches it like a plain word (`name:bc01` finds `ber-core-01`). Works for **every** column, even ones not in the table, and for the names you gave columns in `columns` (`LOCATION:berlin`) |
| `loc:berlin` | the **start** of a column's name is enough, as long as only one column fits: `loc:` = `LOCATION`. Your names from `columns` win over the CSV's own headers; spaces in a name are written as `_` or left out (`site_name:`, `sitename:`) |
| `location:` | the column is empty |
| `-test`, `-type:edge`, `-*-w4` | excludes matches. An excluded word is always exact (a split exclude would hide far too much), but an excluded pattern stays a pattern. `-w3\|w4` excludes both |
| `ping:down` | ping state: `up`, `down`, `wait`, or `none` (not checked yet; a bare `ping:` means the same) |
| `ssh:failed`, `ssh:ok` | outcome of your last ssh attempt to that switch, or `none` (never tried) |
| `is:fav` | your favourites |
| `is:recent` | switches you connected to, newest first |
| `is:marked` | everything you've picked with `Tab` so far, from any search |

### Tips & tricks

**Two short words beat one long one.** Every space-separated term has to match, so each word you add
narrows the list. You rarely need to know the full name:

```
ab s34          site ab, position s34 — in any order, any column
ab s34 w4       narrowed again
```

**Pin a role or a position with a pattern.** A pattern is matched against the **whole** name, which is what
a plain word cannot do:

```
*-w4            names ENDING in -w4
ab-*            names STARTING with ab-
??-??-s??-w3    w3 switches, wherever they sit in the scheme
```

**Either/or goes inside one term**, because space stays AND:

```
w3|w4           the w3 and w4 switches
ab-* w3|w4      site ab, and (w3 or w4)
ping:up|wait    answered, or still being checked
```

**Subtract what's in the way.** A leading `-` removes matches, and it works on words, fields and patterns:

```
ab-* -test          site ab, without the test boxes
*-w4 -ping:down     w4 switches that aren't known to be down
```

**Search columns that aren't on the screen.** Any CSV column works as `field:value`, even one you don't
display — and a bare `field:` finds the rows where it is *empty*, which is handy for spotting gaps:

```
responsible:timmy   everything Timmy owns
location:           rows where location was never filled in
```

**Collect switches across several searches.** Marks (`Tab`) survive a new search, so you can gather from
different corners of the list and then act on all of them at once:

```
ab-*  → Tab Tab      mark two here
cd-*  → Tab          search again, mark another
is:marked            see the pile — then ssh opens them all (see below)
```

**After pinging marked switches, let the result drive the next search.** `ping:down` is the follow-up list, and
`ssh:failed` is the "I tried and it didn't work" list — **details** shows the reason for each.

**`'` turns a word back into plain text** (`'10.1.2`), and **ESC steps back one layer at a time**: first the
search, then a running ping, then the marks, then the sort.

## Several switches at once (tmux)

> Needs `tmux` on the server. Turn it off with `tmux = no`.

**Marks survive a new search.** Search, mark a couple, search for something else, mark a couple
more — then run **ssh** and you connect to all of them. `is:marked` shows the collection so far,
and the top bar counts it. `ESC` (with an empty search) clears it.

Mark switches with **`Tab`**, then run **ssh**. With **two or more** marked, TRuffle opens its
own tmux session with **one pane per switch**, up to **9**. You type your password **once** and every pane
logs in by itself.

| You want | Press |
|---|---|
| mark / unmark a switch | `Tab` (`Shift-Tab` marks the one above) |
| see what you've marked | search `is:marked` |
| clear all marks | `ESC` (with an empty search) |
| **back to TRuffle**, panes keep running | `Ctrl-b d` |
| **back into the panes** | `Ctrl-T` in TRuffle |
| **close them all**, from TRuffle | `Ctrl-K` (asks first) |
| switch between panes | `Ctrl-b o`, or `Ctrl-b` and an arrow key |
| make one pane full screen (and back) | `Ctrl-b z` |
| log out of one switch | `exit` in that pane; its pane closes |

`Ctrl-K` in TRuffle is the reliable way to close everything: it needs no tmux key and works on any keyboard
layout. tmux's own `Ctrl-b &` does the same from inside, but the `&` is awkward on some layouts.

When the last pane is gone the tmux session ends by itself and you are back in TRuffle.
The tmux status bar shows these keys while you are in the session, and each pane border carries its switch name.

**From any shell**, the sessions are normal tmux sessions named `truffle-HHMMSS`:

```bash
tmux ls                              # which are still running
tmux attach -t truffle-143052        # go back into one
tmux kill-session -t truffle-143052  # close one and its logins
```

**They keep running after you detach.** That is the point — a dropped PuTTY connection does not lose your
sessions — but it also means switches stay logged in. TRuffle shows `N tmux` in the top bar while any of
its sessions are alive, and names them again when you quit.

**How the single login works, and what it costs:** panes are started by tmux, so their command line is
visible to every user on the machine (`ps`) and cannot carry the password. Each pane gets a one-time ticket
instead and fetches the login through a Unix socket in a private directory. Before answering, TRuffle asks
the kernel who is connecting and replies only to **your own user** and to **the exact process tmux started**,
once, within 15 seconds. The socket is deleted as soon as the panes have their login.
Anything running as *your* user could still ask for it during those seconds — that is the trade-off of the
single login. Set `tmux = no` if you would rather type the password per pane.

**If a pane can't log in,** it says so in that pane and tells TRuffle, which drops the stored password and
asks you again. A mistyped password therefore costs you the panes you opened, not every switch you visit
afterwards. The password is also forgotten 10 hours after you typed it (see [Security](#security)); that
only clears it inside TRuffle and leaves running panes alone.

**Worried about the shared login, or asked to justify it?** [TMUX-SECURITY.md](TMUX-SECURITY.md) explains
the whole mechanism from first principles — what a Unix socket is, why the ticket is deliberately public,
who could and could not get the password, and what we honestly do *not* claim. It's written to be handed
to a colleague who doesn't work in Linux every day.

## Terminal servers (console)

> Only for rows whose name matches `console_hosts` (default `*-*-ts?-*`). Turn it off with `console_hosts =`.

A terminal server is reached with ssh like a switch, but the **username carries the line**:
`timmy:7012@ab-12-ts1-01` is line 12. Behind it, the switch on that serial line asks for its
own login. TRuffle does both logins in one go:

| Login | Who | Your choice |
|---|---|---|
| 1. the terminal server | **always your RADIUS login** — a terminal server has no local account | none |
| 2. the switch behind it | RADIUS, its local account, or you yourself | `radius` / `local` / `manual` |

**Which rows are terminal servers** is decided by their **name**, with the same `*` / `?` patterns as
the [search](#search): `ab-12-ts1-01` is one, `ab-12-s34-w4` is not. `truffle --check` prints how many it
recognised.

Press **Enter** (ssh) on a terminal server and TRuffle asks:

```
  ╭─ Console · ab-12-ts1-01 ─────────────────────────────────────╮
  │  Line               12                                       │
  │                                                              │
  │  Terminal server   RADIUS, always  ·  timmy:7012             │
  │                                                              │
  │  Switch login      ‹ radius ›                                │
  │                    RADIUS as well (timmy), TRuffle types it  │
  ╰──────────────────────────────────────────────────────────────╯
```

- **Line:** type the number, `12` becomes `7012` (`console_port_base = 7000`). The last line you
  used on that terminal server is filled in — only as a suggestion, lines get re-cabled.
- **Terminal server:** not a choice. It always gets your RADIUS login — the same one as for ssh,
  asked once per session. The window shows the username it will send (`timmy:7012`).
- **Switch login** (`←` `→`), only for the switch behind it:
  - **radius**: your RADIUS login again.
  - **local**: the switch's local account, for a switch that can't reach its RADIUS server. Asked
    once, then kept in memory like your password (same lifetime, `Ctrl-G` `p` forgets it). The
    top bar shows `local: <user>` while it is held.
  - **manual**: TRuffle logs you into the terminal server and wakes the line, you log in at the switch.

| You want | Press |
|---|---|
| choose the line | type its number (`Backspace` / `Ctrl-U` deletes) |
| choose who logs in at the switch | `←` `→` |
| connect | `Enter` |
| cancel | `ESC` |
| **back to TRuffle** | `Ctrl-Q` in the session — after you've logged out of the switch |

What TRuffle then does, in one ssh session:

1. types your RADIUS password for the terminal server,
2. presses **Enter** to wake the serial line,
3. at the switch's `Login:` prompt types the username, at `Password:` the password,
4. waits — a switch whose RADIUS server is out of reach can take **minutes**. After a few seconds
   without an answer it says so; any key takes over. (`console_login_wait = 240` seconds.)

**TRuffle types only at a prompt it recognises.** A console can still be logged in from the last
person. Enter then shows a CLI prompt, and typing your username and password there would put
them into the switch's command history, its syslog and onto the screen of anyone else on that
line. So when no login prompt shows up, TRuffle types nothing and hands over to you. Same when
the switch **refuses** the login: it is typed **once**, never again, and the password is kept,
because the terminal server has just accepted it. You log in by hand.

**Getting back to TRuffle:** logging out of the switch does not end the session, it only brings
back the switch's `Login:` prompt — TRuffle then shows *"Logged out? Ctrl-Q goes back to
TRuffle."* **`Ctrl-Q`** ends the session at any time. **Log out of the switch first**: `Ctrl-Q`
while you're still logged in leaves the console logged in for the next person.

- Terminal servers open **one at a time**, not in [tmux panes](#several-switches-at-once-tmux).
- The **SSH** column of a terminal server says whether the terminal server let you in.
- If the login on your terminal server misbehaves, `truffle --debug` records both logins'
  prompts (never a password) — see [Debug log](#debug-log).
- Another login scheme (another prefix than `70`, a word before the port): `console_login` and
  `console_port_base` in [`truffle.conf.example`](truffle.conf.example).

## Settings

Some things you only want for the next hour — recording a change window, or chasing one switch
that won't log in. **`Ctrl-G`** opens them without restarting TRuffle:

| Key | Setting | What it does |
|---|---|---|
| `l` | Session log | start/stop recording ssh sessions to files ([details](#session-logging)), **including tmux panes that are already running**. Shows the folder while on |
| `d` | Debug log | start/stop recording what happens around each login ([details](#debug-log)). Shows the file while on |
| `t` | Several at once (tmux) | turn the [multi-switch panes](#several-switches-at-once-tmux) on or off |
| `c` | Screen symbols | `auto` → `unicode` → `ascii`, applied at once if lines look garbled |
| `p` | Forget the stored password | drops it now, e.g. before you leave your desk — the [local account](#terminal-servers-console) too. Running sessions and tmux panes are untouched |
| `f` | Log files of this session | lists every log file written since TRuffle started, with its [full path](#where-the-log-files-are) |
| `ESC` | | close |

Changes apply to **this TRuffle only** and take effect on the next connection (the session log also on running tmux panes) — put them in
[`truffle.conf`](#configuration) to make them permanent.

Everything else (columns, paths, password lifetime) is set once in the configuration
file; nothing else is worth flipping mid-day.

## Favourites and recent switches

- `Ctrl-F` marks a switch as a favourite (`*`). Favourites are listed first as long as no column is sorted.
  During a search, better matches come first and favourites only win ties.
- Every successful login is remembered. Find those switches with `is:recent`, or see "Last connected" in **details**.
- Both are stored **per user** in `~/.local/state/truffle/` (only readable by you), never in the shared folder or the CSV.

## Saved check results

The PING results, and your last ssh attempts with the reason they failed, each with its time, are saved per user in
`~/.local/state/truffle/status`. After a restart they're shown again, with their [age](#screen), until the next check, and **details** shows when
each one was taken — and `ping:down`, `ssh:failed` and the other [status searches](#search) find them right away.
Several TRuffle windows merge their results, and the newest one wins.

They're saved as soon as you have them, and also when TRuffle is closed the hard way — the PuTTY
window closed or the tmux session killed with a ping still on screen or still running: what had
answered by then is kept. Switches that hadn't answered yet keep their previous result.

## Data check

`truffle --check` checks the switch list and shows the CSV line of every problem:
- rows with more or fewer fields than the header (often a `;` inside a comment, which shifts the columns)
- names or IPs that appear more than once
- missing IPs, unusable hosts, invalid IPv4 addresses (`10.0.0.300`), leading zeros (`010.0.0.5`, which ping reads as octal)
- `ssh results`: whether this system lets TRuffle see that ssh started a session. The SSH column depends on it;
  `NOT RELIABLE` means every login would be recorded as failed

TRuffle also says so at startup when the list has warnings.

An unknown or retired option in `truffle.conf` stops TRuffle at startup and names the option, so `--check` reports it too.

**Exit codes**, so you can run it from cron or a pipeline:

| Code | Meaning |
|---|---|
| `0` | everything fine |
| `1` | warnings: the switch list (duplicates, bad addresses, shifted columns), or `ssh results` not reliable |
| `2` | cannot run: switch list missing or unreadable, or `ssh` / `ping` not installed |

```bash
./truffle --check || echo "please fix the switch list"
```

## Switch list (`data.csv`)

```csv
Name;IP;subnet;aliases;comment;type;id;responsible;aix_server
ber-core-01;192.0.2.1;ber;Core switch Berlin;5520;core;101;Ruffy;-
```

- The first line is the header. Only `Name` and `IP` are required, and header names are case-insensitive.
- The delimiter (`;` `,` `|` tab) is detected automatically. UTF-8 and Excel/Windows files both work.
- Empty lines and lines starting with `#` are ignored.
- **New columns** (e.g. `location`) show up in **details** and `field:` [search](#search) right away.
  To show one in the table, add it to `columns` in the [configuration](#configuration).
- `data.csv` is in `.gitignore`, so your inventory never ends up in git.

### A list whose columns are named differently

An export from another system rarely has columns called `Name` and `IP`. You don't have to rename
anything — **the label you give a column in `columns` decides what it is**: the column you label
`Name` becomes the switch name, the one you label `IP` becomes the ssh target.

For an Infoblox network export, where the hostname is in `PRIMARY_DN_CODE`, the host address is in
`ADDRESS`, and the **first** column is the network address (`SUBNET`):

```csv
SUBNET,MASK,VLAN_ID,PRIMARY_DN_CODE,CREATION_DATE,...,ADDRESS
198.51.100.0,255.255.255.0,2301,cd-34-s56-r1.example.net,...,198.51.100.20
```

one line in [`truffle.conf`](#configuration) is the whole setup:

```ini
columns = PRIMARY_DN_CODE:Name, ADDRESS:IP
```

Every other column is still there — searchable as `vlan_id:2301` and listed by **details** — so you
can add more to the table later (`columns = PRIMARY_DN_CODE:Name, ADDRESS:IP, location, comment`)
as soon as the export carries them.

**Check it before you trust it.** `truffle --check` prints which column it uses for each job, every
header it found, and the first switch's resolved values — which is all you need to see what went wrong:

```
columns      : PRIMARY_DN_CODE (Name), ADDRESS (IP)
switch name  : PRIMARY_DN_CODE
ssh target   : ADDRESS
headers found: SUBNET, MASK, VLAN_ID, PRIMARY_DN_CODE, ..., ADDRESS
first switch : name 'cd-34-s56-r1.example.net'  ssh to '198.51.100.20'
data check   : ok
```

Without the labels it warns instead of guessing silently — using the first column as the name would
give every switch in a subnet the same identity, and favourites and history go by that name.
It also tells you when:

- **fewer than two of your `columns` exist in the list** — the table then falls back to showing the
  switch name and its address, instead of one near-useless column;
- **rows have nothing in the name column** — their NAME cell stays empty and they fall back to their
  IP, which otherwise just looks broken.

## Configuration

Everything is optional. All options with explanations are in [`truffle.conf.example`](truffle.conf.example).
TRuffle reads these files in order, and later ones win:

1. `truffle.conf` next to the `truffle` script: team defaults (git-ignored)
2. `~/.config/truffle/truffle.conf`: your personal settings
3. the file given with `--config FILE`

| Command line | Effect |
|---|---|
| `--data CSV` | use another switch list |
| `--debug` | write what happens around each ssh login to a [debug log](#debug-log) |
| `--log` | turn on [session logging](#session-logging) |
| `--ascii` | plain ASCII instead of lines and symbols ([why](#colours-and-symbols)) |
| `--check` | check config, switch list ([data check](#data-check)) and required tools, then exit |
| `--logs` | show where the log files are and the newest ones, then exit ([details](#where-the-log-files-are)) |
| `--version` | show the version |

`--debug` writes to `debug.log` in the state directory; `truffle --check` and `truffle --logs` print that path.

## Team setup

No system-wide install is needed. Put the TRuffle directory where your colleagues can read it, e.g.
`/srv/netops/truffle`, together with one `data.csv` and an optional `truffle.conf` for team defaults.
Everyone runs the same `truffle`. Passwords, favourites, history and logs stay per user.

## Single-file bundle

To move TRuffle without git, e.g. as a mail attachment, pack it into one plain-text file:

```bash
python3 tools/make-bundle.py          # creates dist/truffle-bundle-<version>.py
```

**Bump `VERSION` in `src/truffle/__init__.py` before building a bundle whose contents changed.** The version is part of
the file name, so two different bundles must never share one. `make-bundle.py` refuses to overwrite an
existing bundle that has different contents and tells you to bump; `--force` overrides that.

On the server, copy the bundle into the folder you want to update and run it there:

```bash
cd ~/truffle                       # e.g. your git checkout
python3 truffle-bundle-<version>.py
git status                         # if it's a git checkout: review, commit, push
```

| Run | Effect |
|---|---|
| `python3 truffle-bundle-<version>.py` | inside an existing TRuffle folder: **updates it in place**; anywhere else: unpacks into `./truffle` |
| `python3 truffle-bundle-<version>.py DIR` | unpacks / updates exactly in `DIR` |
| `python3 truffle-bundle-<version>.py --list` | only shows what's inside |

- **Damage check:** a checksum catches a damaged attachment before anything is written.
- **Removed files:** files that a newer version no longer has are removed, but only files a bundle installed
  (they're listed in `.truffle-files`).
- **Never touched:** `.git`, `data.csv`, `truffle.conf` and your own files.
- **No accidental downgrade:** if the folder already holds a newer TRuffle, the bundle says so and asks before
  installing the older one.
- **Not committed by accident:** the bundle file and `.truffle-files` are in `.gitignore`.

## Session logging

Off by default. Turn it on with `--log`, `session_log = yes`, or **`Ctrl-G`** inside TRuffle when
you want it just for the next session (a change window, say). Each ssh session is written to
`~/.local/state/truffle/logs/<date>-<time>_<switch>.log` (a console:
`..._<terminal server>_line_<n>.log`), readable only by you. [Where the log files are](#where-the-log-files-are)
shows how to find them again.
The log contains what was on screen, never the password TRuffle typed. Commands like
`show running-config` can still put secrets into it.

**Recording panes that are already logged in** — say, show commands before a migration: `Ctrl-b d`
back to TRuffle, `Ctrl-G` → `l`, `Ctrl-T` back in. From then on every pane this TRuffle opened writes
its own log file, until you switch it off the same way or the pane closes (quitting TRuffle does not
stop it; sessions from before a restart are named, not recorded). tmux records only what a pane shows.

## Debug log

`truffle --debug` — or **`Ctrl-G`** inside TRuffle, when a switch starts misbehaving and you don't
want to restart — appends a short report of every ssh login to `~/.local/state/truffle/debug.log`
(readable only by you):
- the ssh command
- which password prompts TRuffle saw
- whether it typed the password
- on a [terminal server](#terminal-servers-console): each step of the switch's login — the prompts it
  saw, what it typed (never the password itself) and why it handed over
- whether the session started (ssh switched the terminal to raw mode), the exit code and the reason for a failure
- the switch's output **before** the login (banner, prompts)

The password and the session itself are never in it.

## Where the log files are

A full path is far too long for TRuffle's footer, so:
- After a logged session the footer names the **file** (`20261020-141233_ab-12-ts1-01_line_12.log`).
- **`Ctrl-G` → `f`** lists every log file this TRuffle has written, grouped by folder, so every
  name fits on a line — session logs, tmux pane logs and the debug log.
- **When TRuffle exits**, it prints the same list with full paths to the shell, where you can
  select and copy them:

```
TRuffle closed - credentials forgotten.
Log files written while TRuffle was open:
  /home/timmy/.local/state/truffle/logs/20261020-141233_ab-12-ts1-01_line_12.log
  /home/timmy/.local/state/truffle/debug.log
```

- **`truffle --logs`** from any shell: the log folder, the debug log and the newest log files.

A second TRuffle window of yours that logs at the same time shows up in the list too — they share the folder.

## Colours and symbols

- **Colours:** shades of blue with small orange/green/red highlights ([STYLE.md](STYLE.md)).
  256 colours in Tabby or with `TERM=xterm-256color`, 8 colours in PuTTY's default `TERM=xterm`,
  and bold/reverse on terminals without colour.
- **Symbols:** lines and symbols use Unicode on UTF-8 terminals. If they look garbled, use `--ascii` or `charset = ascii`.

## Security

- **Memory only.** The password lives only in the memory of the running TRuffle. It never goes to disk,
  command lines or environment variables, so it isn't visible in `ps`.
- **Memory protected:**
  - TRuffle switches off crash dumps for itself, so a crash can't write the password to a file.
  - On Linux it also marks itself "not dumpable", so other programs of your own user can't attach to it or read its memory.
  - root still can, as with every program.
- **Typed once, only at a real prompt.** TRuffle types it once per connection, only at a real password prompt,
  and never at an SSH-key passphrase prompt. If it does not recognise the switch's prompt it types **nothing**
  and says so afterwards, so you always know whether the auto-login fired.
- **Wrong password:** ssh is stopped right away instead of retrying, the stored password is wiped,
  and you're asked again. This protects a central (TACACS+/RADIUS) account from lockouts.
  A [tmux pane](#several-switches-at-once-tmux) that can't log in reports it back, so one mistyped
  password is not spent on switch after switch.
  A switch behind a [terminal server](#terminal-servers-console) that refuses the login is different:
  the terminal server has just accepted the password, so it is kept, and you log in by hand.
- **Forgotten after 10 hours.** The password is dropped 10 hours after you **typed** it and you're asked
  again (`password_lifetime` in minutes, `0` turns it off). It's measured from when you typed it, not from
  your last keypress, so a window left running for days can't keep a live login — but it never expires in
  the middle of a working day.
  **It only deletes the password inside TRuffle.** A switch session you're sitting in keeps running, and
  tmux panes keep running and stay logged in. Nothing in your workspace is touched.
- **Once you type in a session,** TRuffle stops watching. A later `Password:` prompt on the switch is never answered for you.
- **Terminal servers:** the switch's login is typed only at a `Login:` / `Password:` prompt TRuffle
  recognises, once, and never into a console that is still logged in. A switch's **local account** is
  kept like your password: in memory only, forgotten with it.
- **Host keys:** new switches are added to `~/.ssh/known_hosts` automatically. If a key **changes**,
  TRuffle asks before removing the old one. That's expected after a hardware swap, but can also mean an attack.
- **CSV values** never pass through a shell, and hosts that look like command-line options (`-o...`) are rejected.

## Troubleshooting

| Problem | Fix |
|---|---|
| `switch list not found` | `cp data.example.csv data.csv`, or set `data =` in `truffle.conf` |
| `python3\r: No such file or directory` or `Permission denied` after copying via Windows | `sed -i 's/\r$//' truffle; chmod +x truffle`, or start it with `python3 truffle` |
| Old switch: `no matching key exchange method` / `host key type` | e.g. `ssh_options = -o KexAlgorithms=+diffie-hellman-group14-sha1 -o HostKeyAlgorithms=+ssh-rsa`. On RHEL 9 the system crypto policy may also need to allow SHA-1 |
| Lines or symbols look like `â”€` or `?` | `--ascii` / `charset = ascii`, or PuTTY *Window → Translation* → UTF-8 |
| Only a few colours in PuTTY | PuTTY *Connection → Data → Terminal-type string* → `xterm-256color` |
| F-keys don't sort | PuTTY *Terminal → Keyboard → Function keys* → `ESC[n~` (default) or `Xterm R6`. `ESC` with an empty search clears a sort |
| TRuffle says *"no password prompt recognised"* | The switch words its prompt differently, so you have to type the password yourself. Run `truffle --debug`, connect again, and send the "before login" part of the [debug log](#debug-log) — the prompt pattern can then be adjusted |
| Terminal server: *"No login prompt on the line"* | The console is still logged in (you see a CLI prompt) or busy. TRuffle typed nothing — log out of what's there or log in by hand. `truffle --debug` shows what the line sent |
| Terminal server: a row is not recognised | Its name doesn't match `console_hosts` (default `*-*-ts?-*`). `truffle --check` counts the terminal servers it found |
| Login works with plain ssh but not in TRuffle | Start with `truffle --debug`, try again, and look at the [debug log](#debug-log) |
| Screen garbled, or still the old size after resizing the window | `Ctrl-L`. TRuffle follows a resize within a fraction of a second, also after an ssh session; if not, `Ctrl-L` redraws |
| Every ssh shows `failed`, even good logins | Run `truffle --check`: if `ssh results` says `NOT RELIABLE`, TRuffle cannot see sessions start on this system - send the output. Also check `ssh_options` has no `-T` / `RequestTTY=no` |
| Not sure what's wrong | `truffle --check` |

## Development

```bash
python3 -m unittest discover -s tests -v
```

- The `truffle` file is only a launcher; the code is the package in `src/truffle/`, one module per job.
  Its docstring (`src/truffle/__init__.py`) maps them: the lower modules (config, switch list, search,
  results, ssh in a pty, tmux, ...) never import the curses screens in `src/truffle/ui/`, so they are
  tested without a terminal. Python 3.8+ and the standard library only.
- `tests/fake_ssh.py` acts as a switch (password `secret`, a changed host key, timeouts, a connect that
  hangs) and as a terminal server with four kinds of switch behind it (normal, still logged in, local
  account only, slow RADIUS). Like the real ssh it switches the terminal to raw mode once logged in -
  that is how TRuffle tells a session from a failed connect. Point `ssh_command` at it in a test config.
- The tmux tests run on a **private tmux server** of their own, so running them never touches the
  sessions of a TRuffle you have open.
- Design rules: [STYLE.md](STYLE.md).
