from typing import Callable

import mypy.plugin
from mypy.checker import TypeChecker
from mypy.nodes import ArgKind, TypeInfo
from mypy.plugin import FunctionContext
from mypy.types import Type, CallableType, get_proper_type, Instance, UnionType


DEPENDS_CLS_NAME = "typed_di._depends.Depends"
PARTIAL_NAME = "typed_di._partial.partial"


def process_partial(ctx: FunctionContext) -> Type:
    """
    Decide correct return type of ``typed_di.partial(fn)``. Impl is very basic and makes some assumptions without
    prior checking, thus fragile. Doesn't work with overloads, but might to.
    """

    match ctx:
        case FunctionContext(arg_types=[[CallableType() as receiver]]):
            pass
        case _:
            ctx.api.fail(f"Seems that `{PARTIAL_NAME}` were called on invalid type", ctx.context)
            return ctx.default_return_type

    if receiver.is_ellipsis_args:
        return ctx.default_return_type

    args = zip(receiver.arg_types, receiver.arg_kinds, receiver.arg_names)
    ret_args = [
        (type_, kind, name)
        for type_, kind, name in args
        if not isinstance(p := get_proper_type(type_), Instance) or p.type.fullname != DEPENDS_CLS_NAME
    ]

    if not isinstance(ctx.api, TypeChecker):
        raise RuntimeError("Type-checker API isn't available")

    contexts_mod = ctx.api.modules["typed_di._contexts"]
    assert isinstance(contexts_mod.names["AppContext"].node, TypeInfo)
    assert isinstance(contexts_mod.names["HandlerContext"].node, TypeInfo)

    ret_args = [
        (
            UnionType(
                [
                    Instance(contexts_mod.names["AppContext"].node, []),
                    Instance(contexts_mod.names["HandlerContext"].node, []),
                ]
            ),
            ArgKind.ARG_POS,
            None,
        )
    ] + ret_args

    return CallableType(
        arg_types=[at for at, _, _ in ret_args],
        arg_kinds=[kind for _, kind, _ in ret_args],
        arg_names=[name for _, _, name in ret_args],
        ret_type=receiver.ret_type,
        fallback=receiver.fallback,
        name=receiver.name,
        definition=receiver.definition,
        variables=receiver.variables,
        line=receiver.line,
        column=receiver.column,
        is_ellipsis_args=receiver.is_ellipsis_args,
        implicit=receiver.implicit,
        special_sig=receiver.special_sig,
        from_type_type=receiver.from_type_type,
        bound_args=receiver.bound_args,
        def_extras=receiver.def_extras,
        type_guard=receiver.type_guard,
        from_concatenate=receiver.from_concatenate,
    )


class Plugin(mypy.plugin.Plugin):
    def get_function_hook(self, fullname: str) -> Callable[[FunctionContext], Type] | None:
        if fullname != "typed_di._partial.partial":
            return None

        return process_partial


def plugin(version: str) -> type[mypy.plugin.Plugin]:
    return Plugin
