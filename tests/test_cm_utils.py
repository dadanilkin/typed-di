import contextlib
import sys
import warnings
from functools import wraps
from typing import (
    ContextManager,
    AsyncContextManager,
    Generic,
    TypeVar,
    Iterator,
    Generator,
    AsyncIterator,
    AsyncGenerator,
    Awaitable,
    Coroutine,
)

import pytest

from typed_di._utils import (
    cm_factory_count_nesting_levels,
    cm_count_nesting_levels,
    async_cm_count_nesting_levels,
    async_cm_factory_count_nesting_levels,
    awaitable_count_nesting_levels,
    awaitable_factory_count_nesting_levels,
)


def test_supports_contextlib_cm_decorator_detection():
    decorated = contextlib.contextmanager(lambda: None)
    tester = contextlib.contextmanager(lambda: None)
    try:
        assert decorated.__code__ is tester.__code__
    except Exception:
        pytest.exit(
            f"It seems, that current Python {sys.version} does not reliably supports detecting "
            f"`contextlib.contextmanager` decorated context managers, thus not supported"
        )
        raise


def test_supports_contextlib_async_cm_decorator_detection():
    decorated = contextlib.asynccontextmanager(lambda: None)
    tester = contextlib.asynccontextmanager(lambda: None)
    try:
        assert decorated.__code__ is tester.__code__
    except Exception:
        pytest.exit(
            f"It seems, that current Python {sys.version} does not reliably supports detecting "
            f"`contextlib.asynccontextmanager` decorated context managers, thus not supported"
        )
        raise


def dummy_decorator(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)

    return wrapper


T1 = TypeVar("T1")
T2 = TypeVar("T2")
T3 = TypeVar("T3")


class TestCM:
    class CustomCM:
        def __enter__(self):
            ...

        def __exit__(self, exc_type, exc_val, exc_tb):
            ...

    class CustomGenericCM(Generic[T1, T2, T3]):
        def __enter__(self) -> T3:
            ...

        def __exit__(self, exc_type, exc_val, exc_tb):
            ...

    @pytest.mark.parametrize(
        "cm, expect_nesting_level",
        [
            (int, 0),
            (ContextManager[int], 1),
            (ContextManager[ContextManager[int]], 2),
            (ContextManager[ContextManager[ContextManager[int]]], 3),
            #
            (ContextManager[AsyncContextManager[ContextManager[int]]], 1),
            (ContextManager[ContextManager[AsyncContextManager[int]]], 2),
            #
            (CustomCM, 1),
            (ContextManager[CustomCM], 2),
        ]
        + [
            pytest.param(
                *args,
                marks=pytest.mark.xfail(reason="Custom generic CM is not implemented"),
            )
            for args in [
                (CustomGenericCM[ContextManager[None], None, None], 1),
                (CustomGenericCM[int, ContextManager[None], None], 1),
                (CustomGenericCM[int, None, None], 1),
                (CustomGenericCM[int, None, ContextManager[int]], 2),
                (ContextManager[CustomGenericCM[int, None, None]], 2),
            ]
        ],
    )
    def test_count_cm_nesting_levels(self, cm, expect_nesting_level):
        assert cm_count_nesting_levels(cm) == expect_nesting_level

    def returns_int(self) -> int:
        ...

    def returns_cm(self) -> ContextManager[int]:
        ...

    def returns_nested_cm(self) -> ContextManager[ContextManager[int]]:
        ...

    def returns_nested_nested_cm(self) -> ContextManager[ContextManager[ContextManager[int]]]:
        ...

    def returns_custom_cm(self) -> CustomCM:
        ...

    def returns_nested_custom_cm(self) -> ContextManager[CustomCM]:
        ...

    def returns_iter(self) -> Iterator[int]:
        ...

    def returns_gen(self) -> Generator[int, None, None]:
        ...

    @contextlib.contextmanager
    def decorated_iter_cm(self) -> Iterator[int]:
        ...

    @contextlib.contextmanager
    def decorated_gen_cm(self) -> Generator[int, None, None]:
        ...

    @contextlib.contextmanager
    def decorated_iter_nested_cm(self) -> Iterator[ContextManager[int]]:
        ...

    @contextlib.contextmanager
    def decorated_gen_nested_cm(self) -> Generator[ContextManager[int], None, None]:
        ...

    @dummy_decorator
    @contextlib.contextmanager
    def twice_decorated_iter_cm(self) -> Iterator[int]:
        ...

    @dummy_decorator
    @contextlib.contextmanager
    def twice_decorated_gen_cm(self) -> Generator[int, None, None]:
        ...

    @pytest.mark.parametrize(
        "factory, expect_nesting_level",
        [
            (returns_int, 0),
            (returns_cm, 1),
            (returns_nested_cm, 2),
            (returns_nested_nested_cm, 3),
            (returns_custom_cm, 1),
            (returns_nested_custom_cm, 2),
            # No false positives
            (returns_iter, 0),
            (returns_gen, 0),
            # Handles decorated context managers correctly
            (decorated_iter_cm, 1),
            (decorated_gen_cm, 1),
            (decorated_iter_nested_cm, 2),
            (decorated_gen_nested_cm, 2),
            (twice_decorated_iter_cm, 1),
            (twice_decorated_gen_cm, 1),
        ],
    )
    def test_count_factory_cm_nesting_level(self, factory, expect_nesting_level):
        assert cm_factory_count_nesting_levels(factory) == expect_nesting_level


