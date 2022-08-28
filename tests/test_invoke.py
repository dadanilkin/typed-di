import contextlib
import copy
import dataclasses
import re
from typing import (
    ContextManager,
    AsyncIterator,
    Iterator,
    AsyncContextManager,
    Protocol,
    runtime_checkable,
)
from unittest.mock import Mock, AsyncMock, call, MagicMock

import pytest

from tests.utils import ComparableDepends
from typed_di import Depends, invoke, RootContext, enter_next_scope, create, scoped
from typed_di._exceptions import ValueOfUnexpectedTypeReceived, HandlerScopeDepRequestedFromAppScope


@dataclasses.dataclass
class Foo:
    val: str


class Bar:
    ...


def sync_foo() -> Foo:
    return Foo("sync")


def cm_foo() -> ContextManager[Foo]:
    @contextlib.contextmanager
    def cm() -> Iterator[Foo]:
        yield Foo("cm")

    return cm()


async def async_foo() -> Foo:
    return Foo("async")


def async_cm_foo() -> AsyncContextManager[Foo]:
    @contextlib.asynccontextmanager
    async def cm() -> AsyncIterator[Foo]:
        yield Foo("async-cm")

    return cm()


@pytest.fixture
def root_ctx():
    return RootContext()


@pytest.fixture
async def app_ctx(root_ctx):
    async with enter_next_scope(root_ctx) as app_ctx:
        yield app_ctx


@pytest.fixture
async def handler_ctx(app_ctx):
    async with enter_next_scope(app_ctx) as handler_ctx:
        yield handler_ctx


class TestResolvesDependencies:
    async def test_factories_types(self, handler_ctx):
        async def fn(
            sync_foo: Depends[Foo] = Depends(sync_foo),
            cm_foo: Depends[Foo] = Depends(cm_foo),
            async_foo: Depends[Foo] = Depends(async_foo),
            async_cm_foo: Depends[Foo] = Depends(async_cm_foo),
        ) -> tuple[Foo, Foo, Foo, Foo]:
            return sync_foo(), cm_foo(), async_foo(), async_cm_foo()

        res = await invoke(handler_ctx, fn)

        assert res == (Foo("sync"), Foo("cm"), Foo("async"), Foo("async-cm"))

    async def test_type_as_factory_no_subdeps(self, handler_ctx):
        class Bar:
            def __init__(self) -> None:
                ...

        async def fn(bar: Depends[Bar] = Depends(Bar)) -> Bar:
            return bar()

        res = await invoke(handler_ctx, fn)
        assert isinstance(res, Bar)

    async def test_type_as_factory_with_subdeps(self, handler_ctx):
        class Bar:
            def __init__(self, foo: Depends[Foo] = Depends(sync_foo)) -> None:
                self.foo = foo()

        async def fn(bar: Depends[Bar] = Depends(Bar)) -> Bar:
            return bar()

        res = await invoke(handler_ctx, fn)
        assert isinstance(res, Bar)
        assert isinstance(res.foo, Foo)

    async def test_nested_dependencies(self, handler_ctx):
        @dataclasses.dataclass
        class A:
            v: str

        @dataclasses.dataclass
        class B:
            a: A

        @dataclasses.dataclass
        class C:
            b: B

        @dataclasses.dataclass
        class D:
            c: C

        @contextlib.asynccontextmanager
        async def create_a() -> AsyncIterator[A]:
            yield A("from `create_a` factory")

        async def create_b(a: Depends[A] = Depends(create_a)) -> B:
            return B(a())

        @contextlib.contextmanager
        def create_c(b: Depends[B] = Depends(create_b)) -> Iterator[C]:
            yield C(b())

        def create_d(c: Depends[C] = Depends(create_c)) -> D:
            return D(c())

        async def fn(d: Depends[D] = Depends(create_d)) -> D:
            return d()

        res = await invoke(handler_ctx, fn)
        assert res == D(C(B(A("from `create_a` factory"))))


