import compiler_modules.ctx as ctx
import compiler_modules._types_ as _types_
import re
import compiler_modules.errors as errors
import compiler_modules.structs as structs
import compiler_modules._libs_ as _libs_
import compiler_modules.evals as evals
import compiler_modules.utils as utils
import compiler_modules.mem as mem
import compiler_modules.compy as compy

def parse_struct_const(name: str, type_token: str, value: str):
    # const NAME: StructName = StructName { val1, val2, ... } or { key: val, ... }
    struct_def: structs.VoxStruct = ctx.context.structs[type_token]
    field_types = struct_def.get_feild_types()  # typo corrected

    # Strip the struct name and outer braces
    args_str = value[len(type_token):].strip()
    if args_str.startswith("{") and args_str.endswith("}"):
        args_str = args_str[1:-1].strip()
    else:
        errors.err(f"Struct initialization must use braces: {value}")

    construct_args = []

    # Check if using named fields (key: value)
    if ":" in args_str:
        # named fields, e.g., name: 67, age: 30
        for pair in args_str.split(","):
            pair = pair.strip()
            if not pair: continue
            if ":" not in pair: errors.err(f"Expected named field 'key: value', got '{pair}'")
            key, val = map(str.strip, pair.split(":", 1))
            if key not in struct_def.fields: errors.err(f"Unknown field '{key}' for struct '{type_token}'")
            construct_args.append((key, val))
        
        # Ensure all fields are provided (optional: could allow defaults)
        if len(construct_args) != len(field_types):
            errors.err(f"Struct '{type_token}' expects {len(field_types)} fields, got {len(construct_args)}")

        # Generate LLVM constant
        ret = f"@{name} = constant %{type_token} {{ "
        for i, (key, val) in enumerate(construct_args):
            f_type = struct_def.fields[key]
            llvm_f_type = _types_.llvm_numbers[f_type]
            ret += f", {llvm_f_type} {val}"
        ret = ret.replace("{ ,", "{ ") + " }\n"
        return ret

    else:
        # positional fields, e.g., 67, 30
        construct_args = [arg.strip() for arg in args_str.split(",") if arg.strip()]

        if len(construct_args) != len(field_types):
            errors.err(f"Struct '{type_token}' expects {len(field_types)} fields, got {len(construct_args)}")

        ret = f"@{name} = constant %{type_token} {{ "
        for i in range(len(construct_args)):
            arg = construct_args[i]
            f_type = field_types[i]
            llvm_f_type = f_type
            ret += f", {llvm_f_type} {arg}"
        ret = ret.replace("{ ,", "{ ") + " }\n"
        return ret

def parse_struct_var(name: str, type_token: str, value: str):
    return parse_struct_const(name, type_token, value).replace("constant ", "global ")

