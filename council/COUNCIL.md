# The Council

| Seat | Role | Mandate |
|---|---|---|
| **Drafter** | Chair | Owns the current plan (`PLAN.md`), turns decisions into concrete next steps, leads the others, and closes debates |
| **Architect** | Builder | Writes the code, owns the structure and the implementation choices |
| **Researcher** | Knowledge | Investigates every open question and maintains `KNOWLEDGE.md` |
| **Critic** | Second thought | Challenges a step only when there is a real mistake or gap. Once a decision is made, it is accepted |
| **Operator** | User advocate *(added)* | Represents the network admin at 3 a.m. over a laggy PuTTY session. Guards "stupid to use", keystroke count, and clear error messages |
| **Tester** | Verification *(added at build time)* | Unit tests, the fake switch, tmux end-to-end runs. Owns Milestone 2 together with the user |
| **Warden** | Security *(added)* | Handles credentials in memory, the shell-injection surface, host keys and logging. Covers the area where a "simple tool" can quietly leak passwords |

**Membership rule:** a seat that adds noise instead of value gets removed. New seats are added when the scope changes (e.g. a *Tester* once there is code to verify).

## Standing rules

These hold for every decision and every seat. They are not up for re-debate each time; a
proposal that breaks one is either changed or dropped.

### R1: As few dependencies as possible (user, 2026-10-04)

Use the fewest external libraries and dependencies possible. The default is the Python 3
standard library and the tools already on the server (`ssh`, `ping`, `tmux`).

A dependency may be added **only** when it makes things clearly **easier, more secure, or
brings another clear benefit** - and the proposer has to name that benefit out loud. "It is
nicer", "everyone uses it" and "it saves a few lines" are not benefits. Weigh the cost
honestly: on a locked-down RHEL server every `pip install` is a ticket, a review and a thing
that can break on the next patch day, and TRuffle's whole promise is "copy one file".

Order of preference:
1. the standard library
2. a tool that is already installed on the target server (call it, do not wrap it)
3. a vendored single file we can read in full and own
4. an external package - only with a stated benefit and the Warden's agreement if it
   touches credentials, the terminal or a socket

This is why D2 (stdlib only, one file) and D3 (the system `ssh` binary in a pty, instead of
paramiko or `sshpass`) look the way they do. R1 is the general rule behind both.

### R2: RHEL Linux is the target, macOS is only a test bench (user, 2026-10-04)

Every feature has to work on **RHEL Linux**, because that is where TRuffle actually runs.
Local development and testing happens on macOS, which makes macOS support a convenience,
never the yardstick.

- "works on my Mac" is not evidence. Anything platform-specific needs the Linux path written
  first and the macOS path second, and both have to be stated in the code.
- Existing split paths to keep in mind: `ping -W` (seconds on Linux, milliseconds on macOS),
  `SO_PEERCRED` vs. `LOCAL_PEERCRED`/`LOCAL_PEERPID`, `parent_pid()` via `/proc/<pid>/stat`
  vs. `ps`, `PR_SET_DUMPABLE` (Linux only), `XDG_RUNTIME_DIR` (`/run/user/<uid>` on Linux).
- The supported Pythons are the ones RHEL ships: 3.8 / 3.9 upwards (RHEL 9's `python3` is
  3.9). No syntax or stdlib call that is newer than 3.8.
- A feature that can only work on macOS does not get built.

## Log
- 2026-10-02: Council formed. Operator and Warden added because the core features (one-time credentials, simplicity) sit exactly on their fields.
- 2026-10-02: Tester added once there was code. Review: Operator and Warden both changed real decisions (D3, D5, D9, D10), so both stay.
- 2026-10-04: Council reconvened for review round 5. Standing rules R1 (as few dependencies as possible) and R2 (RHEL is the target, macOS is only a test bench) written down after the user stated both. All seven seats kept: the Architect found the crash, the Warden found the unreported pane login failure, the Operator found the lying "N marked" counter. No seat was silent, so none is removed.