class TestCaching:
    async def test_caches_sync_factory(self):
        pass


class TestLifespans:
    async def test_async(self, root_ctx):
        root_mock = Mock()
        root_mock.app_dep.return_value = AsyncMock()
        root_mock.handler_dep.return_value = AsyncMock()

        @scoped("app")
        @contextlib.asynccontextmanager
        async def app_dep_factory() -> AsyncIterator[Foo]:
            async with root_mock.app_dep() as res:
                yield res

        @contextlib.asynccontextmanager
        async def handler_dep_factory(app_dep: Depends[Foo] = Depends(app_dep_factory)) -> AsyncIterator[Foo]:
            async with root_mock.handler_dep(app_dep()) as res:
                yield res

        async def fn(handler_dep: Depends[Foo] = Depends(handler_dep_factory)) -> None:
            root_mock.fn(handler_dep())

        async with enter_next_scope(root_ctx) as app_ctx:
            async with enter_next_scope(app_ctx) as handler_ctx:
                await invoke(handler_ctx, fn)

            async with enter_next_scope(app_ctx) as handler_ctx:
                await invoke(handler_ctx, fn)

        assert root_mock.mock_calls == [
            call.app_dep(),
            call.app_dep().__aenter__(),
            call.handler_dep(root_mock.app_dep.return_value.__aenter__.return_value),
            call.handler_dep().__aenter__(),
            call.fn(root_mock.handler_dep.return_value.__aenter__.return_value),
            call.handler_dep().__aexit__(None, None, None),
            call.handler_dep(root_mock.app_dep.return_value.__aenter__.return_value),
            call.handler_dep().__aenter__(),
            call.fn(root_mock.handler_dep.return_value.__aenter__.return_value),
            call.handler_dep().__aexit__(None, None, None),
            call.app_dep().__aexit__(None, None, None),
        ]

    async def test_async_v2(self, root_ctx):
        root_mock = Mock()
        root_mock.app_dep1.return_value = AsyncMock()
        root_mock.app_dep2.return_value = AsyncMock()
        root_mock.handler_dep1.return_value = AsyncMock()
        root_mock.handler_dep2.return_value = AsyncMock()

        @scoped("app")
        @contextlib.asynccontextmanager
        async def app_dep_factory1() -> AsyncIterator[Foo]:
            async with root_mock.app_dep1() as res:
                yield res

        @scoped("app")
        @contextlib.asynccontextmanager
        async def app_dep_factory2() -> AsyncIterator[Foo]:
            async with root_mock.app_dep2() as res:
                yield res

        @contextlib.asynccontextmanager
        async def handler_dep_factory1(app_dep: Depends[Foo] = Depends(app_dep_factory1)) -> AsyncIterator[Foo]:
            async with root_mock.handler_dep1(app_dep()) as res:
                yield res

        @contextlib.asynccontextmanager
        async def handler_dep_factory2(app_dep: Depends[Foo] = Depends(app_dep_factory2)) -> AsyncIterator[Foo]:
            async with root_mock.handler_dep2(app_dep()) as res:
                yield res

        async def fn(
            handler_dep1: Depends[Foo] = Depends(handler_dep_factory1),
            handler_dep2: Depends[Foo] = Depends(handler_dep_factory2),
        ) -> None:
            root_mock.fn(handler_dep1(), handler_dep2())

        async with enter_next_scope(root_ctx) as app_ctx:
            async with enter_next_scope(app_ctx) as handler_ctx:
                await invoke(handler_ctx, fn)

            async with enter_next_scope(app_ctx) as handler_ctx:
                await invoke(handler_ctx, fn)

        assert root_mock.mock_calls == [
            call.app_dep1(),
            call.app_dep1().__aenter__(),
            call.handler_dep1(root_mock.app_dep1.return_value.__aenter__.return_value),
            call.handler_dep1().__aenter__(),
            call.app_dep2(),
            call.app_dep2().__aenter__(),
            call.handler_dep2(root_mock.app_dep2.return_value.__aenter__.return_value),
            call.handler_dep2().__aenter__(),
            call.fn(
                root_mock.handler_dep1.return_value.__aenter__.return_value,
                root_mock.handler_dep2.return_value.__aenter__.return_value,
            ),
            call.handler_dep2().__aexit__(None, None, None),
            call.handler_dep1().__aexit__(None, None, None),
            call.handler_dep1(root_mock.app_dep1.return_value.__aenter__.return_value),
            call.handler_dep1().__aenter__(),
            call.handler_dep2(root_mock.app_dep2.return_value.__aenter__.return_value),
            call.handler_dep2().__aenter__(),
            call.fn(
                root_mock.handler_dep1.return_value.__aenter__.return_value,
                root_mock.handler_dep2.return_value.__aenter__.return_value,
            ),
            call.handler_dep2().__aexit__(None, None, None),
            call.handler_dep1().__aexit__(None, None, None),
            call.app_dep2().__aexit__(None, None, None),
            call.app_dep1().__aexit__(None, None, None),
        ]

    async def test_app_level_values_are_not_created_eagerly(self, root_ctx):
        root_mock = Mock()
        root_mock.app_dep.return_value = AsyncMock()
        root_mock.handler_no_app_dep.return_value = AsyncMock()
        root_mock.handler_app_dep.return_value = AsyncMock()

        @scoped("app")
        @contextlib.asynccontextmanager
        async def app_dep_factory() -> AsyncIterator[Foo]:
            async with root_mock.app_dep() as res:
                yield res

        @contextlib.asynccontextmanager
        async def handler_no_app_dep_factory() -> AsyncIterator[Foo]:
            async with root_mock.handler_no_app_dep() as res:
                yield res

        @contextlib.asynccontextmanager
        async def handler_app_dep_factory(app_dep: Depends[Foo] = Depends(app_dep_factory)) -> AsyncIterator[Foo]:
            async with root_mock.handler_app_dep(app_dep()) as res:
                yield res

        async with enter_next_scope(root_ctx) as app_ctx:
            async with enter_next_scope(app_ctx) as handler_ctx:
                assert (
                    await create(handler_ctx, Depends[Foo], Depends(handler_no_app_dep_factory))
                    is root_mock.handler_no_app_dep.return_value.__aenter__.return_value
                )
                assert (
                    await create(handler_ctx, Depends[Foo], Depends(handler_app_dep_factory))
                    is root_mock.handler_app_dep.return_value.__aenter__.return_value
                )

        assert root_mock.mock_calls == [
            call.handler_no_app_dep(),
            call.handler_no_app_dep().__aenter__(),
            # App were created after first requested handler dependency ...
            call.app_dep(),
            call.app_dep().__aenter__(),
            call.handler_app_dep(root_mock.app_dep.return_value.__aenter__.return_value),
            call.handler_app_dep().__aenter__(),
            call.handler_app_dep().__aexit__(None, None, None),
            call.handler_no_app_dep().__aexit__(None, None, None),
            # But were finalized the last
            call.app_dep().__aexit__(None, None, None),
        ]

    async def test_sync(self, root_ctx):
        root_mock = Mock()
        root_mock.app_dep.return_value = MagicMock()
        root_mock.handler_dep.return_value = MagicMock()

        @scoped("app")
        @contextlib.contextmanager
        def app_dep_factory() -> Iterator[Foo]:
            with root_mock.app_dep() as res:
                yield res

        @contextlib.contextmanager
        def handler_dep_factory(app_dep: Depends[Foo] = Depends(app_dep_factory)) -> Iterator[Foo]:
            with root_mock.handler_dep(app_dep()) as res:
                yield res

        async def fn(handler_dep: Depends[Foo] = Depends(handler_dep_factory)) -> None:
            root_mock.fn(handler_dep())

        async with enter_next_scope(root_ctx) as app_ctx:
            async with enter_next_scope(app_ctx) as handler_ctx:
                await invoke(handler_ctx, fn)

            async with enter_next_scope(app_ctx) as handler_ctx:
                await invoke(handler_ctx, fn)

        assert root_mock.mock_calls == [
            call.app_dep(),
            call.app_dep().__enter__(),
            call.handler_dep(root_mock.app_dep.return_value.__enter__.return_value),
            call.handler_dep().__enter__(),
            call.fn(root_mock.handler_dep.return_value.__enter__.return_value),
            call.handler_dep().__exit__(None, None, None),
            call.handler_dep(root_mock.app_dep.return_value.__enter__.return_value),
            call.handler_dep().__enter__(),
            call.fn(root_mock.handler_dep.return_value.__enter__.return_value),
            call.handler_dep().__exit__(None, None, None),
            call.app_dep().__exit__(None, None, None),
        ]

    async def test_handler_deps_lives_as_outer_lifespan(self, app_ctx):
        dep_val = Mock()
        root_mock = Mock()
        root_mock.handler_dep.return_value = AsyncMock()

        @contextlib.contextmanager
        def handler_dep_factory() -> Iterator[Foo]:
            with root_mock.handler_dep():
                yield dep_val

        async def fn(handler_dep: Depends[Foo] = Depends(handler_dep_factory)) -> Foo:
            root_mock.fn()
            return handler_dep()

        async with enter_next_scope(app_ctx) as handler_ctx1:
            assert (await invoke(handler_ctx1, fn)) is dep_val

            async with enter_next_scope(app_ctx) as handler_ctx2:
                assert (await invoke(handler_ctx2, fn)) is dep_val

                async with enter_next_scope(app_ctx) as handler_ctx3:
                    assert (await invoke(handler_ctx3, fn)) is dep_val

                assert (await invoke(handler_ctx2, fn)) is dep_val

            assert (await invoke(handler_ctx1, fn)) is dep_val


