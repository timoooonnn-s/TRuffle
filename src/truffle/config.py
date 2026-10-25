"""truffle.conf -> Config.  Every option is documented in truffle.conf.example."""

import configparser
import dataclasses
import getpass
import locale
import os
import re
import shlex
import time

from . import INSTALL_DIR

CONFIG_NAME = "truffle.conf"
CONFIG_SECTION = "truffle"

# How long TRuffle keeps the password, in minutes from when it was TYPED (D28): THE one
# number to change for the whole team (truffle.conf: password_lifetime).  600 = one working
# day, 0 = until exit.  Expiry never touches a running session or tmux pane.
PASSWORD_LIFETIME_MINUTES = 600

DEFAULTS = {
    "data": "data.csv",
    "columns": "Name, IP, subnet, aliases:Alias, comment",
    "user": "",
    "ssh_command": "ssh",
    "ssh_options": "",
    "connect_timeout": "10",
    "session_log": "no",
    "log_dir": "~/.local/state/truffle/logs",
    "log_keep_days": "180",
    "state_dir": "",
    "ping_timeout": "1",
    "password_lifetime": str(PASSWORD_LIFETIME_MINUTES),
    "charset": "auto",
    "tmux": "yes",
    "console_hosts": "*-*-ts?-*",
    "console_login": "{user}:{port}",
    "console_port_base": "7000",
    "console_login_wait": "240",
}
PATH_OPTIONS = ("data", "log_dir", "state_dir")       # relative = relative to the file that set it
CHARSET_SETTINGS = ("auto", "unicode", "ascii")


class ConfigError(Exception):
    pass


@dataclasses.dataclass
class Config:
    """The resolved settings.  The Ctrl-G screen changes session_log, debug, tmux and
    charset_setting while TRuffle runs; nothing is ever written back to truffle.conf."""
    files: list                 # the config files that were read, in order
    data: str                   # the switch list
    columns: list               # [(CSV header, table label)]
    user: str
    ssh_command: list
    ssh_options: list
    connect_timeout: int
    session_log: bool
    log_dir: str
    log_keep_days: int          # session logs older than this are deleted at start, 0 = never
    state_dir: str
    ping_timeout: int
    password_lifetime: int      # minutes, 0 = until TRuffle exits
    charset_setting: str        # auto / unicode / ascii
    tmux: bool
    console_hosts: list         # lower-case name patterns of terminal servers
    console_login: str          # "{user}:{port}"
    console_port_base: int
    console_login_wait: int
    debug: bool = False
    config_file: str = None     # --config FILE, passed on to tmux panes
    started: float = dataclasses.field(default_factory=time.time)   # logs since then are "this session's"

    @property
    def charset(self):
        """The symbol set in use: 'unicode' or 'ascii'."""
        return resolve_charset(self.charset_setting)

    @property
    def debug_log(self):
        return os.path.join(self.state_dir, "debug.log")


def resolve_charset(setting):
    """auto -> unicode when the terminal speaks UTF-8, else ascii.  Needs setlocale() first."""
    if setting != "auto":
        return setting
    encoding = (locale.getpreferredencoding(False) or "").lower().replace("-", "").replace("_", "")
    return "unicode" if encoding == "utf8" else "ascii"


def parse_bool(value, option):
    v = value.strip().lower()
    if v in ("1", "yes", "true", "on"):
        return True
    if v in ("", "0", "no", "false", "off"):
        return False
    raise ConfigError("%s: expected yes or no, got '%s'" % (option, value))


def parse_int(value, option, lo, hi):
    try:
        n = int(value)
    except ValueError:
        raise ConfigError("%s: expected a number, got '%s'" % (option, value))
    if not lo <= n <= hi:
        raise ConfigError("%s: must be between %d and %d" % (option, lo, hi))
    return n


def parse_columns(spec):
    """'Name, aliases:Alias' -> [('Name', 'Name'), ('aliases', 'Alias')]"""
    columns = []
    for part in spec.split(","):
        key, _, label = part.partition(":")
        key, label = key.strip(), label.strip()
        if key:
            columns.append((key, label or key))
    if not columns:
        raise ConfigError("columns: at least one column is required")
    return columns


def valid_user(user):
    """A user name that cannot pass for an ssh option.  ':' is allowed (terminal servers)."""
    return bool(user) and not user.startswith("-") and re.match(r"^[^\s\x00-\x1f\x7f@]+$", user) is not None


