#!/usr/bin/env python3
"""Stand-in for `ssh` in the tests: behaves like a switch, chosen by host.

  10.99.0.1  password "secret", then a small CLI ("exit" ends the session with
             exit code 255 like many switches do; "pwtest" prints a password prompt;
             "denied" prints "Permission denied" like a rejected command)
  10.99.0.2  host key changed while $HOME/.ssh/known_hosts mentions 10.99.0.2
  10.99.0.3  connection timeout
  10.99.0.6  connection timeout with the macOS wording ("Operation timed out")
  10.99.0.7  like .1, but its banner after the login ends in "password:"
  10.99.0.8  like .1, but the password prompt takes 0.6 s (a slow connect)
  10.99.0.4  hangs while connecting until it is killed (press Ctrl-C), like an
             unreachable switch before ConnectTimeout
  10.99.0.9  terminal server: user "<name>:70NN", password "secret", then silent until
             Enter; behind it, by line NN:
               01  a switch: "Login:" / "Password:" (secret), "exit" -> "Login:" again
               02  a console somebody left logged in: Enter shows "FAKE-CON:1>" only
               03  a switch that only takes the local account admin / local123
               04  a switch whose RADIUS server is away: the password takes 2 s
Every invocation's argv is appended to $FAKE_SSH_ARGV (if set).

Like the real ssh, the terminal stays in line mode while logging in (password prompts)
and is switched to RAW mode once the session starts - TRuffle relies on exactly that to
know a session started.  In raw mode the "switch" echoes what you type itself.
"""
import os
import signal
import sys
import termios
import time
import tty


def read_secret(prompt):
    """ssh's own password prompt: line mode, echo off."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    new = termios.tcgetattr(fd)
    new[3] &= ~termios.ECHO
    termios.tcsetattr(fd, termios.TCSADRAIN, new)       # echo off BEFORE the prompt, like ssh
    sys.stdout.write(prompt)
    sys.stdout.flush()
    try:
        line = sys.stdin.readline()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    sys.stdout.write("\n")
    return line.rstrip("\r\n")


class Session(object):
    """The remote side once ssh is logged in: the local terminal is raw, the far end
    echoes and ends its lines with CR LF."""

    def __enter__(self):
        self.old = termios.tcgetattr(0)
        tty.setraw(0)
        return self

    def __exit__(self, *exc):
        termios.tcsetattr(0, termios.TCSADRAIN, self.old)

    def write(self, text):
        os.write(1, text.replace("\n", "\r\n").encode())

    def read_line(self, prompt="", echo=True):
        """One line, or raises EOFError when the terminal is gone."""
        self.write(prompt)
        line = b""
        while True:
            try:
                ch = os.read(0, 1)
            except OSError:
                ch = b""
            if not ch:
                raise EOFError
            if ch in (b"\r", b"\n"):
                self.write("\n")
                return line.decode("utf-8", "replace")
            line += ch
            if echo:
                os.write(1, ch)


def console_cli(s):
    """The switch CLI on the serial line; returns when you log out."""
    s.write("\n")
    while True:
        cmd = s.read_line("FAKE-CON:1>").strip()
        if cmd in ("exit", "logout"):
            return
        if cmd:
            s.write("you typed: %s\n" % cmd)


def terminal_server(user, host):
    name, _, port = user.partition(":")
    pw = read_secret("%s@%s's password: " % (user, host))
    if pw != "secret" or not port.startswith("70"):
        sys.stderr.write("%s@%s: Permission denied (password).\n" % (user, host))
        return 255
    line = port[2:]
    with Session() as s:
        try:
            s.read_line(echo=False)                        # the line is silent until Enter
            if line == "02":
                console_cli(s)
                return 0
            while True:
                login = s.read_line("\nLogin: ")
                if not login:
                    continue
                pw = s.read_line("Password: ", echo=False)
                if line == "04":
                    time.sleep(2)
                ok = (login, pw) == (("admin", "local123") if line == "03" else (name, "secret"))
                if not ok:
                    s.write("Login incorrect\n")
                    continue
                console_cli(s)
        except EOFError:
            return 0


def switch_cli(host):
    with Session() as s:
        s.write("\nExtreme Networks Fabric Engine (fake)\n\n")
        if host == "10.99.0.7":
            s.write("Reminder: never share your password:")
        try:
            while True:
                cmd = s.read_line("FAKE-SW:1>").strip()
                if cmd in ("exit", "logout"):
                    break
                if cmd == "pwtest":
                    s.write("got %r\n" % s.read_line("Enter password:", echo=False).strip())
                elif cmd == "denied":
                    s.write("Permission denied\n")
                elif cmd:
                    s.write("you typed: %s\n" % cmd)
        except EOFError:
            return 0
    sys.stdout.write("Connection to %s closed by remote host.\n" % host)
    return 255


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)      # Ctrl-C kills it like it kills ssh: exit 130
    args = sys.argv[1:]
    if os.environ.get("FAKE_SSH_ARGV"):
        with open(os.environ["FAKE_SSH_ARGV"], "a") as f:
            f.write(repr(args) + "\n")
    host = args[-1]
    user = args[args.index("-l") + 1] if "-l" in args else "nobody"
    one_try = "NumberOfPasswordPrompts=1" in args

    if host == "10.99.0.9":
        return terminal_server(user, host)
    if host in ("10.99.0.3", "10.99.0.6"):
        time.sleep(0.5)
        sys.stderr.write("ssh: connect to host %s port 22: %s timed out\n"
                         % (host, "Connection" if host == "10.99.0.3" else "Operation"))
        return 255
    if host == "10.99.0.4":
        time.sleep(30)                         # Ctrl-C (SIGINT from the line discipline) ends it
        return 255
    if host == "10.99.0.2":
        kh = os.path.join(os.path.expanduser("~"), ".ssh", "known_hosts")
        if os.path.exists(kh) and host in open(kh).read():
            sys.stderr.write(
                "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@\n"
                "@    WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!     @\n"
                "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@\n"
                "Offending ED25519 key in %s:1\n"
                "Host key verification failed.\n" % kh)
            return 255

    if host == "10.99.0.8":
        time.sleep(0.6)
    tries = 0
    while True:
        tries += 1
        pw = read_secret("%s@%s's password: " % (user, host))
        if pw == "secret":
            break
        if one_try or tries >= 3:
            sys.stderr.write("%s@%s: Permission denied (publickey,keyboard-interactive).\n" % (user, host))
            return 255
        sys.stdout.write("Permission denied, please try again.\n")
    return switch_cli(host)


if __name__ == "__main__":
    sys.exit(main())