class TestAsyncCM:
    class CustomCM:
        async def __aenter__(self):
            ...

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            ...

    class CustomGenericCM(Generic[T1, T2, T3]):
        async def __aenter__(self) -> T3:
            ...

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            ...

    @pytest.mark.parametrize(
        "cm, expect_nesting_level",
        [
            (int, 0),
            (AsyncContextManager[int], 1),
            (AsyncContextManager[AsyncContextManager[int]], 2),
            (AsyncContextManager[AsyncContextManager[AsyncContextManager[int]]], 3),
            #
            (AsyncContextManager[ContextManager[AsyncContextManager[int]]], 1),
            (AsyncContextManager[AsyncContextManager[ContextManager[int]]], 2),
            #
            (CustomCM, 1),
            (AsyncContextManager[CustomCM], 2),
        ]
        + [
            pytest.param(
                *args,
                marks=pytest.mark.xfail(reason="Custom generic CM is not implemented"),
            )
            for args in [
                (CustomGenericCM[AsyncContextManager[None], None, None], 1),
                (CustomGenericCM[int, AsyncContextManager[None], None], 1),
                (CustomGenericCM[int, None, None], 1),
                (CustomGenericCM[int, None, AsyncContextManager[int]], 2),
                (AsyncContextManager[CustomGenericCM[int, None, None]], 2),
            ]
        ],
    )
    def test_count_cm_nesting_levels(self, cm, expect_nesting_level):
        assert async_cm_count_nesting_levels(cm) == expect_nesting_level

    def returns_int(self) -> int:
        ...

    def returns_cm(self) -> AsyncContextManager[int]:
        ...

    def returns_nested_cm(self) -> AsyncContextManager[AsyncContextManager[int]]:
        ...

    def returns_nested_nested_cm(self) -> AsyncContextManager[AsyncContextManager[AsyncContextManager[int]]]:
        ...

    def returns_custom_cm(self) -> CustomCM:
        ...

    def returns_nested_custom_cm(self) -> AsyncContextManager[CustomCM]:
        ...

    def returns_iter(self) -> AsyncIterator[int]:
        ...

    def returns_gen(self) -> AsyncGenerator[int, None]:
        ...

    @contextlib.asynccontextmanager
    def decorated_iter_cm(self) -> AsyncIterator[int]:
        ...

    @contextlib.asynccontextmanager
    def decorated_gen_cm(self) -> AsyncGenerator[int, None]:
        ...

    @contextlib.asynccontextmanager
    def decorated_iter_nested_cm(self) -> AsyncIterator[AsyncContextManager[int]]:
        ...

    @contextlib.asynccontextmanager
    def decorated_gen_nested_cm(self) -> AsyncGenerator[AsyncContextManager[int], None]:
        ...

    @dummy_decorator
    @contextlib.asynccontextmanager
    def twice_decorated_iter_cm(self) -> AsyncIterator[int]:
        ...

    @dummy_decorator
    @contextlib.asynccontextmanager
    def twice_decorated_gen_cm(self) -> AsyncGenerator[int, None]:
        ...

    @pytest.mark.parametrize(
        "factory, expect_nesting_level",
        [
            (returns_int, 0),
            (returns_cm, 1),
            (returns_nested_cm, 2),
            (returns_nested_nested_cm, 3),
            (returns_custom_cm, 1),
            (returns_nested_custom_cm, 2),
            # No false positives
            (returns_iter, 0),
            (returns_gen, 0),
            # Handles decorated context managers correctly
            (decorated_iter_cm, 1),
            (decorated_gen_cm, 1),
            (decorated_iter_nested_cm, 2),
            (decorated_gen_nested_cm, 2),
            (twice_decorated_iter_cm, 1),
            (twice_decorated_gen_cm, 1),
        ],
    )
    def test_count_factory_cm_nesting_level(self, factory, expect_nesting_level):
        assert async_cm_factory_count_nesting_levels(factory) == expect_nesting_level


