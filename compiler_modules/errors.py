import compiler_modules.consts as consts
import compiler_modules.ctx as ctx
import sys

def CurrentFunction() -> str:
    if not ctx.context.current_function is None:
        return ctx.context.current_function
    else:
        return "Vmain"

def err(msg: str, code: int = 1):
    print(consts.RED_ESCAPE + msg + consts.RESET_ESCAPE + f" (at line {ctx.context.lineN}: '{ctx.context.line_content.strip()}' and function {CurrentFunction()})", file=sys.stderr)
    #ctx.context.has_errors = True
    ctx.context.exit_code = code

def FATAL(msg: str, code: int = 1):
    err("[FATAL ERROR]: " + msg, code)
    sys.exit(code)