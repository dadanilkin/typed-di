import contextlib
from typing import AsyncIterator, Iterator
from unittest.mock import Mock, call

from typed_di import Depends, create, enter_next_scope, scoped


async def perform_cache_test(ctx, request_as, factory_mock):
    res1 = await create(ctx, Depends[object], request_as)
    res2 = await create(ctx, Depends[object], request_as)
    res3 = await create(ctx, Depends[object], request_as)

    assert res1 == res2 == res3 == factory_mock.return_value

    assert factory_mock.mock_calls == [call()]

    return True


async def test_caches_sync_factory_result(handler_ctx):
    factory = Mock(name="factory")

    def create_smth() -> object:
        return factory()

    assert await perform_cache_test(handler_ctx, Depends(create_smth), factory)


async def test_caches_cm_factory_result(handler_ctx):
    factory = Mock(name="factory")

    @contextlib.contextmanager
    def create_smth() -> Iterator[object]:
        yield factory()

    assert await perform_cache_test(handler_ctx, Depends(create_smth), factory)


async def test_caches_async_factory_result(handler_ctx):
    factory = Mock(name="factory")

    async def create_smth() -> object:
        return factory()

    assert await perform_cache_test(handler_ctx, Depends(create_smth), factory)


async def test_caches_async_cm_factory_result(handler_ctx):
    factory = Mock(name="factory")

    @contextlib.asynccontextmanager
    async def create_smth() -> AsyncIterator[object]:
        yield factory()

    assert await perform_cache_test(handler_ctx, Depends(create_smth), factory)


async def test_caches_implicit_sync_factory_result(app_ctx):
    factory = Mock(name="factory")

    def create_smth() -> object:
        return factory()

    async with enter_next_scope(app_ctx, implicit_factories={"smth": create_smth}) as handler_ctx:
        assert await perform_cache_test(handler_ctx, "smth", factory)


async def test_caches_implicit_cm_factory_result(app_ctx):
    factory = Mock(name="factory")

    @contextlib.contextmanager
    def create_smth() -> Iterator[object]:
        yield factory()

    async with enter_next_scope(app_ctx, implicit_factories={"smth": create_smth}) as handler_ctx:
        assert await perform_cache_test(handler_ctx, "smth", factory)


async def test_caches_implicit_async_factory_result(app_ctx):
    factory = Mock(name="factory")

    async def create_smth() -> object:
        return factory()

    async with enter_next_scope(app_ctx, implicit_factories={"smth": create_smth}) as handler_ctx:
        assert await perform_cache_test(handler_ctx, "smth", factory)


async def test_caches_implicit_async_cm_factory_result(app_ctx):
    factory = Mock(name="factory")

    @contextlib.asynccontextmanager
    async def create_smth() -> AsyncIterator[object]:
        yield factory()

    async with enter_next_scope(app_ctx, implicit_factories={"smth": create_smth}) as handler_ctx:
        assert await perform_cache_test(handler_ctx, "smth", factory)


async def test_cached_handler_dep_lives_within_context(app_ctx):
    v1 = Mock()
    v2 = Mock()
    factory = Mock(name="factory", side_effect=[v1, v2])

    def create_smth() -> object:
        return factory()

    async with enter_next_scope(app_ctx) as handler_ctx:
        res11 = await create(handler_ctx, Depends[object], Depends(create_smth))
        res12 = await create(handler_ctx, Depends[object], Depends(create_smth))

    async with enter_next_scope(app_ctx) as handler_ctx:
        res21 = await create(handler_ctx, Depends[object], Depends(create_smth))
        res22 = await create(handler_ctx, Depends[object], Depends(create_smth))

    assert res11 != res21
    assert res11 == res12 == v1
    assert res21 == res22 == v2

    assert factory.mock_calls == [call(), call()]


async def test_cached_app_dep_lives_within_context(root_ctx):
    v1 = Mock()
    v2 = Mock()
    factory = Mock(name="factory", side_effect=[v1, v2])

    @scoped("app")
    def create_smth() -> object:
        return factory()

    async with enter_next_scope(root_ctx) as app_ctx:
        res11 = await create(app_ctx, Depends[object], Depends(create_smth))
        res12 = await create(app_ctx, Depends[object], Depends(create_smth))

    async with enter_next_scope(root_ctx) as app_ctx:
        res21 = await create(app_ctx, Depends[object], Depends(create_smth))
        res22 = await create(app_ctx, Depends[object], Depends(create_smth))

    assert res11 != res21
    assert res11 == res12 == v1
    assert res21 == res22 == v2

    assert factory.mock_calls == [call(), call()]


async def test_cached_app_dep_lives_within_context_as_transitive(root_ctx):
    v1 = Mock()
    v2 = Mock()

    root = Mock()
    root.factory = Mock(side_effect=[v1, v2])
    root.pass_ = Mock(wraps=lambda x: x)

    @scoped("app")
    def create_smth() -> object:
        return root.factory()

    @scoped("handler")
    def smth_transitive(dep: Depends[object] = Depends(create_smth)) -> object:
        return root.pass_(dep())

    root.before_app_scope()
    async with enter_next_scope(root_ctx) as app_ctx:
        root.before_handler_scope()

        async with enter_next_scope(app_ctx) as handler_ctx:
            res11 = await create(handler_ctx, Depends[object], Depends(smth_transitive))

        root.after_handler_scope()
        root.before_handler_scope()

        async with enter_next_scope(app_ctx) as handler_ctx:
            res12 = await create(handler_ctx, Depends[object], Depends(smth_transitive))

        root.after_handler_scope()
    root.after_app_scope()

    root.before_app_scope()
    async with enter_next_scope(root_ctx) as app_ctx:
        root.before_handler_scope()

        async with enter_next_scope(app_ctx) as handler_ctx:
            res21 = await create(handler_ctx, Depends[object], Depends(smth_transitive))

        root.after_handler_scope()
        root.before_handler_scope()

        async with enter_next_scope(app_ctx) as handler_ctx:
            res22 = await create(handler_ctx, Depends[object], Depends(smth_transitive))

        root.after_handler_scope()
    root.after_app_scope()

    assert res11 != res21
    assert res11 == res12 == v1
    assert res21 == res22 == v2

    # Detailed proof of creation cycle
    assert root.mock_calls == [
        call.before_app_scope(),
        #
        call.before_handler_scope(),
        # Factory is being called when first time app dep requested
        call.factory(),
        # Handler dep called with app value
        call.pass_(v1),
        call.after_handler_scope(),
        #
        call.before_handler_scope(),
        # App dep factory isn't being called because it were already cached,
        #  but handler dep recalled because handler dep value were invalidated by living handler scope
        call.pass_(v1),
        call.after_handler_scope(),
        #
        call.after_app_scope(),
        call.before_app_scope(),
        #
        call.before_handler_scope(),
        # App factory called again because value were invalidated by living app scope
        call.factory(),
        # All from above repeated here but with new app factory value
        call.pass_(v2),
        call.after_handler_scope(),
        #
        call.before_handler_scope(),
        call.pass_(v2),
        call.after_handler_scope(),
        #
        call.after_app_scope(),
    ]
