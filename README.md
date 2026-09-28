# Claude global configuration

This repository is the portable, tracked source for a personal Claude Code
workflow. It contains the global policy, custom agents and skills, helper
commands, and user-level settings that are installed under `~/.claude`.

The repository intentionally does not contain session transcripts, history,
caches, backups, authentication state, remote-runner host definitions, plugin
downloads, synced skills, or other generated and machine-specific state.

## Contents

- `CLAUDE.md` — global engineering and safety policy.
- `settings.json` — permissions and enabled-plugin preferences.
- `agents/` — focused implementer, read-only reviewer, adversarial
  security-reviewer, researcher, committer, and Graphify semantic agents.
- `hooks/review_agent_guard.py` — allowlist `PreToolUse` guard wired into the
  reviewer, security-reviewer, and researcher agents (see below).
- `skills/` — architecture-decision, Graphify workflow, security-review, and
  Verilog formal-verification (SymbiYosys) and simulation (Verilator)
  skills maintained with this configuration.
- `tests/` — regression tests for the helpers and the guard (see Testing).
- `bin/claude-workflow` — guarded Git and Graphify operations.
- `bin/remote-runner` — optional Git-backed remote test runner.
- `config-manifest.txt` — the complete allowlist installed into `~/.claude`.
- `install.sh` — an idempotent installer with dry-run, drift-check, and backup
  support.

## Prerequisites

Required:

- A POSIX-compatible environment
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
- Git
- Python 3.11 or newer (`remote-runner` uses the standard-library `tomllib`)

Recommended command-line tools are `rg` (ripgrep), `jq`, and `make`. Individual
projects may require additional language toolchains.

## Install

Clone the repository, review the files, and run:

```sh
./install.sh --dry-run
./install.sh
./install.sh --check
```

The installer copies only paths listed in `config-manifest.txt`. Before
replacing a differing destination file, it saves the old version under
`~/.claude/backups/claude-global-config-<UTC timestamp>/`. It never deletes
unmanaged files. The two helper commands are linked into `~/.local/bin`; use
`--no-link-bin` to skip those links. Ensure `~/.local/bin` is on `PATH`.

Set `CLAUDE_CONFIG_DIR` or `LOCAL_BIN_DIR` to test or install in alternate
locations:

```sh
test_root=$(mktemp -d)
CLAUDE_CONFIG_DIR="$test_root/.claude" LOCAL_BIN_DIR="$test_root/bin" ./install.sh
```

## Updating an installed configuration

Re-run `install.sh` whenever the tracked repository changes. The installer is
idempotent: it skips matching files, installs changed files, and backs up every
differing destination before replacement. A separate `--update` option is not
needed.

Before pulling, check from the repository root whether the working `~/.claude`
files have local changes that have not been mirrored:

```sh
./install.sh --check
```

A zero exit status means every managed working file matches the repository. A
nonzero result prints each differing path as `DIFF <path>`. Review and preserve
intentional live-only edits before continuing; otherwise a later install will
replace them, although the previous versions will be backed up.

For a normal repository-first update, run from the repository root:

```sh
./install.sh --check
git pull --ff-only
./install.sh --dry-run
./install.sh
./install.sh --check
```

Review the dry-run output before installation. The final check should print
`Configuration matches the tracked repository.` Restart Claude Code when an
updated policy, agent, skill, setting, or plugin needs a new session to load.

When a working file under `~/.claude` was intentionally edited first, do not
blindly run the installer. Copy the portable change into the corresponding file
in this repository, review it, run the relevant validation, and commit it. Then
run `./install.sh --check` to confirm both copies match.

The manifest is an installation allowlist, not a deletion list. Removing a path
from `config-manifest.txt` stops future installations but does not remove the
existing file from `~/.claude`; inspect and remove that working file separately
if it is no longer wanted. The installer also does not pull Git changes or
install, update, or remove external dependencies such as Claude Code,
Superpowers, Graphify, SSH configuration, or project toolchains. Update those
with their own documented commands and review their release notes separately.

To test an update without touching the working configuration, install into a
temporary destination first:

```sh
test_root=$(mktemp -d)
CLAUDE_CONFIG_DIR="$test_root/.claude" \
LOCAL_BIN_DIR="$test_root/bin" \
./install.sh
CLAUDE_CONFIG_DIR="$test_root/.claude" \
LOCAL_BIN_DIR="$test_root/bin" \
./install.sh --check
```

## Agent guard hook

`hooks/review_agent_guard.py` enforces, outside the prompt, what the review
agents may do. Each agent runs it as a `PreToolUse` hook in one mode:

- `reviewer` (`workflow-reviewer`): Bash is limited to read-only inspection and
  the repository's checks; Write and Edit are refused; credential files cannot
  be read.
