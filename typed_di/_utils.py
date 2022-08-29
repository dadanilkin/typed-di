import contextlib
import inspect
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Coroutine, Generator, Iterator
from types import CodeType, FunctionType
from typing import AsyncContextManager, Callable, Container, ContextManager, get_args, get_origin, get_type_hints


def _get_iterator_t_or_rise(t: object) -> object:
    match get_args(t):
        case []:
            raise TypeError(f"Unsubscribed generic `{t!r}` used where subscribed expected")
        case [t]:
            return t
        case _:
            raise TypeError(f"Unexpected num of generic args for `{t!r}` being found, expected 1 argument")


def _get_generator_t_or_rise(t: object) -> object:
    origin = get_origin(t)
    if origin is Generator:
        args_count = 3
    elif origin is AsyncGenerator:
        args_count = 2
    else:
        raise TypeError(f"Unexpected generator type `{t}`, `Generator` or `AsyncGenerator` expected")

    match get_args(t):
        case []:
            raise TypeError(f"Unsubscribed generic `{t!r}` used where subscribed expected")
        case [t, *rest] if len(rest) == args_count - 1:
            return t
        case _:
            raise TypeError(f"Unexpected num of generic args for `{t!r}` being found, expected {args_count} arguments")

    assert False  # mypy complains with "No return statement", but match/case above handles all branches


def _get_awaitable_t_or_rise(t: object) -> object:
    match get_args(t):
        case []:
            raise TypeError(f"Unsubscribed `Awaitable` `{t!r}` used where subscribed expected")
        case [t]:
            return t
        case _:
            raise TypeError(f"Unexpected num of generic args for `{t!r}` being found, expected 1 arguments")


def _get_coroutine_t_or_rise(t: object) -> object:
    match get_args(t):
        case []:
            raise TypeError(f"Unsubscribed `Coroutine` `{t!r}` used where subscribed expected")
        case [_, _, t]:
            return t
        case _:
            raise TypeError(f"Unexpected num of generic args for `{t!r}` being found, expected 3 arguments")


def _get_cm_t_or_rise(t: object) -> object:
    assert get_origin(t) is not None
    match get_args(t):
        case []:
            raise TypeError(f"Unsubscribed `ContextManager` `{t!r}` used where subscribed expected")
        case [t]:
            return t
        case _:
            raise TypeError(f"Unexpected num of generic args for `{t!r}` being found, expected 1 arguments")


def _is_iter_or_gen(t: object) -> tuple[object, object] | None:
    origin = get_origin(t)
    if origin in (Iterator, AsyncIterator):
        return origin, _get_iterator_t_or_rise(t)
    if origin in (Generator, AsyncGenerator):
        return origin, _get_generator_t_or_rise(t)
    return None


def _is_awaitable_or_coro(t: object) -> tuple[object, object] | None:
    origin = get_origin(t)
    if origin is Awaitable:
        return origin, _get_awaitable_t_or_rise(t)
    if origin is Coroutine:
        return origin, _get_coroutine_t_or_rise(t)
    return None


def _is_wrapped_test_by_code(fn: object, wrapper_code: CodeType) -> bool:
    def test(f: object) -> bool:
        return isinstance(f, FunctionType) and f.__code__ is wrapper_code

    wrapper = fn
    if test(wrapper):
        return True

    while wrapper := getattr(wrapper, "__wrapped__", None):
        if test(wrapper):
            return True

    return False


def is_cm(t: object) -> bool:
    if isinstance(t, type):
        return issubclass(t, ContextManager)

    origin = get_origin(t)
    if origin is None:
        return False

    return issubclass(origin, ContextManager)


def is_async_cm(t: object) -> bool:
    if isinstance(t, type):
        return issubclass(t, AsyncContextManager)

    origin = get_origin(t)
    if origin is None:
        return False

    return issubclass(origin, AsyncContextManager)


def is_awaitable(t: object) -> bool:
    if isinstance(t, type):
        return issubclass(t, Awaitable)

    origin = get_origin(t)
    if origin is None:
        return False

    return issubclass(origin, Awaitable)


def _get_return_type(fn: object) -> object:
    annotations = get_type_hints(fn)
    try:
        return annotations["return"]
    except KeyError as exc:
        raise TypeError(f"Function `{fn!r}` doesn't have annotated return type") from exc


def _cm_factory_count_nesting_levels(
    factory: object,
    count_nesting_levels: Callable[[object], int],
    cl_cm_return_origins: Container[object],
    cl_cm_wrapper_code: CodeType,
) -> int:
    return_type = _get_return_type(factory)
    count = 0
    if res := _is_iter_or_gen(return_type):
        dec_orig, dec_t = res
        if dec_orig in cl_cm_return_origins and _is_wrapped_test_by_code(factory, cl_cm_wrapper_code):
            count += 1
            return_type = dec_t

    return count + count_nesting_levels(return_type)


def cm_count_nesting_levels(t: object) -> int:
    count = 0
    while is_cm(t):
        count += 1
        origin = get_origin(t)
        if origin is None:
            break
        t = _get_cm_t_or_rise(t)

    return count


@contextlib.contextmanager
def _dummy_decorated_cm() -> Iterator[None]:
    yield


_CL_CM_RETURN_ORIGINS = {Iterator, Generator}
_CL_CM_WRAPPER_CODE = _dummy_decorated_cm.__code__


def cm_factory_count_nesting_levels(factory: object) -> int:
    return _cm_factory_count_nesting_levels(
        factory,
        cm_count_nesting_levels,
        _CL_CM_RETURN_ORIGINS,
        _CL_CM_WRAPPER_CODE,
    )


def async_cm_count_nesting_levels(t: object) -> int:
    count = 0
    while is_async_cm(t):
        count += 1
        origin = get_origin(t)
        if origin is None:
            break
        t = _get_cm_t_or_rise(t)

    return count


@contextlib.asynccontextmanager
async def _dummy_decorated_async_cm() -> AsyncIterator[None]:
    yield


_CL_ASYNC_CM_WRAPPER_CODE = _dummy_decorated_async_cm.__code__
_CL_ASYNC_CM_RETURN_ORIGINS = {AsyncIterator, AsyncGenerator}


def async_cm_factory_count_nesting_levels(factory: object) -> int:
    return _cm_factory_count_nesting_levels(
        factory,
        async_cm_count_nesting_levels,
        _CL_ASYNC_CM_RETURN_ORIGINS,
        _CL_ASYNC_CM_WRAPPER_CODE,
    )


def awaitable_count_nesting_levels(t: object) -> int:
    count = 0
    while True:
        res = _is_awaitable_or_coro(t)
        if res:
            t = res[1]
            count += 1
        elif is_awaitable(t):
            return count + 1
        else:
            return count

    return count


def awaitable_factory_count_nesting_levels(factory: object) -> int:
    return_type = _get_return_type(factory)

    count = 0
    if inspect.iscoroutinefunction(factory):
        count += 1
    return count + awaitable_count_nesting_levels(return_type)


def is_runtime_checkable(type_: object) -> bool:
    try:
        isinstance(None, type_)  # type: ignore[arg-type]
    except TypeError:
        return False

    is_protocol = getattr(type_, "_is_protocol", False)
    return not is_protocol
