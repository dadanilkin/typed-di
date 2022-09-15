from inspect import Parameter, Signature, signature
from types import NoneType
from typing import get_type_hints
from unittest.mock import AsyncMock, call

import pytest

from tests.shared import Foo
from tests.utils import ComparableDepends
from typed_di import AppContext, Depends, HandlerContext, RootContext, enter_next_scope, invoke, partial
from typed_di._partial import make_fn_deps_creator

EXPLICIT_FOO = Foo("explicit")
IMPLICIT_FOO = Foo("implicit")
BOOTSTRAP_FOO = Foo("bootstrap")


def explicit_foo() -> Foo:
    return EXPLICIT_FOO


def implicit_foo() -> Foo:
    return IMPLICIT_FOO


async def fn1() -> None:
    ...


async def fn2(v: str) -> None:
    ...


async def fn3(v: str, /) -> None:
    ...


async def fn4(*, v: str) -> None:
    ...


async def fn5(*args: str) -> None:
    ...


async def fn6(**kwargs: str) -> None:
    ...


async def mfn2(v: str, dep: Depends[Foo] = Depends(explicit_foo)) -> None:
    ...


async def mfn3(v: str, /, dep: Depends[Foo] = Depends(explicit_foo)) -> None:
    ...


async def mfn4(*, v: str, dep: Depends[Foo] = Depends(explicit_foo)) -> None:
    ...


async def mfn5(*args: str, dep: Depends[Foo] = Depends(explicit_foo)) -> None:
    ...


async def mfn6(dep: Depends[Foo] = Depends(explicit_foo), **kwargs: str) -> None:
    ...


async def fn_complex_signature(
    val1: int, /, implicit: Depends[Foo], val2: str, dep2: Depends[Foo] = Depends(explicit_foo), *, val3: float = 10.0
) -> None:
    ...


async def fn_explicit_dep(v: str, dep: Depends[Foo] = Depends(explicit_foo)) -> None:
    ...


async def fn_implicit_dep(v: str, implicit: Depends[Foo]) -> None:
    ...


async def fn_bootstrap_dep(v: str, bootstrap: Depends[Foo]) -> None:
    ...


@pytest.fixture
def root_ctx():
    return RootContext(bootstrap=BOOTSTRAP_FOO)


@pytest.fixture
async def app_ctx(root_ctx):
    async with enter_next_scope(root_ctx) as app_ctx:
        yield app_ctx


@pytest.fixture
async def handler_ctx(app_ctx):
    async with enter_next_scope(app_ctx, implicit_factories={"implicit": implicit_foo}) as handler_ctx:
        yield handler_ctx


@pytest.mark.parametrize(
    "fn, expect_res_deps",
    [
        (fn1, {}),
        (fn2, {}),
        (fn3, {}),
        (fn4, {}),
        (fn5, {}),
        (fn6, {}),
        (mfn2, {"dep": ComparableDepends.resolved(EXPLICIT_FOO)}),
        (mfn3, {"dep": ComparableDepends.resolved(EXPLICIT_FOO)}),
        (mfn4, {"dep": ComparableDepends.resolved(EXPLICIT_FOO)}),
        (mfn5, {"dep": ComparableDepends.resolved(EXPLICIT_FOO)}),
        (mfn6, {"dep": ComparableDepends.resolved(EXPLICIT_FOO)}),
        (
            fn_complex_signature,
            {"implicit": ComparableDepends.resolved(IMPLICIT_FOO), "dep2": ComparableDepends.resolved(EXPLICIT_FOO)},
        ),
    ],
)
async def test_deps_creator_maker(handler_ctx, fn, expect_res_deps):
    res = await invoke(handler_ctx, make_fn_deps_creator(fn))
    assert res == expect_res_deps


