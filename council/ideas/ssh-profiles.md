# Device-group settings (was: per-device ssh option profiles)

**Status: PARKED (user, 2026-10-25).** Not needed today: the only non-switch devices in the list are
the terminal servers, which are their own case. Picked up only if **load balancers and other device
types** join the list - that is under discussion in the team.

**The shape changed in the feature review (2026-10-25): per device GROUP, not per device.** A group
(`switch`, `loadbalancer`, ...) is selected by a CSV column value and carries its settings in
`truffle.conf` - ssh options, maybe another user, maybe "no ssh at all, ping only". The security rule
below stays: the shared CSV only ever holds the group's name.

The original note (2026-10-04) follows.

## The problem it would solve
`ssh_options` is global, so one old switch that needs `+diffie-hellman-group14-sha1` or
`+ssh-rsa` forces those options on all ~700. See [KNOWLEDGE.md](../KNOWLEDGE.md) section 4,
whose plan line ("per-device or global extra ssh options, configurable") was only ever built
for the global half.

## The shape the council agreed on
The options live in `truffle.conf`; the CSV only carries a **value that selects** one:

```ini
ssh_options.legacy = -o KexAlgorithms=+diffie-hellman-group14-sha1 -o HostKeyAlgorithms=+ssh-rsa
ssh_profile_column = type        # or a new "profile" column
```

A switch with `type = legacy` gets those options, everything else gets the defaults. An unknown
profile name is a `--check` warning.

## Why NOT free-form options in the CSV (*Warden*)
`data.csv` is a shared team file. Free-form ssh options there means anyone who can write it gets
`-o ProxyCommand=...`, i.e. command execution as every colleague who opens TRuffle - the same
class of hole as V-Li's AppleScript injection. The shared file must only ever hold a *name*.

## Effort
~30 lines plus tests. Also covers a jump host (`-J`), so no separate bastion feature is needed.
