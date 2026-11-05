# Security

## What it promises, in short

Work the system dispatches runs unattended, so it runs in Docker, which the installation requires (the one exception is your
word, `GFSO_LOCAL_AGENTS=allow`, which puts it on your machine, with none of what follows). Under either network switch, for that work:
- Nothing of your disk is mounted where an agent runs. Your repository enters as its committed HEAD with all its history, so a shallow clone or a sha256 repository is refused at import with that cause, which
  every session can read: clean a secret out of the history first. What is uncommitted does not enter, and the project's log says so.
  The root's accepted result comes back as the branch `gfso/<project>/accepted`, your working tree and branches untouched.
- No agent process holds your provider's credential: one small container does, and it passes the model's messages alone.
- No session reads another node's files but by the plan's edges, nor reaches the log of signals and verdicts, and no one validates its own
  delivery: the check is on a copy of the commit delivered, in a container of its own.

The switch is yours, per execution or per project, and the default is `open`:
- `open` is for work that may leak or needs the current internet: it reaches outward, and two sessions may relay through a server out
  there. Your machine and the private networks it stands on are shut; a service of yours on a public address is the internet.
- `off` is for what must not leak and for checking runs: a container reaches nothing but its model, through that door, which passes
  only what the model answers by itself.

Under `off` your code still goes to the model's provider, as far as an agent sends it there, on your account. It stays with you only
where every role, the system's own too (`set_mode(system_model=, planner_model=)`), names a local model. Not promised: a boundary
against an escape from Docker or its kernel, which every project shares (no VM per task); a check a validation writes itself, which the
delivered code it runs can reach, where only a pinned one is out of its reach; a model validator's reading, which what it reads can argue with, where only a check pinned with `exact: true` decides by itself; anything for what runs on your machine, namely the work your
own agent does in its chat, the validator of that work, and the reader of a plan's documents. What the agents wrote reaches that
agent of yours as text, in what a check printed and in a plan's words, past every container: it is told to take these as data, which
a model can be argued out of, measured on one plain instruction alone (a cheap model followed it in none of six tries, told or not); a result is read before it is run
on your machine. The rest of this file says how each of these holds, and what stays open.

## What this software does on your machine

Two properties matter before you run it anywhere but a laptop.

**The server is unauthenticated.** `gfso up` starts one server bound to `127.0.0.1:8000`. It has no
login, no accounts and no authorization: identity in GFSO is an agent id carried by the protocol, and
the protocol's guarantees take a permissioned scope as a premise — authenticated transport, one
sequencer (canon §16.4, §16.15). Any process on your machine that can reach that port can read and
mutate every project on it. Do not bind it to a public interface, and do not put it behind a reverse
proxy without adding authentication of your own.

What the server does refuse is a web page: it answers only to its own host names (so a name re-pointed
at 127.0.0.1 is not served), and from a browser page that is not its own it serves no write and no
live socket — and nothing at all to a browser that says the page is another site's (`Sec-Fetch-Site`).
What agents write is shown on that page escaped, and a policy under it (`Content-Security-Policy`) runs no script but its own and
what the library's host serves, should the escaping miss: the page's own tags pin its libraries by hash, the policy that host.
A server started on another name (`gfso serve --host`) answers to that name; any further name is added
by hand in `GFSO_ALLOWED_HOSTS` (comma-separated). A front that forwards such a name to the server (a
reverse proxy, `tailscale serve`) gives whatever reaches the front the server's every door: the
system's own containers are kept off a front on your machine's addresses or your networks (below), nothing else
there is — one the internet reaches a session under an `open` switch reaches too.

**The engine executes code it did not write.** In the delegated regime it runs agents through the project's
provider — a model client such as the Claude Code CLI as a subprocess, or, for a chat API, the server calling the model
and carrying out its tool calls — as executors that write and run code in a working directory you name, and validators that
run the criteria of a delivery against the artifact. Where they run is said below: unattended work
in a container, work your own agent does in its chat on your machine with your user's permissions.
Treat a task graph from an untrusted source as untrusted input: its criteria are instructions that
will reach a model with a shell.

