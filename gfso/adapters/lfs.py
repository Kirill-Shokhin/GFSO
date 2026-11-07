"""Git LFS inside a project's volume, done by the system: no git-lfs and no config of the user's runs there.

A file the user's `.gitattributes` marks `filter=lfs` is committed as a POINTER (its object's sha256 and size) and
its content kept in `.git/lfs/objects`. The base's import carries the objects HEAD's pointers name, a join and a
landing the objects of the pointers they carry (`worktrees._lfs_carried`), and every git call the system makes in a
container names this module as the `lfs` filter (`filter_args`): a checkout writes an object's content where its
pointer stood — only once its size and sha256 are the pointer's; otherwise the pointer stays —, and a staging writes
the pointer back, the content kept in the repository's own store, so no delivery commits an LFS file's content as a
blob. One process per git call, speaking git's long-running filter protocol (`main`). Run as a filter, this file is
the whole program — stdlib only, under `python -I`: git starts it in the work tree, whose files are an agent's."""
import ast
import base64
import functools
import hashlib
import os
import subprocess
import sys
import tempfile
import zlib

SPEC = b"version https://git-lfs.github.com/spec/v1\n"
#: a pointer is at most this long (git-lfs's own bound); anything longer is content
LONGEST = 1024
CHUNK = 1 << 20
#: the largest payload of one pkt-line
PKT = 65516


def parse(data: bytes):
    """(oid, size) of an LFS pointer, None for anything else."""
    if len(data) > LONGEST or not data.startswith(SPEC):
        return None
    keys = dict(line.split(b" ", 1) for line in data[len(SPEC):].splitlines() if b" " in line)
    oid, size = keys.get(b"oid", b"").removeprefix(b"sha256:").decode("ascii", "replace"), keys.get(b"size", b"")
    ok = len(oid) == 64 and all(c in "0123456789abcdef" for c in oid) and size.isdigit()
    return (oid, int(size)) if ok else None


def pointer(oid: str, size: int) -> bytes:
    """The LFS pointer of an object."""
    return SPEC + f"oid sha256:{oid}\nsize {size}\n".encode()


def path_in(store: str, oid: str) -> str:
    """Where `store` keeps the object `oid`, as git-lfs lays it out."""
    return os.path.join(store, oid[:2], oid[2:4], oid)


def verified(path: str, oid: str, size: int) -> bool:
    """Is the object at `path` the pointer's — its size, then its sha256?"""
    try:
        if os.path.getsize(path) != size:
            return False
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(CHUNK):
                h.update(chunk)
        return h.hexdigest() == oid
    except OSError:
        return False


def smudge(src, dst, stores) -> bool:
    """`src` to `dst`: a pointer as its object's content, from the first of `stores` holding it verified; anything
    else — content, a pointer with no verified object — as it stands. True where content was written."""
    head = src.read(LONGEST + 1)
    if (p := parse(head)) is not None:
        for s in stores:
            if verified(at := path_in(s, p[0]), *p):
                with open(at, "rb") as f:
                    while chunk := f.read(CHUNK):
                        dst.write(chunk)
                return True
        if any(os.path.exists(path_in(s, p[0])) for s in stores):
            sys.stderr.write(f"gfso lfs: the object {p[0]} is not the pointer's (size or sha256): left a pointer\n")
    # …the input read whole before any output: git writes a file's whole content before it reads the reply, and a
    # raw blob past a pipe's size at an LFS path hung both ends (critic over 63b75ae, run: 3 MiB)
    with tempfile.TemporaryFile() as rest:
        while chunk := src.read(CHUNK):
            rest.write(chunk)
        rest.seek(0)
        dst.write(head)
        while chunk := rest.read(CHUNK):
            dst.write(chunk)
    return False


def clean(src, dst, store: str) -> None:
    """`src` to `dst` as its pointer, the content kept in `store` — a pointer passed as it stands."""
    head = src.read(LONGEST + 1)
    if parse(head) is not None:
        dst.write(head)
        return
    os.makedirs(store, exist_ok=True)
    h, size = hashlib.sha256(), 0
    with tempfile.NamedTemporaryFile(dir=store, delete=False) as tmp:
        chunk = head
        while chunk:
            h.update(chunk)
            tmp.write(chunk)
            size += len(chunk)
            chunk = src.read(CHUNK)
    oid = h.hexdigest()
    os.makedirs(os.path.dirname(at := path_in(store, oid)), exist_ok=True)
    if verified(at, oid, size):
        os.unlink(tmp.name)
    else:
        os.replace(tmp.name, at)
    dst.write(pointer(oid, size))


def stores_of(common: str) -> list:
    """The repository's own store, then each of its borrowed object stores' — a node's clone reads the base's."""
    out, alt = [os.path.join(common, "lfs", "objects")], os.path.join(common, "objects", "info", "alternates")
    if os.path.isfile(alt):
        with open(alt, encoding="utf-8", errors="replace") as f:
            out += [os.path.normpath(os.path.join(common, "objects", a.strip(), "..", "lfs", "objects"))
                    for a in f if a.strip() and not a.startswith("#")]
    return out


