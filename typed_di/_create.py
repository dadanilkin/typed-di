import dataclasses
import inspect
import itertools
from typing import TypeVar, Callable, ContextManager, Awaitable, AsyncContextManager, cast

from typing_extensions import assert_never

from typed_di import _depends, _utils, _contexts
from typed_di._contexts import AppContext, HandlerContext
from typed_di._depends import Depends
from typed_di._scope import get_factory_scope
from typed_di._utils import is_runtime_checkable
from typed_di._exceptions import (
    DependencyByNameNotFound,
    ValueOfUnexpectedTypeReceived,
    HandlerScopeDepRequestedFromAppScope,
    ValueFromFactoryAlreadyResolved,
    ValueFromFactoryWereRequestedUnresolved,
)


class _ByNameLookupError(LookupError):
    pass


@dataclasses.dataclass
class CreationContext:
    prev: object | None = None
    # Dict provides O(1) "in"-checks while keeping insertion order
    factories_in_stack: dict[object, None] = dataclasses.field(default_factory=dict)


T = TypeVar("T")


async def create(
    ctx: AppContext | HandlerContext,
    dep_type: type[Depends[T]],
    dep_or_name: Depends[T] | str,
    /,
    *,
    _creation_ctx: CreationContext | None = None,
) -> T:
    if _creation_ctx is None:
        _creation_ctx = CreationContext()

    if isinstance(dep_or_name, str):
        expect_type = get_runtime_checkable_type(dep_type)

        fn = _contexts.lookup_implicit_factory(ctx, dep_or_name)
        if fn:
            return await create_from_implicit_factory_cached(ctx, dep_type, expect_type, dep_or_name, fn, _creation_ctx)

        try:
            return create_from_bootstrap_values(ctx, dep_type, expect_type, dep_or_name)
        except _ByNameLookupError as exc:
            raise DependencyByNameNotFound(dep_type, dep_or_name, "implicit-or-bootstrap") from exc

    else:
        state = _depends.get_state(dep_or_name)
        if isinstance(state, _depends.Resolved):
            raise RuntimeError(
                f"While resolving dependency `{dep_type}`, resolved depends marker unexpectedly received"
            )

        return await create_from_factory_cached(ctx, dep_type, dep_or_name, state.factory, _creation_ctx, True)


async def create_from_implicit_factory_cached(
    ctx: AppContext | HandlerContext,
    dep_type: type[Depends[T]],
    expect_type: type[T],
    name: str,
    fn: Callable[..., object],
    creation_ctx: CreationContext,
    /,
) -> T:
    assert is_runtime_checkable(expect_type)

    dep_type_downcasted: type[Depends[object]] = dep_type
    val = await create_from_factory_cached(ctx, dep_type_downcasted, name, fn, creation_ctx, False)

    if not isinstance(val, expect_type):
        raise ValueOfUnexpectedTypeReceived(dep_type, name, "implicit", expect_type, type(val))

    return val


def create_from_bootstrap_values(
    ctx: AppContext | HandlerContext, dep_type: type[Depends[T]], expect_type: type[T], name: str, /
) -> T:
    root_ctx = _contexts.get_root_ctx(ctx)
    try:
        val = root_ctx._bootstrap_values[name]
    except KeyError as exc:
        raise _ByNameLookupError(name) from exc

    if not isinstance(val, expect_type):
        raise ValueOfUnexpectedTypeReceived(dep_type, name, "bootstrap", expect_type, type(val))

    return val


async def create_from_factory_cached(
    ctx: AppContext | HandlerContext,
    dep_type: type[Depends[T]],
    dep_or_name: Depends[T] | str,
    fn: _depends.AnyFactory[T],
    creation_ctx: CreationContext,
    explicit: bool,
    /,
) -> T:
    scope = get_factory_scope(fn)
    match scope:
        case "app":
            cache = _contexts.get_app_cache(ctx)
        case "handler" if isinstance(ctx, HandlerContext):
            cache = _contexts.get_handler_cache(ctx)
        case "handler":
            raise HandlerScopeDepRequestedFromAppScope(
                dep_type,
                dep_or_name,
                "explicit" if explicit else "implicit",
            )
        case _:
            assert_never(scope)

    try:
        val, requested_as, action_performed = cache[fn]
    except KeyError:
        pass
    else:
        need_action = any(_dep_need_action(fn, dep_type))
        if need_action == action_performed:
            # This cast is unsafe, but guarantied by uniqueness of mapping from `fn` to provided value
            return cast(T, val)

        raise _render_cache_already_have_value_in_other_form_error(
            dep_type,
            dep_or_name,
            fn,
            requested_as,
            need_action,
            action_performed,
            explicit,
        )

    val_, action_performed = await create_from_factory(ctx, dep_type, dep_or_name, fn, creation_ctx, explicit)
    cache[fn] = (val_, dep_type, action_performed)
    return val_