@pytest.mark.parametrize(
    "fn, call_args, call_kwargs, expect_fn_call",
    [
        (fn1, (), {}, call()),
        (fn2, ("TEST-VALUE",), {}, call("TEST-VALUE")),
        (fn3, ("TEST-VALUE",), {}, call("TEST-VALUE")),
        (fn4, (), {"v": "TEST-VALUE"}, call(v="TEST-VALUE")),
        (fn5, ("TEST-VALUE1", "TEST-VALUE2", "TEST-VALUE3"), {}, call("TEST-VALUE1", "TEST-VALUE2", "TEST-VALUE3")),
        (
            fn6,
            (),
            {"v1": "TEST-VALUE1", "v2": "TEST-VALUE2", "v3": "TEST-VALUE3"},
            call(v1="TEST-VALUE1", v2="TEST-VALUE2", v3="TEST-VALUE3"),
        ),
        (mfn2, ("TEST-VALUE",), {}, call("TEST-VALUE", ComparableDepends.resolved(EXPLICIT_FOO))),
        (mfn3, ("TEST-VALUE",), {}, call("TEST-VALUE", ComparableDepends.resolved(EXPLICIT_FOO))),
        (mfn4, (), {"v": "TEST-VALUE"}, call(v="TEST-VALUE", dep=ComparableDepends.resolved(EXPLICIT_FOO))),
        (
            mfn5,
            ("TEST-VALUE1", "TEST-VALUE2", "TEST-VALUE3"),
            {},
            call("TEST-VALUE1", "TEST-VALUE2", "TEST-VALUE3", dep=ComparableDepends.resolved(EXPLICIT_FOO)),
        ),
        (
            mfn6,
            (),
            {"v1": "TEST-VALUE1", "v2": "TEST-VALUE2", "v3": "TEST-VALUE3"},
            call(ComparableDepends.resolved(EXPLICIT_FOO), v1="TEST-VALUE1", v2="TEST-VALUE2", v3="TEST-VALUE3"),
        ),
        (
            fn_complex_signature,
            (1000, "TEST-VALUE"),
            {"val3": 15.5},
            call(
                1000,
                ComparableDepends.resolved(IMPLICIT_FOO),
                "TEST-VALUE",
                ComparableDepends.resolved(EXPLICIT_FOO),
                val3=15.5,
            ),
        ),
    ],
)
async def test_partial(handler_ctx, fn, call_args, call_kwargs, expect_fn_call):
    fn_wrapped = AsyncMock(wraps=fn)
    fn_wrapped.__annotations__ = fn.__annotations__
    fn_wrapped.__signature__ = signature(fn)
    del fn_wrapped.__code__

    partialized = partial(fn_wrapped)

    await partialized(handler_ctx, *call_args, **call_kwargs)

    assert fn_wrapped.mock_calls == [expect_fn_call]


CTX_PARAM = Parameter("__ctx__", Parameter.POSITIONAL_ONLY, annotation=AppContext | HandlerContext)


@pytest.mark.parametrize(
    "fn, sig",
    [
        (fn1, Signature([CTX_PARAM], return_annotation=NoneType)),
        (
            fn2,
            Signature(
                [CTX_PARAM, Parameter("v", Parameter.POSITIONAL_OR_KEYWORD, annotation=str)], return_annotation=NoneType
            ),
        ),
        (
            fn3,
            Signature(
                [CTX_PARAM, Parameter("v", Parameter.POSITIONAL_ONLY, annotation=str)], return_annotation=NoneType
            ),
        ),
        (
            fn4,
            Signature([CTX_PARAM, Parameter("v", Parameter.KEYWORD_ONLY, annotation=str)], return_annotation=NoneType),
        ),
        (
            fn5,
            Signature(
                [CTX_PARAM, Parameter("args", Parameter.VAR_POSITIONAL, annotation=str)], return_annotation=NoneType
            ),
        ),
        (
            fn6,
            Signature(
                [CTX_PARAM, Parameter("kwargs", Parameter.VAR_KEYWORD, annotation=str)], return_annotation=NoneType
            ),
        ),
        (
            mfn2,
            Signature(
                [CTX_PARAM, Parameter("v", Parameter.POSITIONAL_OR_KEYWORD, annotation=str)], return_annotation=NoneType
            ),
        ),
        (
            mfn3,
            Signature(
                [CTX_PARAM, Parameter("v", Parameter.POSITIONAL_ONLY, annotation=str)], return_annotation=NoneType
            ),
        ),
        (
            mfn4,
            Signature([CTX_PARAM, Parameter("v", Parameter.KEYWORD_ONLY, annotation=str)], return_annotation=NoneType),
        ),
        (
            mfn5,
            Signature(
                [CTX_PARAM, Parameter("args", Parameter.VAR_POSITIONAL, annotation=str)], return_annotation=NoneType
            ),
        ),
        (
            mfn6,
            Signature(
                [CTX_PARAM, Parameter("kwargs", Parameter.VAR_KEYWORD, annotation=str)], return_annotation=NoneType
            ),
        ),
        (
            fn_complex_signature,
            Signature(
                [
                    CTX_PARAM,
                    Parameter("val1", Parameter.POSITIONAL_ONLY, annotation=int),
                    Parameter("val2", Parameter.POSITIONAL_OR_KEYWORD, annotation=str),
                    Parameter("val3", Parameter.KEYWORD_ONLY, annotation=float, default=10.0),
                ],
                return_annotation=NoneType,
            ),
        ),
    ],
)
def test_partialized_fn_signature(fn, sig):
    assert signature(partial(fn)) == sig


BASE_AN = {"__ctx__": AppContext | HandlerContext}


@pytest.mark.parametrize(
    "fn, annotations",
    [
        (fn1, BASE_AN),
        (fn2, BASE_AN | {"v": str}),
        (fn3, BASE_AN | {"v": str}),
        (fn4, BASE_AN | {"v": str}),
        (fn5, BASE_AN | {"args": str}),
        (fn6, BASE_AN | {"kwargs": str}),
        (mfn2, BASE_AN | {"v": str}),
        (mfn3, BASE_AN | {"v": str}),
        (mfn4, BASE_AN | {"v": str}),
        (mfn5, BASE_AN | {"args": str}),
        (mfn6, BASE_AN | {"kwargs": str}),
    ],
)
def test_partialized_fn_annotations(fn, annotations):
    assert get_type_hints(partial(fn)) == annotations