Unattended work runs in a container. The work the system dispatches — an executor's session, a
scope's, a system-held parent's consent — is a model with tools whose commands nobody watches, and
before it the plan's checks of its place run; on your machine none of it starts unless the server
was started with `"GFSO_LOCAL_AGENTS": "allow"` in `data/serve.json` (or that variable in its
environment; `data/serve.json` is where `gfso up` keeps it, and
a server started without it is restarted). Without that, the first such round stops its project with
the cause named, nothing of the node having run or been consented to, and the project stays
stopped until the word is given or an execution is declared; a mode that would dispatch such work
is not set as ready. Work your own agent does in its chat, the validator that
checks it, and the reader of a plan's documents a goal you hand `auto_decompose` names (read-only tools)
run on your machine as before: a person asked for them. With the word, dispatched work runs on
your machine unattended, with what is said below for a session with no execution.
Docker is part of the installation: `gfso setup` builds the agents' image from the file the package
ships (no credential and no agent state in it; built from a base named by its digest and a CLI
binary refused unless its checksum is the one the file names) and declares it in `data/executions.json` as the
execution `default`, moving it to the new image on an upgrade and keeping one you declared under that
name. A project's executors registered with no execution of their own take it when a mode that dispatches
its work is set — not where the project already runs in another, its work is done in your own chat, or the
server has the word above. `gfso doctor`, `gfso setup` and every container execution hold a Docker Desktop older than 4.44.3 not usable: before it a
container reached Docker's own API unauthenticated (CVE-2025-9074), and every boundary below stands on Docker
holding; no container of the system's mounts Docker's socket. What you declare in an execution's `env_file` reaches
every container of the project, validations' included: only a provider's credential is refused there, by its name. The
system's own calls take the system's directories first on PATH, so no program a command laid is what they run. A build, a
check and a chat API provider's command take the image's PATH, a build and a check with what lies under the home last, so no
program delivered code laid there replaces one a later step of the check runs by name (one a declared image keeps under its
home is found last: name its path). The Claude Code client's commands keep the system's directories first, its shell
restoring the client's own PATH: a program of a declared image that shadows a system one needs activating in the command. What a call prints reaches the server to 64 MiB a stream, its head and tail: the rest is said
as dropped; a file or directory the system digests or keeps as a finding's is read to 64 MiB, past that not read. A `unittest-checker` runs a delivery in the server's process, so it is refused for a project in a container. That boundary is a container on the one kernel of Docker's
VM, shared by every project: not a VM per task, as the best-isolated products use, so an escape from a container crosses
it. Enhanced Container Isolation is neither required nor checked, and Docker Desktop's licence for an organization is
yours to check. A role registered with an execution (`register_agent(execution=)`,
declared in `data/executions.json`) runs its project's work in Docker, with the host's network shut,
and nothing of your disk is mounted into any of its containers:
- The project's work lives in Docker volumes of its own: the agents' places, the validations' copies, the
  temps, the system's own copies and every session's model-client state. Your repository enters
  once per root: your own git bundles its committed HEAD, and the project's copy is cloned inside
  with none of your configuration or hooks; what did not come in (uncommitted or untracked files,
  submodule contents) is said in the project's log when it comes in. The root's accepted result comes back as the
  branch `gfso/<project>/accepted` of your repository — your git fetches a bundle of it, every
  object checked as it takes it where your git is 2.46 or newer — an older one takes the bundle
  unchecked — (what parses that pack, made where an agent writes, is your git; a bundle carrying history your git would
  refuse does not land, the cause said), nothing of the agents' configuration travels, and your working tree and branches
  are not touched; a
  project whose base is no git repository gets its result in `.gfso-accepted-<base>/<project>/`
  beside it. `gfso export-places`, which holds in memory only the names of what it carries, writes the
  places out for reading, no link leading out of them, with the configuration and hooks of every
  repository replaced, each known by its shape whatever its directory is called, and a `.git` that is a file removed; a
  directory shaped as one loses its `config` and `hooks` though it was none. On a disk that reads two spellings as one
  name, an entry that would land on another is not written. What landed is then read on your own disk: anything git would
  run or follow there is removed; if it cannot be, no export is left. A sparse file over 1 MiB is not exported, its holes being real bytes on the host's disk and nothing against a session's bound. The notes beside the export say what was.
