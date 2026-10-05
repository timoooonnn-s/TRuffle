# TRuffle Switch Manager: Knowledge Base

Maintained by **the Researcher**. Facts only; decisions go in `DECISIONS.md`.

---

## 1. Reference tool: V-Li Switch Manager (seismicindustries/switch-manager)

- Python 3 + **Textual 2.1.2 / rich** (10 pinned pip deps). One file `main.py` (~520 lines) + `switch_manager.css`.
- **Layout, top to bottom:** title bar → horizontal command bar → search field → table → status line.
- **Command bar, in this order:** `ssh` · `ping` · `traceroute` · `batch ping` · `details` · `help` · `exit`
- **Keys**
  - `↑/↓` select a row
  - `←/→` select a command
  - `Enter` runs the selected command on the selected row
  - any printable key jumps to the search field
  - `F1–F5` sort by column (press again to reverse the order)
  - `ESC` closes the output popup
- **Search:** the query is split on whitespace. Every token has to match (AND). Matching is a case-insensitive substring match over Name, IP, subnet, aliases and comment.
- **Table columns:** Name, IP, subnet, Alias (`aliases`), comment. The other CSV columns appear only in `details`.
- **Data:** CSV with a `;` delimiter. Header: `Name;IP;subnet;aliases;comment;type;id;responsible;aix_server`
- **Env vars:** `SM_USER` (ssh user), `SM_CSV_DATA` (default `data.csv`, resolved against the current working directory), `SM_DELIMITER`, `SM_DEBUG`.
- **Commands**
  - `ssh` opens a **new GUI terminal window** (osascript/Terminal.app, xterm or cmd.exe). This cannot work over an SSH session, and it is the main thing TRuffle has to replace.
  - `ping` streams the output of `ping -c 4`.
  - `traceroute` streams its output.
  - `batch ping` runs `ping -c 1` in parallel on all *filtered* rows and shows the combined text.
  - `details` dumps every column as `key: value`.

### Defects / lessons learned (the Critic)
- `launch_external_ssh` is defined twice.
- The IP is interpolated into an AppleScript string, so a crafted CSV field can inject commands.
- `data.csv` is resolved against the CWD, not the script location. Starting the tool from another directory gives an empty table and no error.
- `batch ping` reads only the `IP` key. Other code paths also accept `ip`.
- `batch ping` has no concurrency limit: 500 switches means 500 ping processes at once.
- There is no credential handling at all. The password is typed for every connection.
- Sorting depends on F-keys only. Some PuTTY keyboard modes send F1–F5 in ways that apps don't recognize, so a fallback key is needed.

---

## 2. Language / runtime options

| Option | Deps on target server | Pros | Cons |
|---|---|---|---|
| **Python 3 stdlib (`curses`, `pty`, `csv`)** | python3 (present on nearly every Linux server) | Single file, no pip. `pty` makes credential injection possible. Easy to read and patch. | Python version varies (3.6 on RHEL 7 / 3.9 on RHEL 9), so code must stay conservative |
| Bash + `whiptail`/`dialog` | whiptail (Debian/Ubuntu default; often missing on minimal RHEL) | Very "standard" | Hard to do live search and a table; dialog boxes don't fit the original menu UX. Can't feed passwords without `expect`/`sshpass` |
| Bash pure (tput) | none | Zero deps | Building a robust TUI with search in bash is fragile |
| Go single binary | none at runtime | Fully static | Needs a TUI library (external dep) and a build toolchain. Harder to patch on the server |

**Early recommendation:** Python 3, standard library only, one file, no pip. Status: pending confirmation of the server OS and Python version.

---

## 3. Entering the credentials once per session: mechanisms

| Mechanism | Works with | Notes |
|---|---|---|
| **Python `pty` relay** (expect pattern, stdlib) | every OpenSSH version, telnet, `enable` prompts | Spawns ssh in a pseudo-terminal, watches for the `password:` prompt, writes the password, then relays I/O transparently. The password stays in process memory and is never written to disk, argv or env. Must handle SIGWINCH (window resize), raw mode, and restoring the tty. |
| `SSH_ASKPASS` + `SSH_ASKPASS_REQUIRE=force` | OpenSSH **≥ 8.4** only | Not available on RHEL 8 (OpenSSH 8.0) or Ubuntu 20.04 (8.2). The helper also needs a way to get the secret. |
| `sshpass` | needs sshpass installed | External dep. `-e` passes the password via env (visible in `/proc/<pid>/environ` to the same user and root). |
| `expect` | needs expect/Tcl | External dep |
| SSH keys + ssh-agent | switches with key auth | Best practice, but switch fleets on TACACS+/RADIUS are usually password-only |

"Back in the menu after disconnect" comes for free with the pty/subprocess approach: `curses.endwin()`, run the session, then resume curses.

---

## 4. Legacy switch crypto (possible problem)
- OpenSSH 7.0 disabled `diffie-hellman-group1-sha1`. OpenSSH 8.8 disabled `ssh-rsa` (SHA-1) host key signatures.
- Old IOS/ProCurve may need `-oKexAlgorithms=+diffie-hellman-group14-sha1`, `-oHostKeyAlgorithms=+ssh-rsa`, `-oPubkeyAcceptedAlgorithms=+ssh-rsa`, `-oCiphers=+aes128-cbc`.
- On RHEL 9 the system crypto-policy can block SHA-1 even when those options are passed.
- Plan: per-device or global extra ssh options, configurable, not hard-coded.

---

