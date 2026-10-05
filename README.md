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

- **One file, Python 3 standard library only.** No pip, no venv, no root.
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
5. **← →** selects the other commands (ping, batch ping, details, help, exit).

All keys: [Keys](#keys) or the **help** command inside TRuffle. If something looks wrong, see [Troubleshooting](#troubleshooting).

---

# Reference

- [Screen](#screen)
- [Keys](#keys)
- [Commands](#commands)
- [Search](#search)
- [Several switches at once (tmux)](#several-switches-at-once-tmux)
- [Settings](#settings)
- [Favourites and recent switches](#favourites-and-recent-switches)
- [Saved check results](#saved-check-results)
- [Export](#export)
- [Data check](#data-check)
- [Switch list (`data.csv`)](#switch-list-datacsv)
- [Configuration](#configuration)
- [Team setup](#team-setup)
- [Single-file bundle](#single-file-bundle)
- [Session logging](#session-logging)
- [Debug log](#debug-log)
- [Colours and symbols](#colours-and-symbols)
- [Security](#security)
- [Troubleshooting](#troubleshooting)
- [Development](#development)

## Screen

```
  TRuffle  Switch Manager                                     timmy · 2/29 switches
───────────────────────────────────────────────────────────────────────────────────

   ssh   ping   batch ping   details   help   exit

  ›  ber core

    NAME          IP            SUBNET    ALIAS                COMMENT    PING ▲  MS      SSH
    ─────────────────────────────────────────────────────────────────────────────────────────
 ▌* ber-core-01   192.0.2.1     ber       Core switch Berlin   5520       ● down          ● failed
    ber-core-02   192.0.2.7     ber       Core switch Berlin   VSP7400    ● up    1.24    ● ok

───────────────────────────────────────────────────────────────────────────────────
  Enter run  ←→ command  ^F favourite  F1-F8 sort  ^G settings  ^R reload  ^C quit
```

From top to bottom:
- **Top bar:** your login user once you've connected, and how many switches are shown.
- **Command tabs.**
- **Search line.**
- **Table:**
  - `▌` marks the selected row.
  - `*` marks a [favourite](#favourites-and-recent-switches).
  - `▲`/`▼` shows the sorted column.
  - **PING** shows the last ping result. **MS** is how long that ping took — one packet, so it's one
    number, not packet loss and not jitter. Sorting MS puts the slowest switches first, which is how you
    find the one behind a congested link.
  - **SSH** shows how your last real ssh attempt went: `ok` or `failed`.
    TRuffle never tests SSH on its own, so there's no extra traffic. When it failed, **details** and the
    [export](#export) also tell you *why* — `Connection timed out` is a different job from `Permission denied`.
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
| `ESC` | step by step: 1. clears the search, 2. clears the marks, 3. cancels a running batch ping, 4. clears the sort |
| `F1` … `F8` | sort by that column: ▲ ascending → ▼ descending → original order |
| `Ctrl-F` | mark / unmark the selected switch as a [favourite](#favourites-and-recent-switches) |
| `Tab` / `Shift-Tab` | mark / unmark a switch for [several at once](#several-switches-at-once-tmux) (`+`) |
| `Ctrl-T` | back into the running [tmux session](#several-switches-at-once-tmux) |
| `Ctrl-K` | close the running tmux sessions (asks first) |
| `Ctrl-G` | [settings](#settings) for this session: session log, debug log, tmux, symbols, forget password |
| `Ctrl-E` | [export](#export) the current list to a CSV file |
| `Ctrl-R` | reload the switch list |
| `Ctrl-L` | redraw the screen |
| `Ctrl-C` | quit |

In full-screen output (ping, details, help): `↑` `↓` `PgUp` `PgDn` scroll, and `ESC` / `Enter` / `q` closes.

**No mouse.** TRuffle is keyboard-only on purpose, so selecting text in PuTTY or Tabby works
normally — no Shift needed.

## Commands

| Command | What it does |
|---|---|
| **ssh** | Connects to the selected switch. The first time, TRuffle asks for username and password (see [Security](#security)). Log out to come back; `~.` at the start of a line force-closes a hanging session. |
| **ping** | `ping -c 4` with live output; also updates the Ping and MS columns. `ESC` stops it: replies that already arrived still count as **up**, and stopping before any reply leaves the old result alone. |
| **batch ping** | Pings every switch in the **current, filtered** list and fills the PING column. It's deliberately **quiet**: at most 20 pings per second (`ping_rate`), so 700 switches take about 35 s and one site a few seconds. You can keep working meanwhile; `ESC` (with an empty search) cancels. |
| **details** | All CSV fields of the switch, plus ping/SSH result with time, favourite and last connection. |
| **help** | Keys, search syntax, and the file paths in use. |
| **exit** | Quits and forgets the password. |

## Search

All terms must match, case doesn't matter. Plain words are **fuzzy**, like fzf: the letters only have to appear
in this order within one visible column. The best matches come first, and the matched letters are underlined.

| You type | Shows |
|---|---|
| `bc01`, `ber core` | fuzzy: `bc01` finds `ber-core-01`; exact hits rank above scattered ones |
| `'10.1.2` | exactly this text (a leading `'` switches fuzzy off for this word) |
| `type:core` | the CSV column `type` contains "core". Works for **every** column, even ones not in the table, and for table labels (`alias:munich`) |
| `location:` | the column is empty |
| `-test`, `-type:edge` | excludes matches (always exact) |
| `ping:down` | ping state: `up`, `down`, `wait`, or `none` (not checked yet; a bare `ping:` means the same) |
| `ssh:failed`, `ssh:ok` | outcome of your last ssh attempt to that switch, or `none` (never tried) |
| `is:fav` | your favourites |
| `is:recent` | switches you connected to, newest first |

Example: `type:core -ber ping:up ssh:failed` shows core switches outside Berlin that answer ping but where your last ssh attempt failed.
Press `Ctrl-E` on that and you have the list [exported](#export) — with the reason each one failed.

## Several switches at once (tmux)

> **Experimental**, on the `tmux-version` branch. Needs `tmux` on the server. Turn it off with `tmux = no`.

Mark switches with **`Tab`**, then run **ssh**. With **two or more** marked, TRuffle opens its
own tmux session with **one pane per switch**, up to **9**. You type your password **once** and every pane
logs in by itself.

| You want | Press |
|---|---|
| mark / unmark a switch | `Tab` (`Shift-Tab` marks the one above) |
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

## Settings

Some things you only want for the next hour — recording a change window, or chasing one switch
that won't log in. **`Ctrl-G`** opens them without restarting TRuffle:

| Key | Setting | What it does |
|---|---|---|
| `l` | Session log | start/stop recording ssh sessions to files ([details](#session-logging)). Shows the folder while on |
| `d` | Debug log | start/stop recording what happens around each login ([details](#debug-log)). Shows the file while on |
| `t` | Several at once (tmux) | turn the [multi-switch panes](#several-switches-at-once-tmux) on or off |
| `c` | Screen symbols | `auto` → `unicode` → `ascii`, applied at once if lines look garbled |
| `p` | Forget the stored password | drops it now, e.g. before you leave your desk. Running sessions and tmux panes are untouched |
| `ESC` | | close |

Changes apply to **this TRuffle only** and take effect on the next connection — put them in
[`truffle.conf`](#configuration) to make them permanent.

Everything else (columns, ping rate, paths, password lifetime) is set once in the configuration
file; nothing else is worth flipping mid-day.

## Favourites and recent switches

- `Ctrl-F` marks a switch as a favourite (`*`). Favourites are listed first as long as no column is sorted.
  During a search, better matches come first and favourites only win ties.
- Every successful login is remembered. Find those switches with `is:recent`, or see "Last connected" in **details**.
- Both are stored **per user** in `~/.local/state/truffle/` (only readable by you), never in the shared folder or the CSV.

## Saved check results

The PING results (with their ms), and your last ssh attempts with the reason they failed, each with its time, are saved per user in
`~/.local/state/truffle/status`. After a restart they're shown again until the next check, and **details** shows when
each one was taken. Several TRuffle windows merge their results, and the newest one wins.

## Export

`Ctrl-E` writes the **current list** (filter and order as on screen) to `truffle-export-<date>-<time>.csv`
in your home directory (`export_dir` in the [configuration](#configuration)). It contains:
- all CSV columns
- **Ping** with its round-trip time in ms, and your last **SSH** attempt with the reason it failed, each with its time

A name that already exists is never overwritten — the next export becomes `...-2.csv`.

Example: search `ping:down`, press `Ctrl-E`, and you have the list of switches that didn't answer.
The file uses the switch list's delimiter, opens directly in Excel, and is readable only by you.

## Data check

`truffle --check` checks the switch list and shows the CSV line of every problem:
- rows with more or fewer fields than the header (often a `;` inside a comment, which shifts the columns)
- names or IPs that appear more than once
- missing IPs, unusable hosts, invalid IPv4 addresses (`10.0.0.300`), leading zeros (`010.0.0.5`, which ping reads as octal)

TRuffle also says so at startup when the list has warnings.

It reports obsolete options from an older `truffle.conf` too (they are ignored, not applied).

**Exit codes**, so you can run it from cron or a pipeline:

| Code | Meaning |
|---|---|
| `0` | everything fine |
| `1` | the switch list has warnings (duplicates, bad addresses, shifted columns) |
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
| `--version` | show the version |

`--debug` writes to `debug.log` in the state directory; `truffle --check` prints that path.

## Team setup

No system-wide install is needed. Put the TRuffle directory where your colleagues can read it, e.g.
`/srv/netops/truffle`, together with one `data.csv` and an optional `truffle.conf` for team defaults.
Everyone runs the same `truffle`. Passwords, favourites, history and logs stay per user.

## Single-file bundle

To move TRuffle without git, e.g. as a mail attachment, pack it into one plain-text file:

```bash
python3 tools/make-bundle.py          # creates dist/truffle-bundle-<version>.py
```

**Bump `VERSION` in `truffle` before building a bundle whose contents changed.** The version is part of
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
`~/.local/state/truffle/logs/<date>-<time>_<switch>.log`, readable only by you.
The log contains what was on screen, never the password TRuffle typed. Commands like
`show running-config` can still put secrets into it.

## Debug log

`truffle --debug` — or **`Ctrl-G`** inside TRuffle, when a switch starts misbehaving and you don't
want to restart — appends a short report of every ssh login to `~/.local/state/truffle/debug.log`
(readable only by you):
- the ssh command
- which password prompts TRuffle saw
- whether it typed the password
- exit code and the reason for a failure
- the switch's output **before** the login (banner, prompts)

The password and the session itself are never in it.

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
- **Forgotten after 10 hours.** The password is dropped 10 hours after you **typed** it and you're asked
  again (`password_lifetime` in minutes, `0` turns it off). It's measured from when you typed it, not from
  your last keypress, so a window left running for days can't keep a live login — but it never expires in
  the middle of a working day.
  **It only deletes the password inside TRuffle.** A switch session you're sitting in keeps running, and
  tmux panes keep running and stay logged in. Nothing in your workspace is touched.
- **Once you type in a session,** TRuffle stops watching. A later `Password:` prompt on the switch is never answered for you.
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
| F-keys don't sort | Click the column header |
| TRuffle says *"no password prompt recognised"* | The switch words its prompt differently, so you have to type the password yourself. Run `truffle --debug`, connect again, and send the "before login" part of the [debug log](#debug-log) — the prompt pattern can then be adjusted |
| Login works with plain ssh but not in TRuffle | Start with `truffle --debug`, try again, and look at the [debug log](#debug-log) |
| Screen garbled | `Ctrl-L` |
| Not sure what's wrong | `truffle --check` |

## Development

```bash
python3 -m unittest discover -s tests -v
```

- `tests/fake_ssh.py` acts as a switch (password `secret`, a changed host key, a timeout).
  Point `ssh_command` at it in a test config.
- Design rules: [STYLE.md](STYLE.md).