async def create_from_factory(
    ctx: AppContext | HandlerContext,
    dep_type: type[Depends[T]],
    dep_or_name: Depends[T] | str,
    fn: _depends.AnyFactory[T],
    creation_ctx: CreationContext,
    explicit: bool,
    /,
) -> tuple[T, bool]:
    from typed_di._invoke import resolve_fn_deps

    if fn in creation_ctx.factories_in_stack:
        it = iter(creation_ctx.factories_in_stack.keys())
        for f in it:
            if f is fn:
                break

        cycled_factories = itertools.chain([fn], it)
        cycled_factories_repr = ", ".join(f"`{f!r}`" for f in cycled_factories)
        raise RuntimeError(
            f"Factories recursion detected for dependency `{dep_type}` "
            f"before invoking factory `{fn}`, cycle:\n\t{cycled_factories_repr}"
        )

    scope = get_factory_scope(fn)
    match scope:
        case "app":
            exit_stack = _contexts.get_app_exit_stack(ctx)
        case "handler" if isinstance(ctx, HandlerContext):
            exit_stack = _contexts.get_handler_exit_stack(ctx)
        case "handler":
            raise HandlerScopeDepRequestedFromAppScope(dep_type, dep_or_name, "explicit" if explicit else "implicit")
        case _:
            assert_never(scope)

    prev_factory = creation_ctx.prev
    if prev_factory:
        if scope == "handler" and get_factory_scope(prev_factory) == "app":
            raise HandlerScopeDepRequestedFromAppScope(dep_type, dep_or_name, "explicit" if explicit else "implicit")

    creation_ctx.prev = fn
    creation_ctx.factories_in_stack[fn] = None
    try:
        fn_args = await resolve_fn_deps(ctx, fn, creation_ctx)

        val: T | ContextManager[T] | Awaitable[T] | AsyncContextManager[T] = fn(**fn_args)
        if isinstance(val, Awaitable) and _dep_need_await(fn, dep_type):
            return cast(T, await val), True
        elif isinstance(val, ContextManager) and _dep_need_enter(fn, dep_type):
            return cast(T, exit_stack.enter_context(val)), True
        elif isinstance(val, AsyncContextManager) and _dep_need_aenter(fn, dep_type):
            return cast(T, await exit_stack.enter_async_context(val)), True
        else:
            return cast(T, val), False

    finally:
        creation_ctx.prev = prev_factory
        del creation_ctx.factories_in_stack[fn]


def _decide_need_action(n: int, fn: Callable[..., object], dep_type: type[Depends[object]]) -> bool:
    """
    Awaitable[Foo] <- () -> Awaitable[Foo] - n == 0
    Foo <- () -> Awaitable[Foo] - n == 1
    """
    if n != 0 and n != 1:
        raise TypeError(f"Inconsistent type returned by factory `{fn!r}` for dependency of type `{dep_type}`")

    return bool(n)


def _dep_need_await(fn: Callable[..., object], dep_type: type[Depends[object]]) -> bool:
    n = _utils.awaitable_factory_count_nesting_levels(fn) - _utils.awaitable_count_nesting_levels(
        _depends.get_type_arg(dep_type)
    )
    return _decide_need_action(n, fn, dep_type)


def _dep_need_enter(fn: Callable[..., object], dep_type: type[Depends[object]]) -> bool:
    n = _utils.cm_factory_count_nesting_levels(fn) - _utils.cm_count_nesting_levels(_depends.get_type_arg(dep_type))
    return _decide_need_action(n, fn, dep_type)


def _dep_need_aenter(fn: Callable[..., object], dep_type: type[Depends[object]]) -> bool:
    n = _utils.async_cm_factory_count_nesting_levels(fn) - _utils.async_cm_count_nesting_levels(
        _depends.get_type_arg(dep_type)
    )
    return _decide_need_action(n, fn, dep_type)


def _dep_need_action(fn: Callable[..., object], dep_type: type[Depends[object]]) -> tuple[bool, bool, bool]:
    return _dep_need_enter(fn, dep_type), _dep_need_aenter(fn, dep_type), _dep_need_await(fn, dep_type)


def get_runtime_checkable_type(dep_type: type[Depends[T]]) -> type[T]:
    type_ = _depends.get_type_arg(dep_type)
    if not isinstance(type_, type):
        raise TypeError(f"Type `{inspect.formatannotation(type_)}` of dependency `{dep_type}` is not a simple type")
    if not is_runtime_checkable(type_):
        raise TypeError(f"Type `{inspect.formatannotation(type_)}` of dependency `{dep_type}` is not runtime-checkable")
    return type_


def _render_cache_already_have_value_in_other_form_error(
    dep_type: type[Depends[object]],
    dep_or_name: Depends[object] | str,
    fn: Callable[..., object],
    requested_as: object,
    need_action: bool,
    action_performed: bool,
    explicit: bool,
) -> RuntimeError:
    assert need_action != action_performed

    c_type = "explicit" if explicit else "implicit"
    if need_action:
        return ValueFromFactoryWereRequestedUnresolved(dep_type, dep_or_name, c_type, requested_as, fn)
    else:
        return ValueFromFactoryAlreadyResolved(dep_type, dep_or_name, c_type, requested_as, fn)
