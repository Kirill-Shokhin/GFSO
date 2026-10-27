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
declared in `data/executions.json`) runs its project's sessions in a Docker container that holds only
that project's directories, with the host's network shut; the system's own git operations on the
agents' repositories run there too — save two that find a place by the path it was registered under
(locking it, removing it), which fall back to the host for places registered there, and run nothing
the agents wrote. Without one, sessions run as you, on your
machine, with nothing between them and the rest of it.

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
