import compiler_modules.ctx as ctx
import compiler_modules.errors as errors

def evaluate_expression(expr: str) -> str:
    expr = expr.strip()
    expr = expr.replace("^", "**")  # fix inplace replace

    # Replace constants with their numeric values
    for name, val in ctx.context.const_map.items():
        # ensure val is a number
        expr = expr.replace(name, str(val))

    try:
        result = eval(expr, {"__builtins__": None}, {})
        return str(result)
    except Exception as e:
        errors.err(f"Error evaluating expression '{expr}': {e}")
