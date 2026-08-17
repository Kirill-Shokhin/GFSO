# Security

## What this software does on your machine

Two properties matter before you run it anywhere but a laptop.

**The server is unauthenticated.** `gfso up` starts one server bound to `127.0.0.1:8000`. It has no
login, no accounts and no authorization: identity in GFSO is an agent id carried by the protocol, and
the protocol assumes non-adversarial parties (canon §24.2). Anyone who can reach that port can read
and mutate every project on it. Do not bind it to a public interface, and do not put it behind a
reverse proxy without adding authentication of your own.

**The engine executes code it did not write.** In the delegated regime it spawns Claude Code CLI
subprocesses — executors that write and run code in a working directory you name, and validators that
run the criteria of a delivery against the artifact. Both run with your user's permissions. Point
them at a directory you are willing to lose, and treat a task graph from an untrusted source as
untrusted input: its criteria are instructions that will reach a model with a shell.

The SQLite database and the agent registry are plain local files with no encryption. They record
every signal, including whatever text your specs, results and verdicts carry.

**The UI page fetches three scripts from a CDN.** The graph view loads its rendering libraries
(cytoscape, dagre) from `unpkg.com` at version, not at hash — so the page executes third-party code
served at request time, in a tab that can drive the local tool surface. Everything else is local:
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
