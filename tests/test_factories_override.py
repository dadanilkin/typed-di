import contextlib
from typing import AsyncIterator, Iterator

import pytest

from tests.shared import Foo
from tests.utils import ComparableDepends, raises_match_by_val
from typed_di import (
    Depends,
    HandlerScopeDepRequestedFromAppScope,
    InvokableDependencyError,
    InvokeError,
    NestedInvokeError,
    RootContext,
    enter_next_scope,
    invoke,
    scoped,
)


async def test_overrides_explicit_factory():
    def orig_factory() -> Foo:
        raise RuntimeError("Should not be called")

    def mocked_factory() -> Foo:
        return Foo("from-mock")

    async def fn(dep: Depends[Foo] = Depends(orig_factory)) -> Foo:
        return dep()

    root_ctx = RootContext({orig_factory: mocked_factory})
    async with enter_next_scope(root_ctx) as app_ctx:
        async with enter_next_scope(app_ctx) as handler_ctx:
            res = await invoke(handler_ctx, fn)

    assert res == Foo("from-mock")


async def test_overrides_implicit_factory():
    def orig_factory() -> Foo:
        raise RuntimeError("Should not be called")

    def mocked_factory() -> Foo:
        return Foo("from-mock")

    async def fn(dep: Depends[Foo]) -> Foo:
        return dep()

    root_ctx = RootContext({orig_factory: mocked_factory})
    async with enter_next_scope(root_ctx) as app_ctx:
        async with enter_next_scope(app_ctx, implicit_factories={"dep": orig_factory}) as handler_ctx:
            res = await invoke(handler_ctx, fn)

    assert res == Foo("from-mock")


async def test_overridden_factory_sub_deps():
    def orig_factory() -> Foo:
        raise RuntimeError("Should not be called")

    def mocked_subdep_factory() -> str:
        return "from-mock-subdep-factory"

    def mocked_factory(v: Depends[str] = Depends(mocked_subdep_factory)) -> Foo:
        return Foo(v())

    async def fn(dep: Depends[Foo] = Depends(orig_factory)) -> Foo:
        return dep()

    root_ctx = RootContext({orig_factory: mocked_factory})
    async with enter_next_scope(root_ctx) as app_ctx:
        async with enter_next_scope(app_ctx) as handler_ctx:
            res = await invoke(handler_ctx, fn)

    assert res == Foo("from-mock-subdep-factory")


def mocked_sync_create_foo() -> Foo:
    return Foo("mocked-sync")


@contextlib.contextmanager
def mocked_cm_create_foo() -> Iterator[Foo]:
    yield Foo("mocked-cm")


async def mocked_async_create_foo() -> Foo:
    return Foo("mocked-async")


@contextlib.asynccontextmanager
async def mocked_async_cm_create_foo() -> AsyncIterator[Foo]:
    yield Foo("mocked-async-cm")


@pytest.mark.parametrize(
    "override_factory, override_value",
    [
        (mocked_sync_create_foo, Foo("mocked-sync")),
        (mocked_cm_create_foo, Foo("mocked-cm")),
        (mocked_async_create_foo, Foo("mocked-async")),
        (mocked_async_cm_create_foo, Foo("mocked-async-cm")),
    ],
)
async def test_override_factory_forms(override_factory, override_value):
    def orig_factory() -> Foo:
        return Foo("from-orig")

    async def fn(dep: Depends[Foo] = Depends(orig_factory)) -> Foo:
        return dep()

    root_ctx = RootContext({orig_factory: override_factory})
    async with enter_next_scope(root_ctx) as app_ctx:
        async with enter_next_scope(app_ctx) as handler_ctx:
            res = await invoke(handler_ctx, fn)

    assert res == override_value


async def test_invoke_error_sets_override_orig():
    def will_cause_exc() -> object:
        raise RuntimeError("Should not be called")

    @scoped("app")
    def orig_factory() -> Foo:
        raise RuntimeError("Should not be called")

    @scoped("app")
    def mocked_factory(dep: Depends[object] = Depends(will_cause_exc)) -> Foo:
        raise RuntimeError("Should not be called")

    async def fn(dep: Depends[Foo] = Depends(orig_factory)) -> Foo:
        return dep()

    root_ctx = RootContext({orig_factory: mocked_factory})
    async with enter_next_scope(root_ctx) as app_ctx:
        async with enter_next_scope(app_ctx) as handler_ctx:
            with raises_match_by_val(
                NestedInvokeError(
                    fn,
                    InvokableDependencyError(
                        mocked_factory,
                        HandlerScopeDepRequestedFromAppScope(
                            Depends[object],
                            ComparableDepends(will_cause_exc),
                            "explicit",
                        ),
                        orig_factory,
                    ),
                )
            ):
                await invoke(handler_ctx, fn)
