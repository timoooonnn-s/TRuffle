# TRee-Li: Switch Manager

```
 _____  ____                      _      _
|_   _||  _ \   ___   ___        | |    (_)
  | |  | |_) | / _ \ / _ \ _____ | |    | |
  | |  |  _ < |  __/|  __/|_____|| |___ | |
  |_|  |_| \_\ \___| \___|       |_____||_|
```

*by Timmy & Ruffy*

Search your switch list, ssh into a switch, log out, and you're back in the list,
all inside the terminal of a Linux server you reach over SSH (PuTTY, Tabby, ...).

- **One file, Python 3 standard library only.** No pip, no venv, no root.
- **Password asked once per session.** It stays in memory only and is forgotten when TRee-Li exits.
- **After you log out of a switch, you're back in TRee-Li.**

Inspired by [V-Li: Switch Manager](https://github.com/seismicindustries/switch-manager).
TRee-Li keeps its menu, but runs ssh inside your terminal instead of a new desktop window.

**[Quick start](#quick-start)**: up and running in five minutes.
**[Reference](#reference)**: everything in detail.

---

# Quick start

### 1. Check the requirements

On the server: Linux, **Python 3.8 or newer** (`python3 --version`), the OpenSSH client and `ping`.

### 2. Get TRee-Li

```bash
git clone <repo-url> ~/tree-li
```

Any directory works, for example a [shared team folder](#team-setup).
No git on the server? Use the [single-file bundle](#single-file-bundle) instead.

### 3. Add your switches

```bash
cd ~/tree-li
cp data.example.csv data.csv
```

Then put your switches into `data.csv`: one line per switch, at least `Name` and `IP`
([format](#switch-list-datacsv)). Check it, including a [data check](#data-check) for duplicates and typos:

```bash
./tree-li --check
```

### 4. Start it

```bash
./tree-li
```

To start it from anywhere with just `tree-li`, add an alias:

```bash
echo "alias tree-li='$HOME/tree-li/tree-li'" >> ~/.bashrc
```

### 5. Use it

1. **Type** to filter the list. A few letters are enough: `bc01` finds `ber-core-01`.
2. Pick a switch with **↑ ↓**. **ssh** is already selected, so press **Enter**.
3. Enter your username and password **once**. TRee-Li logs you in, now and for every following switch.
4. **Log out** of the switch, and you're back in the list.
5. **← →** selects the other commands (ping, batch ping, details, help, exit).

All keys: [Keys](#keys) or the **help** command inside TRee-Li. If something looks wrong, see [Troubleshooting](#troubleshooting).

---

# Reference

- [Screen](#screen)
- [Keys](#keys)
- [Commands](#commands)
- [Search](#search)
- [Several switches at once (tmux)](#several-switches-at-once-tmux)
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
  TRee-Li  Switch Manager                                     timmy · 2/29 switches
───────────────────────────────────────────────────────────────────────────────────

   ssh   ping   batch ping   details   help   exit

  ›  ber core

    NAME          IP            SUBNET    ALIAS                COMMENT    PING ▲  SSH
    ─────────────────────────────────────────────────────────────────────────────────────────
 ▌* ber-core-01   192.0.2.1     ber       Core switch Berlin   5520       ● down  ● failed
    ber-core-02   192.0.2.7     ber       Core switch Berlin   VSP7400    ● up    ● ok

───────────────────────────────────────────────────────────────────────────────────
  Enter run  ←→ command  ^F favourite  F1-F6 sort  ^R reload  ^C quit
```

From top to bottom:
- **Top bar:** your login user once you've connected, and how many switches are shown.
- **Command tabs.**
- **Search line.**
- **Table:**
  - `▌` marks the selected row.
  - `*` marks a [favourite](#favourites-and-recent-switches).
  - `▲`/`▼` shows the sorted column.
  - **PING** shows the last ping result. **SSH** shows how your last real ssh attempt went: `ok` or `failed`.
    TRee-Li never tests SSH on its own, so there's no extra traffic.
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
| `ESC` | step by step: 1. clears the search, 2. cancels a running batch ping, 3. clears the sort |
| `F1` … `F7` | sort by that column: ▲ ascending → ▼ descending → original order |
| `Ctrl-F` | mark / unmark the selected switch as a [favourite](#favourites-and-recent-switches) |
| `Tab` / `Shift-Tab` | mark / unmark a switch for [several at once](#several-switches-at-once-tmux) (`+`) |
| `Ctrl-T` | back into the running [tmux session](#several-switches-at-once-tmux) |
| `Ctrl-E` | [export](#export) the current list to a CSV file |
| `Ctrl-R` | reload the switch list |
| `Ctrl-L` | redraw the screen |
| `Ctrl-C` | quit |

In full-screen output (ping, details, help): `↑` `↓` `PgUp` `PgDn` scroll, and `ESC` / `Enter` / `q` closes.

**Mouse:**
- **Click:** a row or tab selects it.
- **Right-click:** marks a row for [several at once](#several-switches-at-once-tmux).
- **Double-click:** runs the selected command (e.g. ssh on a switch).
- **Column header:** sorts by that column.
- **Wheel:** scrolls.

While TRee-Li has the mouse, PuTTY and Tabby select text only with **Shift** held down. If you'd rather keep normal selection, set `mouse = no`.

## Commands

| Command | What it does |
|---|---|
| **ssh** | Connects to the selected switch. The first time, TRee-Li asks for username and password (see [Security](#security)). Log out to come back; `~.` at the start of a line force-closes a hanging session. |
| **ping** | `ping -c 4` with live output; also updates the Ping column. |
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
| `ping:down` | ping state: `up`, `down`, `wait`, or `none` (not checked yet) |
| `ssh:failed`, `ssh:ok` | outcome of your last ssh attempt to that switch, or `none` (never tried) |
| `is:fav` | your favourites |
| `is:recent` | switches you connected to, newest first |

Example: `type:core -ber ping:up ssh:failed` shows core switches outside Berlin that answer ping but where your last ssh attempt failed.

## Several switches at once (tmux)

> **Experimental**, on the `tmux-version` branch. Needs `tmux` on the server. Turn it off with `tmux = no`.

Mark switches with **`Tab`** (or right-click), then run **ssh**. With **two or more** marked, TRee-Li opens its
own tmux session with **one pane per switch**, up to **9**. You type your password **once** and every pane
logs in by itself.

| You want | Press |
|---|---|
| mark / unmark a switch | `Tab` (`Shift-Tab` marks the one above) |
| clear all marks | `ESC` (with an empty search) |
| **back to TRee-Li**, panes keep running | `Ctrl-b d` |
| **back into the panes** | `Ctrl-T` in TRee-Li |
| switch between panes | `Ctrl-b o`, or `Ctrl-b` and an arrow key |
| make one pane full screen (and back) | `Ctrl-b z` |
| log out of one switch | `exit` in that pane; its pane closes |
| close everything at once | `Ctrl-b &` (asks first) |

When the last pane is gone the tmux session ends by itself and you are back in TRee-Li.
The tmux status bar shows these keys while you are in the session, and each pane border carries its switch name.

**From any shell**, the sessions are normal tmux sessions named `tree-li-HHMMSS`:

```bash
tmux ls                              # which are still running
tmux attach -t tree-li-143052        # go back into one
tmux kill-session -t tree-li-143052  # close one and its logins
```

**They keep running after you detach.** That is the point — a dropped PuTTY connection does not lose your
sessions — but it also means switches stay logged in. TRee-Li shows `N tmux` in the top bar while any of
its sessions are alive, and names them again when you quit.

**How the single login works, and what it costs:** panes are started by tmux, so their command line is
visible to every user on the machine (`ps`) and cannot carry the password. Each pane gets a one-time ticket
instead and fetches the login through a Unix socket in a private directory. Before answering, TRee-Li asks
the kernel who is connecting and replies only to **your own user** and to **the exact process tmux started**,
once, within 15 seconds. The socket is deleted as soon as the panes have their login.
Anything running as *your* user could still ask for it during those seconds — that is the trade-off of the
single login. Set `tmux = no` if you would rather type the password per pane.

## Favourites and recent switches

- `Ctrl-F` marks a switch as a favourite (`*`). Favourites are listed first as long as no column is sorted.
  During a search, better matches come first and favourites only win ties.
- Every successful login is remembered. Find those switches with `is:recent`, or see "Last connected" in **details**.
- Both are stored **per user** in `~/.local/state/tree-li/` (only readable by you), never in the shared folder or the CSV.

## Saved check results

The PING results and your last ssh attempts (SSH), each with its time, are saved per user in
`~/.local/state/tree-li/status`. After a restart they're shown again until the next check, and **details** shows when
each one was taken. Several TRee-Li windows merge their results, and the newest one wins.

## Export

`Ctrl-E` writes the **current list** (filter and order as on screen) to `tree-li-export-<date>-<time>.csv`
in your home directory (`export_dir` in the [configuration](#configuration)). It contains:
- all CSV columns
- **Ping** and your last **SSH** attempt, each with its time

Example: search `ping:down`, press `Ctrl-E`, and you have the list of switches that didn't answer.
The file uses the switch list's delimiter, opens directly in Excel, and is readable only by you.

## Data check

`tree-li --check` checks the switch list and shows the CSV line of every problem:
- rows with more or fewer fields than the header (often a `;` inside a comment, which shifts the columns)
- names or IPs that appear more than once
- missing IPs, unusable hosts, invalid IPv4 addresses (`10.0.0.300`), leading zeros (`010.0.0.5`, which ping reads as octal)

TRee-Li also says so at startup when the list has warnings.

It reports obsolete options from an older `tree-li.conf` too (they are ignored, not applied).

**Exit codes**, so you can run it from cron or a pipeline:

| Code | Meaning |
|---|---|
| `0` | everything fine |
| `1` | the switch list has warnings (duplicates, bad addresses, shifted columns) |
| `2` | cannot run: switch list missing or unreadable, or `ssh` / `ping` not installed |

```bash
./tree-li --check || echo "please fix the switch list"
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

## Configuration

Everything is optional. All options with explanations are in [`tree-li.conf.example`](tree-li.conf.example).
TRee-Li reads these files in order, and later ones win:

1. `tree-li.conf` next to the `tree-li` script: team defaults (git-ignored)
2. `~/.config/tree-li/tree-li.conf`: your personal settings
3. the file given with `--config FILE`

| Command line | Effect |
|---|---|
| `--data CSV` | use another switch list |
| `--debug` | write what happens around each ssh login to a [debug log](#debug-log) |
| `--log` | turn on [session logging](#session-logging) |
| `--ascii` | plain ASCII instead of lines and symbols ([why](#colours-and-symbols)) |
| `--check` | check config, switch list ([data check](#data-check)) and required tools, then exit |
| `--version` | show the version |

`--debug` writes to `debug.log` in the state directory; `tree-li --check` prints that path.

## Team setup

No system-wide install is needed. Put the TRee-Li directory where your colleagues can read it, e.g.
`/srv/netops/tree-li`, together with one `data.csv` and an optional `tree-li.conf` for team defaults.
Everyone runs the same `tree-li`. Passwords, favourites, history and logs stay per user.

## Single-file bundle

To move TRee-Li without git, e.g. as a mail attachment, pack it into one plain-text file:

```bash
python3 tools/make-bundle.py          # creates dist/tree-li-bundle-<version>.py
```

**Bump `VERSION` in `tree-li` before building a bundle whose contents changed.** The version is part of
the file name, so two different bundles must never share one. `make-bundle.py` refuses to overwrite an
existing bundle that has different contents and tells you to bump; `--force` overrides that.

On the server, copy the bundle into the folder you want to update and run it there:

```bash
cd ~/tree-li                       # e.g. your git checkout
python3 tree-li-bundle-<version>.py
git status                         # if it's a git checkout: review, commit, push
```

| Run | Effect |
|---|---|
| `python3 tree-li-bundle-<version>.py` | inside an existing TRee-Li folder: **updates it in place**; anywhere else: unpacks into `./tree-li` |
| `python3 tree-li-bundle-<version>.py DIR` | unpacks / updates exactly in `DIR` |
| `python3 tree-li-bundle-<version>.py --list` | only shows what's inside |

- **Damage check:** a checksum catches a damaged attachment before anything is written.
- **Removed files:** files that a newer version no longer has are removed, but only files a bundle installed
  (they're listed in `.tree-li-files`).
- **Never touched:** `.git`, `data.csv`, `tree-li.conf` and your own files.
- **No accidental downgrade:** if the folder already holds a newer TRee-Li, the bundle says so and asks before
  installing the older one.
- **Not committed by accident:** the bundle file and `.tree-li-files` are in `.gitignore`.

## Session logging

Off by default. Turn it on with `--log` or `session_log = yes`. Each ssh session is written to
`~/.local/state/tree-li/logs/<date>-<time>_<switch>.log`, readable only by you.
The log contains what was on screen, never the password TRee-Li typed. Commands like
`show running-config` can still put secrets into it.

## Debug log

`tree-li --debug` appends a short report of every ssh login to `~/.local/state/tree-li/debug.log`
(readable only by you):
- the ssh command
- which password prompts TRee-Li saw
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

- **Memory only.** The password lives only in the memory of the running TRee-Li. It never goes to disk,
  command lines or environment variables, so it isn't visible in `ps`.
- **Memory protected:**
  - TRee-Li switches off crash dumps for itself, so a crash can't write the password to a file.
  - On Linux it also marks itself "not dumpable", so other programs of your own user can't attach to it or read its memory.
  - root still can, as with every program.
- **Typed once, only at a real prompt.** TRee-Li types it once per connection, only at a real password prompt,
  and never at an SSH-key passphrase prompt. If it does not recognise the switch's prompt it types **nothing**
  and says so afterwards, so you always know whether the auto-login fired.
- **Wrong password:** ssh is stopped right away instead of retrying, the stored password is wiped,
  and you're asked again. This protects a central (TACACS+/RADIUS) account from lockouts.
- **Once you type in a session,** TRee-Li stops watching. A later `Password:` prompt on the switch is never answered for you.
- **Host keys:** new switches are added to `~/.ssh/known_hosts` automatically. If a key **changes**,
  TRee-Li asks before removing the old one. That's expected after a hardware swap, but can also mean an attack.
- **CSV values** never pass through a shell, and hosts that look like command-line options (`-o...`) are rejected.

## Troubleshooting

| Problem | Fix |
|---|---|
| `switch list not found` | `cp data.example.csv data.csv`, or set `data =` in `tree-li.conf` |
| `python3\r: No such file or directory` or `Permission denied` after copying via Windows | `sed -i 's/\r$//' tree-li; chmod +x tree-li`, or start it with `python3 tree-li` |
| Old switch: `no matching key exchange method` / `host key type` | e.g. `ssh_options = -o KexAlgorithms=+diffie-hellman-group14-sha1 -o HostKeyAlgorithms=+ssh-rsa`. On RHEL 9 the system crypto policy may also need to allow SHA-1 |
| Lines or symbols look like `â”€` or `?` | `--ascii` / `charset = ascii`, or PuTTY *Window → Translation* → UTF-8 |
| Only a few colours in PuTTY | PuTTY *Connection → Data → Terminal-type string* → `xterm-256color` |
| F-keys don't sort | Click the column header |
| TRee-Li says *"no password prompt recognised"* | The switch words its prompt differently, so you have to type the password yourself. Run `tree-li --debug`, connect again, and send the "before login" part of the [debug log](#debug-log) — the prompt pattern can then be adjusted |
| Login works with plain ssh but not in TRee-Li | Start with `tree-li --debug`, try again, and look at the [debug log](#debug-log) |
| Screen garbled | `Ctrl-L` |
| Can't select text with the mouse | Hold **Shift** while selecting, or set `mouse = no` |
| Not sure what's wrong | `tree-li --check` |

## Development

```bash
python3 -m unittest discover -s tests -v
```

- `tests/fake_ssh.py` acts as a switch (password `secret`, a changed host key, a timeout).
  Point `ssh_command` at it in a test config.
- Design rules: [STYLE.md](STYLE.md).
