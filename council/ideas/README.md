# Ideas: not decided, not built

These are parked here so nothing gets lost. Each entry has a status. Nothing in this folder is part of TRuffle.

Every idea is measured against the standing rules in [COUNCIL.md](../COUNCIL.md#standing-rules):
**R1** as few dependencies as possible, **R2** RHEL Linux is the target (macOS is only a test bench).

| Idea | Status | Details |
|---|---|---|
| **Several switches in tmux panes** (mark with Tab, one pane per switch, single login via a handover) | **built on the `tmux-version` branch**, experimental, not merged - the user is trying it out | [tmux-panes.md](tmux-panes.md) |
| **Serial multi-connect** (mark N switches, connect one after another, no tmux) | **under discussion with the user** (2026-10-04) | [serial-connect.md](serial-connect.md) |
| ~~Bracketed paste~~ | **BUILT** (D28) | was [bracketed-paste.md](bracketed-paste.md); PuTTY support still to confirm with Ruffy |
| Quick connect from the shell: `truffle bc01` | idea | fuzzy-find and connect directly (one match) or open with that search (several) |
| ~~Forget the password after N idle minutes~~ | **BUILT** (D26, `password_timeout = 15`) | was the *Warden*'s condition for background tmux sessions |
| Per-device ssh option profiles (legacy crypto per switch, selected by a CSV column value) | **parked, not needed short term** (user, 2026-10-04) | [ssh-profiles.md](ssh-profiles.md) |
| ~~Latency (ms)~~ | **BUILT** (D28): own sortable `MS` column, slowest first | |
| `--check` shows the ssh crypto actually in force (`ssh -G`, local only, no traffic) | idea, cheap | answers the top troubleshooting row |
| ~~Keep the reason a ssh attempt failed~~ | **BUILT** (D28): saved, survives a restart, in details + export | the status file now takes 4 **or** 5 fields |
| Saved named searches (`filter.problems = ping:down ssh:failed`) | idea, **no consensus**: no free key (printables are the search, F1-F7 sort) | |
| Make the session log findable (show its path after a session) | idea, small | D22: session logging is the one feature with no demonstrated user |
| Run show commands on many switches (read-only, confirmation step, limited parallel logins) | idea, big | outputs one file per switch |
| Config backup (`show running-config` into dated files) | idea | builds on the previous one |
| Wrong-IP warning (switch prompt vs. CSV name) | idea | |
| Latency column in batch ping | idea | |
| LLDP neighbours, jump to neighbour | idea | Fabric Engine-specific parsing |
| Tree view by site / location | idea | |
| Copy IP to clipboard (OSC 52) | idea | works in Tabby, partly in PuTTY. The only reason to want a pointer back |
| ~~Mouse support~~ | **REMOVED** (D29): cost Shift-to-select daily for a rarely used click | |
| Session logging: keep or cut? | **kept for now** (user, 2026-10-04), reachable with `Ctrl-G` | still no demonstrated user; PuTTY and Tabby both log sessions natively and better |
| Live monitor (repeat batch ping every N minutes) | **probably not**: the network already has good monitoring, and the noise concern applies | |
| Active SSH reachability test | **rejected** (D20): too noisy, the monitoring noticed it | |