def parse_const(name: str, type_token: str, value: str) -> str:
    # @NAME = constant LLVM_T VALUE
    llvm_type = _types_.vox_type_to_llvm(type_token)
    pre_val = ""
    struct_names = list(ctx.context.structs.keys())
    if type_token in _types_.llvm_numbers:
        llvm_type = _types_.llvm_numbers[type_token]
        if type_token == "bool":
            value = _types_.handle_bool(value)
        # If value looks like a runtime call (e.g., GetStdHandle(...)) don't try to eval it here.
        if not (isinstance(value, str) and "(" in value and value.strip().endswith(")")):
            value = evals.evaluate_expression(value)
        
    elif type_token in struct_names:
        return parse_struct_const(name, type_token, value)

    elif type_token.startswith("buff"):

        base, size = _types_.parse_buff_type(type_token)
        if base == "" or size == 0:
            errors.err(f"Invalid buff type for variable '{name}'")
        elif base == "char" or base == "uchar":
            pre_val = "c"
            value = _types_.process_string(value, size)
        llvm_type = f"[{size} x { _types_.llvm_numbers.get(base, 'i8*')}]"
    elif type_token.startswith("ptr"):
        # FORMAT ptr[TYPE]
        base_type = type_token.replace("ptr[", "").replace("]", "")
        llvm_type = ""
        if base_type in _types_.llvm_numbers:
            llvm_type = f"{ _types_.llvm_numbers[base_type]}*"
            # const NAME: ptr[TYPE] = VALUE
            # OR
            # const NAME: ptr[TYPE] = addr CONST_NAME | VAR_NAME -> @MyPtr = constant TYPE* @CONST_NAME | @VAR_NAME
            # if CONST_NAME or VAR_NAME is a buff[T; N] use T* getelementptr ([N x T], [N x T]* @NAME, i32 0, i32 0)

        else:
            errors.err(f"Unknown base type '{base_type}' for pointer variable '{name}'")

        const_val = ""
        const_t = ""
        if value.replace("addr ", "").strip() in ctx.context.const_map:
            const_val = ctx.context.const_map[value.replace("addr ", "").strip()][0]
            const_t = ctx.context.const_map[value.replace("addr ", "").strip()][1]

        if value.startswith("addr "):
            if const_t.startswith("buff"): return _types_.HandleGetElementPtr(name,base_type, value)
            return f"@{name} = constant {llvm_type} @{value.replace('addr ', '').strip()}\n"
        else:
            return f"@{name} = constant {llvm_type} inttoptr (i64 {value} to i32*)\n"
    else:
        errors.err(f"Unknown type '{type_token}' for variable '{name}' not in vox numbers or a struct: {ctx.context.structs}")
    # Handle runtime-initialized constants (e.g., GetStdHandle(...)) by creating
    # a zero-initialized global and emitting a runtime init sequence in Vmain.
    if "(" in value and value.strip().endswith(")"):
        # extract function name and inner arg
        func_name = value[:value.find("(")].strip()
        inner = value[value.find("(")+1:-1].strip()
        inner_val = inner
        if inner in ctx.context.const_map:
            inner_val = ctx.context.const_map[inner][0]
        # add zero-initialized global
        if not f"@{name} = global {llvm_type} zeroinitializer\n" in ctx.context.pre_entry: ctx.context.pre_entry += f"@{name} = global {llvm_type} zeroinitializer\n"
        # emit runtime init in Vmain: call the function with properly-typed literal
        # try to format inner_val: if it's an integer literal, use as-is, else if it's a global ref (@name)
        formatted_inner = inner_val
        # if inner_val is numeric string, keep; if startswith('@') use as is; otherwise if it's a bare name and exists in const_map, use its stored value
        if inner in ctx.context.const_map:
            formatted_inner = ctx.context.const_map[inner][0]
        # choose literal formatting: assume parameter is i32 unless const_map gives type
        param_str = formatted_inner
        tmp = f"%tmp_init{ctx.context.fn_call_num}"
        ctx.context.fn_call_num += 1
        utils.AddToScope(f"  {tmp} = {parseFunctionCallS(value, retT=llvm_type)}\n", ctx.context.current_function)
        utils.AddToScope(f"  store {llvm_type} {tmp}, {llvm_type}* @{name}\n", ctx.context.current_function)
        # Register constant as a reference to the global we created
        ctx.context.const_map[name] = [f"@{name}", type_token.strip()]
        return ""

    # Normal constant: register and emit
    ctx.context.const_map[name] = [value.strip(), type_token.strip()]
    return f"@{name} = constant {llvm_type} {pre_val}{value}\n"

