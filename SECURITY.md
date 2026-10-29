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
run the criteria of a delivery against the artifact. Both run with your user's permissions. Point
them at a directory you are willing to lose, and treat a task graph from an untrusted source as
untrusted input: its criteria are instructions that will reach a model with a shell.

Run unattended work in a container. A role registered with an execution (`register_agent(execution=)`,
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
  base read-only, and holds its node's own temp and its place's own model-client state. It does not
  see another node's place, conversations or inputs, nor the system's own checks; what it receives
  of other nodes' work comes by the joins the system makes into its place and the base.
- The checks the system runs over a delivery run what the agents wrote (the plan's probes, the
  delivery's own scripts), so each runs in a container of its own copy of the delivery, with the
  base read-only and nothing of another node.
- The system's own commands over an agent's repository — git, reading and writing its files — run in
  the container of the place that repository stands in, chosen by the system's own record of the
  place, never by what stands there: what that repository's configuration tells git to run reaches
  nothing its agent did not already reach. Commits move between repositories as bundles.
- No one who judges a delivery works in its executor's place: a validation and an issuer's
  contact, a root's included, each run in a container of their own copy of it, each batch of a
  validation in its own, and the place's validation scratch is read-only to its executor. Before a
  validation, or an issuer's ruling on a dispute, starts, the copy is compared with the tree recorded
  at delivery, by a git the system makes;
  a copy that differs, or that could not be made, is not judged: its validation reads as one that
  never started — asked again, then put to a person. A delivery holding a nested repository or a
  submodule, whose files that record cannot hold, is refused when it is delivered, with what lifts it.

What one session can still reach:
- The sessions working in the base share it and its model-client state: a root's executor, and a
  parent's consent asked before its own place exists.
- A judge's copy shares its node's temp with the node's executor.
- What git does not record — ignored files such as a build, a file whose name differs from a tracked
  one only by case on a case-insensitive base — is judged as it stands in the copy.
- A process an executor starts may outlive its session in its place's container, which stands
  until the place goes.

Under a container execution a node performed in your own chat (`perform="in_chat"`) is refused: its
work stands on your disk, where no container reads it.

Without an execution, sessions run as you, on your machine, with nothing between them and the rest
of it.

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
