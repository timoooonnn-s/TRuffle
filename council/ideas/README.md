# Ideas: not decided, not built

These are parked here so nothing gets lost. Each entry has a status. Nothing in this folder is part of TRee-Li.

| Idea | Status | Details |
|---|---|---|
| **Several switches in tmux panes** (mark with Tab, one pane per switch, single login via a handover) | **built on the `tmux-version` branch**, experimental, not merged - the user is trying it out | [tmux-panes.md](tmux-panes.md) |
| Quick connect from the shell: `tree-li bc01` | idea | fuzzy-find and connect directly (one match) or open with that search (several) |
| Forget the password after N idle minutes | idea, *Warden*: mandatory if tmux sessions ever run in the background | |
| Run show commands on many switches (read-only, confirmation step, limited parallel logins) | idea, big | outputs one file per switch |
| Config backup (`show running-config` into dated files) | idea | builds on the previous one |
| Wrong-IP warning (switch prompt vs. CSV name) | idea | |
| Latency column in batch ping | idea | |
| LLDP neighbours, jump to neighbour | idea | Fabric Engine-specific parsing |
| Tree view by site / location | idea | |
| Copy IP to clipboard (OSC 52) | idea | works in Tabby, partly in PuTTY |
| Live monitor (repeat batch ping every N minutes) | **probably not**: the network already has good monitoring, and the noise concern applies | |
| Active SSH reachability test | **rejected** (D20): too noisy, the monitoring noticed it | |
