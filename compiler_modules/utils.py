import compiler_modules.ctx as ctx
import compiler_modules.errors as errors

def AddToScope(code: str, scope: str, show=False):
    if show: print(f"SCOPE: {scope}, CODE: {code}")
    if scope == "Vmain" or scope is None:   # Vmain
        ctx.context.Vmain += code
    else:    # regular function
        ctx.context.functions[scope][0].body += code

def GetAssignValue(toks: list[str]) -> str:
    type_found = False
    value = ""
    for t in toks:
        if type_found:
            value += t + " "
        if t == "=":
            type_found = True
    return value.strip()
    
def assure_not_None(val, fatal: bool):
    if val is None:
        if fatal: errors.FATAL("val is none and fatal")
        else: errors.err("val is none")

def word_count(sentence: str) -> int:
    words = 0
    in_word = False
    
    for char in sentence:
        if char.isspace():
            in_word = False
        elif not in_word:
            words += 1
            in_word = True
    
    return words
