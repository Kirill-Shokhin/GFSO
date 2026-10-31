# Security

## What this software does on your machine

Two properties matter before you run it anywhere but a laptop.

**The server is unauthenticated.** `gfso up` starts one server bound to `127.0.0.1:8000`. It has no
login, no accounts and no authorization: identity in GFSO is an agent id carried by the protocol, and
the protocol's guarantees take a permissioned scope as a premise — authenticated transport, one
sequencer (canon §16.4, §16.15). Any process on your machine that can reach that port can read and
mutate every project on it. Do not bind it to a public interface, and do not put it behind a reverse
proxy without adding authentication of your own.

What the server does refuse is a web page: it answers only to its own host names (so a name re-pointed
at 127.0.0.1 is not served), and from a browser page that is not its own it serves reads only — no
write, no live socket. A server started on another name (`gfso serve --host`) answers to that name;
any further name is added by hand in `GFSO_ALLOWED_HOSTS` (comma-separated).

**The engine executes code it did not write.** In the delegated regime it spawns Claude Code CLI
subprocesses — executors that write and run code in a working directory you name, and validators that
run the criteria of a delivery against the artifact. Where they run is said below: unattended work
in a container, work your own agent does in its chat on your machine with your user's permissions.
Treat a task graph from an untrusted source as untrusted input: its criteria are instructions that
will reach a model with a shell.

Unattended work runs in a container. The work the system dispatches — an executor's session, a
scope's, a system-held parent's consent — is a model with tools whose commands nobody watches, and
before it the plan's checks of its place run; on your machine none of it starts unless the server
was started with `"GFSO_LOCAL_AGENTS": "allow"` in `data/serve.json` (so `gfso up` keeps it, and
a server started without it is restarted). Without that, the first such round stops its project with
the cause named, nothing of the node having run or been consented to, and the project stays
stopped until the word is given or an execution is declared; a mode that would dispatch such work
is not set as ready. Work your own agent does in its chat, and the validator that
judges it, run on your machine as before: a person is there. With the word, dispatched work runs on
your machine unattended, with what is said below for a session with no execution.
Docker is part of the installation: `gfso setup` builds the agents' image from the file the package
ships (no credential and no agent state in it) and declares it in `data/executions.json` as the
execution `default`, moving it to the new image on an upgrade and keeping one you declared under that
name. A project's executors registered with no execution of their own take it when a mode that dispatches
its work is set — not where the project already runs in another, its work is done in your own chat, or the
server has the word above. `gfso doctor`, `gfso setup` and every container execution hold a Docker Desktop older than 4.44.3 not usable: before it a
container reached Docker's own API unauthenticated (CVE-2025-9074), and every boundary below stands on Docker
holding; no container of the system's mounts Docker's socket. A role registered with an execution (`register_agent(execution=)`,
declared in `data/executions.json`) runs its project's work in Docker, with the host's network shut,
and nothing of your disk is mounted into any of its containers:
- The project's work lives in Docker volumes of its own: the agents' places, the judges' copies, the
  temps, the system's own copies and every session's model-client state. Your repository enters
  once per root: your own git bundles its committed HEAD, and the project's copy is cloned inside
  with none of your configuration or hooks; what did not come in (uncommitted or untracked files,
  submodule contents) is said in the project's log when it comes in. The root's accepted result comes back as the
  branch `gfso/<project>/accepted` of your repository — your git fetches a bundle of it, nothing
  of the agents' configuration travels, and your working tree and branches are not touched; a
  project whose base is no git repository gets its result in `.gfso-accepted-<base>/<project>/`
  beside it. `gfso export-places` writes the places out for reading, with every agent repository's
  configuration and hooks replaced.
- Each agent session runs in a container of its own place. It writes there alone, reads the project's
  base read-only, and holds its node's own temp and its place's own model-client state. Its client runs in a
  container of the place apart from the one the system runs its own commands over the place in: only the client's
  mounts that state. What the client's own start reads from the place is kept from running beside it: it has no git —
  its `git status` there finds none, so no clean filter its agent or a delivered build wrote runs —, it loads no
  setting source — no `.claude/settings.json` a delivered tree carries (a key helper, hooks, environment) —, and its
  own file tools may not write under the home it runs from, where a program laid on its PATH would run at its next
  start. It does not
  see another node's place, conversations or inputs, nor the system's own checks; what it receives
  of other nodes' work comes by the joins the system makes into its place and the base.
