# linuxmuster-opnsense — OPNsense integration for linuxmuster.net 7.3

Rulebook of the hub: `../../CLAUDE.md`; package conventions: `../../docs/paket-konventionen.md`
(paths relative to this repo checked out under `linuxmusterDEV/packages/` or `worktrees/`).
Kevin speaks German; code, commits, changelog and CLI texts are English, `README.md` is German
(its audience are German school admins).

## Overview

| Component | Path | Stack |
|---|---|---|
| CLIs | `usr/sbin/opn-update-aliases`, `opn-captive-voucher`, `opn-captive-sessions` | Python 3.12, argparse, no `.py` extension |
| Library | `usr/lib/python3/dist-packages/linuxmusterOPNsense/` (`config.py` = `SchoolConfig`, `LinuxmusterOPNsenseAPI.py` = REST client, alias sanitizing/ownership) | requests |
| Hooks | `var/lib/linuxmuster/hooks/device-import.post.d/opn-update-all-schools` (base7 device import), `etc/linuxmuster/tools/hooks/group-manager/99_kill_wlan_sessions` (linuxmuster-tools GroupManager) | Python / bash |
| Config | `etc/linuxmuster/opnsense/default-school.ini.default`; one `<school>.ini` per school | INI |
| Packaging | `debian/` (`make deb`) | debhelper 13, dh-python, native 3.0, dist lmn73 |
| Tests | none yet (planned: `tests/` with pytest for `sanitize_alias_name`, `alias_owner_*`, `parse_time_to_seconds`, `_request`) | |

Runtime: the linuxmuster.net 7.3 server. Only `opn-update-aliases` imports `linuxmusterTools`
(`Devices`); the other CLIs need just `python3-requests` and a school INI.

## Constraints (do not violate)

- Version: the top entry of `debian/changelog` is the only hand-edited version (`7.3.N`, dist
  `lmn73`). Never bump it in a feature PR; Kevin bumps and tags `v7.3.N` at release (CI gate:
  tag == changelog version).
- Depends declare the linuxmuster line: `linuxmuster-tools7 (>= 7.3), linuxmuster-tools7 (<< 7.4)`.
- Alias names: OPNsense allows `[a-zA-Z0-9_]`, max 32 chars; go through `sanitize_alias_name`.
  Every managed alias carries the owner tag `[linuxmuster-opnsense school=<name>]`; an alias
  owned by another school is skipped with a warning and exit 1, never overwritten.
- API calls go through `_request`; HTTP 200 with `result=failed` is an error. Keep timeouts.
- CLI errors are printed in English and end with exit 1; `--help` must work without a config
  or firewall (the install smoke relies on it).
- No real-server or firewall actions outside the hub's lab workflow (`../../CLAUDE.md`,
  lock + snapshot first).

## Way of working

- Branch `feat/<topic>` or `fix/<topic>` from `main`; English conventional commits
  `type(scope): subject`.
- Fast tier locally before every commit (same as `.github/workflows/ci.yml`):
  `python3 -m py_compile <files> && ruff check <files> && shellcheck etc/linuxmuster/tools/hooks/group-manager/99_kill_wlan_sessions`
  (file list in `ci.yml`, `PY_FILES`; ruff 0.15.21, default rule set, snake_case).
- `make deb` builds the package (`.deb` lands one level up); CI builds in
  `ghcr.io/linuxmuster/lmndev-runner:24.04` as root and installs the result on ubuntu-24.04
  with `dpkg -i --ignore-depends=linuxmuster-tools7`.
- Lab test via the hub: `bin/lab-lock`, `bin/lab-snapshot`, `bin/lab-deploy lmn-test <deb>`,
  then `opn-update-aliases --school default-school` against the lab OPNsense (10.250.0.1);
  journal in `work/linuxmuster-opnsense/`.
- Changelog entry (`debian/changelog`, top block, `urgency=medium`) in the same PR as the
  change, written for admins.