- `security` (`security-reviewer`): the same, plus writes and script execution
  confined to the session scratchpad, for experiments on copies.
- `research` (`technical-researcher`): credential paths are refused, and web
  fetches must be short https URLs without credentials.

The guard is an allowlist over command text, not a sandbox: code an agent is
allowed to run, such as a repository's tests, is not confined. Anything it does
not recognize is denied. The hooks resolve the script through
`${CLAUDE_CONFIG_DIR:-$HOME/.claude}`.

## Testing

Run the regression tests from the repository root:

```sh
python3 -B -m unittest discover -s tests
python3 -B -m unittest discover -s skills/graphify-workflow/tests
```

Set `TOOLS_BIN` or `GUARD` to run the same tests against another copy of the
tools or the guard. The Graphify end-to-end tests need the `graphify` CLI on
`PATH`.

## Superpowers

The policy uses Superpowers for appropriate brainstorming, planning, TDD,
debugging, review, and verification workflows. Install the official plugin:

```sh
claude plugin install superpowers@claude-plugins-official
```

Restart Claude Code after installing or updating a plugin. Superpowers may
shape plan content, but this configuration keeps the sole active plan in
`docs/plans/next.md` unless repository-owned instructions explicitly choose a
different location.

## Graphify

Graphify is optional for narrow work but required by the `graphify-workflow`
skill and the graph-related `claude-workflow` commands. Install `uv`, then the
Graphify CLI package:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install graphifyy
graphify --version
```

The helper expects the `graphify` executable on `PATH`. Graph output is written
inside the target project under `graphify-out/` and should normally remain
untracked.

For queries, use one anchor and one relationship at a time. Prefer
`graph-explain` for component context, `graph-affected` for impact, and
`graph-path` between two known nodes; reserve `graph-query` for orientation when
the anchor is unknown. A `[!] TRUNCATED` result is incomplete rather than
failed: narrow to a returned node before raising the default 2,000-token budget,
and do not clip Graphify output with `head`, `tail`, or `cut`. One automatic
narrowing follow-up is allowed after truncation, and conclusions still require
verification against current repository files.

Semantic refreshes group ordinary sources by both file count and total byte
size, while exceptionally large sources receive their own chunk. Each semantic
worker must read every assigned source through EOF before writing, and its chunk
contains exact source/digest coverage receipts checked against the prepared
manifest. The parent accepts only an explicit completion handoff and treats the
validator's counts as authoritative. These checks detect missing, stale, or
partial coverage declarations; they do not prove the quality or completeness of
the worker's semantic interpretation.

## Optional remote runner

`remote-runner` needs Python 3, Git, SSH, and access to the project's Git
remote. Keep host-specific definitions outside this repository in either
`~/.claude/remotes.toml` or `~/.config/remote-runner/remotes.toml`. Each project
that uses it supplies `.claude/remote-runner.toml`. Do not commit credentials or
private host configuration here.

The controller streams its own Python worker over SSH. The remote host does not
need this repository installed, but it does need `python3`, Git, Bash, access to
the submitted repository's `origin`, and every tool used by the selected
profile command.

### Host configuration

Define machines in `~/.claude/remotes.toml`. If that file does not exist, the
runner falls back to `~/.config/remote-runner/remotes.toml`; when both exist,
the `~/.claude` file wins.

```toml
[remotes.buildbox]
ssh_host = "buildbox"
workspace_root = "~/runner-workspaces"
max_jobs = 2

[remotes.buildbox.capabilities]
os = "linux"
arch = "x86_64"
cpu_cores = 16
memory_gib = 64
labels = ["build", "test", "formal"]

[remotes.platform-builder]
ssh_host = "ci-user@platform-builder.example.net"
workspace_root = "~/runner-workspaces"
max_jobs = 1

[remotes.platform-builder.capabilities]
os = "macos"
arch = "arm64"
cpu_cores = 10
memory_gib = 32
labels = ["build", "platform-build"]
```

Each `[remotes.<name>]` table requires:

- `ssh_host`: an SSH destination accepted by `ssh`; an alias from
  `~/.ssh/config`, `user@host`, or another non-interactive destination works.
- `workspace_root`: a persistent directory on that host. The worker creates
  `projects/<project-id>/repo.git` for its bare cache and
  `jobs/<job-id>/worktree` for each detached checkout. A leading `~` expands on
  the remote host.
- `max_jobs`: the maximum number of live jobs accepted concurrently.

The optional `capabilities` table is used by `recommend` and `submit --best`.
Supported fields are `os`, `arch`, numeric `cpu_cores`, numeric `memory_gib`,
and an array of string `labels`. Values are declarations, not automatic host
discovery, so keep them accurate. Protect this file with normal user-only
permissions when it contains private hostnames:

```sh
chmod 600 ~/.claude/remotes.toml
ssh buildbox 'python3 --version && git --version && bash --version'
remote-runner remotes
```

SSH keys, agent configuration, known-host verification, repository credentials,
and host setup stay in their normal system locations; never put private keys or
tokens in the TOML file.

### Project configuration

Commit `.claude/remote-runner.toml` in each repository that uses remote jobs:

```toml
[project]
id = "example-project"