def parse_var(name: str, type_token: str, value: str) -> str:
    """
    Parse a Vox variable into LLVM IR.
    Handles numbers, pointers, buffers, structs, and runtime function calls.
    Ensures globals are always stored with pointer types in LLVM.
    """
    llvm_type = _types_.vox_type_to_llvm(type_token)
    pre_val = ""
    struct_names = list(ctx.context.structs.keys())

    # ===========================
    # Number types (int, bool, etc.)
    # ===========================
    if type_token in _types_.llvm_numbers:
        llvm_type = _types_.llvm_numbers[type_token]
        if type_token == "bool":
            value = _types_.handle_bool(value)
        # Evaluate constant expressions
        if not (isinstance(value, str) and "(" in value and value.strip().endswith(")")):
            value = evals.evaluate_expression(value)
        # Simple constant global
        if "(" not in value:
            return f"@{name} = global {llvm_type} {value}\n"

    # ===========================
    # Struct types
    # ===========================
    elif type_token in struct_names:
        return parse_struct_var(name, type_token, value)

    # ===========================
    # Buffers
    # ===========================
    elif type_token.startswith("buff"):
        base, size = _types_.parse_buff_type(type_token)
        if base == "" or size == 0:
            errors.err(f"Invalid buff type for variable '{name}'")
        elif base in ("char", "uchar"):
            pre_val = "c"
            value = _types_.process_string(value, size)
        llvm_type = f"[{size} x {_types_.llvm_numbers.get(base, 'i8')}]"
        return f"@{name} = global {llvm_type} c{value}\n"

    # ===========================
    # Pointers
    # ===========================
    elif type_token.startswith("ptr"):
        base_type = type_token.replace("ptr[", "").replace("]", "")
        if base_type in _types_.llvm_numbers:
            llvm_type = f"{_types_.llvm_numbers[base_type]}*"
        else:
            errors.err(f"Unknown base type '{base_type}' for pointer variable '{name}'")
        # addr reference
        if value.startswith("addr "):
            ref_name = value.replace("addr ", "").strip()
            if not ref_name in ctx.context.const_map: errors.err(f"Unknown reference '{ref_name}' for pointer variable '{name}'")
            const_type = ctx.context.const_map[ref_name][1]
            if const_type.startswith("buff"): return _types_.HandleGetElementPtr(name, base_type, value)
            return f"@{name} = global {llvm_type} @{ref_name}\n"
        # int -> pointer cast
        return f"@{name} = global {llvm_type} inttoptr (i64 {value} to {llvm_type})\n"

    # ===========================
    # Runtime-initialized globals
    # ===========================
    if "(" in value and value.strip().endswith(")"):
        # Pre-declare zero-initialized global
        ctx.context.pre_entry += f"@{name} = global {llvm_type} zeroinitializer\n"
        tmp = f"%tmp_init{ctx.context.fn_call_num}"
        ctx.context.fn_call_num += 1
        # Generate call and store inside function
        utils.AddToScope(
            f"  {tmp} = {parseFunctionCallS(value, retT=llvm_type)}\n",
            ctx.context.current_function
        )
        utils.AddToScope(
            f"  store {llvm_type} {tmp}, {llvm_type}* %{name}\n",
            ctx.context.current_function
        )
        return ""

    # ===========================
    # Default: simple runtime global
    # ===========================
    return f"@{name} = global {llvm_type} {pre_val}{value}\n"


def parse_debug_print(toks):
    ret = ""
    for tok in toks[1:]:
        if ctx.context.const_map.__contains__(tok):
            ret += ctx.context.const_map[tok][0]
        elif tok == "ctime_print":
            pass
        else:
            ret += tok + " "
    return "[CTIME_PRINT]" + ret

def parseDynImport(line: str) -> str:
    """
    Parse a dyn_import function line, register it as a Funtion object,
    and return LLVM declaration.
    """
    from compiler_modules.functions import Funtion
    line = line.strip()
    if not line.startswith("dyn_import fn "):
        errors.err("Line must start with 'dyn_import fn '")
        return ""
    
    line = line[len("dyn_import fn "):].strip()
    
    # Extract return type and rest
    ret_type_end = line.find(" ")
    if ret_type_end == -1:
        errors.err("Invalid function declaration: missing function name")
        return ""
    
    ret_type_vox = line[:ret_type_end].strip()
    rest = line[ret_type_end:].strip()
    
    # Extract function name and parameters
    name_start = rest.find("(")
    name_end = rest.rfind(")")
    if name_start == -1 or name_end == -1:
        errors.err("Invalid function declaration: missing parameters")
        return ""
    
    func_name = rest[:name_start].strip()
    params_str = rest[name_start+1:name_end].strip()
    
    # Parse parameters
    llvm_params = []
    args_dict = {}
    if params_str:
        for param in params_str.split(","):
            param_name, param_type_vox = param.split(":")
            param_name = param_name.strip()
            param_type_vox = param_type_vox.strip()
            llvm_type = _types_.vox_type_to_llvm(param_type_vox)
            llvm_params.append(f"{llvm_type} %{param_name}")
            args_dict[param_name] = llvm_type
    
    # Map return type
    ret_type_llvm = _types_.vox_type_to_llvm(ret_type_vox)
    
    # Register function: declare-only
    func_obj = Funtion(name=func_name, args=args_dict, ret_type=ret_type_llvm, body="")
    ctx.context.functions[func_name] = [func_obj, True]  # True = declare-only
    
    # Build LLVM declaration
    llvm_decl = f"declare {ret_type_llvm} @{func_name}({', '.join(llvm_params)})\n\n"
    return llvm_decl