class TestBootstrapValues:
    async def test_receives_in_app_scope(self):
        root_ctx = RootContext(b1=Foo("b1"), b2=Foo("b2"))

        async def fn(b1: Depends[Foo], b2: Depends[Foo]) -> tuple[Foo, Foo]:
            return b1(), b2()

        async with enter_next_scope(root_ctx) as app_ctx:
            res = await invoke(app_ctx, fn)
            assert res == (Foo("b1"), Foo("b2"))

    async def test_receives_in_handler_scope(self):
        root_ctx = RootContext(b1=Foo("b1"), b2=Foo("b2"))

        async def fn(b1: Depends[Foo], b2: Depends[Foo]) -> tuple[Foo, Foo]:
            return b1(), b2()

        async with enter_next_scope(root_ctx) as app_ctx:
            async with enter_next_scope(app_ctx) as handler_ctx:
                res = await invoke(handler_ctx, fn)
                assert res == (Foo("b1"), Foo("b2"))

    async def test_provided_value_is_not_type_of_requested(self):
        class Bar:
            pass

        cb = Mock()

        root_ctx = RootContext(b=Foo("b1"))

        async def fn(b: Depends[Bar]) -> None:
            cb(b())

        async with enter_next_scope(root_ctx) as app_ctx:
            async with enter_next_scope(app_ctx) as handler_ctx:
                with pytest.raises(ValueOfUnexpectedTypeReceived) as exc_info:
                    await create(handler_ctx, Depends[None], Depends(fn))

            assert exc_info.value.args == (Depends[Bar], "b", "bootstrap", Bar, Foo)

        assert cb.mock_calls == []

    async def test_requested_type_is_not_trivial_for_generic(self, app_ctx):
        cb = Mock()

        root_ctx = RootContext(b=Foo("b1"))

        async def fn(b: Depends[list[int]]) -> None:
            cb()

        async with enter_next_scope(root_ctx) as app_ctx:
            with pytest.raises(
                TypeError,
                match=re.escape(
                    "Type `list[int]` of dependency `typed_di.Depends[list[int]]` is not runtime checkable"
                ),
            ):
                await invoke(app_ctx, fn)

        assert cb.mock_calls == []

    async def test_requested_type_is_not_trivial_for_rt_protocol(self, app_ctx):
        @runtime_checkable
        class Proto(Protocol):
            ...

        cb = Mock()

        root_ctx = RootContext(b=Foo("b1"))

        async def fn(b: Depends[Proto]) -> None:
            cb()

        async with enter_next_scope(root_ctx) as app_ctx:
            with pytest.raises(
                TypeError,
                match=re.compile(
                    r"Type `.*Proto` of dependency `typed_di.Depends\[.*Proto\]` is not runtime checkable"
                ),
            ):
                await invoke(app_ctx, fn)

        assert cb.mock_calls == []


