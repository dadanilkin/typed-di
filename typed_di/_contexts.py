from __future__ import annotations

import abc
import contextlib
from contextlib import AsyncExitStack
from typing import AsyncContextManager, AsyncIterator, Callable, Generic, Mapping, TypeAlias, TypeVar, final, overload

from typing_extensions import assert_never

from typed_di import _scope


@overload
def enter_next_scope(
    ctx: RootContext, /, *, implicit_factories: Mapping[str, Callable[..., object]] | None = None
) -> AsyncContextManager[AppContext]:
    ...


@overload
def enter_next_scope(
    ctx: AppContext, /, *, implicit_factories: Mapping[str, Callable[..., object]] | None = None
) -> AsyncContextManager[HandlerContext]:
    ...


@overload
def enter_next_scope(
    ctx: HandlerContext, /, *, implicit_factories: Mapping[str, Callable[..., object]] | None = None
) -> AsyncContextManager[HandlerContext]:
    ...


def enter_next_scope(
    ctx: RootContext | AppContext | HandlerContext,
    /,
    *,
    implicit_factories: Mapping[str, Callable[..., object]] | None = None,
) -> AsyncContextManager[AppContext | HandlerContext]:
    next_ctx: AppContext | HandlerContext
    match ctx:
        case RootContext():
            next_ctx = AppContext(ctx, implicit_factories or {}, _used_internally=True)
        case AppContext():
            next_ctx = HandlerContext(ctx, implicit_factories or {}, _used_internally=True)
        case HandlerContext():
            return contextlib.nullcontext(ctx)
        case _:
            assert_never(ctx)

    return _enter_inner(next_ctx)


@contextlib.asynccontextmanager
async def _enter_inner(ctx: AppContext | HandlerContext) -> AsyncIterator[AppContext | HandlerContext]:
    async with ctx._enter():
        yield ctx


ObjectsCache: TypeAlias = dict[object, tuple[object, object, bool]]


class _BaseContext(abc.ABC):
    def __init__(self) -> None:
        self._entered = False
        self._exited = False

        self._name = type(self).__name__.rstrip("Context").lower()

    @contextlib.asynccontextmanager
    async def _enter(self) -> AsyncIterator[None]:
        if self._entered:
            raise RuntimeError(f"{self._name.capitalize()} already entered")
        self._entered = True

        try:
            yield
        finally:
            self._entered = False


PC = TypeVar("PC", bound=_BaseContext)
T = TypeVar("T", bound="_BaseNonRootContext[_BaseContext]")


class _BaseNonRootContext(_BaseContext, Generic[PC]):
    def __init__(
        self,
        prev_ctx: PC,
        implicit_factories: Mapping[str, Callable[..., object]],
        /,
        *,
        used_internally: bool,
    ) -> None:
        if not used_internally:
            raise RuntimeError(
                f"Attempt to create `{type(self).__name__}` detected, class is intended for internal creation only"
            )

        super().__init__()

        self._exit_stack = AsyncExitStack()

        self._prev_ctx: PC = prev_ctx
        self._implicit_factories = implicit_factories
        self._cache: ObjectsCache = {}

    @contextlib.asynccontextmanager
    async def _enter(self) -> AsyncIterator[None]:
        async with super()._enter():
            async with self._exit_stack:
                yield


@final
class RootContext(_BaseContext):
    def __init__(
        self,
        override_factories: Mapping[Callable[..., object], Callable[..., object]] | None = None,
        /,
        **bootstrap_values: object,
    ) -> None:
        super().__init__()

        self._override_factories = override_factories or {}
        self._bootstrap_values = bootstrap_values


@final
class AppContext(_BaseNonRootContext[RootContext]):
    def __init__(
        self,
        root_ctx: RootContext,
        implicit_factories: Mapping[str, Callable[..., object]],
        /,
        *,
        _used_internally: bool = False,
    ) -> None:
        super().__init__(root_ctx, implicit_factories, used_internally=_used_internally)


HT = TypeVar("HT", bound="HandlerContext")


@final
class HandlerContext(_BaseNonRootContext[AppContext]):
    def __init__(
        self,
        app_ctx: AppContext,
        implicit_factories: Mapping[str, Callable[..., object]],
        /,
        *,
        _used_internally: bool = False,
    ) -> None:
        if any(factory for factory in implicit_factories.values() if _scope.get_factory_scope(factory) == "app"):
            raise ValueError(
                "It is forbidden to use app scope implicit factories in handler context, "
                "use them while entering app scope"
            )

        super().__init__(app_ctx, implicit_factories, used_internally=_used_internally)


def check_context_entered(ctx: AppContext | HandlerContext) -> None:
    if ctx._entered:
        return

    raise RuntimeError(f"Attempt to operate on unentered context `{type(ctx).__qualname__}`")


def get_root_ctx(ctx: AppContext | HandlerContext) -> RootContext:
    c: AppContext | HandlerContext | RootContext = ctx
    while not isinstance(c, RootContext):
        c = c._prev_ctx

    return c


def get_app_ctx(ctx: AppContext | HandlerContext) -> AppContext:
    if isinstance(ctx, AppContext):
        return ctx
    else:
        return ctx._prev_ctx


def get_app_cache(ctx: AppContext | HandlerContext) -> ObjectsCache:
    return get_app_ctx(ctx)._cache


def get_handler_cache(ctx: HandlerContext) -> ObjectsCache:
    return ctx._cache


def get_app_exit_stack(ctx: AppContext | HandlerContext) -> AsyncExitStack:
    return get_app_ctx(ctx)._exit_stack


def get_handler_exit_stack(ctx: HandlerContext) -> AsyncExitStack:
    return ctx._exit_stack


def lookup_implicit_factory(ctx: AppContext | HandlerContext, name: str) -> Callable[..., object] | None:
    while True:
        try:
            return ctx._implicit_factories[name]
        except KeyError:
            if isinstance(ctx, HandlerContext):
                ctx = ctx._prev_ctx
            else:
                break

    return None