def default_user():
    try:
        return getpass.getuser()          # already looks at $LOGNAME, $USER, ... first
    except Exception:
        return ""


def user_config_path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "truffle", CONFIG_NAME)


def read_config_files(paths):
    """Merge the [truffle] sections of the files that exist.  Returns (raw values, the
    folder each path option was set in, files read)."""
    raw, bases, read = dict(DEFAULTS), {}, []
    for path in paths:
        if not os.path.isfile(path):
            continue
        parser = configparser.ConfigParser(interpolation=None)
        try:
            with open(path, encoding="utf-8-sig") as f:
                parser.read_file(f, source=path)
        except (configparser.Error, OSError, UnicodeDecodeError) as e:
            raise ConfigError("cannot read %s: %s" % (path, e))
        if not parser.has_section(CONFIG_SECTION):
            raise ConfigError("%s: missing the [%s] section" % (path, CONFIG_SECTION))
        for key, value in parser.items(CONFIG_SECTION):
            if key not in DEFAULTS:
                raise ConfigError("%s: unknown option '%s'" % (path, key))
            raw[key] = value.strip()
            if key in PATH_OPTIONS:
                bases[key] = os.path.dirname(os.path.abspath(path))
        read.append(path)
    return raw, bases, read


def resolve_path(value, base):
    """~ is expanded; a relative path is relative to `base`, NEVER the current directory
    (D7) - otherwise it depends on where truffle happened to be started."""
    return os.path.normpath(os.path.join(base, os.path.expanduser(value)))


def load_config(args):
    """Defaults <- truffle.conf next to the launcher <- ~/.config/truffle/truffle.conf
    <- --config FILE <- command line."""
    paths = [os.path.join(INSTALL_DIR, CONFIG_NAME), user_config_path()]
    if args.config:
        if not os.path.isfile(args.config):
            raise ConfigError("config file not found: %s" % args.config)
        paths.append(args.config)
    raw, bases, files = read_config_files(paths)

    data = resolve_path(raw["data"] or DEFAULTS["data"], bases.get("data", INSTALL_DIR))
    if args.data:
        data = os.path.abspath(os.path.expanduser(args.data))     # typed on the command line: the CWD is meant
    state_home = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    state_dir = (resolve_path(raw["state_dir"], bases.get("state_dir", INSTALL_DIR)) if raw["state_dir"]
                 else os.path.join(state_home, "truffle"))
    user = raw["user"] or default_user()
    if user and not valid_user(user):
        raise ConfigError("user: '%s' is not a valid user name" % user)
    try:
        ssh_command = shlex.split(raw["ssh_command"]) or ["ssh"]
        ssh_options = shlex.split(raw["ssh_options"])
    except ValueError as e:
        raise ConfigError("ssh_command/ssh_options: %s" % e)
    charset = "ascii" if args.ascii else (raw["charset"] or "auto").lower()
    if charset not in CHARSET_SETTINGS:
        raise ConfigError("charset: use auto, unicode or ascii")
    console_login = raw["console_login"] or DEFAULTS["console_login"]
    if "{port}" not in console_login or re.search(r"\{(?!user\}|port\})", console_login):
        raise ConfigError("console_login: use {user} and {port}, e.g. {user}:{port}")

    return Config(
        files=files,
        data=data,
        columns=parse_columns(raw["columns"]),
        user=user,
        ssh_command=ssh_command,
        ssh_options=ssh_options,
        connect_timeout=parse_int(raw["connect_timeout"], "connect_timeout", 1, 300),
        session_log=args.log or parse_bool(raw["session_log"], "session_log"),
        log_dir=resolve_path(raw["log_dir"], bases.get("log_dir", INSTALL_DIR)),
        log_keep_days=parse_int(raw["log_keep_days"], "log_keep_days", 0, 3650),
        state_dir=state_dir,
        ping_timeout=parse_int(raw["ping_timeout"], "ping_timeout", 1, 30),
        password_lifetime=parse_int(raw["password_lifetime"], "password_lifetime", 0, 1440),
        charset_setting=charset,
        tmux=parse_bool(raw["tmux"], "tmux"),
        console_hosts=[p.lower() for p in re.split(r"[\s,]+", raw["console_hosts"]) if p],
        console_login=console_login,
        console_port_base=parse_int(raw["console_port_base"], "console_port_base", 0, 65000),
        console_login_wait=parse_int(raw["console_login_wait"], "console_login_wait", 10, 900),
        debug=args.debug,
        config_file=args.config,
    )
