from typed_di import Depends, partial


class Foo:
    pass


def explicit_foo() -> Foo:
    ...


def implicit_foo() -> Foo:
    ...


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


reveal_type(partial(fn1))
reveal_type(partial(fn2))
reveal_type(partial(fn3))
reveal_type(partial(fn4))
reveal_type(partial(fn5))
reveal_type(partial(fn6))
reveal_type(partial(mfn2))
reveal_type(partial(mfn3))
reveal_type(partial(mfn4))
reveal_type(partial(mfn5))
reveal_type(partial(mfn6))
reveal_type(partial(fn_complex_signature))
