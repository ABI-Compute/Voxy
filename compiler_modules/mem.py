import compiler_modules.ctx as ctx
import compiler_modules.errors as errors
import compiler_modules._types_ as _types_
import compiler_modules.utils as utils

def HandleMem_Write(line: list, scope: str):
    print("Handling memory write:", line)
    # format: [ADDR, TYPE, VALUE]
    addr = line[0]
    _type = line[1]
    value = line [2]
    if addr in ctx.context.const_map:
        addr = f"@{addr}"
    if value in ctx.context.const_map:
        value = ctx.context.const_map[value][0]
    if _type in _types_.llvm_numbers:
        _type = _types_.llvm_numbers[_type]
    else:
        errors.err("Only primitive types are allowed in memory writes")
    
    
    utils.AddToScope(f"  store {_type} {value}, {_type}* {addr}\n", scope)
   