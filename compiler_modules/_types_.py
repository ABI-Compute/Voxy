import re
import compiler_modules.errors as errors
import compiler_modules.ctx as ctx
import compiler_modules.utils as utils

# ---- type maps ----
llvm_numbers = {
    "int": "i32",
    "int64": "i64",
    "uint8": "i8",
    "char": "i8",
    "uchar": "i16",
    "uint16": "i16",
    "uint": "i32",
    "uint64": "i64",
    "float": "float",
    "float64": "double",
    "intptr": "i32*",
    "bool": "i1",
    "void": "void"
}

vox_numbers = set(llvm_numbers.keys())

def handle_bool(value: str) -> str:
    if value.lower() in ["true", "1"]:
        return "1"
    else:
        return "0"

def strchars(s: str) -> list[str]:
    chars_ = []
    for c in s:
        chars_.append(c)
    return chars_

def process_string(s: str, size: int) -> str:
    old = len(strchars(s))
    if old > size:
        errors.err(f"String '{s}' too long for buff type (max {size} chars)")
    s = s.replace("\\0", "\\00")
    s = s.replace("\\n", "\\0A")
    s = s.replace("\\t", "\\09")
    s = s.replace("\\r", "\\0D")
    s = s.replace("\\\"", "\\22")
    s = s.replace("\\\\", "\\5C")
    new_len = len(strchars(s))
    if new_len > size:
        errors.err(f"String '{s}' too long for buff type (max {size} chars)")
    needed = (size - old)
    for i in range(needed):
        s += "\\00"
    return f"\"{s.replace('"', '\\20')}\""
    
def HandleGetElementPtr(name: str, base_type: str, value: str) -> str:
    # T* getelementptr ([N x T], [N x T]* @NAME, i32 0, i32 0)
    buff_name = value.replace("addr ", "").strip()
    if not ctx.context.const_map.__contains__(buff_name):
        errors.err(f"Buffer '{buff_name}' not found for getelementptr")
    type_ = ctx.context.const_map[buff_name][1]
    base, size = parse_buff_type(type_)
    if not base in llvm_numbers or not base_type in llvm_numbers:
        errors.err(f"Unknown base type '{base}' for getelementptr")
    base_type = llvm_numbers[base_type]
    if base != base_type and not ctx.context.unsafe_mode:
        errors.err(f"Type mismatch in getelementptr: buffer base type '{base}' vs pointer base type '{base_type}'")
    

    return f"@{name} = constant {base_type}* getelementptr ([{size} x {base_type}], [{size} x {base_type}]* @{buff_name}, i32 0, i32 0)"


def vox_type_to_llvm(vox_type: str) -> str:
    """
    Recursively convert a Vox type to an LLVM type.
    Supports:
        - ptr[T]
        - buff[T; N]
        - basic types in llvm_numbers
    """
    global llvm_numbers
    vox_type = vox_type.strip()
    
    # Pointer type
    if vox_type.startswith("ptr[") and vox_type.endswith("]"):
        inner = vox_type[4:-1].strip()
        llvm_inner = vox_type_to_llvm(inner)
        if inner.startswith("buff"):
            return f"{llvm_inner}"
        return f"{llvm_inner}*"
    
    # Buffer type
    buff_match = re.match(r"buff\[(\w+)(?:\s*;\s*(\d+))?\]", vox_type)
    if buff_match:
        inner_type = buff_match.group(1)
        size = buff_match.group(2)
        llvm_inner = llvm_numbers.get(inner_type)
        if llvm_inner is None:
            errors.err(f"Unknown buffer type: {inner_type}")
        if size:
            return f"[{size} x {llvm_inner}]"
        else:
            # unspecified length buffer
            return f"{llvm_inner}*"
        
    if vox_type in ctx.context.aliases.keys():
        return vox_type_to_llvm(ctx.context.aliases[vox_type])
    
    # Simple type
    llvm_type = llvm_numbers.get(vox_type)
    return llvm_type

# helper to parse buff type
def parse_buff_type(type_token: str) -> tuple[str, int]:
    # buff[BASE; SIZE]
    toks = type_token.replace(";", " ; ").replace(" ;  ", " ; ").replace("[", " [ ").replace("]", " ] ").split(" ")
    # buff [ BASE ; SIZE ]
    base = ""
    base_found = False
    size = 0
    tpc = 0
    while tpc < len(toks):
        tok = toks[tpc].strip()
        if tok == "buff" and tpc != 0:
            errors.err(f"Invalid buff type  (nested buff)'{type_token}'")
        elif tok == "buff":
            tpc += 1
        elif tok == "[":
            base_found = True
            tpc += 1
            base = toks[tpc]
            tpc += 1
        elif tok == ";" and not base_found:
            errors.err(f"Invalid buff type (missing base type) '{type_token}'")
        elif tok == ";":
            tpc += 1
            size = int(toks[tpc])
            tpc += 1
            break
        else:
            errors.err(f"Invalid buff type (unexpected token {tok}) '{type_token}'")
    return base, size


