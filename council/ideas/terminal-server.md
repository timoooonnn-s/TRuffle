# Terminal server / console server access

**Status: UNDER DISCUSSION with the user (2026-10-19).** Nothing built. The open question is
whether the inventory should record which switch sits on which console line, see
[The inventory question](#the-inventory-question).

## How the login works (confirmed by the user, 2026-10-19)

A terminal server is reached with ssh like a switch, but the **username carries the line**:

```
ssh <user>:70XX@<terminalserver>
```

- `<user>` is the normal username.
- `XX` is the **physical line number** on the terminal server: line 12 → `7012`.
- The **password is the same** as for the switches, so the password TRuffle already holds is reused.
- This applies **only to terminal servers**. A normal switch never gets a `:70XX` username.

## What TRuffle can already do

- `build_ssh_argv` passes the username as `-l <user>`, never through a shell, and `valid_user`
  rejects `@` but allows `:`. So `ssh -l timmy:7012 -- <terminalserver>` works today with no
  special handling. The new work is choosing **when** TRuffle logs in this way and **which line**.
- The automatic password entry, `~.` to force-close, session logging and `--debug` all work unchanged.

**The one catch:** ping and SSH results are stored **per host** (`set_status("ssh", dev.host, ...)`).
Every line on one terminal server has the same address, so if a console login wrote into the SSH
column, the terminal server or the switch would show `ssh ok` when it is not. Console results
need their own storage, keyed by terminal server **and** line.

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
| Leaving a session | Logging out of the switch CLI leaves the console line open. `~.` closes ssh and drops you back in TRuffle. The help text gets one line about this. |
| tmux / marks | Possible later by passing the line through to `pane_main`. **Not part of the first version.** |

## Still to find out

- **The terminal server's password prompt.** Does it look like a normal ssh prompt
  (`timmy:7012@ber-ts-01's password:`) that `is_password_prompt` already recognises? One
  `truffle --debug` connection to a real terminal server answers this.
- **What "line busy" looks like** (text and exit code), so the CON result can say `busy` instead of `failed`.
- **Line numbers above 99:** do our terminal servers have more than 99 lines, and does `7000 + line` still hold then?
- **What the terminal server shows right after login.** A console often stays silent until you
  press Enter. Check that TRuffle doesn't mistake that silence for a failed login.

## Effort

Option A: about 60–80 lines (the console command, the line dialog, the login template, the CON
result) plus tests against `tests/fake_ssh.py`. Option C on top: about 40–60 more (two columns, the
lookup, the `--check` rules). Standard library only (R1), nothing platform-specific (R2).
