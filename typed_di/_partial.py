import copy
import functools
import inspect
from typing import Awaitable, Callable, Mapping, Protocol, TypedDict, TypeVar, get_type_hints

from typed_di import AppContext, HandlerContext, invoke
from typed_di._depends import Depends, is_dep

RT = TypeVar("RT")
RT_cov = TypeVar("RT_cov", covariant=True)


def _check_unannotated_params(fn: object, annotations: Mapping[str, object], sig: inspect.Signature) -> None:
    unannotated_params = sig.parameters.keys() - annotations.keys()
    if len(unannotated_params) > 0:
        raise TypeError(f"Function `{fn}` misses annotations for some of params: {list(unannotated_params)}")
    if "return" not in annotations:
        raise TypeError(f"Function `{fn}` misses return type annotation for function")


_sentry = object()


def _normalize_arguments(
    sig: inspect.Signature, args: tuple[object, ...], kwargs: Mapping[str, object], /
) -> tuple[list[object], dict[str, object]]:
    """
    Mirrors `inspect.Signature.bind`, but considers, that some keyword arguments need to be placed
    somewhere between given ``args`` for POSITIONAL_OR_KEYWORD arguments.
    """

    args_iter = iter(args)
    consumed_kwargs = set()

    args_norm = []
    kwargs_norm = {}
    for param in sig.parameters.values():
        if param.kind == inspect.Parameter.POSITIONAL_ONLY:
            if param.name in kwargs:
                raise TypeError(f"{param.name!r} parameter is positional only, but was passed as a keyword")

            try:
                args_norm.append(next(args_iter))
            except StopIteration:
                raise TypeError(f"missing a required argument: {param.name!r}") from None
        elif param.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD:
            val = kwargs.get(param.name, _sentry)

            if val is _sentry:
                try:
                    val = next(args_iter)
                except StopIteration:
                    raise TypeError(f"missing a required argument: {param.name!r}") from None
            else:
                consumed_kwargs.add(param.name)

            args_norm.append(val)
        elif param.kind == inspect.Parameter.VAR_POSITIONAL:
            args_norm.extend(args_iter)
        elif param.kind == inspect.Parameter.KEYWORD_ONLY:
            val = kwargs.get(param.name, _sentry)

            if val is _sentry:
                if param.default is inspect.Parameter.empty:
                    raise TypeError(f"missing a required argument: {param.name!r}")
            else:
                if param.name in consumed_kwargs:
                    raise TypeError(f"multiple values for argument {param.name!r}")

                consumed_kwargs.add(param.name)
                kwargs_norm[param.name] = val
        elif param.kind == inspect.Parameter.VAR_KEYWORD:
            for name, val in kwargs.items():
                if name in consumed_kwargs:
                    continue
                kwargs_norm[name] = val
                consumed_kwargs.add(name)

    rest = list(args_iter)
    if rest:
        pos_count = sum(
            1
            for param in sig.parameters.values()
            if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        )
        raise TypeError(
            f"function takes {pos_count} positional arguments but {len(args)} positional "
            f"arguments (and {len(kwargs)} keyword-only argument) were given"
        )

    if unconsumed_kwargs := kwargs.keys() - consumed_kwargs:
        raise TypeError(f"function got an unexpected keyword argument {next(iter(unconsumed_kwargs))!r}")

    return args_norm, kwargs_norm


