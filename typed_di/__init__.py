from typing import TYPE_CHECKING

from typed_di._contexts import AppContext, HandlerContext, RootContext, enter_next_scope
from typed_di._create import create
from typed_di._depends import Depends
from typed_di._exceptions import (
    CreationError,
    DependencyByNameNotFound,
    Error,
    HandlerScopeDepRequestedFromAppScope,
    InvalidInvokableFunction,
    InvokableDependencyError,
    InvokeError,
    NestedInvokeError,
    ValueFromFactoryAlreadyResolved,
    ValueFromFactoryWereRequestedUnresolved,
    ValueOfUnexpectedTypeReceived,
)
from typed_di._invoke import invoke, validate_invokable, validated
from typed_di._partial import partial
from typed_di._scope import get_factory_scope, scoped

__all__ = [
    "RootContext",
    "AppContext",
    "HandlerContext",
    "enter_next_scope",
    "create",
    "Depends",
    "invoke",
    "validate_invokable",
    "validated",
    "Error",
    "InvokeError",
    "InvokableDependencyError",
    "InvalidInvokableFunction",
    "CreationError",
    "NestedInvokeError",
    "DependencyByNameNotFound",
    "HandlerScopeDepRequestedFromAppScope",
    "ValueFromFactoryWereRequestedUnresolved",
    "ValueFromFactoryAlreadyResolved",
    "ValueOfUnexpectedTypeReceived",
    "partial",
]


if TYPE_CHECKING:
    from typing import AsyncContextManager, Awaitable, ContextManager, Iterable, Mapping

    def different_factories_example() -> None:
        class Foo:
            ...

        class FooInheritor(Foo):
            ...

        def foo_sync() -> Foo:
            ...

        def foo_cm() -> ContextManager[Foo]:
            ...

        def foo_async() -> Awaitable[Foo]:
            ...

        def foo_async_cm() -> AsyncContextManager[Foo]:
            ...

        def foo_inheritor_sync() -> FooInheritor:
            ...

        async def handler(
            # Без явного указания фабрики
            foo_bare: Depends[Foo],
            # Правильный бинд фабрик
            foo_from_sync: Depends[Foo] = Depends(foo_sync),
            foo_from_cm: Depends[Foo] = Depends(foo_cm),
            foo_from_async: Depends[Foo] = Depends(foo_async),
            foo_from_async_cm: Depends[Foo] = Depends(foo_async_cm),
            # `Depends` ковариантна по `T`, поэтому можно передать фабрику с более
            #  частным возвращаемым типом
            foo_from_inheritor_factory: Depends[Foo] = Depends(foo_inheritor_sync),
        ) -> int:
            ...

    def invalid_factories_example() -> None:
        class Foo:
            ...

        class Bar:
            ...

        def bar_sync() -> Bar:
            ...

        def bar_cm() -> ContextManager[Bar]:
            ...

        def bar_async() -> Awaitable[Bar]:
            ...

        def bar_async_cm() -> AsyncContextManager[Bar]:
            ...

        async def handler(
            # Везде будут выбрасываться ошибки вида "Argument 1 to `Depends` has incompatible type
            #  `(...) -> Bar`, expected `(...) -> Foo | (...) -> ContextManager[Foo] | ...`
            foo_wrong_from_sync: Depends[Foo] = Depends(bar_sync),  # type: ignore[arg-type]
            foo_wrong_from_cm: Depends[Foo] = Depends(bar_cm),  # type: ignore[arg-type]
            foo_wrong_from_async: Depends[Foo] = Depends(bar_async),  # type: ignore[arg-type]
            foo_wrong_from_async_cm: Depends[Foo] = Depends(bar_async_cm),  # type: ignore[arg-type]
        ) -> int:
            ...

    async def partial_function(ctx: HandlerContext) -> None:
        class Foo:
            ...

        class Bar:
            ...

        async def fn(
            pa1: int,
            pa2: str,
            /,
            dep1: Depends[Foo],
            pok1: Mapping[object, object],
            *,
            ko1: Iterable[object],
            dep2: Depends[Bar],
        ) -> Bar:
            ...

        await partial(fn)(
            ctx,
            int(),
            str(),
            {},
            ko1=[],
        )
        await partial(fn)(
            ctx,
            int(),
            str(),
            pok1={},
            ko1=[],
        )

        await partial(fn)(
            ctx,
            int(),
            str(),
            pok1={},
            ko1=[],
            unexpected_arg=10,  # mypy should rise error, but it's not still typed
        )