def help1(llvm_args, arg_name, arg_type, arg_val, scope, tmp):

    fn = None
    arg_list = []
    
    try: fn = ctx.context.functions[ctx.context.current_function][0]; arg_list = list(fn.args.keys())
    except: pass

    if arg_val in arg_list or arg_name in arg_list:
        llvm_args.append(f"{arg_type} %{arg_val}")
    else:
        # local/global load
        src = f"@{arg_val}"
        if scope != "Vmain": 
            fn.body += f"  {tmp} = load {arg_type}, {arg_type}* {src}\n"
        else: ctx.context.Vmain += f"  {tmp} = load {arg_type}, {arg_type}* {src}\n"
        llvm_args.append(f"{arg_type} {tmp}")

def parseFunctionCallS(line: str, retT="?") -> str:
    """
    Convert a Vox function call into LLVM IR. Ensures:
      • argument positions strictly follow the signature
      • string literals become globals in pre_entry
      • constants / args load correctly into the current function scope
      • no argument is ever skipped (no misalignment)
    """
    from compiler_modules.functions import Funtion

    line = line.strip()
    if "(" not in line or not line.endswith(")"):
        errors.err("Not a valid function call line")
        return ""

    # -----------------------------
    # Extract function and call args
    # -----------------------------
    func_name = line[:line.find("(")].strip()
    args_str = line[line.find("(") + 1:-1].strip()

    if func_name not in ctx.context.functions:
        errors.err(f"Unknown function: {func_name}")
        return ""

    func_obj: Funtion = ctx.context.functions[func_name][0]
    declare_only = ctx.context.functions[func_name][1]
    func_obj.MakeNonNone()

    # Safe argument splitter
    args = []
    depth = 0
    cur = ""
    for c in args_str:
        if c == "," and depth == 0:
            args.append(cur.strip())
            cur = ""
        else:
            cur += c
            if c == "(": depth += 1
            elif c == ")": depth -= 1
    if cur.strip():
        args.append(cur.strip())

    # -----------------------------
    # Strict argument count check
    # -----------------------------
    expected = list(func_obj.args.items())

    if len(args) != len(expected):
        errors.err(
            f"Argument mismatch for '{func_name}': "
            f"expected {len(expected)}, got {len(args)}"
        )
        # We stop immediately — never allow misaligned calls.
        return ""

    llvm_args = []

    # ================================================================
    #   For each parameter in the function signature, process arg[i]
    # ================================================================
    for i, (arg_name, arg_type_vox) in enumerate(expected):
        arg_val = args[i]
        arg_type = "i32"   # defualt
        if not ctx.context.current_function is None: 
            fn: Funtion = ctx.context.functions[ctx.context.current_function][0]
            if fn.is_arg(arg_val): arg_type = _types_.vox_type_to_llvm(fn.get_arg_Type(arg_val))

        # Convert Vox → LLVM type
        try:
            arg_type2 = _types_.vox_type_to_llvm(arg_type_vox)
            if not arg_type2 is None: arg_type = arg_type2
        except:
            arg_type = arg_type_vox  # already llvm

        if arg_type is None:
            errors.FATAL(f"Type resolution failure for param '{arg_name}' in {func_name}")

        # ------------------------------------------------------------
        # 1. String literal: addr "hello world"
        # ------------------------------------------------------------
        if arg_val.startswith('addr "') and arg_val.endswith('"'):
            s: str = arg_val[6:-1]

            gname = f"@.str{len(ctx.context.pre_entry)+1}"
            ctx.context.pre_entry += f'{gname} = private constant [{len(s)+1} x i8] c{_types_.process_string(s, len(s)+1)}\n\n'
            

            llvm_args.append( f"i8* getelementptr([{len(s)} x i8], [{len(s)+1} x i8]* {gname}, i32 0, i32 0)" )
            continue

        # ------------------------------------------------------------
        # 2. addr NAME → pointer argument
        # ------------------------------------------------------------
        if arg_val.startswith("addr "):
            name = arg_val[5:].strip()

            # Determine the pointer type: arg_type* if it's not already a pointer
            if not arg_type.endswith("*"): llvm_type_ptr = f"{arg_type}*"
            else: llvm_type_ptr = arg_type

            llvm_args.append(f"{llvm_type_ptr} @{name}")
            continue


        # ------------------------------------------------------------
        # 3. null literal
        # ------------------------------------------------------------
        if arg_val == "null":
            llvm_args.append(f"{arg_type} 0")
            continue

        # ------------------------------------------------------------
        # 4. Load constant / local variable from const_map or locals
        # ------------------------------------------------------------
        if arg_val in ctx.context.const_map:
            scope = ctx.context.current_function or "Vmain"
            tmp = compy.tmp_var()

            # Is the target a function argument?
            help1(llvm_args, arg_name, arg_type, arg_val, scope, tmp)
            continue

        # ------------------------------------------------------------
        # 5. If current function argument
        # ------------------------------------------------------------
        if (
            ctx.context.current_function and
            ctx.context.functions[ctx.context.current_function][0].is_arg(arg_val)
        ):
            llvm_args.append(f"{arg_type} %{arg_val}")
            continue

        # ------------------------------------------------------------
        # 6. Raw literal (integer, number, etc.)
        # ------------------------------------------------------------
        llvm_args.append(f"{arg_type} {arg_val}")

    # -----------------------------
    # Emit LLVM call
    # -----------------------------
    real_ret = retT if retT != "?" else func_obj.ret_type
    return f"  call {real_ret} @{func_name}({', '.join(llvm_args)})\n"

  
