"""Which provider answers a model: a model spec `provider/model`, resolved here and nowhere else.

A spec rides wherever a model id already rides — a roster row, the system model, the engine's model — so each role
picks its own provider and nothing holds one global switch. An unprefixed id is Anthropic's, through the Claude Code CLI,
as it always was (`claude-haiku-4-5`, `sonnet`).

Three sources of providers, looked up in this order:
1. A third party's class, by the entry-point group `gfso.providers`: `name = "package.module:factory"`, where
   `factory(model, execution) -> LLMProviderPort`. A developer installs a package; nothing here changes.
2. A preset — DATA, not a class: the OpenAI-compatible wire at a known address, and whether it takes a key. The
   built-in ones are `PRESETS`; a user's own is the environment's `GFSO_PROVIDER_<NAME>_BASE_URL` (with `_CONTEXT`,
   `_MAX_TOKENS`, `_PRICE` = "input,output[,cached]" dollars per million tokens), which also overrides any field of a
   built-in one (a vLLM on another port).
3. `claude` — the Claude Code CLI, a subscription's token or an API key.
`GFSO_PROVIDER=generic` (with `GFSO_GENERIC_BASE_URL/_MODEL`) keeps meaning what it meant: every unprefixed id goes to
that endpoint.
Every provider's credential is set in ONE place and read from it by the provider alone (`credentials`: the door
`gfso credential <provider>`); a third party's factory reads its own the same way, by its name.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from importlib.metadata import entry_points
from typing import Optional

from gfso import config as _config
from . import credentials
from .chat import ChatProvider, OpenAIWire
from .headless import ClaudeCodeProvider


@dataclass(frozen=True)
class Preset:
    base_url: str
    keyed: bool = False                 # takes an API key (`credentials`, kind `api`)
    local: bool = False                 # runs on the user's machine: no bill, cost 0
    context: Optional[int] = None       # the model's window where the preset knows it
    max_tokens: Optional[int] = None
    price: Optional[tuple] = None       # dollars per million tokens: (input, output[, cached input])
    note: str = ""


PRESETS: dict[str, Preset] = {
    # on this machine
    "ollama": Preset("http://localhost:11434/v1", local=True,
                     note="its /v1 ignores num_ctx: set OLLAMA_CONTEXT_LENGTH on the server, or the model file's num_ctx"),
    "lmstudio": Preset("http://localhost:1234/v1", local=True),
    "llamacpp": Preset("http://localhost:8080/v1", local=True),
    "vllm": Preset("http://localhost:8001/v1", local=True,
                   note="vLLM's default port is gfso's 8000: serve it on another and say so in GFSO_PROVIDER_VLLM_BASE_URL"),
    # by API
    "deepseek": Preset("https://api.deepseek.com/v1", keyed=True),
    "qwen": Preset("https://dashscope-intl.aliyuncs.com/compatible-mode/v1", keyed=True),
    "openrouter": Preset("https://openrouter.ai/api/v1", keyed=True),
    "groq": Preset("https://api.groq.com/openai/v1", keyed=True),
    "together": Preset("https://api.together.xyz/v1", keyed=True),
    "mistral": Preset("https://api.mistral.ai/v1", keyed=True),
    "gemini": Preset("https://generativelanguage.googleapis.com/v1beta/openai", keyed=True),
    "openai": Preset("https://api.openai.com/v1", keyed=True),
}


def preset(name: str) -> Optional[Preset]:
    """The preset `name` stands for — built-in, overridden or defined by the environment — or None."""
    env = {f: _config.provider_env(name, f) for f in ("BASE_URL", "CONTEXT", "MAX_TOKENS", "PRICE")}
    base = PRESETS.get(name)
    if base is None and env["BASE_URL"] is None:
        return None
    p = base or Preset(env["BASE_URL"])
    return replace(p, base_url=env["BASE_URL"] or p.base_url,
                   context=int(env["CONTEXT"]) if env["CONTEXT"] else p.context,
                   max_tokens=int(env["MAX_TOKENS"]) if env["MAX_TOKENS"] else p.max_tokens,
                   price=tuple(float(x) for x in env["PRICE"].split(",")) if env["PRICE"] else p.price)


def _plugins() -> dict:
    try:
        return {e.name: e for e in entry_points(group="gfso.providers")}
    except Exception:  # noqa: BLE001 — a broken installed package's metadata hides its providers, not ours
        return {}


def names() -> list[str]:
    """Every provider name a spec may start with."""
    return sorted({"claude", *PRESETS, *_config.providers_in_env(), *_plugins()})


def split(spec: str) -> tuple[str, str]:
    """(provider, model) of a spec. An id whose first segment names no provider is Claude's whole — `claude-…` ids
    hold no slash, and an OpenRouter id (`openrouter/deepseek/deepseek-chat`) keeps its own after the provider's."""
    head, sep, rest = (spec or "").partition("/")
    if sep and rest and head in names():
        return head, rest
    return ("generic" if _config.provider() == "generic" else "claude"), spec


