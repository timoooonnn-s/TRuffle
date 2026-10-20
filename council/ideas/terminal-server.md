# Terminal server / console server access

**Status: BUILT as a prototype (D42, 2026-10-20)** on the branch `terminal-server`, not yet
tried on a real terminal server. Everything below the line "Discussion" is how we got there.

## What was built (user's decisions, 2026-10-19/20)

- **Option A, no inventory work:** the line is typed in a dialog, because the line numbers are
  documented elsewhere and change from time to time. The last line per terminal server is
  pre-filled, as a suggestion only.
- **Recognised by name:** `console_hosts = *-*-ts?-*` (`x` in `tsx` is always one digit).
- **Switch login choice in the same dialog:** `radius` (your login) / `local` (a local account,
  asked once and kept like the password) / `manual`. A refused login is typed once and then
  yours; **the password is kept** (user: "keep the password, let me log in manually").
- **Back to TRuffle:** logging out of the switch only brings back its `Login:` prompt, and today
  the user closes the whole terminal. Now TRuffle points at **`Ctrl-Q`** when the prompt comes
  back, and `Ctrl-Q` ends the session. Ctrl-Q, not Ctrl-]: `]` is AltGr on a Swiss keyboard.
- **No plain login to the terminal server** (an empty line is refused): plain ssh to it lands on
  the terminal server itself, which is not what this is for.
- The long wait for a switch whose RADIUS server is unreachable (user: "2-3 minutes"):
  `console_login_wait = 240`, with a note after a few seconds, any key takes over.
- Built together with **where the log files are**: `Ctrl-G` `f`, a list at exit, `truffle --logs`.