##===========================================================================================================##
##===========================================================================================================##
##===========================================================================================================##
##===========================================================================================================##
import re

bool_dyn_count = 0
def get_tmp_bool():
    global bool_dyn_count
    bool_dyn_count+=1
    return f"tmp_bool{bool_dyn_count}"

def add_to_current_scope(s: str): utils.AddToScope(s, ctx.context.current_function)

def is_static_bool_expr(expr: str) -> bool:
   maps = list(ctx.context.const_map.keys()) + list(ctx.context.var_map)
   if any(x in expr for x in maps): return False
   return not re.search(r"\*\([\d\s\+\-\*\/\.]+\)", expr)

def convert_to_python_syntax(expr: str) -> str:
   return expr.replace("||"," or ").replace("&&"," and ").replace("^^"," ^ ").replace("!"," not ")

def eval_static_bool_expr(expr):
   return eval(convert_to_python_syntax(expr), {"__builtins__": None}, {"True":True,"False":False})

def llvm_bool_var(name: str) -> str:
   tmp = get_tmp_bool()
   add_to_current_scope(f"%{tmp} = load i1, i1* @{name}\n")
   return f"%{tmp}"

def is_literal(expr):
    # True if expr is a number or boolean
    expr = expr.strip()
    # Check for boolean literals
    if expr.lower() in ["true", "false"]:
        return True
    # Check for numeric literals (integers and floats)
    try:
        float(expr)
        return True
    except ValueError:
        return False
    
def load_t(name, type):
    tmp = "%" + get_tmp_bool()
    add_to_current_scope(f"    {tmp} = load {type}, {type}* @{name}\n")
    return tmp

def is_const(name):
    print(f"matching: {name}")
    return name in list(ctx.context.const_map.keys())

def is_var(name):
    return name in list(ctx.context.var_map.keys())

def handle_bool_expr(expr: str) -> str:
   expr = expr.strip()
   # static literal
   if is_static_bool_expr(expr): return "1" if eval_static_bool_expr(expr) else "0"
   # parentheses
   if expr.startswith("(") and expr.endswith(")"): return handle_bool_expr(expr[1:-1])
   # unary !
   if expr.startswith("!"):
       inner = handle_bool_expr(expr[1:])
       tmp = get_tmp_bool()
       add_to_current_scope(f"%{tmp} = xor i1 1, {inner}\n")
       return f"%{tmp}"
   # binary operators
   for op, llvm_op in [("&&","and"),("||","or"),("^^","xor"),("==","eq"),("!=","ne"),("<=","sle"),("<","slt"),(">=","sge"),(">","sgt")]:
       if op in expr:
            lhs,rhs = map(str.strip, expr.split(op,1))
            lval,rval = handle_bool_expr(lhs), handle_bool_expr(rhs)
            cmp_t = ""
            if is_literal(rhs):
               if rhs == "True": rval = 1
               elif rhs == "False": rval = 0
               else: rval = rhs
            if is_literal(lhs):
               if lhs == "True": lval = 1
               elif lhs == "False": lval = 0
               else: lval = lhs
            if is_var(lhs):
                cmp_t = vox_type_to_llvm(ctx.context.var_map[lhs])
                lval = load_t(lhs, cmp_t)
            elif is_const(lhs):
                lval = load_t(lhs, vox_type_to_llvm(ctx.context.const_map[lhs][1]))
            if is_var(rhs):
                rval = load_t(lhs, vox_type_to_llvm(ctx.context.var_map[rhs]))
            elif is_const(rhs):
                rval = load_t(rhs, vox_type_to_llvm(ctx.context.const_map[rhs][1]))
            tmp = get_tmp_bool()
            # use icmp for comparison ops, logical ops directly
            if llvm_op in ["eq","ne","sle","slt","sge","sgt"]:
                add_to_current_scope(f"%{tmp} = icmp {llvm_op} i1 {lval}, {rval}\n")
            else:
               add_to_current_scope(f"%{tmp} = {llvm_op} i1 {lval}, {rval}\n")
            return f"%{tmp}"
   # single variable or API call
   if utils.word_count(expr) == 1:
       name = expr
       if name in ctx.context.var_map or name in ctx.context.const_map:
           tmp = get_tmp_bool()
           # determine type from const_map, default i1
           ty = vox_type_to_llvm(ctx.context.const_map[name][1]) if name in ctx.context.const_map else "i1"
           add_to_current_scope(f"%{tmp}_val = load {ty}, {ty}* @{name}\n")
           if ty == "i32":  # integer -> i1
               tmp2 = get_tmp_bool()
               add_to_current_scope(f"%{tmp2} = icmp ne i32 %{tmp}_val, 0\n")
               return f"%{tmp2}"
           return f"%{tmp}_val"
   # fallback for dynamic expressions
   tmp = get_tmp_bool()
   add_to_current_scope(f"%{tmp} = icmp ne i32 {expr}, 0\n")
   return f"%{tmp}"