- Each agent session runs in a container of its own place. It writes there alone, reads the project's
  base read-only, and holds its node's own temp and its place's own model-client state. Its client runs in a
  container of the place apart from the one the system runs its own commands over the place in: only the client's
  mounts that state. What the client's own start reads from the place is kept from running beside it: it has no git —
  its `git status` there finds none, so no clean filter its agent or a delivered build wrote runs —, it loads no
  setting source — no `.claude/settings.json` a delivered tree carries (a key helper, hooks, environment) —, and its
  own file tools may not write under the home it runs from, where a program laid on its PATH would run at its next
  start. It does not
  see another node's place, conversations or inputs, nor the system's own checks. What it receives of other nodes' work
  comes by the joins the system makes into its place, by the plan alone: a place starts from where its whole stood
  when the part entered its split, a sibling's work reaching it by a Dep edge, not by the order the parts happened to
  start in. What it reads as the base is a copy holding what was imported (hard links: a file the system writes in place in the base, which git does not, shows there too), never a delivery, whose
  objects reach a place when it joins there; a project made before 0.3.0 keeps, readable by id alone, what its base already held.
- The commands a session's Claude Code client runs (its Bash tool) do not run beside the client. The
  client's shell is one the system lays where no agent process writes, and it sends each command to
  a container of its own beside the session's: the same place mounted, the same network and switch,
  a process space of its own, the image's user with no capability. So no command can write into the
  client's output, which the system reads as the record of what the session did. Each command is
  also recorded as it starts and as it ends — its session, node, role and agent, its arguments, its
  exit code, and what in the place changed while it ran (up to 200 paths, by the change time no
  process of the agent can set; a deletion named by its directory; any process of the place in that
  span counted, a command left running among them) — by the system's listener in that container, which no command
  can signal, read or ask for anything, the paths changed excepted: those it walks as the command's own user, so a process a command left running can blank or forge them, and they are that session's account of itself; the record is kept beside the door's log, and read from what the listener printed
  where its container can start no process. What changed on disk, read from outside the session, is a record of its own (`gfso network <project>` says where
  it lies): every ten seconds, once more after a session has gone and once at the server's clean exit, a server reads each directory a session mounts
  writable, from a container of its own holding that volume read-only, past every mode, and writes on the host what changed
  there: by that change time, whichever way it was written, so what a client's own file tools wrote is on it, and nothing a
  session does to its own containers reaches it. It says where, not who: the system's own writes there show too. What is
  written and removed again between two readings leaves only its directory; each reading names 200 paths at most, the
  quietest directories first, and counts the busiest; one that read its bound of 4 MiB of names says so, the rest of that reading unread; `gfso network` and the `next_steps` answer that a root is done name each such reading;
  the record turns over at 16 MiB as the network's does. Only a server reads, as only a server keeps the disk's bound and the memory ceiling's watch: `gfso mcp` or `gfso run` working with no server keeps no such record, and a session there can fill Docker's disk; the log says so once. A record that says nothing may be a clean run or one never kept. Under an image whose `find` cannot say, it says that. Where a session reached by