class TestAwaitable:
    class CustomAwaitable:
        def __await__(self):
            ...

    class CustomGenericAwaitable(Generic[T1, T2, T3]):
        def __await__(self) -> Generator[int, int, T3]:
            ...

    @pytest.mark.parametrize(
        "cm, expect_nesting_level",
        [
            (int, 0),
            # Awaitables
            (Awaitable[int], 1),
            (Awaitable[Awaitable[int]], 2),
            (Awaitable[Awaitable[Awaitable[int]]], 3),
            #
            (Awaitable[ContextManager[Awaitable[int]]], 1),
            (Awaitable[Awaitable[ContextManager[int]]], 2),
            #
            (CustomAwaitable, 1),
            (Awaitable[CustomAwaitable], 2),
            # Coroutines
            (Coroutine[None, None, int], 1),
            (Coroutine[None, None, Coroutine[None, None, int]], 2),
            (Coroutine[None, None, Coroutine[None, None, Coroutine[None, None, int]]], 3),
            #
            (Coroutine[None, None, ContextManager[Coroutine[None, None, int]]], 1),
            (Coroutine[None, None, Coroutine[None, None, ContextManager[int]]], 2),
            #
            (CustomAwaitable, 1),
            (Awaitable[CustomAwaitable], 2),
        ]
        + [
            pytest.param(
                *args,
                marks=pytest.mark.xfail(reason="TODO: Custom generic Awaitables are not supported"),
            )
            for args in [
                (CustomGenericAwaitable[Awaitable[None], None, None], 1),
                (CustomGenericAwaitable[int, Awaitable[None], None], 1),
                (CustomGenericAwaitable[int, None, None], 1),
                (CustomGenericAwaitable[int, None, Awaitable[int]], 2),
                (AsyncContextManager[CustomGenericAwaitable[int, None, None]], 2),
            ]
        ],
    )
    def test_count_cm_nesting_levels(self, cm, expect_nesting_level):
        assert awaitable_count_nesting_levels(cm) == expect_nesting_level

    def returns_int(self) -> int:
        ...

    def returns_awaitable(self) -> Awaitable[int]:
        ...

    def returns_nested_awaitable(self) -> Awaitable[Awaitable[int]]:
        ...

    def returns_nested_nested_awaitable(self) -> Awaitable[Awaitable[Awaitable[int]]]:
        ...

    def returns_custom_awaitable(self) -> CustomAwaitable:
        ...

    def returns_nested_custom_awaitable(self) -> Awaitable[CustomAwaitable]:
        ...

    def returns_coro(self) -> Coroutine[None, None, int]:
        ...

    def returns_nested_coro(self) -> Coroutine[None, None, Coroutine[None, None, int]]:
        ...

    def returns_nested_nested_coro(self) -> Coroutine[None, None, Coroutine[None, None, Coroutine[None, None, int]]]:
        ...

    def returns_nested_custom_coro(self) -> Coroutine[None, None, CustomAwaitable]:
        ...

    async def async_returns_int(self) -> int:
        ...

    async def async_returns_awaitable(self) -> Awaitable[int]:
        ...

    async def async_returns_coro(self) -> Coroutine[None, None, int]:
        ...

    @pytest.mark.parametrize(
        "factory, expect_nesting_level",
        [
            (returns_int, 0),
            # Awaitables
            (returns_awaitable, 1),
            (returns_nested_awaitable, 2),
            (returns_nested_nested_awaitable, 3),
            (returns_custom_awaitable, 1),
            (returns_nested_custom_awaitable, 2),
            # Coros
            (returns_coro, 1),
            (returns_nested_coro, 2),
            (returns_nested_nested_coro, 3),
            (returns_nested_custom_coro, 2),
            # Handles `async def` fns correctly
            (async_returns_int, 1),
            (async_returns_awaitable, 2),
            (async_returns_coro, 2),
        ],
    )
    def test_count_factory_cm_nesting_level(self, factory, expect_nesting_level):
        assert awaitable_factory_count_nesting_levels(factory) == expect_nesting_level
