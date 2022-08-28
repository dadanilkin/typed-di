import functools
import inspect
from typing import TypeVar, Callable, TypeAlias, Literal, ParamSpec, Awaitable, cast

Scope: TypeAlias = Literal["app", "handler"]


R = TypeVar("R")
P = ParamSpec("P")


def _decorate_as_app_scoped(fn: Callable[P, R], /) -> Callable[P, R]:
    if inspect.iscoroutinefunction(fn):
        # Purpose of this brunch is to keep coroutinefunction marker as original function
        # But, unfortunate, couldn't be properly typed right now
        fn_ = cast(Callable[..., Awaitable[R]], fn)

        @functools.wraps(fn_)
        async def wrapper(*args: object, **kwargs: object) -> R:
            return await fn_(*args, **kwargs)

        setattr(wrapper, "__app_scope__", True)
        return cast(Callable[P, R], wrapper)
    else:

        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            return fn(*args, **kwargs)

        setattr(wrapper, "__app_scope__", True)
        return wrapper


def scoped(scope: Scope, /) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator to mark factory as application scope factory. It destructs original callable type.

    Leaves original function untouched.
    """
    if scope == "handler":
        return lambda x: x

    return _decorate_as_app_scoped


def get_factory_scope(factory: object) -> Scope:
    return "app" if getattr(factory, "__app_scope__", False) else "handler"