**Still to confirm on a real terminal server** (with `truffle --debug`, which now records both
logins' prompts): the exact switch prompts, what a busy line looks like, and whether a line ever
needs more than the two Enters TRuffle sends.

---

# Discussion

## How the login works (confirmed by the user, 2026-10-19)

A terminal server is reached with ssh like a switch, but the **username carries the line**:

```
ssh <user>:70XX@<terminalserver>
```

- `<user>` is the normal username.
- `XX` is the **physical line number** on the terminal server: line 12 → `7012`.
- The **password is the same** as for the switches, so the password TRuffle already holds is reused.
- This applies **only to terminal servers**. A normal switch never gets a `:70XX` username.

It is **two logins in one ssh session**:

| Step | Who asks | What you type |
|---|---|---|
| 1 | the terminal server (ssh) | password (the username already went in as `timmy:7012`) |
| 2 | - | **Enter**, which wakes up the serial line |
| 3 | the switch, over the serial line | username (`timmy`, without the `:7012`) |
| 4 | the switch | password (the same one) |

## What TRuffle can already do

- `build_ssh_argv` passes the username as `-l <user>`, never through a shell, and `valid_user`
  rejects `@` but allows `:`. So `ssh -l timmy:7012 -- <terminalserver>` works today with no
  special handling. The new work is choosing **when** TRuffle logs in this way and **which line**.
- `~.` to force-close, session logging and `--debug` work unchanged.
- The automatic password entry handles **step 1 only**. Steps 2–4 are new, see
  [It is two logins, not one](#it-is-two-logins-not-one).

**Another catch:** ping and SSH results are stored **per host** (`set_status("ssh", dev.host, ...)`).
Every line on one terminal server has the same address, so if a console login wrote into the SSH
column, the terminal server or the switch would show `ssh ok` when it is not. Console results
need their own storage, keyed by terminal server **and** line.

## It is two logins, not one

### What today's code does with it

`run_session` types the password at the **first** password prompt. A **second** password prompt is
taken as "wrong password": TRuffle kills ssh so that a wrong password is never sent twice (account
lockout). On a terminal server, the second password prompt is the **switch's**. So with today's
rules TRuffle would kill the session exactly when the switch asks for its password, **unless you
have typed something first**. Any keystroke from you stops the automation (on purpose), and you
have to press Enter (step 2) before the switch can ask anything. So in practice:

- **Step 1 already works today** with the right username.
- **Steps 2–4 you would type yourself**, and TRuffle stays out of the way.

That's level 1 below, and it costs almost nothing. Typing steps 2–4 for you as well is a new,
small login sequence of its own, not a tweak to the existing one.

### Two levels

**Level 1: TRuffle logs into the terminal server, you do the switch.** TRuffle types the terminal
server password, then hands the session over. You press Enter, type `timmy` and the password.
No new risk, very little new code.

**Level 2: TRuffle does both logins.** After step 1, TRuffle presses Enter itself, waits for the
switch's login prompt, types the username, waits for the password prompt, and types the password.
You land directly at the switch's CLI, just like with a normal ssh.

### The rules for level 2 (*Warden*)

The serial line is the dangerous part: **you can't know what's on it before you look.** The last
person may have left the console logged in (consoles often have no idle timeout). Then Enter gives a
CLI prompt, not a login prompt. Typing `timmy⏎secret⏎` there blindly would put the password into the
switch's CLI: as a "command not found" error, into the command history, maybe into a syslog message
to the log server, and onto the screen of anyone else attached to that line. So:

1. **Type only at a recognised prompt.** The username only after a line that ends like a login
   prompt (`login:`, `username:`). The password only after a password prompt that comes **directly
   after** the username TRuffle typed. Anything else (a CLI prompt, a boot menu, log messages, nothing)
   → TRuffle types nothing more, hands over and says why.
2. **One try.** If the switch asks for the login again or says "Login incorrect", stop and hand over.
   Never type the password a second time.
3. **Enter at most once** (twice at most, with a pause, if the first one only woke up the line).
   No login prompt within a few seconds → hand over.
4. **You typing takes over immediately**, same as today.

### The local account fallback (*Researcher*)

You usually need the console **when the switch is off the network**. Then it often can't reach the
RADIUS/TACACS server and falls back to its **local account**. Your normal password still works on
the terminal server (step 1), but the switch rejects it (step 4). So:

- A rejection at step 4 must **not** wipe the stored password: the terminal server has just accepted it.
- It must not be shown as a failed terminal server login either. The CON result says something
  like `switch login refused`, not `failed`.
- After the rejection you type the local account yourself. Storing local emergency accounts in
  TRuffle is **out of scope** (*Warden*: that would be a second, far more valuable secret to keep).
- To confirm with the user: do our switches fall back to a local account when AAA is unreachable?

## The options

### A. Ask for the line when connecting

A row that is a terminal server (recognised by a configurable column/value, e.g. `type = terminalserver`)
gets a **console** command. It asks for the line, then logs in as `<user>:70XX`:

```
  ╭─ Console · ber-ts-01 ─────────╮
  │  Line  12                     │
  ╰───────────────────────────────╯
```

- You type `12`, not `7012`: since XX is the line number, TRuffle does the `7000 +` itself.
- The last line you used on that terminal server is filled in.
- **Needs no inventory work.** Only the terminal servers have to be in `data.csv` and marked as such.
- The downside: you have to know the line. TRuffle can't tell you that `ber-core-01` is on line 12.

### B. One CSV row per console line

Rows like `ber-core-01-con;10.9.9.5;...;console_line=12`.

- Searchable, works with favourites, recents and tmux marks.
- **Not recommended:** the inventory doubles in size, every line is a fake "switch", and the
  duplicate-IP check in `--check` flags them all.

### C. The switch's own row says where its console is

Two new columns on the **switch's** row: `console_server` (the terminal server's name in the list,
or an address) and `console_line`. The **console** command then works right on the switch:

```
   ssh   console   ping   details   help   exit
```

`ber-core-01` shows `ping down`, you press → and Enter, and TRuffle logs you in as
`timmy:7012@ber-ts-01`. That's the actual use at 3 a.m.: the switch is gone from the network and
you need its console **without looking up where it is wired**.

- A and C share almost all their code. Only the source of the line differs, so C can be added to A later.
- Rows with empty console columns just have no console. **A partly filled inventory is fine.**

## Recommendation (Drafter)

**Build A first. Add C only if the inventory question is answered with "yes".**

A is useful on day one and needs nothing but the terminal servers in the list. C's columns stay
optional, so they can be filled in bit by bit (core switches first) without a big inventory project.

**For the two logins: ship level 1 with A, add level 2 afterwards.** Level 1 is nearly free and
already saves the terminal server password. Level 2 should only be built after one
`truffle --debug` session on a real terminal server has shown the exact prompts (see
[Still to find out](#still-to-find-out)), because its safety rules depend on recognising them.

## The inventory question

The user (2026-10-19): filling in console mappings for every switch would be a lot of extra work,
and that needs discussing before it's decided. Points for that discussion:

- **Only partly.** C works per row. Mapping only the core/distribution switches, the ones you
  actually need a console for, may cover most cases for a fraction of the work.
- **Maybe it already exists.** Many terminal servers let you give each line a name. If the lines
  are already labelled on the devices, an export of those labels could **generate** the mapping
  instead of typing it in. Worth checking what our terminal servers can export.
- **Wrong data is worse than missing data.** A mapping that is out of date sends you to the wrong
  console. Whoever re-cables a switch has to update the list too. If that won't happen, stay with A.
- `--check` can catch the worst mistakes (see below), but it can't tell that a cable has moved.

## Details agreed so far

| Topic | Proposal |
|---|---|
| Username format | Template in `truffle.conf`: `console_login = {user}:{port}`, with `console_port_base = 7000` so that line 12 becomes port `7012`. Other vendors (Opengear `user:port05`, Avocent `user:ttyS5`) only need a different template. |
| Where the format lives (*Warden*) | **Only in `truffle.conf`, never in the CSV.** Same rule as [ssh-profiles.md](ssh-profiles.md): the shared `data.csv` only holds plain values, never something that shapes the login. |
| Line value | Digits only (`^\d{1,3}$`). Anything else is a `--check` warning, and the console command refuses it. |
| Recognising a terminal server | A configurable column and value, e.g. `console_server_type = type:terminalserver`. The console command is greyed out on every other row. |
| Results | Their own **CON** result (`ok` / `failed` / `busy`), keyed by terminal server + line, never mixed into the SSH column. "Line in use by another user" gets its own reason in **details**. |
| `--check` (only with C) | Warns when a `console_server` matches no row, when a line is not a number, and when **two switches have the same terminal server and line** (almost always a copy-paste mistake). |
| Two logins | Level 1 (terminal server only) first, level 2 (switch as well) later, under the rules in [It is two logins, not one](#it-is-two-logins-not-one). |
| Leaving a session | Logging out of the switch CLI leaves the console line open. `~.` closes ssh and drops you back in TRuffle. The help text gets one line about this. |
| tmux / marks | Possible later by passing the line through to `pane_main`. **Not part of the first version.** |

## Still to find out

- **The terminal server's password prompt.** Does it look like a normal ssh prompt
  (`timmy:7012@ber-ts-01's password:`) that `is_password_prompt` already recognises? One
  `truffle --debug` connection to a real terminal server answers this.
- **What "line busy" looks like** (text and exit code), so the CON result can say `busy` instead of `failed`.
- **Line numbers above 99:** do our terminal servers have more than 99 lines, and does `7000 + line` still hold then?
- **What the terminal server shows right after login.** The line stays silent until you press
  Enter. Check that TRuffle doesn't mistake that silence for a failed login, and whether the
  terminal server shows a banner or menu first.
- **The switch's prompts over the console** (for level 2): the exact login and password prompt
  text, what "Login incorrect" looks like, and what Enter shows when the console is still logged in.
- **Local account fallback:** do our switches fall back to a local account when RADIUS/TACACS is
  unreachable? This decides how often level 2 will hand over at step 4.

## Effort

Option A with level 1: about 60–80 lines (the console command, the line dialog, the login template,
the CON result) plus tests against `tests/fake_ssh.py`. Level 2 on top: about 50–80 more (the login
sequence with its stop rules), plus a fake terminal server in the tests that covers each stop case:
already logged in, no prompt, login refused. Option C on top: about 40–60 more (two columns, the
lookup, the `--check` rules). Standard library only (R1), nothing platform-specific (R2).
