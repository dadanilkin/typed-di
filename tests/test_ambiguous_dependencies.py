import dataclasses
import re
from typing import ContextManager, Awaitable, AsyncContextManager

import pytest

from tests.utils import ComparableDepends
from typed_di import Depends, invoke, create
from typed_di._exceptions import ValueFromFactoryWereRequestedUnresolved, ValueFromFactoryAlreadyResolved


@dataclasses.dataclass
class Foo:
    val: str


class FooCM:
    def __enter__(self):
        return Foo("cm")

    def __exit__(self, exc_type, exc_val, exc_tb):
        return


class FooAsyncCM:
    async def __aenter__(self):
        return Foo("async-cm")

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return


class FooAwaitable:
    def __await__(self):
        if False:
            yield

        return Foo("awaitable")


def create_cm() -> ContextManager[Foo]:
    return FooCM()


def create_async() -> Awaitable[Foo]:
    return FooAwaitable()


def create_async_cm() -> AsyncContextManager[Foo]:
    return FooAsyncCM()


def create_async_awaitable() -> Awaitable[Awaitable[Foo]]:
    ...


def create_cm_in_cm() -> ContextManager[ContextManager[Foo]]:
    ...


def create_async_cm_in_async_cm() -> AsyncContextManager[AsyncContextManager[Foo]]:
    ...


class TestForCM:
    async def test_requested_foo(self, handler_ctx):
        async def fn(dep: Depends[Foo] = Depends(create_cm)) -> Foo:
            return dep()

        assert await invoke(handler_ctx, fn) == Foo("cm")

    async def test_requested_cm(self, handler_ctx):
        async def fn(dep: Depends[FooCM] = Depends(create_cm)) -> FooCM:
            return dep()

        res = await create(handler_ctx, Depends[FooCM], Depends(fn))
        assert isinstance(res, FooCM)
        with res as foo:
            assert foo == Foo("cm")

    async def test_rejects_values_requested_twice_in_different_forms(self, handler_ctx):
        async def fn(
            cm_from_callable: Depends[ContextManager[Foo]] = Depends(create_cm),
            val_from_cm: Depends[Foo] = Depends(create_cm),
        ) -> None:
            ...

        with pytest.raises(ValueFromFactoryWereRequestedUnresolved) as exc_info:
            await invoke(handler_ctx, fn)

        assert exc_info.value.args == (
            Depends[Foo],
            ComparableDepends(create_cm),
            "explicit",
            Depends[ContextManager[Foo]],
            create_cm,
        )

    async def test_rejects_values_requested_twice_in_different_forms_transitive(self, handler_ctx):
        async def dep(cm_from_callable: Depends[ContextManager[Foo]] = Depends(create_cm)) -> None:
            ...

        async def fn(
            dep_: Depends[None] = Depends(dep),
            val_from_cm: Depends[Foo] = Depends(create_cm),
        ) -> None:
            ...

        with pytest.raises(ValueFromFactoryWereRequestedUnresolved) as exc_info:
            await invoke(handler_ctx, fn)

        assert exc_info.value.args == (
            Depends[Foo],
            ComparableDepends(create_cm),
            "explicit",
            Depends[ContextManager[Foo]],
            create_cm,
        )

    async def test_rejects_values_requested_twice_in_different_forms_transitive_v2(self, handler_ctx):
        async def dep(
            val_from_cm: Depends[Foo] = Depends(create_cm),
        ) -> None:
            ...

        async def fn(
            dep_: Depends[None] = Depends(dep), cm_from_callable: Depends[ContextManager[Foo]] = Depends(create_cm)
        ) -> None:
            ...

        with pytest.raises(ValueFromFactoryAlreadyResolved) as exc_info:
            await invoke(handler_ctx, fn)

        assert exc_info.value.args == (
            Depends[ContextManager[Foo]],
            ComparableDepends(create_cm),
            "explicit",
            Depends[Foo],
            create_cm,
        )