class TestImplicitFactories:
    async def test_invokes_implicit_factory_on_app_level(self):
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

    async def test_validates_factory_return_type(self, app_ctx):
        def create_bar() -> Bar:
            return Bar()

        async def fn(foo: Depends[Foo]) -> None:
            ...

        async with enter_next_scope(app_ctx, implicit_factories={"foo": create_bar}) as handler_ctx:
            with pytest.raises(ValueOfUnexpectedTypeReceived) as exc_info:
                await invoke(handler_ctx, fn)

            assert exc_info.value.args == (Depends[Foo], "foo", "implicit", Foo, Bar)

    async def test_invokes_implicit_factory_on_handler_level(self):
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

    async def test_rejects_app_level_implicit_factory_on_handler_scope(self, app_ctx):
        sync_foo_ = scoped("app")(copy.copy(sync_foo))

        with pytest.raises(
            ValueError,
            match=(
                "It is forbidden to use app scope implicit factories "
                "in handler context, use them while entering app scope"
            ),
        ):
            async with enter_next_scope(app_ctx, implicit_factories={"sync_foo": sync_foo_}):
                ...


class TestScopingRules:
    async def test_from_app_to_handler(self, handler_ctx):
        @scoped("app")
        def app_dep() -> int:
            return 1024

        @scoped("handler")
        def handler_dep(dep: Depends[int] = Depends(app_dep)) -> str:
            return str(dep())

        async def fn(
            a_dep: Depends[int] = Depends(app_dep), h_dep: Depends[str] = Depends(handler_dep)
        ) -> tuple[int, str]:
            return a_dep(), h_dep()

        res = await invoke(handler_ctx, fn)
        assert res == (1024, "1024")

    async def test_rejects_app_depends_on_handler(self, handler_ctx):
        @scoped("handler")
        def handler_dep() -> int:
            return 1024

        @scoped("app")
        def app_dep(dep: Depends[int] = Depends(handler_dep)) -> str:
            return str(dep())

        async def fn(
            a_dep: Depends[str] = Depends(app_dep), h_dep: Depends[int] = Depends(handler_dep)
        ) -> tuple[str, int]:
            return a_dep(), h_dep()

        with pytest.raises(HandlerScopeDepRequestedFromAppScope) as exc_info:
            await invoke(handler_ctx, fn)

        assert exc_info.value.args == (Depends[int], ComparableDepends(handler_dep), "explicit")

    async def test_rejects_handler_scope_dep_with_app_ctx(self, app_ctx):
        cb = Mock()

        async def fn(foo: Depends[Foo] = Depends(sync_foo)) -> None:
            cb()

        with pytest.raises(HandlerScopeDepRequestedFromAppScope) as exc_info:
            await invoke(app_ctx, fn)

        assert exc_info.value.args == (Depends[Foo], ComparableDepends(sync_foo), "explicit")

    async def test_creating_handler_level_dep_on_app_context_is_forbidden(self, app_ctx):
        with pytest.raises(HandlerScopeDepRequestedFromAppScope) as exc_info:
            await create(app_ctx, Depends[Foo], Depends(sync_foo))

        assert exc_info.value.args == (Depends[Foo], ComparableDepends(sync_foo), "explicit")