[profiles.fast]
command = "make test-fast"

[profiles.fast.requirements]
min_cpu_cores = 4
min_memory_gib = 8
labels = ["test"]

[profiles.full]
command = "make clean && make test-all"

[profiles.full.requirements]
os = "linux"
arch = "x86_64"
min_cpu_cores = 8
min_memory_gib = 16
labels = ["build", "test"]
```

The project `id` is required and may contain only letters, digits, `.`, `_`, and
`-`. It becomes part of remote cache and job paths, so keep it stable and unique
among projects using the same runner.

Every `[profiles.<name>]` needs a string `command`. The worker runs that command
from the clean, detached worktree through `bash -lc`; shell operators therefore
work, but the command is trusted code and should remain reviewable. Prefer a
short repository-owned command such as a Make target or checked-in script over
a long inline shell program. Do not embed credentials, machine-specific paths,
or destructive host maintenance in a profile.

The optional `[profiles.<name>.requirements]` table supports:

- `os` and `arch`: exact matches against the remote declarations.
- `min_cpu_cores` and `min_memory_gib`: numeric minimums.
- `labels`: every requested label must appear on the remote.

Omit `requirements` when any configured remote is suitable. Requirements only
filter selection; they do not install tools or validate the declared machine
properties.

### Submitting and monitoring jobs

Run commands from inside the configured Git repository. A submission always
uses a committed revision and the repository's `origin` URL. Push the branch or
tag first so the remote can fetch it; uncommitted working-tree changes are never
included.

```sh
# Inspect selection before submitting.
remote-runner recommend --profile full

# Choose the best eligible remote with an available slot.
remote-runner submit --best --profile full --ref HEAD

# Or select a specific configured remote and pushed branch.
remote-runner submit --remote buildbox --profile fast --ref feature/my-change
```

`submit` prints a job ID such as
`buildbox--example-project--20260920-130000--1a2b3c4d`. Save that complete ID;
its first component selects the remote for subsequent operations.

```sh
remote-runner status buildbox--example-project--20260920-130000--1a2b3c4d
remote-runner log buildbox--example-project--20260920-130000--1a2b3c4d
remote-runner log --follow buildbox--example-project--20260920-130000--1a2b3c4d
remote-runner artifacts buildbox--example-project--20260920-130000--1a2b3c4d
remote-runner cancel buildbox--example-project--20260920-130000--1a2b3c4d
```

`status` reports the pinned commit as `dut_commit` and whether its initial
checkout was clean as `dut_clean`. Treat results as valid only when those match
the intended revision and cleanliness contract. `log` reads the combined
standard output and error stream. `artifacts` lists files retained in the remote
job directory; it does not download them. Use an intentionally designed profile
or normal authenticated file-transfer tooling when an artifact must be copied.
`cancel` sends `SIGTERM` to the job's process group.

### Retention cleanup

Cleanup is preview-only unless `--apply` is supplied:

```sh
remote-runner prune --remote buildbox --success-days 7 --failure-days 30
remote-runner prune --remote buildbox --success-days 7 --failure-days 30 --apply
```

Successful jobs use `success-days`; failed, cancelled, or otherwise non-passing
jobs use `failure-days`. Running jobs are never selected. Applying the cleanup
removes the selected job directories and their Git worktrees, while retaining
the per-project bare repository cache.

### Operational cautions

- The remote must be able to fetch the exact requested revision from `origin`.
  For private repositories, configure access on the remote host without placing
  credentials in either TOML file.
- Profiles execute with the remote user's permissions. Use a dedicated,
  least-privileged account and an isolated `workspace_root` when practical.
- `max_jobs` is enforced by checking recorded live processes. It is not a CPU,
  memory, disk, container, or network quota.
- Job output and worktrees remain on the remote until pruned. Size retention and
  storage accordingly.
- Keep machine definitions untracked and project profiles tracked. This
  separation allows reproducible project commands without publishing private
  infrastructure details.

## Updating the mirror

Treat this repository and `~/.claude` as a pair. For a portable configuration
change:

1. Make the repository copy authoritative, even when an edit began in the live
   file.
2. Add new portable paths to `config-manifest.txt`.
3. Run the relevant helper syntax checks and `git diff --check`.
4. Use `./install.sh --dry-run`, install the reviewed change, and finish with
   `./install.sh --check`.
5. Review and commit from this repository; never copy runtime state wholesale.

The default source for new project templates is the separate tracked
`claude_project_template` repository.