def _pkt(i):
    """One pkt-line's payload, None for a flush; EOFError where git closed the pipe."""
    if len(head := i.read(4)) < 4:
        raise EOFError
    return i.read(n - 4) if (n := int(head, 16)) else None


def _list(i) -> list:
    """The lines up to a flush, each without its LF."""
    out = []
    while (p := _pkt(i)) is not None:
        out.append(p.rstrip(b"\n"))
    return out


def _send(o, *lines) -> None:
    """`lines` and a flush."""
    for x in lines:
        o.write(b"%04x" % (len(x) + 5) + x + b"\n")
    o.write(b"0000")


class _In:
    """A file's content as git sends it, read as a stream up to its flush."""

    def __init__(self, i):
        self.i, self.buf, self.done = i, bytearray(), False

    def read(self, n: int) -> bytes:
        """Up to `n` bytes, fewer only at the content's end."""
        while len(self.buf) < n and not self.done:
            p = _pkt(self.i)
            self.done = p is None
            self.buf += p or b""
        out = bytes(self.buf[:n])
        del self.buf[:n]
        return out

    def drain(self) -> None:
        """The rest of the content read past, so the next command starts where git sends it."""
        while not self.done:
            self.read(CHUNK)


class _Out:
    """A file's content sent back as pkt-lines."""

    def __init__(self, o):
        self.o = o

    def write(self, data: bytes) -> None:
        """`data` as pkt-lines, each at most `PKT` long."""
        for k in range(0, len(data), PKT):
            self.o.write(b"%04x" % (len(c := data[k:k + PKT]) + 4) + c)


def main() -> None:
    """The filter as git runs it, once per git call, in its repository's work tree: git's long-running filter
    protocol (version 2) over stdin and stdout, `clean` and `smudge` for every file git hands it; a file that fails
    answers `status=error`, and `required` fails git's call."""
    i, o = sys.stdin.buffer, sys.stdout.buffer
    common = subprocess.run(["git", "rev-parse", "--git-common-dir"], capture_output=True, text=True).stdout.strip()
    stores = stores_of(os.path.abspath(common or ".git"))
    if _list(i) != [b"git-filter-client", b"version=2"]:
        sys.exit("gfso lfs: not git's filter protocol, version 2")
    _send(o, b"git-filter-server", b"version=2")
    o.flush()
    asked = _list(i)
    _send(o, *[c for c in (b"capability=clean", b"capability=smudge") if c in asked])
    o.flush()
    while True:
        try:
            how = dict(x.split(b"=", 1) for x in _list(i) if b"=" in x).get(b"command")
        except EOFError:
            return
        src = _In(i)
        _send(o, b"status=success")
        try:
            if how == b"smudge":
                smudge(src, _Out(o), stores)
            elif how == b"clean":
                clean(src, _Out(o), stores[0])
            else:
                raise ValueError(f"no command {how!r}")
            src.drain()
            _send(o)
            _send(o)                                    # …an empty list: the status stays `success`
        except Exception as e:                          # noqa: BLE001 — said to git, which fails its call
            sys.stderr.write(f"gfso lfs: {e}\n")
            src.drain()
            _send(o)
            _send(o, b"status=error")
        o.flush()


#: what runs on the host alone, never in the program the filter rides git's argv as
_HOST = ("settings", "filter_args", "is_object")


@functools.cache
def settings(python: str = "python3") -> tuple:
    """((key, value), …) naming this module, run by `python -I`, the `lfs` filter's process — a git call's `-c`
    (`filter_args`), and a node's clone's own config, so an agent's own git there agrees (`worktrees.ensure`)."""
    with open(__file__, encoding="utf-8") as f:
        tree = ast.parse(f.read())     # …the program without its docstrings and host code: it rides every git call's argv
    tree.body = [n for n in tree.body if not (isinstance(n, ast.FunctionDef) and n.name in _HOST)]
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef)) and isinstance(n.body[0], ast.Expr) \
                and isinstance(n.body[0].value, ast.Constant):
            n.body = n.body[1:] or [ast.Pass()]
    packed = base64.b64encode(zlib.compress(ast.unparse(tree).encode(), 9)).decode()
    return (("filter.lfs.process", f"{python} -I -c \"import base64,zlib;exec(zlib.decompress(base64.b64decode("
                                    f"'{packed}')))\""), ("filter.lfs.required", "true"))


def filter_args(python: str = "python3") -> tuple:
    """`-c` settings of the `lfs` filter (`settings`) — a git call's own, after the repository's, so none of its config
    replaces it: a `process` given by `-c` wins over the repository's `process`, and a `process` over any `clean` or
    `smudge`; required, so a staging whose filter fails commits nothing."""
    return tuple(a for k, v in settings(python) for a in ("-c", f"{k}={v}"))


def is_object(data: bytes, oid: str, size: int) -> bool:
    """Are `data` the object `oid` of `size` bytes?"""
    return len(data) == size and hashlib.sha256(data).hexdigest() == oid


if __name__ == "__main__":
    main()
