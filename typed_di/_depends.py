from __future__ import annotations

from dataclasses import dataclass
from typing import (
    AsyncContextManager,
    Awaitable,
    Callable,
    ContextManager,
    Generic,
    Protocol,
    TypeAlias,
    TypeGuard,
    TypeVar,
    cast,
    final,
    get_args,
    get_origin,
)

from typing_extensions import assert_never

T = TypeVar("T")
T_cov = TypeVar("T_cov", covariant=True)


class SyncFactory(Protocol[T_cov]):
    def __call__(self, *args: object, **kwargs: object) -> T_cov:
        raise NotImplementedError


class CMFactory(Protocol[T_cov]):
    def __call__(self, *args: object, **kwargs: object) -> ContextManager[T_cov]:
        raise NotImplementedError


class AsyncFactory(Protocol[T_cov]):
    def __call__(self, *args: object, **kwargs: object) -> Awaitable[T_cov]:
        raise NotImplementedError


class AsyncCMFactory(Protocol[T_cov]):
    def __call__(self, *args: object, **kwargs: object) -> AsyncContextManager[T_cov]:
        raise NotImplementedError


AnyFactory: TypeAlias = SyncFactory[T_cov] | CMFactory[T_cov] | AsyncFactory[T_cov] | AsyncCMFactory[T_cov]


@dataclass(frozen=True)
class Resolved(Generic[T_cov]):
    value: T_cov


@dataclass(frozen=True)
class Unresolved(Generic[T_cov]):
    factory: AnyFactory[T_cov]


@final
class Depends(Generic[T_cov]):
    def __init__(
        self,
        # Can't use `AnyFactory[T_cov]` here because mypy bug :(
        factory: (
            Callable[..., T_cov]
            | Callable[..., ContextManager[T_cov]]
            | Callable[..., Awaitable[T_cov]]
            | Callable[..., AsyncContextManager[T_cov]]
        ),
        /,
    ) -> None:
        self._state: Resolved[T_cov] | Unresolved[T_cov] = Unresolved(factory)

    def __call__(self) -> T_cov:
        if not isinstance(self._state, Resolved):
            raise RuntimeError("Attempt to access unresolved depends")
        return self._state.value

    def __repr__(self) -> str:
        return f"<Depends state={self._state!r}>"

    @staticmethod
    def resolved(val: T) -> Depends[T]:
        # `cls(...)` makes mypy mad
        dep = Depends(lambda: val)
        dep._state = Resolved(val)
        return dep


def is_dep(val: object) -> TypeGuard[type[Depends[object]]]:
    origin = get_origin(val)
    return isinstance(origin, type) and issubclass(origin, Depends)


def get_type_arg(dep_type: type[Depends[T]]) -> type[T] | object:
    match get_args(dep_type):
        case []:
            raise TypeError("Non parametrized dependency received")
        case [type() as t]:
            return cast(type[T], t)
        case [object() as t]:
            return t
        case _:
            raise TypeError(f"Unexpected parameters found in `{dep_type}`")


def get_state(dep: Depends[T], /) -> Resolved[T] | Unresolved[T]:
    return dep._state