def make_fn_deps_creator(fn: Callable[..., object], /) -> Callable[..., Awaitable[dict[str, Depends[object]]]]:
    """
    Takes a function of mixed arguments: `Depends` and non-`Depends`, and creates a function,
    which being used in `typed_di.invoke` produces dictionary with resolved dependencies.

    Example:
        .. code-block:: python

            def fn(po: int, /, dep1: Depends[Foo], dep2: Depends[Bar] = Depends(create_bar)) -> T: ...

            assert invoke(ctx, make_fn_deps_creator(fn)) == {
                "dep1": await create(ctx, Depends[Foo], "dep1"),
                "dep2": await create(ctx, Depends[Bar], Depends(create_bar),
            }

    As you can see, non-DI arguments aren't included in the result.

    For inspection purposes, creator return type is `TypedDict` with appropriate fields. Unfortunate, function
    return can't be typed right now

    :param fn: function to operate
    :return: creator of dependencies of ``fn``
    """

    async def create_deps(**deps: Depends[object]) -> dict[str, Depends[object]]:
        return deps

    sig = inspect.signature(fn)
    annotations = get_type_hints(fn)
    _check_unannotated_params(fn, annotations, sig)

    di_params = [copy.copy(param) for param in sig.parameters.values() if is_dep(annotations[param.name])]

    # Ignore "Only dict literals supported as second argument"
    ret_type = TypedDict("Unnamed", {param.name: annotations[param.name] for param in di_params})  # type: ignore[misc]

    # Ignore "`create_deps` don't have attribute `__signature__`" error
    create_deps.__signature__ = inspect.Signature(di_params, return_annotation=ret_type)  # type: ignore[attr-defined]
    create_deps.__annotations__ = {param.name: annotations[param.name] for param in di_params} | {"return": ret_type}

    return create_deps


_CTX_PARAM_NAME = "__ctx__"


class Partialized(Protocol[RT_cov]):
    async def __call__(self, __ctx__: AppContext | HandlerContext, /, *args: object, **kwargs: object) -> RT_cov:
        raise NotImplementedError


def partial(fn: Callable[..., Awaitable[RT]], /) -> Partialized[RT]:
    """
    Takes a function of mixed arguments, and creates a function, which strips all `Depends` arguments, instead of
    them places non-positional first arguments with type ``AppContext | HandlerContext``.

    Original function will be called with all arguments, passed to decorated version + resolved dependencies.
    All other dependency rules `typed_di._depends`_ are applied to them, so explicit, implicit and bootstrap deps will
    continue to work.

    As an example, it turns function with signature
    .. code-block:: python

        (dep1: Depends[Foo], val1: str, dep2: Depends[Bar] = Depends(...), *, val2: float = 10.0) -> ...

    into
    .. code-block:: python

        (ctx: AppContext | HandlerContext, /, val1: str, *, val: float = 10.0) -> ...

    This decorator destructs original function signature, because this behaviour can't be typed right now, but it
    makes new signature and annotations, so `inspect.signature` and `typing.get_type_hints` will catch the changes.

    TODO: make mypy plugin, which will handle signature of partialized functions

    :param fn: function to partialize
    :return: partialized function
    """

    deps_creator = make_fn_deps_creator(fn)

    sig = inspect.signature(fn)
    annotations = get_type_hints(fn)
    _check_unannotated_params(fn, annotations, sig)
    if _CTX_PARAM_NAME in annotations:
        raise ValueError(f"Seems function `{fn}` were already partialized")

    non_di_params = [copy.copy(param) for param in sig.parameters.values() if not is_dep(annotations[param.name])]

    @functools.wraps(fn)
    async def wrapper(__ctx__: AppContext | HandlerContext, /, *args: object, **kwargs: object) -> RT:
        deps = await invoke(__ctx__, deps_creator)

        if overlap_args := deps.keys() & kwargs.keys():
            raise ValueError(
                f"Fn `{fn}` were partialized, but some of given keyword arguments "
                f"overlaps with DI-arguments: {list(overlap_args)}"
            )

        mkwargs = {**kwargs, **deps}
        nargs, nkwargs = _normalize_arguments(sig, args, mkwargs)
        return await fn(*nargs, **nkwargs)

    # Create and assign new signature so other code (FastAPI DI, as example) will continue to work like there is no
    #  `Depends` arguments
    ctx_param = inspect.Parameter(
        _CTX_PARAM_NAME, inspect.Parameter.POSITIONAL_ONLY, annotation=AppContext | HandlerContext
    )
    wrapper.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        [ctx_param] + non_di_params,
        return_annotation=annotations["return"],
    )
    wrapper.__annotations__ = {param.name: annotations[param.name] for param in non_di_params}

    return wrapper