- The commands a session's Claude Code client runs (its Bash tool) do not run beside the client. The
  client's shell is one the system lays where no agent process writes, and it sends each command to
  a container of its own beside the session's: the same place mounted, the same network and switch,
  a process space of its own, the image's user with no capability. So no command can write into the
  client's output, which the system reads as the record of what the session did. Each command is
  also recorded as it starts and as it ends — its session, node, role and agent, its arguments, its
  exit code — by the system's listener in that container, which no command can signal, read or ask
  for anything; the record is kept beside the door's log. A client that runs a shell beside itself
  instead (it ignores, silently, a shell it does not accept) runs no command there, and the session
  is refused with that cause: the project stops. The client's own file tools may not write through
  `/proc` or `/dev`, nor into its own state. What the client's shell writes back into the client's container is the
  CLI's own working-directory file and shell snapshot alone, by their shapes and never through a link — not a path a
  command's text names.
- The checks the system runs over a delivery run what the agents wrote (the plan's probes, the
  delivery's own scripts), so each runs in a container of its own copy of the delivery, mounting
  that copy and a temp of its own and nothing else.
- The system's own commands over an agent's repository — git, reading and writing its files — run in
  the container of the place that repository stands in, chosen by the system's own record of the
  place, never by what stands there, which mounts no model client's state: what that repository's configuration
  tells git to run reaches nothing its agent did not already reach. Commits move between repositories as bundles.
- No one who judges a delivery works in its executor's place: a validation and an issuer's
  contact, a root's included, each run in a container of their own copy of it, each batch of a
  validation in its own, and the place's validation scratch is read-only to its executor. A judge's
  container mounts exactly three directories: its own round or batch, writable, holding its copy;
  a temp of its own; and, read-only, the directory the system laid for it from its record beside
  that round or batch. Nothing else — not the base, not its node's temp, not the place, not another
  batch of its round, not an earlier round. Each input comes from the system's record, or from
  content checked against an id that record holds:
  - The copy is a checkout of the commit recorded at delivery and nothing else — no file the
    executor's ignore rules hid, nothing it built or left in its place, nothing it changed there
    afterwards. The commit's objects are packed in the executor's own container and streamed through
    one pipe into a git the system makes in the copy's container, with no configuration, hook, filter
    or rule of the executor's or the base's; every object is hashed again against its id there before
    anything is checked out, so nothing the executor can write is read after that check. Nothing of it
    passes through the server's memory, and no size limit applies but the disk.
  - The Git LFS objects the recorded tree's pointers name are streamed the same way from the place's
    and the base's LFS stores into the copy's own, each kept only where its size and sha256 are its
    pointer's, and the checkout writes their content through the system's own filter; one no store
    holds as its pointer names stays a pointer.
  - The files a standing finding's command names in the round that found it are recorded by the
    system, by their sha256, as the finding is filed. A later round's re-run lays them from that record
    into its read-only directory, and the command it is shown copies them into a fresh directory of
    its batch before it runs.
  - A pinned probe's inputs are laid from the contract into the judge's own batch.
  A copy the delivery itself makes impossible — an object missing or rewritten, a commit not carrying
  the recorded tree, a nested repository or submodule — is not judged: the delivery FAILs with that
  cause, which the executor's next packet states, and nothing of it stands for later rounds; an
  issuer asked about it is told the cause and rules on it. A copy that fails for any other cause (a
  Docker error, a timeout, a full disk) gives no verdict, and the judge is asked again. A delivery
  holding a nested repository or a submodule is refused when it is delivered, with what lifts it.
  An issuer's contact, whatever it asks, rules on the same checkout of the recorded commit.
  A standing finding whose file the record could not keep (not there when it was filed, or past the
  record's size limit) is shown to the judge, not demanded.
- A judge's container ends when its run ends, with every process the run left behind.
- Every container the system makes holds at most 4 GiB of memory, with no swap past it, and 4096 processes
  (`GFSO_CONTAINER_MEMORY`, `GFSO_CONTAINER_PIDS`; the door and the gateway hold 256 MiB and 256). Past its memory
  the kernel ends the container's largest process: a runaway that is one program fails alone, exit 137, as its own
  failure, and the session or check it ran in goes on; one made of many smaller processes (a parallel build) can make
  the session's own model client the largest, and that session then ends with no answer and is asked again. Past its
  processes a new one is refused until some end. Nothing else runs in a judge's copy while it is made and its files
  checked, so a copy whose reading its bound ended is the delivery's FAIL, the bound named as the cause. A build that
  takes the Git LFS objects its checkout wrote as content fails the delivery the same way: which they were is read
  before any build runs. The copy writes files a chunk at a time, save a Git LFS file at its checkout, which git reads
  whole: one about the bound's size fails an honest delivery until the bound is raised. Their sum is bounded
  too: every container the system makes, of every installation on that Docker, stands in one cgroup of Docker's
  (`gfso`) whose memory is at most three quarters of Docker's as it is when the limit is written — no installation
  dials it, so none lowers it under another's running containers. Past it the kernel ends the largest process among
  all of them: what the ceiling keeps is the quarter left to Docker itself and to containers that are not the system's.
  It does not choose the runaway: a runaway made of many small processes can outlast the largest honest one, a
  session's or another installation's, which then ends with no answer and is asked again. A judge's copy the ceiling ended reads as ended by its own bound, and
  its delivery FAILs with that cause. The limit is written at a
  start, and again at a later one past five minutes, by a container of the system's own that runs no agent's code: a
  shell of an image pinned by its digest (busybox), as root with one capability, to write the cgroup's files, no
  network, a read-only root, mounting Docker's cgroup tree — which lets it limit, freeze or end any container on that
  Docker; no other container mounts the tree. Until a write holds (a Docker restarted under the server makes the group
  anew with no limit) the sum stands unbounded, and each failed write is said in the server's log. It needs Docker's
  cgroups as cgroupfs v2 (Docker Desktop's); under a systemd cgroup driver no group is used, the log says so, and each
  container is bounded alone.
- What the delivery needs built is built in that copy, in the judge's container under its network
  switch, before any check: the command the delivery declares (`build`), else `make` where the
  delivered tree has a Makefile at its root, else nothing — the delivered code, run by the judge's
  side, with a bounded time, in the batch's own container, which mounts no model client's state. Every process the build leaves running ends with it, before any check,
  and a delivered file it changed is put back as delivered; what it adds beside them stays. A build
  that fails is the delivery's FAIL, with its output, and nothing of it stands for later rounds:
  the next delivery's own build is the re-check.

What one session can still reach:
- Only the root's executor works in the base; its model-client state still holds what sessions an earlier version
  ran there wrote — consents, and the reader of the places a plan is made from. Every other session, a parent's
  consent and that reader included, works in a place of its own. A project whose base is no git repository with a
  commit has no places, so a container runs none of its dispatched work: it stops with the cause, `git init` and a
  first commit named. On your machine, with the word, such a project's sessions all work in the base and can read
  each other's conversations.
- A delivery with no recorded commit — a project dir that is no git repository, a DELIVER sent by an
  agent through the door rather than by the system's executor — is copied as it stands, ignored files
  and builds included, and nothing is built.
- A process a session starts runs until its call ends; one that left its call's group and dropped its mark runs on
  while another model client of the same place still works there, and ends with the place's last one — or, where the
  server died first, when the place's containers go: at its project's next start, or its place's removal.
- The Claude Code client's own tools — Read, Edit, Write — still run in its process, beside its
  output: the settings above keep them off it, as far as the client holds to them (NotebookEdit onto
  a pipe was not measured). A command cannot read the client's task-output files nor its
  model-client state; its Read tool can. A working directory a command leaves outside the place does
  not carry to the next command.
- A judge runs the delivered code in its own container: while its run lasts, that code can rewrite
  what the judge itself writes in its batch, a pinned probe's inputs laid there — the build included —, and a
  finding's files
  once the re-run has copied them out of the read-only directory and before it reads them. A file the
  delivered code rewrote in the judge's batch before its run ended is recorded as it then stood when
  a finding over it is filed.
- A finding filed before the system recorded probe files has its files recorded at its first re-run,
  from its round as it stands then; one whose round is already gone is shown, not demanded.

Under a container execution a node performed in your own chat (`perform="in_chat"`) is refused: its
work stands on your disk, where no container reads it.

Without an execution, and with `"GFSO_LOCAL_AGENTS": "allow"` in `data/serve.json`, sessions run as you, on your machine, with nothing between them and the rest
of it: a judge's copy is still the recorded commit where a scratch for it can be made, but nothing
is read-only to it, no container ends with its run, and a validation with no scratch runs in the
place itself.

How far a project's container reaches outside is a switch you set in its execution's declaration
(`"network": {"mode": ..., "hosts": [...]}`). For one project, `set_mode(network=...)` can only narrow it —
open → allowlist → off, an allowlist reaching only hosts the declaration also names — never widen it (once the
project has work in it, only with your own words asking for the change):
- `open` (the default) reaches everything but your host — other containers on Docker's bridge
  included.
- `off` reaches nothing but its model, through the door below: the container stands on an internal
  Docker network of its own with no route out and no capability to make one. Each closed project takes one of Docker's address pools;
  past their number a start fails.
- `allowlist` adds one gateway container, the only way out. It opens a connection only to a host
  you named, on 443, when the TLS handshake names that host; what the session then sends inside
  the encrypted stream it does not see, so a host behind a shared front (a CDN) can carry requests
  to other sites of that front. Every opening is logged to a file the sessions cannot reach;
  refusals too, until the log reaches its cap. The gateway is code, not a kernel rule: it keeps
  your host out by refusing every address that is not public, and a gateway taken over is the
  whole way out.

An allowed host carries whatever a session sends it, under any credentials the session presents —
a model API that stores data is a way out to someone else's account.

In a container execution no session holds its provider's credential; a session on the host
(`LocalExecution`) runs as the user it runs under and reads what that user reads, the credential
store included. A provider over a chat API calls its model from the
server itself; only its tools run in the container. The Claude Code client, which runs inside,
reaches its model under every switch through its project's door: a container of its own that
holds the credential (from `gfso credential`) and nothing of the project. The client holds only
the door's key, which opens that door and no other; the door puts the credential in and passes the
request to the provider alone. So no process in a session — the client, its tools, what they run —
holds the credential to read or carry away, and another container is refused by the door. The
credential is in no container's configuration, environment or disk: the door reads it once from
memory and removes it; a credential replaced while calls run keeps its door, and so stays live,
until the project stops. Under every switch the door passes the model's messages alone — the
credential opens far more of the account (its files, its batches) — and it runs on the
execution's own image, which must have `python3`. Under `allowlist` and `off` it passes only the
messages the model answers by itself: every tool the client's own, no content the provider
would fetch from a URL, no server-side tool, MCP server or container — so the door is no way out
the switch does not govern. Under `open` the door stands on Docker's shared bridge and the key
travels there in plain HTTP: a container on that bridge able to intercept its traffic could take
the key and spend through the door, though not the credential. What the door cannot stop: a
session spending the model through it, as its client does. Every passed request is logged beside
the gateway's log as its answer starts; refusals too, until the log reaches its cap.

Nothing watches the declaration: a turned switch is read at the project's next lookup of
its execution, which then ends the project's running container — until then a session already out
stays out. A declaration that does not read shuts the way out.

The SQLite database and the agent registry are plain local files with no encryption. They record
every signal, including whatever text your specs, results and verdicts carry.

**The UI page fetches three scripts from a CDN.** The graph view loads its rendering libraries
(cytoscape, dagre) from `unpkg.com`, each pinned by a subresource-integrity hash: a file the CDN serves
changed does not run, in a tab that can drive the local tool surface. Everything else is local:
the engine, the API and every verb work with no network at all, and on a machine that cannot reach
that host the page comes up without the graph.

## Supported versions

| Version | Supported |
|---|---|
| the newest `0.x` release on PyPI | yes — fixes land here |
| anything earlier | no |

One version is supported at a time, and it is the latest. A fix arrives as a new release rather than
as a backport: a `0.x` line with a single maintainer cannot honestly promise to carry two.
`gfso --version` says which one you are running, and `gfso doctor` prints the rest of what a report
needs.

## Reporting a vulnerability

Use GitHub's private reporting — **Security → Report a vulnerability** on the repository. Please do
not open a public issue for a security defect. If private reporting is not available to you, write
to kashokhin@gmail.com instead.

This is a preliminary research release: expect an acknowledgement, not a schedule. If you need a
guarantee, fork the commit you audited.
