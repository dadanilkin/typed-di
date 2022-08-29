import re
from typing import Protocol, runtime_checkable
from unittest.mock import Mock

import pytest

from tests.shared import Foo
from tests.utils import raises_match_by_val
from typed_di import (
    Depends,
    InvokableDependencyError,
    RootContext,
    ValueOfUnexpectedTypeReceived,
    create,
    enter_next_scope,
    invoke,
)


async def test_receives_in_app_scope():
    root_ctx = RootContext(b1=Foo("b1"), b2=Foo("b2"))

    async def fn(b1: Depends[Foo], b2: Depends[Foo]) -> tuple[Foo, Foo]:
        return b1(), b2()

    async with enter_next_scope(root_ctx) as app_ctx:
        res = await invoke(app_ctx, fn)
        assert res == (Foo("b1"), Foo("b2"))


async def test_receives_in_handler_scope():
    root_ctx = RootContext(b1=Foo("b1"), b2=Foo("b2"))

    async def fn(b1: Depends[Foo], b2: Depends[Foo]) -> tuple[Foo, Foo]:
        return b1(), b2()

    async with enter_next_scope(root_ctx) as app_ctx:
        async with enter_next_scope(app_ctx) as handler_ctx:
            res = await invoke(handler_ctx, fn)
            assert res == (Foo("b1"), Foo("b2"))


async def test_provided_value_is_not_type_of_requested():
    class Bar:
        pass

    cb = Mock()

    root_ctx = RootContext(b=Foo("b1"))

    async def fn(b: Depends[Bar]) -> None:
        cb(b())

    async with enter_next_scope(root_ctx) as app_ctx:
        async with enter_next_scope(app_ctx) as handler_ctx:
            with raises_match_by_val(
                InvokableDependencyError(
                    fn,
                    ValueOfUnexpectedTypeReceived(
                        Depends[Bar],
                        "b",
                        "bootstrap",
                        Bar,
                        Foo,
                    ),
                ),
            ):
                await create(handler_ctx, Depends[None], Depends(fn))

    assert cb.mock_calls == []


async def test_requested_type_is_not_trivial_for_generic(app_ctx):
    cb = Mock()

    root_ctx = RootContext(b=Foo("b1"))

    async def fn(b: Depends[list[int]]) -> None:
        cb()

    async with enter_next_scope(root_ctx) as app_ctx:
        with pytest.raises(
            TypeError,
            match=re.escape("Type `list[int]` of dependency `typed_di.Depends[list[int]]` is not runtime-checkable"),
        ):
            await invoke(app_ctx, fn)

    assert cb.mock_calls == []


async def test_requested_type_is_not_trivial_for_rt_protocol(app_ctx):
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
            match=re.compile(r"Type `.*Proto` of dependency `typed_di.Depends\[.*Proto\]` is not runtime-checkable"),
        ):
            await invoke(app_ctx, fn)

    assert cb.mock_calls == []
