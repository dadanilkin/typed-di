import functools
import inspect
from typing import Awaitable, Callable, ParamSpec, TypeVar, get_args, get_type_hints

from typed_di import _depends
from typed_di._contexts import AppContext, HandlerContext
from typed_di._create import CreationContext, create
from typed_di._depends import Depends
from typed_di._exceptions import CreationError, InvalidInvokableFunction, InvokableDependencyError, NestedInvokeError


def _is_lambda(fn: Callable[..., object], /) -> bool:
    try:
        # Dirty check, since there is no any special type or flags for lambdas
        return "<lambda>" == fn.__name__
    except AttributeError:
        return False


@functools.lru_cache(128)
def _validate_invokable(fn: Callable[..., object], /) -> dict[str, list[str]] | None:
    sig = inspect.signature(fn)
    if isinstance(fn, type):
        annotations = get_type_hints(fn.__init__)
        return_type = fn
    else:
        annotations = get_type_hints(fn)
        return_type = annotations.get("return")

    errs: list[tuple[str, list[str]]] = []
    # All functions must have return annotation, this rule is relaxed for lambdas
    if return_type is None and not _is_lambda(fn):
        errs.append(("", [f"Function `{fn!r}` do not have annotation for it return value"]))

    for arg_name, param in sig.parameters.items():
        arg_type = annotations.get(arg_name)
        arg_errs = []
        if arg_type is None:
            arg_errs.append("annotation is required")
        if param.kind not in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY):
            arg_errs.append(
                f'invalid parameter type `{param.kind}`, "positional or keyword" or "keyword only" are acceptable'
            )
        if _depends.is_dep(arg_type) is None:
            arg_errs.append(f"only `Depends[T]` annotations are supported, not `{arg_type}`")
        if get_args(arg_type) == ():
            arg_errs.append("bare `Depends` are not supported")
        # Checked by mypy in most cases, but not for implicit factories
        if not (param.default is inspect.Parameter.empty or isinstance(param.default, Depends)):
            arg_errs.append(
                "dependency arg should not have default value at all, "
                f"or it must be `Depends` instance, not `{param.default}`"
            )

        if arg_errs:
            errs.append((arg_name, arg_errs))

    if errs:
        return dict(errs)
    return None


def validate_invokable(fn: Callable[..., object], fn_overridden: object | None = None) -> None:
    validation_exc = _validate_invokable(fn)
    if validation_exc:
        raise InvalidInvokableFunction(fn, validation_exc, fn_overridden=fn_overridden)


C = TypeVar("C", bound=Callable[..., object])


def validated(fn: C) -> C:
    validate_invokable(fn)
    return fn


P = ParamSpec("P")
R = TypeVar("R")


async def resolve_fn_deps(
    ctx: AppContext | HandlerContext,
    fn: Callable[P, object],
    creation_ctx: CreationContext,
    fn_overridden: object | None = None,
    /,
) -> dict[str, Depends[object]]:  # impossible to make it typed right now
    validate_invokable(fn)

    sig = inspect.signature(fn)
    if isinstance(fn, type):
        annotations = get_type_hints(fn.__init__)
    else:
        annotations = get_type_hints(fn)

    sub_deps: dict[str, Depends[object]] = {}
    for arg_name, param in sig.parameters.items():
        # All asserts should be checked on validation step
        assert param.default is inspect.Parameter.empty or isinstance(param.default, Depends)
        assert arg_name in annotations

        try:
            if param.default is inspect.Parameter.empty:
                dep_val = await create(ctx, annotations[arg_name], arg_name, _creation_ctx=creation_ctx)
            else:
                dep_val = await create(ctx, annotations[arg_name], param.default, _creation_ctx=creation_ctx)
        except CreationError as exc:
            raise InvokableDependencyError(fn, exc, fn_overridden=fn_overridden) from exc
        except (NestedInvokeError, InvalidInvokableFunction, InvokableDependencyError) as exc:
            raise NestedInvokeError(fn, exc, fn_overridden=fn_overridden)

        sub_deps[arg_name] = Depends.resolved(dep_val)

    return sub_deps


async def invoke(ctx: AppContext | HandlerContext, fn: Callable[P, Awaitable[R]], /) -> R:
    fn_args = await resolve_fn_deps(ctx, fn, CreationContext())

    return await fn(**fn_args)  # type: ignore[arg-type]  # impossible to make it typed right now


if False:
    from typed_di import RootContext

    def inject(fn: Callable[P, Awaitable[R]], /) -> Callable[[RootContext | AppContext | HandlerContext], Awaitable[R]]:
        @functools.wraps(fn)
        async def wrapper(ctx: AppContext | HandlerContext, /) -> R:
            return await invoke(ctx, fn)

        annotations = get_type_hints(fn)
        new_sig = inspect.Signature(
            [inspect.Parameter("ctx", inspect.Parameter.POSITIONAL_ONLY, annotation=AppContext | HandlerContext)],
            return_annotation=annotations.get("return", inspect.Signature.empty),
        )
        new_annotations = {"ctx": AppContext | HandlerContext} | (
            {"return": annotations["return"]} if "return" in annotations else {}
        )
        try:
            wrapper.__signature__ = new_sig
            wrapper.__annotations__ = new_annotations
        except AttributeError:
            pass

        return wrapper