def chat_provider(p: Preset, model: str, execution=None, key: Optional[str] = None) -> ChatProvider:
    """The OpenAI-compatible provider a preset describes; a local one bills nothing unless it declares a tariff."""
    wire = OpenAIWire(p.base_url, model, key, max_tokens=p.max_tokens, context_window=p.context,
                      tariff=(0.0, 0.0, 0.0) if p.local and p.price is None else p.price)
    return ChatProvider(wire, model, execution=execution)


def provider_for(spec: str, execution=None):
    """THE resolution of a model spec into the provider that answers it."""
    name, model = split(spec)
    if name == "generic":
        g = _config.generic_provider()
        if not g["base_url"]:
            raise ValueError("GFSO_PROVIDER=generic needs GFSO_GENERIC_BASE_URL — the OpenAI-compatible endpoint")
        return chat_provider(Preset(g["base_url"]), g["model"] or model, execution, _key("generic"))
    if (plugin := _plugins().get(name)) is not None:
        return plugin.load()(model, execution)
    if (p := preset(name)) is not None:
        made = chat_provider(p, model, execution, key := _key(name))
        if p.keyed and not key:                # every call answers "unauthorized": the project stops, no node is parked
            made.wire.missing_key = f"set it: gfso credential {name} --kind api"
        return made
    return ClaudeCodeProvider(model=model, execution=execution)    # its credential read at each call's start


def _key(name: str) -> Optional[str]:
    """`name`'s API key, where its one place holds one."""
    c = credentials.get(name)
    return c.value if c and c.kind == "api" else None


def takes(name: str) -> tuple[str, ...]:
    """The kinds of credential the provider `name` takes (`credentials`) — the door refuses any other."""
    if name == "claude":                       # the one name its credential is read by (`provider_for`)
        return ClaudeCodeProvider.credential_kinds
    if name == "generic":
        return ("api",)
    if name in _plugins():                     # a third party's factory reads its own by its name, of either kind
        return credentials.KINDS
    if (p := preset(name)) is not None:
        # …a user's own endpoint may want one or not (a vLLM behind a gateway): it takes one and needs none
        return ("api",) if p.keyed or name not in PRESETS else ()
    raise ValueError(f"no provider {name!r}: one of {', '.join(names())}")


def set_credential(name: str, kind: str, value: str | None, label: str | None = None) -> dict:
    """THE door's one act, for every provider: set (or, with None, remove) `name`'s credential `label` of `kind` in its
    one place. Answers what is set now, never a value. An API key pasted at Claude's token prompt is held as what it is:
    as a token it reached the client as one, and every call was refused."""
    if name == "claude" and value and value.strip().startswith("sk-ant-api"):
        kind = "api"
    return credentials.put(name, kind, value, takes(name), label)
