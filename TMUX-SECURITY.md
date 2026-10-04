# Is the tmux single login safe?

**Short answer: yes, and this page explains exactly why, in plain terms.**

When TRee-Li opens several switches at once it puts each one in its own tmux pane and logs
them all in from the password you typed once. That means the password is handed from one
process to another, and "passing a password between processes" is the kind of sentence that
should make an engineer suspicious. Good. This page is the honest answer to that suspicion.

It is written for engineers who do not spend their days in Linux internals. Every Linux
concept it relies on is explained where it is first used. Nothing here asks you to take
"trust us" for an answer.

**Contents**

- [The verdict in one box](#the-verdict-in-one-box)
- [What the feature actually does](#what-the-feature-actually-does)
- [Four things you need to know about Linux first](#four-things-you-need-to-know-about-linux-first)
- [How the handover works, step by step](#how-the-handover-works-step-by-step)
- ["But the ticket is visible in `ps`!"](#but-the-ticket-is-visible-in-ps)
- [Who could get the password?](#who-could-get-the-password)
- [What we do NOT claim](#what-we-do-not-claim)
- [The thing that is actually riskier than the password](#the-thing-that-is-actually-riskier-than-the-password)
- [This is not a new invention](#this-is-not-a-new-invention)
- [What has been tested and what has not](#what-has-been-tested-and-what-has-not)
- [If you are still not comfortable](#if-you-are-still-not-comfortable)

---

## The verdict in one box

> To steal the password out of the handover, an attacker must **already be running as your
> own user account on that server**. And if they are, they do not need the password: they can
> read your keystrokes, or simply type `tmux attach` and land in switch sessions that are
> *already logged in*.
>
> In other words: the handover does not open a door. It is behind a door that, once open,
> makes the handover irrelevant.

There is one real risk in this feature, and it is not cryptographic — it is that about 80
lines of security-relevant code were written in-house. That is why it has not been merged into
`main` and why a second engineer reviews it before anyone else uses it. See
[What has been tested](#what-has-been-tested-and-what-has-not).

---

## What the feature actually does

You mark 3 switches and press `ssh`. TRee-Li:

1. starts a tmux session with one pane per switch,
2. gives each pane the information it needs to log in,
3. each pane runs `ssh` to its switch and types the password at the prompt,
4. and then the password is no longer needed by anybody but TRee-Li itself.

Step 2 is the whole question. **Why can't TRee-Li just put the password on the pane's command
line?** Because command lines on Linux are public — see the next section. So it cannot, and it
does not. Everything below is how step 2 is done instead.

---

## Four things you need to know about Linux first

### 1. Command lines are public. File permissions are not.

Anyone logged in on a Linux box can run `ps aux` and see the **full command line** of every
process, including other people's. So any secret placed in a command line is effectively
published to everyone on that machine. This is also why `sshpass` is a bad idea, and it is the
first design constraint here.

Files, by contrast, have an owner and permission bits. `0600` means "only the owner may read
or write". `0700` on a *directory* means "only the owner may even look inside". Those are
enforced by the kernel, not by the application, so a program cannot be tricked into ignoring
them.

### 2. A "Unix socket" is a file, not a network port

TRee-Li uses a **Unix domain socket**. Despite the name, this is not networking:

- it has **no IP address and no port**, so nothing can reach it from another machine — not
  from the office LAN, not from the internet, not from another server;
- it appears in the filesystem as a special file, and therefore it **has owner and permission
  bits like any other file**;
- on Linux, connecting to it requires write permission on that file.

So "the password travels over a socket" does **not** mean it goes on the network. It never
leaves the machine, and it never even leaves a directory only you can open.

### 3. `/run/user/<your-uid>` is a private, RAM-only folder

On RHEL (and every modern systemd Linux) the system creates a folder for each logged-in user:

```
/run/user/1001        owned by you, mode 0700, on a RAM filesystem (tmpfs)
```

Three properties matter:

- **0700, owned by you** — no other user can even list it, let alone open files in it;
- **tmpfs = RAM** — its contents never touch a disk, so they cannot end up in a backup, a
  snapshot, or on a decommissioned drive;
- **it is deleted when your last session ends** — nothing can be left behind for later.

TRee-Li creates its socket in a fresh randomly-named subfolder in there, also `0700`, and the
socket itself is `0600`.

### 4. The kernel knows who is calling, and the caller cannot lie about it

This is the important one, and it is the part most people do not know exists.

When a process connects to a Unix socket, the program on the other end can ask the kernel:
*"who is this?"* On Linux this is `SO_PEERCRED`; it returns the connecting process's **user ID
and process ID**.

The crucial detail: **the kernel fills those in, not the connecting program.** There is no
message a client can send to claim a different identity, the way an HTTP client can send any
`User-Agent` it likes. It is not a claim that gets verified; it is a fact that gets reported.

---

## How the handover works, step by step

```
    TRee-Li (holds the password)
        |
        |  creates /run/user/<uid>/tree-li-XXXX/handover.sock
        |          directory 0700, socket 0600, in RAM
        |
        |  for each pane: one random 128-bit one-time ticket
        |
     tmux  ──starts──>  pane 1    pane 2    pane 3
                           |
                           |  connects to the socket, sends "GET <ticket>"
                           v
    TRee-Li answers ONLY IF all of these hold:
        1. the kernel says the caller's user ID is mine
        2. the ticket exists
        3. the ticket has never been used before
        4. the ticket is less than 15 seconds old
        5. the kernel says the caller's process ID is the process
           tmux reported for THAT ticket (or its direct parent)
        |
        |  -> sends user + password, once
        v
    socket closed and deleted as soon as every pane has its login
```

Then each pane runs `ssh` and types the password at the switch's prompt — exactly what you do
by hand, and exactly what TRee-Li already does for a single switch.

Note condition 5. It is the one that does the real work, and it is explained next.

---

## "But the ticket is visible in `ps`!"

**Yes. On purpose. The ticket is not the secret.**

This is the single most common objection, and it is worth being very clear: we know the ticket
is public, we designed around it, and the design does not rely on it being hidden.

Run `ps` while panes are starting and you will see something like:

```
tree-li --pane /run/user/1001/tree-li-a9f3/handover.sock 7c1e...  10.0.3.12  ber-dist-02
```

A hostile process running as you could copy that ticket and ask for the password. Here is what
happens when it does:

```
$ (attacker, running as you, with a stolen ticket)
  connect  -> allowed, same user
  GET 7c1e...
  <- ERR wrong process
```

It is refused, because the ticket is **bound to the process ID that tmux started for that
pane**. TRee-Li asked tmux "what is this pane's process ID?" and will only answer a caller
whose kernel-reported process ID matches. An attacker cannot present someone else's process
ID — see point 4 above.

For it to succeed, the attacker would have to *be* that pane process (or its parent) — which
means already controlling your tmux server. At that point they are inside your session and can
read what you type anyway.

So the layers are: **the folder keeps other users out, the kernel's user check keeps other
users out a second time, and the process check keeps *your own* stray processes out.** The
ticket just says *which* request is which.

---

## Who could get the password?

| Who | Can they? | Why |
|---|---|---|
| Someone on another machine / the network | **No** | A Unix socket has no port. There is nothing to connect to from off-box |
| Another user on the same server | **No** | Two independent barriers: a `0700` folder they cannot open, and the kernel user-ID check. Either one alone is sufficient |
| A backup, a snapshot, a disk | **No** | The folder is in RAM (tmpfs) and is deleted at logout. A socket has no file contents to read |
| A crash dump / core file | **No** | TRee-Li disables core dumps for itself, so a crash cannot write the password to disk |
| **Another program running as you** | **Practically no** | It can read the ticket from `ps` and is then refused by the process check. To pass it, it must already control your tmux server — from where it could read your keystrokes instead |
| Someone who debugs the running TRee-Li | **No** | On Linux, TRee-Li marks itself "not dumpable", which stops other programs *of your own user* from attaching a debugger or reading its memory |
| **root** | **Yes** | See below |

### About root

Root can read the password. Root can also read the memory of any program, attach a debugger to
your `ssh`, record your terminal, or read the TACACS+ logs. **This feature gives root nothing
it did not already have**, so "root could read it" is not an argument about this feature — it is
the normal condition of running software on a machine someone else administers.

---

## What we do NOT claim

Being straight about the limits is the point of this page.

1. **For a few seconds, the password exists in up to 9 more processes.** Each pane holds it
   just long enough to type it at the switch's prompt. That is genuinely more exposure than
   typing it nine times by hand. It is small, and it is bounded by the checks above, but it is
   not zero.
2. **Python cannot reliably wipe a string from memory.** Once TRee-Li drops the password it is
   unreachable and will be reused and overwritten by the running program, but we cannot promise
   the bytes are gone at a particular instant. No Python program can. This is why core dumps
   are disabled and why the process is marked not-dumpable — those are the mitigations that
   actually work.
3. **Once a pane runs `ssh`, that `ssh` process holds the password briefly, like always.**
   Starting a program resets the "not dumpable" protection, so `ssh` is a normal process here.
   This is **identical** to typing your password into `ssh` yourself — the handover does not
   make it worse.
4. **`ps` reveals which switches you are connecting to** (host and name are on the pane's
   command line). That is no different from a normal `ssh -l user 10.0.3.12`, which is equally
   visible, so nothing new is disclosed.
5. **A mistyped password is spent on the panes you opened.** All panes log in at once, so if
   the password is wrong, each of those switches sees one failed attempt. TRee-Li then drops
   the password and asks again, so the damage stops there instead of continuing onto the next
   switch you visit. (`ssh` is also told to allow exactly one attempt per connection, so a
   central TACACS+/RADIUS account cannot be walked into a lockout.)

---

## The thing that is actually riskier than the password

Honest prioritisation matters more than a long list of reassurances, so here is the part that
deserves your attention more than the handover does.

When you press `Ctrl-b d` to leave tmux, **the panes keep running and those switch sessions
stay logged in.** That is the point of the feature — a dropped PuTTY connection does not cost
you your work — but it means that for as long as they live, anyone who can run commands as you
on that server can type `tmux attach` and be on those switches **with no password at all**.

That is worse than leaking a password, because it skips authentication entirely and produces no
new login record to audit.

**Why this is nevertheless fine here:** our switches drop an idle session after **900 seconds
(15 minutes)**, so the window is minutes, not hours or days. On top of that:

- TRee-Li shows `N tmux` in its top bar the whole time any of its sessions are alive, and names
  them again when you quit, so you cannot forget them silently;
- `Ctrl-K` closes them all from inside TRee-Li after a confirmation;
- TRee-Li forgets the password **10 hours after you typed it** regardless of what you are
  doing, so a window left running for days cannot keep a live credential. (That only deletes
  the password from TRee-Li. Sessions you are in and panes that are running are never touched.)

---

## This is not a new invention

The pattern used here — a `0600` socket inside a `0700` directory, plus a kernel-verified
check of who is connecting — is the same shape as tools you already rely on:

| Tool | What it holds | How a program asks for it |
|---|---|---|
| `ssh-agent` | your unlocked SSH private keys | a Unix socket in a `0700` directory (`$SSH_AUTH_SOCK`) |
| `gpg-agent` | your unlocked GPG keys | a Unix socket under `/run/user/<uid>` |
| **TRee-Li** | one password, for ~15 seconds | a Unix socket under `/run/user/<uid>`, plus a one-time ticket bound to the specific process |

If `ssh-agent` holding your private keys all day behind a socket is acceptable — and on every
Linux workstation it is — then TRee-Li holding one password behind the same mechanism *plus* a
one-time, process-bound, 15-second ticket is not a step down. If anything the ticket binding is
a check `ssh-agent` does not make.

---

## What has been tested and what has not

**Tested:** 14 automated tests cover the security properties directly, rather than assuming
them — that a valid request works exactly once, that a reused ticket is refused, that a
stolen ticket from the wrong process is refused, that an unknown ticket is refused, that an
expired ticket is refused, that an unbound ticket is never answered, that the folder is `0700`
and the socket has nothing for group or others, that closing really removes the socket so
nothing can connect afterwards, and that the kernel user/process lookup genuinely works on this
platform instead of silently failing open. Two further end-to-end tests drive the real program
in a real tmux session and confirm that two marked switches do share one login, that **no pane
command line contains the password**, and that a pane which cannot log in makes TRee-Li drop it.

**The honest open items:**

1. **In-house code.** About 80 lines of this are security-relevant and were written for this
   tool. The *pattern* is proven; this *implementation* has only had one reviewer. A second
   engineer reviews it before anyone beyond the author uses it. This is the real reason the
   feature sits on an unmerged branch rather than in `main`.
2. **Company policy.** Whether passing credentials between processes is permitted at all is a
   policy question, not a technical one, and it can rule this out no matter how sound the code
   is. Worth confirming with whoever owns that policy before a wider rollout.

---

## If you are still not comfortable

You do not have to use it, and turning it off costs you nothing else:

```ini
# tree-li.conf
tmux = no
```

With that set, TRee-Li never shares a password between processes. You connect to one switch at
a time, exactly as before.

There is also a middle option that was deliberately kept on the table: **each pane asks for its
own password.** That removes the socket, the ticket and all 80 lines of handover code, at the
cost of typing your password up to nine times. If the review in point 1 above comes back
unhappy, that is the fallback — not dropping multi-switch work altogether.

Questions, or something in here that looks wrong? Raise it. A design that cannot survive being
questioned by a colleague is not a design worth shipping.
