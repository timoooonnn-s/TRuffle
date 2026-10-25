# Ideas: not decided, not built

These are parked here so nothing gets lost. Each entry has a status. Nothing in this folder is part of TRuffle.

Every idea is measured against the standing rules in [COUNCIL.md](../COUNCIL.md#standing-rules):
**R1** as few dependencies as possible, **R2** RHEL Linux is the target (macOS is only a test bench).

| Idea | Status | Details |
|---|---|---|
| **Several switches in tmux panes** (mark with Tab, one pane per switch, single login via a handover) | **BUILT and live** (D40, 2026-10-09) | [tmux-panes.md](tmux-panes.md) |
| **Serial multi-connect** (mark N switches, connect one after another, no tmux) | **under discussion with the user** (2026-10-04) | [serial-connect.md](serial-connect.md) |
| **Terminal server / console access** (`user:70XX@terminalserver`, XX = line number, then the switch's own login) | **BUILT and live** (D42, D47): used on the real terminal servers, "worked great" (user, 2026-10-25) | [terminal-server.md](terminal-server.md) |
| ~~Bracketed paste~~ | **BUILT** (D28), confirmed in PuTTY (user, 2026-10-25) | was [bracketed-paste.md](bracketed-paste.md) |
| ~~Quick connect from the shell: `truffle bc01`~~ | **not needed** (user, feature review 2026-10-25) | |
| ~~Forget the password after N idle minutes~~ | **BUILT, then changed**: D26 built `password_timeout` (idle minutes); now `password_lifetime = 600`, counted from when you typed it | was the *Warden*'s condition for background tmux sessions |
| **Device-group settings** (ssh options, user, ... per group of devices, selected by a CSV column value) - was "per-device ssh profiles" | **parked** (user, 2026-10-25): only if load balancers and other device types join the list - that is under discussion | [ssh-profiles.md](ssh-profiles.md) |
| Sort PING / SSH with more than ~10 columns (they are always the last columns, beyond `F12`) | **parked, keep in mind** (user, 2026-10-25): today 7 columns, so not a problem yet | [REVIEW-features.md](../REVIEW-features.md) B2 |
| ~~Latency (ms)~~ | **BUILT** (D28), **REMOVED** (D36): ping is a reachability check, the `MS` column had no job left | |
| `--check` shows the ssh crypto actually in force (`ssh -G`, local only, no traffic) | idea, cheap | answers the top troubleshooting row |
| ~~Keep the reason a ssh attempt failed~~ | **BUILT** (D28): saved, survives a restart, in details (the CSV export is gone, D35) | the status file now takes 4 **or** 5 fields |
| Saved named searches (`filter.problems = ping:down ssh:failed`) | idea, **no consensus**: no free key (printables are the search, F1-F7 sort) | |
| ~~Make the session log findable~~ | **BUILT** (D42): file name after a session, `Ctrl-G` `f`, the list at exit, `--logs`. Session logging is used daily now (user, 2026-10-25) | cleanup of old logs: [REVIEW-features.md](../REVIEW-features.md) M4 |
| Run show commands on many switches (read-only, confirmation step, limited parallel logins) | idea, big | outputs one file per switch |
| Config backup (`show running-config` into dated files) | idea | builds on the previous one |
| Wrong-IP warning (switch prompt vs. CSV name) | idea | |
| ~~Console from a down switch, by the site in its name~~ | **dropped** (user, D50): few console servers, mostly in the data centre, where the site blocks of the name hardly vary | [REVIEW-features.md](../REVIEW-features.md) M3 |
| ~~Latency column in batch ping~~ | **dropped**: batch ping is now `ping` with marks (D35), and the `MS` column was removed (D36) | |
| LLDP neighbours, jump to neighbour | idea | Fabric Engine-specific parsing |
| Tree view by site / location | idea | |
| Copy IP to clipboard (OSC 52) | idea | works in Tabby, partly in PuTTY. The only reason to want a pointer back |
| ~~Mouse support~~ | **REMOVED** (D29): cost Shift-to-select daily for a rarely used click | |
| ~~Session logging: keep or cut?~~ | **KEPT**: used daily (user, 2026-10-25) | |
| Live monitor (repeat the ping of the marked switches every N minutes) | **probably not**: the network already has good monitoring, and the noise concern applies | |
| Active SSH reachability test | **rejected** (D20): too noisy, the monitoring noticed it | |