def chars(s: str) -> list:
    return [c for c in s]

def joinchars(l: list) -> str:
    return "".join(l)

Pscope = ""

# Globals expected to exist:
# Pscope
# utils.AddToScope(code: str, scope: str)
# _types_.handle_bool(cond_str) -> str

# Internal bookkeeping for open if contexts
last_ifnum = 0

def _ensure_trailing_newline(s: str) -> str:
    return s if s.endswith("\n") else s + "\n"

def parse_line(line: str, scope: str = "Vmain"):
    global Pscope
    if scope != Pscope: print(f"============================= SCOPE CNAHGE +++++++++++++++++\n{Pscope} -> {scope}\n")
    Pscope = scope

    # remove the first space
    if line.startswith(" "): line = joinchars(chars(line)[1:])
    if ctx.context.asm_mode:
        # # call void asm sideeffect inteldialect "mov eax, 1", ""
        if line.__contains__("#"):
            pass
        else:
            utils.AddToScope(f"    call void asm sideeffect {ctx.context.asm_dialect} \"{line.strip()}\", \"\"\n", scope)

    elif line.strip().startswith("ASM:"):
        ctx.context.asm_mode = True

    elif line.strip().startswith("asmend:"):
        ctx.context.asm_mode = False

    elif line.strip().startswith("return"):
        scope = ctx.context.current_function

        # Extract text after "return"
        parts = line.strip().split(None, 1)

        # Look up current function return type
        func, _ = ctx.context.functions[ctx.context.current_function]
        ret_type = func.ret_type.strip()

        # Case 1: bare "return"
        if len(parts) == 1:
            # Expect void return
            if ret_type == "void": utils.AddToScope("  ret void\n", scope)
            else: errors.err(f"Function {scope} must return {ret_type}, but got empty return")
            return

        # Case 2: "return VALUE"
        value = parts[1].strip()

        # If the return type is void but user returned something
        if ret_type == "void": errors.err(f"Function {scope} returns void but got: return {value}")

        # Emit typed return
        utils.AddToScope(f"  ret {ret_type} {value}\n", scope)



    # === ctx.context.functions ===
    elif re.match(r'^\s*(\w+)\s*\((.*)\)\s*$', line.strip()):

        utils.AddToScope(parseFunctionCallS(line), scope)

    elif line.strip().startswith("using "):
        # using NAME = TYPE
        toks = line.split(" ")
        ctx.context.aliases[toks[1]] = toks[3]

    # === DEBUG ===
    elif line.strip().startswith("ctime_print"):
        toks = line.replace("\"", "").strip().split(" ")
        toprint = parse_debug_print(toks)
        print(toprint)

    # ==== IMPORTS ====
    elif line.strip().startswith("lib"):
        # lib dyn|static <LIB_NAME>|"LIB_NAME"
        toks = line.split(" ")
        if toks[1] == "dyn":
            _libs_.HandleDynLib(toks[2], scope)
        elif toks[1] == "static":
            _libs_.HandleStaticLib(toks[2], scope)
        else:
            errors.err(f"Unknown lib type '{toks[1]}'")

    elif line.strip().startswith("dyn_import fn ") and line.endswith("."):
        ctx.context.pre_entry += parseDynImport(line)

    elif line.strip().startswith("dyn_import fn "):
        ctx.context.in_dyn_fn_import = True
        ctx.context.current_dyn_fn_import = line.strip().replace("  ", "")

    elif ctx.context.in_dyn_fn_import:
        ctx.context.current_dyn_fn_import += line.strip().replace("  ", "")
        if line.endswith("."):
            ctx.context.pre_entry += parseDynImport(ctx.context.current_dyn_fn_import)
            ctx.context.in_dyn_fn_import = False
            ctx.context.current_dyn_fn_import = ""
            
    elif line.strip().startswith("dyn_import "):
        ctx.context.pre_entry += parseDynImport(line)


    # ==== LABELS AND GOTOs ====
    
    elif line.startswith("lb "):
        label_name = line.strip()[3:].strip()
        utils.AddToScope(f"  br label %{label_name}\n{label_name}:\n", scope)
        
    elif line.strip().startswith("goto "):
        label_name = line.strip()[5:].strip()
        utils.AddToScope(f"  br label %{label_name}\n", scope)

    # ==== CONST AND VAR DECLARATIONS ====
    elif line.strip().startswith("const "):
        # const NAME: TYPE = VALUE
        line_fixed = re.sub(r'(\b\w+):', r'\1 :', line)
        toks = line_fixed.strip().split(" ")
        # format: var NAME : TYPE = VALUE
        name = toks[1].split(":")[0]
        colon = toks[2]
        value = utils.GetAssignValue(toks)
        match = re.search(r':\s*(.*?)\s*=', line)
        type_token = ""
        if match: type_token = match.group(1)
        res = parse_const(name, type_token, value.strip())
        ctx.context.pre_entry += res

    elif line.strip().startswith("var "):
        toks = line.strip().replace(":", " : ").replace(" :  ", " : ").split(" ")
        # format: var NAME : TYPE = VALUE
        name = toks[1].split(":")[0]
        colon = toks[2]
        value = utils.GetAssignValue(toks)
        type_token = line.replace(colon, "").replace(f"var {name}", "").replace(" = ", "").replace(value, "").strip()
        ctx.context.var_map[name] = type_token
        ctx.context.pre_entry += parse_var(name, type_token, value.strip())

    # ==== MEMORY ====
    elif line.startswith("*"):
        # *(MEM_ADDR): TYPE = VALUE
        # ->
        # %ptrX = inttoptr i64 MEM_ADDR to i32*
        # store TYPE VALUE, TYPE* MEM_ADDR
        line = line.replace("*", "").replace("(", "").replace(")", "").replace(" = ", " ").replace(":", "").strip()
        # line: [MEM_ADDR, TYPE, VALUE]
        toks = line.split(" ")
        mem.HandleMem_Write(toks, scope)

    else:
        errors.err(f"Unrecognized line: {line}")