class TestForAsyncCM:
    async def test_requested_foo(self, handler_ctx):
        async def fn(dep: Depends[Foo] = Depends(create_async_cm)) -> Foo:
            return dep()

        assert await invoke(handler_ctx, fn) == Foo("async-cm")

    async def test_requested_async_cm(self, handler_ctx):
        async def fn(dep: Depends[FooAsyncCM] = Depends(create_async_cm)) -> FooAsyncCM:
            return dep()

        res = await invoke(handler_ctx, fn)
        assert isinstance(res, FooAsyncCM)
        async with res as foo:
            assert foo == Foo("async-cm")

    async def test_rejects_values_requested_twice_in_different_forms(self, handler_ctx):
        async def fn(
            async_cm_from_callable: Depends[AsyncContextManager[Foo]] = Depends(create_async_cm),
            val_from_async_cm: Depends[Foo] = Depends(create_async_cm),
        ) -> None:
            ...

        with pytest.raises(ValueFromFactoryWereRequestedUnresolved) as exc_info:
            await invoke(handler_ctx, fn)

        assert exc_info.value.args == (
            Depends[Foo],
            ComparableDepends(create_async_cm),
            "explicit",
            Depends[AsyncContextManager[Foo]],
            create_async_cm,
        )

    async def test_rejects_values_requested_twice_in_different_forms_transitive(self, handler_ctx):
        async def dep(async_cm_from_callable: Depends[AsyncContextManager[Foo]] = Depends(create_async_cm)) -> None:
            ...

        async def fn(
            dep_: Depends[None] = Depends(dep),
            val_from_async_cm: Depends[Foo] = Depends(create_async_cm),
        ) -> None:
            ...

        with pytest.raises(ValueFromFactoryWereRequestedUnresolved) as exc_info:
            await invoke(handler_ctx, fn)

        assert exc_info.value.args == (
            Depends[Foo],
            ComparableDepends(create_async_cm),
            "explicit",
            Depends[AsyncContextManager[Foo]],
            create_async_cm,
        )

    async def test_rejects_values_requested_twice_in_different_forms_transitive_v2(self, handler_ctx):
        async def dep(
            val_from_async_cm: Depends[Foo] = Depends(create_async_cm),
        ) -> None:
            ...

        async def fn(
            dep_: Depends[None] = Depends(dep),
            async_cm_from_callable: Depends[AsyncContextManager[Foo]] = Depends(create_async_cm),
        ) -> None:
            ...

        with pytest.raises(ValueFromFactoryAlreadyResolved) as exc_info:
            await invoke(handler_ctx, fn)

        assert exc_info.value.args == (
            Depends[AsyncContextManager[Foo]],
            ComparableDepends(create_async_cm),
            "explicit",
            Depends[Foo],
            create_async_cm,
        )


class TestForAwaitable:
    async def test_requested_foo(self, handler_ctx):
        async def fn(dep: Depends[Foo] = Depends(create_async)) -> Foo:
            return dep()

        assert await invoke(handler_ctx, fn) == Foo("awaitable")

    async def test_requested_awaitable(self, handler_ctx):
        async def fn(dep: Depends[FooAwaitable] = Depends(create_async)) -> FooAwaitable:
            return dep()

        res = await invoke(handler_ctx, fn)
        assert isinstance(res, FooAwaitable)

        foo = await res
        assert foo == Foo("awaitable")

    async def test_rejects_values_requested_twice_in_different_forms(self, handler_ctx):
        async def fn(
            awaitable_from_callable: Depends[Awaitable[Foo]] = Depends(create_async),
            val_from_awaitable: Depends[Foo] = Depends(create_async),
        ) -> None:
            ...

        with pytest.raises(ValueFromFactoryWereRequestedUnresolved) as exc_info:
            await invoke(handler_ctx, fn)

        assert exc_info.value.args == (
            Depends[Foo],
            ComparableDepends(create_async),
            "explicit",
            Depends[Awaitable[Foo]],
            create_async,
        )

    async def test_rejects_values_requested_twice_in_different_forms_transitive(self, handler_ctx):
        async def dep(awaitable_from_callable: Depends[Awaitable[Foo]] = Depends(create_async)) -> None:
            ...

        async def fn(
            dep_: Depends[None] = Depends(dep),
            val_from_awaitable: Depends[Foo] = Depends(create_async),
        ) -> None:
            ...

        with pytest.raises(ValueFromFactoryWereRequestedUnresolved) as exc_info:
            await invoke(handler_ctx, fn)

        assert exc_info.value.args == (
            Depends[Foo],
            ComparableDepends(create_async),
            "explicit",
            Depends[Awaitable[Foo]],
            create_async,
        )

    async def test_rejects_values_requested_twice_in_different_forms_transitive_v2(self, handler_ctx):
        async def dep(val_from_awaitable: Depends[Foo] = Depends(create_async)) -> None:
            ...

        async def fn(
            dep_: Depends[None] = Depends(dep), awaitable_from_callable: Depends[Awaitable[Foo]] = Depends(create_async)
        ) -> None:
            ...

        with pytest.raises(ValueFromFactoryAlreadyResolved) as exc_info:
            await invoke(handler_ctx, fn)

        assert exc_info.value.args == (
            Depends[Awaitable[Foo]],
            ComparableDepends(create_async),
            "explicit",
            Depends[Foo],
            create_async,
        )