network is a record of its own, the same under every switch (`gfso network <project>` says where it lies): while an
installation has work, a listener of the system's own for each process that starts its containers, on Docker's host network, holding only the right to read packets and
sharing nothing with a session, writes for each container the destination of each new connection leaving it, whatever the protocol, and
the first name of each plain DNS query over UDP (over TCP, or encrypted, only the address). It changes no traffic, and a container's code starts only
once the listener stands, knows its address and has said its link is open, so a first packet is on it; where it cannot stand at a start the project stops with the cause,
unless the installation said `GFSO_NETWORK_RECORD=off`. One that dies later has the gap said on the record at once and is raised again; sessions already running go on meanwhile; a server that dies with its work standing takes its listener along, and the next server's start ends that work and says the gap on both records; `gfso mcp` killed with no server after it says none, its work standing until one starts. It holds addresses, ports and names, not what passed; nothing the kernel refused
before it left a container. Each container lists 2,000
destinations, and past that says so, and 64 ports of one host, and past that says so; a project's record turns over at 16 MiB, keeping its last turn and saying so, and goes with the project.
Under an allowlist it names the gateway, whose own log has the target. A flood costs its own container's lines alone: each container is read apart, and what arrives at one is not read.
A session under `open` can still hide where it went, by sending faster than the listener reads or past its 2,000 destinations: what it cannot do is hide that it did. The packets lost and the limit passed are on the record under its name and in the server's log, `gfso network` and `gfso status` name them, and so do the `next_steps` answer that says a root is done and the answer to `stop_project`, on the agent's door and, of a stopped or closed goal, the page. Such a session is not ended: `open` is the switch for work where a leak does not matter, and a measure that stops an honest upload would make it no longer open. Under the closed switches only new connections to the door and the gateway leave a container; each request a door passes takes a port and a lookup on the host, so a door opens the provider at most 20 times a second, a burst of 300, and answers 429 past that, about two containers' worth of ports a project, under every switch. The allowlist's gateway makes one connection out per connection in and has no such bound. Unbounded, one session opening new UDP flows as fast as it could stalled Docker Desktop's API for about 40 s and then ended its backend, and with it every project's containers. And on Docker Desktop each flow let out is a socket of a process on the host: at an earlier, larger bound eight containers held 15,407 of Windows' 16,384 ports, and other programs on the machine, nothing to do with GFSO, could bind none. So the bounds below are set by those ports, 16,384 for each protocol: a TCP connection's port stays taken for 120 s after it closes, a datagram flow's for about 83 s after its last packet. Under `open` each container opens at most 10 new TCP connections a second and 15 other new flows a second, bursts of 100 and 300 (`GFSO_NEW_FLOWS` sets the first, the rest in proportion), and holds at most 1,024 TCP connections, where its image has `nft` and its kernel the module (the product's image and Docker Desktop's kernel do; elsewhere no such bound, and nothing says so); the rest refused in the kernel, before they leave it. All that leaves a container but TCP is held to 5,000 packets a second, so an answered flow is bounded too. Measured once each, on one machine, floods lasting minutes on an otherwise empty Docker: other new flows from one container, API within 0.34 s, 1,546 sockets at the peak; from eight at once, API within 0.31 s, a new container started within 1 s, 12,341 sockets at the peak, the backend at 4.9 GB, another program binding throughout; an answered UDP flow at the packet bound, API within 0.17 s; connect-and-close from one container at twice its rate, beside other work, 1,481 ports in TIME_WAIT. All of an installation's containers together may hold half the VM's processes, beside their memory ceiling, past which forks in any project fail; what one kernel shares past that, as inotify's instances per user and asynchronous I/O, has no such bound, at a hostile session's price. What is still open: nothing sums over containers or projects, and a delivery's validation runs as many containers as it has batches, so about ten containers at a bound at once, or six each also holding its 1,024, fill the machine's ports for that protocol, and other programs then fail too; an exact check's fresh container is a fresh burst, so a delivered program in a loop under many checks in sequence takes up to about 13,000 datagram ports, derived, not run; the backend's memory peaks with its sockets and comes back slowly. TCP on an open connection paces itself and has no bound. The price: this kernel cannot tell a flow's first packet, so a UDP stream nothing answers is held to 15 packets a second; an upload by HTTP/3 past about 48 Mbit/s meets the packet bound; on Docker's default bridge each name lookup takes two flows, so about 150 at once and 7 a second after that, in sequence as much as in parallel, past which a program sees only that a name did not resolve: a critic's 200 HTTPS requests after 250 lookups lost 181, and `npm install` of a large tree ran at 12 of the 15 flows a second with none dropped; pip of 120 packages and two git clones dropped none. A connection past its rate waits on TCP's own retry; a datagram past a bound fails at once, which a program may read as its own failure; a session is not told as it runs, and how many were refused goes on the record as it ends, unless its container can start no process then or was ended outright. Under a closed switch the way out through Docker's proxy is shut; Docker's own name resolver on a container's loopback, which a closed switch still reaches, takes 50 packets a second, a burst of 300 (at 200 a second it stood a five-minute flood, API within 0.89 s). A project's door holds 16 connections from one address, so one session's idle connections leave the others room; past that it answers 429, which a model client retries for about 200 s and then ends on, said as an API error and not as the account's limit, and says so on its log and on the project's record as its doors close. Commands and their client share that address, so a session's own program holding 16 model calls makes its client wait. Nothing sums over addresses but the door's 256 processes: enough sessions of one project holding their shares can refuse others of that project, not another's. A door's memory is bounded from inside, under its container's 640 MiB, which it takes only when a large body comes, and it holds what has arrived of three of the largest bodies at once, one address at most one, each until it is sent on: past that, or with no memory or thread for a request, it answers 503, which a model client retries, and says so on its log, so one session (two addresses) can keep two thirds of that room from the rest of its project for as long as it sends; a body over the provider's cap gets 413, a request it will not pass with its key 400, and no key alone 403, which a client reads as its credential refused. Sixteen of the largest bodies at once, 32 MiB of small objects and a million nested brackets, sent with its key, left it answering. On a Linux host the listener reads the headers of every
container there, and writes those of this installation alone. A container is known by its address and the MAC Docker gave that start, so another's container taking a freed address is written under no one, on a Docker that gives each start a MAC of its own, as 29 does. Two processes of one installation that both start containers each stand a listener and each write every row. A client that runs a shell beside itself
  instead (it ignores, silently, a shell it does not accept) runs no command there, and the session
  is refused with that cause: the project stops. The client's own file tools may not write through
  `/proc` or `/dev`, nor into its own state. What the client's shell writes back into the client's container is the
  CLI's own working-directory file and shell snapshot alone, by their shapes and never through a link — not a path a
  command's text names.
