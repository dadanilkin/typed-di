import pytest

from tests.shared import Bar, Foo, async_cm_foo, async_foo, cm_foo, sync_foo
from tests.utils import raises_match_by_val
from typed_di import (
    Depends,
    InvokableDependencyError,
    RootContext,
    ValueOfUnexpectedTypeReceived,
    enter_next_scope,
    invoke,
    scoped,
)


async def test_invokes_implicit_factory_on_app_level():
    root_ctx = RootContext()

    async def fn(
        sync_foo: Depends[Foo], cm_foo: Depends[Foo], async_foo: Depends[Foo], async_cm_foo: Depends[Foo]
    ) -> tuple[Foo, Foo, Foo, Foo]:
        return sync_foo(), cm_foo(), async_foo(), async_cm_foo()

    sync_foo_ = scoped("app")(sync_foo)
    cm_foo_ = scoped("app")(cm_foo)
    async_foo_ = scoped("app")(async_foo)
    async_cm_foo_ = scoped("app")(async_cm_foo)

    async with enter_next_scope(
        root_ctx,
        implicit_factories={
            "sync_foo": sync_foo_,
            "cm_foo": cm_foo_,
            "async_foo": async_foo_,
            "async_cm_foo": async_cm_foo_,
        },
    ) as app_scope:
        res = await invoke(app_scope, fn)
        assert res == (Foo("sync"), Foo("cm"), Foo("async"), Foo("async-cm"))


async def test_validates_factory_return_type(app_ctx):
    def create_bar() -> Bar:
        return Bar()

    async def fn(foo: Depends[Foo]) -> None:
        ...

    async with enter_next_scope(app_ctx, implicit_factories={"foo": create_bar}) as handler_ctx:
        with raises_match_by_val(
            InvokableDependencyError(
                fn,
                ValueOfUnexpectedTypeReceived(
                    Depends[Foo],
                    "foo",
                    "implicit",
                    Foo,
                    Bar,
                ),
            ),
        ):
            await invoke(handler_ctx, fn)


async def test_invokes_implicit_factory_on_handler_level():
    root_ctx = RootContext()

    async def fn(
        sync_foo: Depends[Foo], cm_foo: Depends[Foo], async_foo: Depends[Foo], async_cm_foo: Depends[Foo]
    ) -> tuple[Foo, Foo, Foo, Foo]:
        return sync_foo(), cm_foo(), async_foo(), async_cm_foo()

    async with enter_next_scope(root_ctx) as app_ctx:
        async with enter_next_scope(
            app_ctx,
            implicit_factories={
                "sync_foo": sync_foo,
                "cm_foo": cm_foo,
                "async_foo": async_foo,
                "async_cm_foo": async_cm_foo,
            },
        ) as handler_ctx:
            res = await invoke(handler_ctx, fn)
            assert res == (Foo("sync"), Foo("cm"), Foo("async"), Foo("async-cm"))


async def test_rejects_app_level_implicit_factory_on_handler_scope(app_ctx):
    sync_foo_ = scoped("app")(sync_foo)

    with pytest.raises(
        ValueError,
        match=(
            "It is forbidden to use app scope implicit factories "
            "in handler context, use them while entering app scope"
        ),
    ):
        async with enter_next_scope(app_ctx, implicit_factories={"sync_foo": sync_foo_}):
            ...