def parse_line_tool(line: str, scope: str = "Vmain"):
    global Pscope
    if scope != Pscope: print(f"============================= SCOPE CNAHGE +++++++++++++++++\n{Pscope} -> {scope}\n")
    Pscope = scope

    # remove the first space
    if line.startswith(" "): line = joinchars(chars(line)[1:])
    if ctx.context.asm_mode:
        # # call void asm sideeffect inteldialect "mov eax, 1", ""
        if line.__contains__("#"):
            pass
        else:
            return f"    call void asm sideeffect {ctx.context.asm_dialect} \"{line.strip()}\", \"\"\n"

    elif line.strip().startswith("ASM:"):
        ctx.context.asm_mode = True

    elif line.strip().startswith("asmend:"):
        ctx.context.asm_mode = False

    elif line.strip().startswith("return"):
        scope = ctx.context.current_function

        # Extract text after "return"
        parts = line.strip().split(None, 1)

        # Look up current function return type
        func, _ = ctx.context.functions[ctx.context.current_function]
        ret_type = func.ret_type.strip()

        # Case 1: bare "return"
        if len(parts) == 1:
            # Expect void return
            if ret_type == "void": return "  ret void\n", scope
            else: errors.err(f"Function {scope} must return {ret_type}, but got empty return")
            return "\n; error here with return"

        # Case 2: "return VALUE"
        value = parts[1].strip()

        # If the return type is void but user returned something
        if ret_type == "void": errors.err(f"Function {scope} returns void but got: return {value}")

        # Emit typed return
        return f"  ret {ret_type} {value}\n"



    # === ctx.context.functions ===
    elif re.match(r'^\s*(\w+)\s*\((.*)\)\s*$', line.strip()):

        return parseFunctionCallS(line)

    elif line.strip().startswith("using "):
        # using NAME = TYPE
        toks = line.split(" ")
        ctx.context.aliases[toks[1]] = toks[3]

    # === DEBUG ===
    elif line.strip().startswith("ctime_print"):
        toks = line.replace("\"", "").strip().split(" ")
        toprint = parse_debug_print(toks)
        print(toprint)

    # ==== IMPORTS ====
    elif line.strip().startswith("lib"):
        # lib dyn|static <LIB_NAME>|"LIB_NAME"
        toks = line.split(" ")
        if toks[1] == "dyn":
            _libs_.HandleDynLib(toks[2], scope)
        elif toks[1] == "static":
            _libs_.HandleStaticLib(toks[2], scope)
        else:
            errors.err(f"Unknown lib type '{toks[1]}'")

    elif line.strip().startswith("dyn_import fn ") and line.endswith("."):
        ctx.context.pre_entry += parseDynImport(line)

    elif line.strip().startswith("dyn_import fn "):
        ctx.context.in_dyn_fn_import = True
        ctx.context.current_dyn_fn_import = line.strip().replace("  ", "")

    elif ctx.context.in_dyn_fn_import:
        ctx.context.current_dyn_fn_import += line.strip().replace("  ", "")
        if line.endswith("."):
            ctx.context.pre_entry += parseDynImport(ctx.context.current_dyn_fn_import)
            ctx.context.in_dyn_fn_import = False
            ctx.context.current_dyn_fn_import = ""
            
    elif line.strip().startswith("dyn_import "):
        ctx.context.pre_entry += parseDynImport(line)


    # ==== LABELS AND GOTOs ====
    
    elif line.startswith("lb "):
        label_name = line.strip()[3:].strip()
        return f"  br label %{label_name}\n{label_name}:\n"
        
    elif line.strip().startswith("goto "):
        label_name = line.strip()[5:].strip()
        return f"  br label %{label_name}\n"

    # ==== CONST AND VAR DECLARATIONS ====
    elif line.strip().startswith("const "):
        # const NAME: TYPE = VALUE
        line_fixed = re.sub(r'(\b\w+):', r'\1 :', line)
        toks = line_fixed.strip().split(" ")
        # format: var NAME : TYPE = VALUE
        name = toks[1].split(":")[0]
        colon = toks[2]
        value = utils.GetAssignValue(toks)
        match = re.search(r':\s*(.*?)\s*=', line)
        type_token = ""
        if match: type_token = match.group(1)
        res = parse_const(name, type_token, value.strip())
        ctx.context.pre_entry += res

    elif line.strip().startswith("var "):
        toks = line.strip().replace(":", " : ").replace(" :  ", " : ").split(" ")
        # format: var NAME : TYPE = VALUE
        name = toks[1].split(":")[0]
        colon = toks[2]
        value = utils.GetAssignValue(toks)
        type_token = line.replace(colon, "").replace(f"var {name}", "").replace(" = ", "").replace(value, "").strip()
        ctx.context.var_map[name] = type_token
        ctx.context.pre_entry += parse_var(name, type_token, value.strip())

    # ==== MEMORY ====
    elif line.startswith("*"):
        # *(MEM_ADDR): TYPE = VALUE
        # ->
        # %ptrX = inttoptr i64 MEM_ADDR to i32*
        # store TYPE VALUE, TYPE* MEM_ADDR
        line = line.replace("*", "").replace("(", "").replace(")", "").replace(" = ", " ").replace(":", "").strip()
        # line: [MEM_ADDR, TYPE, VALUE]
        toks = line.split(" ")
        mem.HandleMem_Write(toks, scope)

    else:
        errors.err(f"Unrecognized line: {line}")
