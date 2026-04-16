from dataclasses import dataclass
from typing import Callable, Protocol

from PIL import Image


class EffectRenderFn(Protocol):
    def __call__(self, **kwargs) -> Image.Image: ...


@dataclass(frozen=True)
class Effect:
    name: str
    kind: str                  # "single" or "dual"
    render: EffectRenderFn
    description: str = ""


EFFECT_REGISTRY: dict[str, Effect] = {}


def register_effect(name: str, kind: str, description: str = "") -> Callable:
    if kind not in {"single", "dual"}:
        raise ValueError(f"Unknown effect kind: {kind!r}")

    def decorator(fn: EffectRenderFn) -> EffectRenderFn:
        if name in EFFECT_REGISTRY:
            raise ValueError(f"Effect {name!r} already registered")
        EFFECT_REGISTRY[name] = Effect(
            name=name, kind=kind, render=fn, description=description,
        )
        return fn

    return decorator


def get_effect(name: str) -> Effect:
    if name not in EFFECT_REGISTRY:
        valid = ", ".join(sorted(EFFECT_REGISTRY)) or "<none>"
        raise KeyError(f"Unknown effect {name!r}. Registered: {valid}")
    return EFFECT_REGISTRY[name]


def list_effects() -> list[Effect]:
    return list(EFFECT_REGISTRY.values())


# Import effect modules so their @register_effect decorators run.
from api_functions.effects import black_bar, frosted_glass  # noqa: E402, F401