## 5. Findings during the build (2026-10-02)
- **RHEL 9:** `/usr/bin/python3` is 3.9 (3.11 is an extra package, `python3.11`). The `#!/usr/bin/env python3` shebang therefore usually runs 3.9. Supported and tested.
- **Exit code 255 on logout:** network devices often close the channel without sending an exit status. See decision D9.
- **Fabric Engine / VOSS:** SSH password and keyboard-interactive auth are enabled by default. Older VOSS releases only offer RSA/DSA host keys, which may need `HostKeyAlgorithms=+ssh-rsa`.
  Sources: [VOSS: Enable SSH password authentication](https://documentation.extremenetworks.com/VOSS/SW/90/VOSSUserGuide/GUID-EA130EDE-AA9C-4171-8D4B-8744557DEBD5.shtml), [Control::CLI::Extreme](https://metacpan.org/pod/Control::CLI::Extreme)
- **PuTTY + ncurses line drawing** breaks under UTF-8, so TRuffle uses only ASCII chrome.
- **PuTTY default F-keys** are `ESC[11~`..`ESC[15~`. Under `TERM=xterm`, ncurses doesn't recognise them, so TRuffle parses them itself.
- **Python strings can't be wiped from memory.** The password object lives until the process exits (it is dropped on auth failure). This is acceptable for the threat model: same-user/root memory access already means game over.
- **ControlPersist in ~/.ssh/config** can keep the pty open after ssh exits. TRuffle also polls the child with `waitpid` so it doesn't hang.

---

## 6. Hard numbers from the field

| Fact | Value | Why it matters |
|---|---|---|
| **Switch idle timeout** | **900 seconds (15 min)** - confirmed by the user, 2026-10-04 | The number the whole tmux security case rests on. After `Ctrl-b d` the panes stay logged in, and anyone who can run commands as you could `tmux attach` into them without a password. That window is **15 minutes**, not hours - which is why the background-session risk (`ideas/tmux-panes.md` risk 5) is acceptable and why a tight password timeout was not needed. Quote this number in any security discussion rather than re-deriving it |

## 7. Field results (2026-10-04)

- **Tabby:** tested by the user. Works, nothing to change.
- **PuTTY:** tested and approved by Ruffy, the second engineer. So the bets taken for PuTTY hold in
  practice: TRuffle's own escape-sequence parser (default F-keys `ESC[11~`..`ESC[15~`, which ncurses
  does not recognise under `TERM=xterm`), ASCII-only UI chrome, the 8-colour fallback, and the login
  dialog drawing its own block cursor.
- **Still unverified:** the full ~700-switch inventory (batch ping timing, ssh pass, screen behaviour
  with a list that long). Everything so far was measured on small lists.
- **Platform reminder (R2):** development and these local test runs happen on macOS, the real
  deployment is RHEL. macOS-only evidence does not count as tested.

### The real inventory: Infoblox network export (2026-10-05)
The switch list comes from **Infoblox**, exported per network, not hand-written. First export's
header:
```
SUBNET,MASK,VLAN_ID,PRIMARY_DN_CODE,CREATION_DATE,Default-GW,Name-Server,WINS-Server,
BootP_NextServer,BootP_BootFile,MAC_ADDRESS,RFC_MAC_ADDRESS,ADDRESS
```
- **`PRIMARY_DN_CODE` is the hostname**, as an FQDN (`cd-34-s56-r1.prod...`).
- **`ADDRESS` is the switch's own address.** `SUBNET` is the network address and must never be used
  as the ssh target or the name - it is the same for every switch in that subnet.
- Comma-separated, `CREATION_DATE` is quoted, and most fields are empty. All auto-detected.
- **Hostname pattern: `xx-xx-sxx-xx`**, where each `x` can be any letter or digit, plus the domain
  suffix. Fuzzy search works well on it: `s56r` finds `cd-34-s56-r1` and `cd-34-s56-r2`.
- Still to come from Infoblox **extensible attributes (EAs)**: location and comments. They will
  appear as extra columns; only `columns` has to change when they do.
- Only `Name` and `IP` are actually wanted in the table (user, 2026-10-05).

### Terminal keys that never arrive (2026-10-04)
`curses.wrapper` puts the terminal in **cbreak**, which clears `ICANON` but **not `IEXTEN`**. So:
- `^U` (kill), `^W` (werase), `^R` (rprnt) are `ICANON`-only specials and **do** reach the
  application - which is why TRuffle has always been able to bind them.
- `^O` (**discard**, `VDISCARD`) and `^V` (lnext) are `IEXTEN` specials: the tty driver consumes
  them and curses never sees them. A shortcut bound to `^O` silently does nothing.
- Also unusable: `^S`/`^Q` (flow control - `^S` freezes the terminal), `^C` (intr), `^Z` (susp),
  `^D` (eof), `^\` (quit), and `^H`/`^I`/`^M` (which are Backspace/Tab/Enter).
- Free and safe, and why the settings page is on `Ctrl-G`: `^G`, `^A`, `^N`, `^P`, `^X`, `^Y`.
  Avoid `^B` as well - tmux eats it as its prefix when TRuffle runs inside tmux.

### Pane timestamps, the hard way (2026-10-04)
A tmux pane reporting a failed login writes its timestamp into the shared state directory. Written as
whole seconds (`%d`), a pane that fails in the *same second* the password was typed looks **older** than
that password, so the "is this failure about the password I am holding?" test fails and nothing happens.
Sub-second stamps fix it. Only the end-to-end test surfaced this - reading the code did not.
