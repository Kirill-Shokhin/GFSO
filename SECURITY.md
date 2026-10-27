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
declared in `data/executions.json`) runs its project's work in Docker, with the host's network shut:
- Each agent session runs in a container of its own place. It writes there alone, reads the project's
  base read-only, and holds its node's own temp and its place's own model-client state. It does not
  see another node's place, conversations or inputs, nor the system's own checks; what it receives
  of other nodes' work comes by the joins the system makes into its place and the base.
- The checks the system runs over a delivery run what the agents wrote (the plan's probes, the
  delivery's own scripts), so each runs in a container of its own copy of the delivery, with the
  base read-only and nothing of another node.
- The system's own commands — git on the agents' repositories, the copies it makes — run in the
  project's container, which holds every place of the project and no session's state. Two git
  operations that find a place by the path it was registered under (locking it, removing it) fall
  back to the host for places registered there, and run nothing the agents wrote.

What one session can still reach:
- The sessions working in one place share it and its model-client state. A root's executor, its
  validations and its issuer's contacts all work in the base, which they can write, and in the
  base's validation scratch, where the probes of its standing findings stand.
- A project whose base is not a git repository works every node in the base: no node is held apart.
- A parent's consent asked before its own place exists runs in the base and reads its inputs from
  the base's temp.

Without an execution, sessions run as you, on your machine, with nothing between them and the rest
of it.

How far a project's container reaches outside is a switch you set in its execution's declaration
(`"network": {"mode": ..., "hosts": [...]}`):
- `open` (the default) reaches everything but your host — other containers on Docker's bridge
  included.
- `off` reaches nothing: the container stands on an internal Docker network of its own with no
  route out and no capability to make one. Each closed project takes one of Docker's address pools;
  past their number a start fails.
- `allowlist` adds one gateway container, the only way out. It opens a connection only to a host
  you named, on 443, when the TLS handshake names that host; what the session then sends inside
  the encrypted stream it does not see, so a host behind a shared front (a CDN) can carry requests
  to other sites of that front. Every opening is logged to a file the sessions cannot reach;
  refusals too, until the log reaches its cap. The gateway is code, not a kernel rule: it keeps
  your host out by refusing every address that is not public, and a gateway taken over is the
  whole way out.

An allowed host carries whatever a session sends it, under any credentials the session presents —
a model API that stores data is a way out to someone else's account. A session's own model client
calls its model from inside the container, so under `allowlist` the provider's host must be on the
list, and that host is such a way out; `off` suits only a provider that calls the model from
outside. Nothing watches the declaration: a turned switch is read at the project's next lookup of
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