- The checks the system runs over a delivery run what the agents wrote (the plan's probes, the
  delivery's own scripts), so each runs in a container of its own copy of the delivery, mounting
  a directory that holds that copy, its inputs and its temp, gone with the check, and nothing else.
- The system's own commands over an agent's repository — git, reading and writing its files — run in
  the container of the place that repository stands in, chosen by the system's own record of the
  place, never by what stands there, which mounts no model client's state: what that repository's configuration
  tells git to run reaches nothing its agent did not already reach. Commits move between repositories as bundles.
- No one who validates a delivery works in its executor's place: a validation and an issuer's
  contact, a root's included, each run in a container of their own copy of it, each batch of a
  validation in its own, and the place's validation scratch is read-only to its executor. A validation's
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
    passes through the server's memory, and no size limit applies but the disk, as a copy costs what its place does: a tree that would lay more than its place holds on disk, what the imported commit records and 1 GiB, by what it records and an LFS file whose object is held at its pointer's size, is no delivery that can be copied and FAILs naming it, and a parent's such commit starts no child. Two honest cases past that margin meet it too, each rare and within its project: a large file a part made and a later part removed stops a sibling that started before the removal, its node parking; and a part's file of more than 1 GiB that git lays with holes, past the imported commit's size, FAILs the whole it joined. A delivery's own commit does: it is
    carried from its place into the project, and at a join into its whole, through the server's memory, to 512 MiB beyond what the target
    holds (an LFS file apart). Past that the delivery is not handed in, its executor told why, or the join is refused, the cause in the whole's packet.
  - The Git LFS objects the recorded tree's pointers name are streamed the same way from the place's
    and the base's LFS stores into the copy's own, each kept only where its size and sha256 are its
    pointer's, and the checkout writes their content through the system's own filter; one no store
    holds as its pointer names stays a pointer.
  - The files a standing finding's command names in the round that found it are recorded by the
    system, by their sha256, as the finding is filed. A later round's re-run lays them from that record
    into its read-only directory, and the command it is shown copies them into a fresh directory of
    its batch before it runs.
  - A pinned probe's inputs are laid from the contract into the validation's own batch, as the system's
    own and read-only: the code run beside them may add files there, never change, move or remove a
    pinned one, nor any directory above them up to the root the validation's container writes. A probe
    that edits an input in place fails; it edits a copy it made (none of 4,987 recorded validations'
    commands did otherwise). The system's own exact checks each run in a container started anew —
    every process and file an earlier one left gone with it — over a copy of the built delivery of
    their own and their inputs laid afresh in a directory no earlier check or build could know the
    name of: no check changes what a later one reads, and checks pinning one command over different
    inputs each run. A check whose copy the built delivery makes impossible (a path past the
    system's limit) FAILs the delivery with that cause, as a checkout it makes impossible does; the
    copies' making and removal are not counted against the observation's time. A check that does not
    finish within its own bound is not observed, the validation's own reading deciding it.
  A copy the delivery itself makes impossible — an object missing or rewritten, a commit not carrying
  the recorded tree, a nested repository or submodule — is not validated: the delivery FAILs with that
  cause, which the executor's next packet states, and nothing of it stands for later rounds; an
  issuer asked about it is told the cause and rules on it. A copy that fails for any other cause (a
  Docker error, a timeout, a full disk) gives no verdict, and the validation is asked again. A delivery
  holding a nested repository or a submodule of its own is refused when it is delivered, with what lifts it; one the user's imported commit records, at that commit, passes, empty in every copy, so a check that needs its files has none.
  An issuer's contact, whatever it asks, rules on the same checkout of the recorded commit.
  A standing finding whose file the record could not keep (not there when it was filed, or past the
  record's size limit) is shown to the validator, not demanded.
- A validation's container ends when its run ends, with every process the run left behind; a node's
  place, client and commands containers end once it passed and joined, or was cancelled, and any of its
  rounds' with them. Once every node is settled and the result has landed, all of the project's containers
  end, its volumes kept.
- Every container the system makes holds at most 4 GiB of memory, with no swap past it, and 4096 processes
  (`GFSO_CONTAINER_MEMORY`, `GFSO_CONTAINER_PIDS`; the door and the gateway hold 256 MiB and 256). Past its memory
  the kernel ends the container's largest process: a runaway that is one program fails alone, exit 137, as its own
  failure, and the session or check it ran in goes on; one made of many smaller processes (a parallel build) can make
  the session's own model client the largest, and that session then ends with no answer and is asked again. Past its
  processes a new one is refused until some end. Nothing else runs in a validation's copy while it is made and its files
  checked, so a copy whose reading its bound ended is the delivery's FAIL, the bound named as the cause. A build that
  takes the Git LFS objects its checkout wrote as content fails the delivery the same way: which they were is read
  before any build runs. The copy writes files a chunk at a time, save a Git LFS file at its checkout, which git reads
  whole: one about the bound's size fails an honest delivery until the bound is raised. Their sum is bounded
  too: every container the system makes, of every installation on that Docker, stands in one cgroup of Docker's
  (`gfso`) whose memory is at most three quarters of Docker's as it is when the limit is written — no installation
  dials it, so none lowers it under another's running containers: what it keeps is the quarter left to Docker itself
  and to containers that are not the system's. Before the kernel chooses, a running server does: every two seconds it
  reads the group, and once what it holds that no reclaim gives back — all its memory less its page cache, a tmpfs or
  memfd counted as memory — passes 85% of the ceiling, it ends every container of the one node's work standing furthest
  over its share (the ceiling over the works holding at least 64 MiB), whatever number of containers that work runs in,
  if that work is its own installation's: another's is its own server's to end, and with none running, the kernel's;
  nobody over a share, nothing is ended. Honest page cache fires nothing, a runaway spread over three containers or
  hidden in a memfd is ended and its neighbour left running (measured). The price: an honest work over its share
  while the rest stand near the ceiling is ended too, though the sum might never have reached it. Past the ceiling itself, for a runaway faster
  than two seconds or with no server watching, the kernel ends the largest process among all of them, which can be an
  honest one; that session then ends with no answer and is asked again. A validation's copy or build the watch ended is no
  verdict on its delivery and is made again; one the kernel ended at the copy's own bound or at the ceiling reads as
  ended by its own bound, and its delivery FAILs with that cause. The limit is written at a
  start, and again at a later one past five minutes, by a container of the system's own that runs no agent's code: a
  shell of an image pinned by its digest (busybox), as root with one capability, to write the cgroup's files, no
  network, a read-only root, mounting Docker's cgroup tree — which lets it limit, freeze or end any container on that
  Docker; no other container mounts the tree. Until a write holds (a Docker restarted under the server makes the group
  anew with no limit) the sum stands unbounded, and each failed write is said in the server's log. It needs Docker's
  cgroups as cgroupfs v2 (Docker Desktop's); under a systemd cgroup driver no group is used, the log says so, and each
  container is bounded alone.
- What the delivery needs built is built in that copy, in the validation's container under its network
  switch, before any check: the command the delivery declares (`build`), else `make` where the
  delivered tree has a Makefile at its root, else nothing — the delivered code, run by the validation's
  side, with a bounded time, in the batch's own container, which mounts no model client's state. Every process the build leaves running ends with it, before any check,
  and a delivered file it changed is put back as delivered; what it adds beside them stays. A build
  that fails is the delivery's FAIL, with its output, and nothing of it stands for later rounds:
  the next delivery's own build is the re-check.

What one session can still reach:
- On a git base every session works in a place of its own, a root's executor, a parent's consent and the reader of
  the places a plan is made from included; a project's model-client state from an earlier version still holds what
  sessions then ran in the base wrote. A project whose base is no git repository with a
  commit has no places, so a container runs none of its dispatched work: it stops with the cause, `git init` and a
  first commit named. On your machine, with the word, such a project's sessions all work in the base and can read
  each other's conversations.
- A delivery with no recorded commit — a project dir that is no git repository, a DELIVER sent by an
  agent through the door rather than by the system's executor — is copied as it stands, ignored files
  and builds included, and nothing is built.
- Disk has no quota on Docker Desktop: a place, a validation's copy and a container's own layer stand on
  Docker's disk, shared by every project. Each session's work — a node's executor's, and each round
  or batch of its validations and checks apart — has a bound of its own instead: what it adds, over every
  directory its containers mount writable (its place, its round, its temp, its CLI state) and their
  own layers (bytes, and the paths a layer changed), `GFSO_NODE_DISK` (default 20 GiB) and
  `GFSO_NODE_FILES` (default 1,000,000). It counts from where the system left each directory when it
  made it and from nothing for a container made since; what the system itself writes there — a
  commit, a child's work carried into the base and the bundle that carries it, a join into a parent's
  place, a validation's copy, a check's copy and inputs, their removal — is no node's: the directory is
  measured just before and after each such write and the difference taken out, and a session is
  never ended while the system writes into one of its directories. Every 10 seconds the server reads its own
  installation's sessions; one past its bound has its containers removed, their layers with them,
  its directories kept, and the server's log says so; a validation's build so ended FAILs the delivery,
  the bound named. What a place's directories hold stays charged, so an executor whose place stays
  past its bound parks its node at once, the cause said to its issuer: every later session there
  would be ended again, and what lifts it is cancelling the node or a server restart, which counts
  the place again; one ended for what its own container's layer held goes on, that layer gone. Nothing a neighbour holds or writes, and no reading of free space, moves that. What a container prints is Docker's log, past every directory that bound reads: each keeps at most its last 20 MiB, so what the commands' record falls back on when a session holds every process it may start is that much. Not
  held: a session may overshoot by what it writes in 10 seconds plus the time a reading takes, which
  grows with what the installation holds; what a session writes into a directory while the system
  writes there is taken out with the system's write; the reader runs as root in the session's own
  image and needs GNU find there (the product's image has it): a directory it cannot read whole —
  in an image without it, its walk failing, or not within a minute — is left out, said in the server's
  log, and the session's charge there stands as it was, no other directory's touched; a session whose
  directory nests deeper than 4,096 levels, or whose walk fails or runs past a minute three readings
  in a row (its volume's whole reading running out counts for each of its directories; an image
  without GNU find does not count), is ended for it, and so is
  each later session there until the nest is gone; a server restart counts a place past its bound
  from what it then holds, so its next session there may add a bound again; each system write costs
  two readings (about half a second to a second and a half), none of it counted in the time the
  system's own checks are given; a layer's paths are counted again only after it grew 8 MiB;
  what stood before the server first read it is not counted (a restart starts the count again); N sessions may add N
  bounds together; and Docker's own disk on Windows is a file on the host's drive, which fills first
  if it is the smaller.
- A process a session starts runs until its call ends; one that left its call's group and dropped its mark runs on
  while another model client of the same place still works there, and ends with the place's last one — or, where the
  server died first, when the place's containers go: at its project's next start, or its place's removal.
- The Claude Code client's own tools — Read, Edit, Write — still run in its process, beside its
  output: the settings above keep them off it, as far as the client holds to them (NotebookEdit onto
  a pipe was not measured). A command cannot read the client's task-output files nor its
  model-client state; its Read tool can. A working directory a command leaves outside the place does
  not carry to the next command.
- A validation runs the delivered code in its own container: while its run lasts, that code can rewrite
  what the validation itself writes in its batch — the build included — and what the validation's later commands
  load (its shell's setup, its home), so a check the validation writes and runs itself is in the
  code's reach; a check that must be trusted is pinned with `exact: true`, and the system runs it in a container of its
  own on a fresh copy. It can also add files beside a pinned probe's
  inputs that a later step of the same command, or a later command of the validation, reads where it
  lists or searches that directory (a `GNUmakefile` beside a pinned `Makefile`), and a finding's files
  once the re-run has copied them out of the read-only directory and before it reads them. A file the
  delivered code rewrote in the validation's batch before its run ended is recorded as it then stood when
  a finding over it is filed.
- A finding filed before the system recorded probe files has its files recorded at its first re-run,
  from its round as it stands then; one whose round is already gone is shown, not demanded.

Under a container execution a node performed in your own chat (`perform="in_chat"`) is refused: its
work stands on your disk, where no container reads it.

Without an execution, and with `"GFSO_LOCAL_AGENTS": "allow"` in `data/serve.json`, sessions run as you, on your machine, with nothing between them and the rest
of it: a validation's copy is still the recorded commit where a scratch for it can be made, but nothing
is read-only to it, no container ends with its run, and a validation with no scratch runs in the
place itself.

How far a project's container reaches outside is a switch you set in its execution's declaration
(`"network": {"mode": ..., "hosts": [...]}`). For one project, `set_mode(network=...)` can only narrow it —
open → allowlist → off, an allowlist reaching only hosts the declaration also names — never widen it (once the
project has work in it, only with your own words asking for the change):
- `open` (the default) reaches outward: the internet, and its names through its resolvers — not your
  host's loopback nor Docker's own address for it, not the networks your machine stands on (private
  addresses, a tailnet's, link-local ones, a cloud's metadata among them: no switch reaches an intranet),
  and no IPv6 at all. A service of your host on a public address is the internet: bind it to `127.0.0.1`. On
  Docker's default bridge it opens one port alone, its project's doors' (a number in 20000–29999 by the project), on any
  container there: a service of yours listening on that very number answers it, and another project's door answers only to
  its own key.
- `off` reaches nothing but its model, through the door below (a Linux Docker Engine whose internal network still forwards name
  lookups, CVE-2024-29018, is refused at setup and at every start, as a Docker Desktop below its floor is): the container stands on an internal Docker network of its own with no route out, and none of its agent's processes holds a
  capability to make one. Each closed project takes one of Docker's address pools; past their
  number a start fails.
- Under every switch nothing reaches INTO a session's or a validation's container, and nothing passes
  directly between two of them (under `open` two may still relay through a server on the internet): before any call, root there admits only its own loopback and the answers to
  connections it opened, and on its own network it opens nothing but TCP to its project's door and
  gateway, from a port the kernel picks — two containers each sending to the other were each other's
  «answers» under the first rule alone. So no node's session reaches what another node's validation runs
  from a delivery, nor any other node's session.
- `allowlist`, a custom mode beside the two above (with the internet, or without it), kept minimal, adds one gateway container, the only way out. It opens a connection only to a host
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
server itself; only its tools run in the container: its commands through the system's shell into the commands' container
above, on the same record, under the same switch, what they left running ending with its run; its Read, Write and Edit in its place's client container, reading the base as a session reads it and a file up to
32 MiB, following a link a command laid as far as that container reaches (its own state and home, its own node alone), its Glob and
Grep read-only in the place's own, on no record but the agent trace you may turn on. The Claude Code client, which runs inside,
reaches its model under every switch through its project's door: a container of its own that
holds the credential (from `gfso credential`) and nothing of the project. The client — and every
command it runs, which inherits its environment — holds only the door's key, which opens that door and
no other; the door puts the credential in and passes the
request to the provider alone. So no process in a session — the client, its tools, what they run —
holds the credential to read or carry away, and another container is refused by the door. The
credential is in no container's configuration, environment or disk: the door reads it once from
memory and removes it; a credential replaced while calls run keeps its door, and so stays live,
until the project stops. Under every switch the door passes the model's messages alone, as one
JSON object it reads strictly (no compressed body, no key given twice) and sends on as it read it,
naming no file nor container the account holds — the credential opens far more of the account (its files, its
batches) — and it runs on the
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
changed does not run, in a tab that can drive the local tool surface. Everything else is local, the page's web font and that library's host aside:
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
