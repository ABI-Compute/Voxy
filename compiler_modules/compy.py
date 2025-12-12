import regex as re
import sys
import compiler_modules.consts as consts
import compiler_modules._types_ as _types_
import compiler_modules.ctx as ctx
import compiler_modules.preproc as preproc
import compiler_modules.structs as structs
import compiler_modules.functions as functions
import compiler_modules.parsing as parsing
import compiler_modules.errors as errors
import compiler_modules.utils as utils


def get_temp_fn_store():   # generate unique function call label
    global fn_call_num
    ctx.context.fn_call_num += 1
    return f"fn_call_{ctx.context.fn_call_num}"


def Get_tmp_ptr():
    global ptr_count
    ctx.context.ptr_count += 1
    return f"%ptr{ctx.context.ptr_count}"

dll_to_lib = {
    "kernel32.dll": "kernel32",
    "user32.dll": "user32",
    "opengl32.dll": "opengl32"
}

def DLL_AS_LIB(dll: str):    # dll -> lib name
    return dll_to_lib.get(dll.lower(), dll.replace(".dll", ""))

tmp_var_count = 0

def tmp_var():
    """Generate a unique temporary variable name."""
    global tmp_var_count
    tmp_var_count += 1
    return f"%t{tmp_var_count}"

def getArgs(toks: list[str]):
    args = {}
    # Clean tokens: remove empty strings and stray ':' tokens
    cleaned = [t for t in toks if t is not None and t.strip() != '' and t != ':']
    # Expect cleaned layout: [RET_TYPE, FUNC_NAME, ARG1_NAME, ARG1_TYPE, ARG2_NAME, ARG2_TYPE, ...]
    for i in range(2, len(cleaned), 2):
        name = cleaned[i]
        if i + 1 < len(cleaned):
            typ = cleaned[i + 1]
            args[name] = typ
        else:
            errors.FATAL("Missing type for argument")
    return args

import re

if_num = 0

def AddToCurrent(code: str):
    utils.AddToScope(code, ctx.context.current_function)

def Handle_IF(code: str):
    # if CONDITON:
    #     BODY
    # elif CONDITION:
    #     BODY
    # else:
    #     BODY
    # endif
    #
    # into...
    #
    # br i1 %CONDITON, label %if{if_num}, label %else{ifnum} | %elif{if_num}
    global if_num
    lines = code.splitlines()
    has_elif = False
    has_else = False
    num_of_elif = 0
    if "elif" in code: has_elif = True
    if "else" in code: has_else = True
    if has_elif: num_of_elif = code.count("elif")
    elif_rest = num_of_elif
    cond_pattern = r"^(?:if|elif)\s+(.*?)\s*:"
    seen_if = False
    seen_endif = False
    for line in lines:

        if line.strip().startswith("elif "):
            elif_rest -= 1
            is_cond = re.search(cond_pattern, line)
            cond = ""
            if is_cond: cond = is_cond.group(1)
            cond = _types_.handle_bool_expr(cond)
            AddToCurrent(f" br label %endif{if_num}\ncheck_elif{if_num}_{elif_rest+1}:\n")
            if elif_rest != 0: AddToCurrent(f"  br i1 {cond}, label %elif{if_num}_{elif_rest}, label %check_elif{if_num}_{elif_rest}\n")
            elif has_else: AddToCurrent(f"  br i1 {cond}, label %elif{if_num}_{elif_rest}, label %else{if_num}\n")
            else: AddToCurrent(f"   br i1 {cond}, label %if{if_num}, label %endif{if_num}\n")
            AddToCurrent(f"elif{if_num}_{elif_rest}:\n")
        elif line.strip().startswith("if ") and not seen_if:
            seen_if = True
            is_cond = re.search(cond_pattern, line)
            cond = ""
            if is_cond: cond = is_cond.group(1)
            cond = _types_.handle_bool_expr(cond)
            if has_elif: AddToCurrent(f"    br i1 {cond}, label %if{if_num}, label %check_elif{if_num}_{elif_rest}\n")
            elif not has_else: AddToCurrent(f"  br i1 {cond}, label %if{if_num}, label %endif{if_num}\n")
            else: AddToCurrent(f"   br i1 {cond}, label %if{if_num}, label %else{if_num}\n")
            AddToCurrent(f"if{if_num}:\n")
        elif line.strip().startswith(f"else:"):
            AddToCurrent(f"    br label %endif{if_num}\nelse{if_num}:\n")
        elif line.strip().startswith("endif "):
            seen_endif = True
            AddToCurrent(f"    br label %endif{if_num}\nendif{if_num}:\n")
            return
        else:
            code_ = parsing.parse_line_tool(line)
            if not code_ is None and code != "": AddToCurrent(code_ + "\n")
    if not seen_endif: AddToCurrent(f"    br label %endif{if_num}\nendif{if_num}:\n")
    return




def generate_ir(code: str, ll_path: str, save: bool):
    instruct = False
    struct_content = ""
    lines = code.splitlines()
    pc = 0
    struct_name = ""
    funtion_name = ""
    ret_type = ""
    args = {}
    in_func = False
    func_body_current = ""
    in_if = False
    if_body_current = ""
    while pc < len(lines):
        ctx.context.lineN = pc + 1
        ctx.context.line_content = lines[pc]
        line = lines[pc]

        if line.strip().startswith("endif"):
            if_body_current += line.strip().replace("    ", "") + "\n"
            pc += 1

            Handle_IF(if_body_current)
            if_body_current = ""
            in_if = False

        elif in_if:
            if_body_current += line.strip().replace("    ", "") + "\n"
            pc += 1
        
        elif line.strip() == "":
            pc += 1

        elif line.strip().endswith("endfn"):
            ctx.context.functions[funtion_name] = [functions.Funtion(funtion_name, args=args, ret_type=ret_type, body=func_body_current), False]
            ctx.context.functions[funtion_name][0].COOK()
            func_body_current = ""
            in_func = False
            pc += 1

        elif in_func:
            func_body_current += line.strip().replace("    ", "") + "\n"
            pc += 1

        
        elif line.strip().startswith("unsafe"):
            ctx.context.unsafe_mode = True
            pc += 1
        elif line.strip().startswith("safe"):
            ctx.context.unsafe_mode = False
            pc += 1
        elif line.strip().startswith("#"):
            pc += 1
        elif line.strip().startswith("d_if") or line.strip().startswith("d_elif") or line.strip().startswith("d_endif") or line.strip().startswith("d_else"):
            pc += 1
            # ==== STRUCTS ====
        elif line.strip().startswith("struct "):
            # syntax:
            # struct StructName:
            #     field1: type1,
            #     field2: type2,
            #     ...
            # endstruct
            #
            # turns into... 
            #
            # %StructName = type { type1, type2, ... }
            toks = line.strip().split(" ")
            struct_name = toks[1].replace(":", "").strip()
            instruct = True
            pc += 1

            struct_content = f"%{struct_name} = type {{ "
        elif line.strip().startswith("endstruct"):
            struct_content = struct_content.replace("{  ,", "{ ") + " }\n"
            ctx.context.pre_entry += struct_content
            ctx.context.structs[struct_name] = structs.llvm_struct_to_Vox_struct(struct_content)
            instruct = False
            pc += 1

        elif instruct:
            regex_to_strip = re.compile("\\s*([A-Za-z]+): ")
            type_ = _types_.llvm_numbers[regex_to_strip.sub("", line).replace(",", "").strip()]
            struct_content += f" ,{type_}"
            pc += 1

        # === FUNCTION DEFINITIONS ===
        elif line.strip().startswith("fn "):
            # syntax:
            # fn RET_TYPE FUNC_NAME(ARG1_NAME: ARG1_TYPE, ARG2_NAME: ARG2_TYPE, ...):
            #     body
            # endfn
            #
            # turns into...
            #
            # define i32 @FUNC_NAME(ARG1_TYPE ARG1_NAME, ARG2_TYPE ARG2_NAME, ...) {
            #     body
            # }
            toks = line.strip().replace("fn ", "").replace("(", " ").replace(")", " ").replace(":", " ").replace(",", "").split(" ")
            # toks => RET_TYPE FUNC_NAME ARG1_NAME ARG1_TYPE ARG2_NAME ARG2_TYPE ...
            funtion_name = toks[1]
            ret_type = toks[0]
            args = getArgs(toks)
            in_func = True
            pc += 1

        # ======= if  ====== #
        elif line.strip().startswith("if "):
            in_if = True
            if_body_current += line.strip().replace("    ", "") + "\n"

            
        else:
            parsing.parse_line(line)
            pc += 1

    if not ctx.context.has_errors:
        with open(ll_path, "w", encoding="utf-8") as f:
            f.write(ctx.context.imports)
            f.write(ctx.context.pre_entry)
            f.write(ctx.context.Vmain_header)
            f.write(ctx.context.Vmain)
            f.write(ctx.context.Vmain_exit)
        functions.write_functions(ll_path)
        print(f"Generated LLVM IR at '{ll_path}'")
        print(f"{ctx.context.Vmain_header}{ctx.context.Vmain}{ctx.context.Vmain_exit}")
    else:
        print(f"{consts.RED_ESCAPE}Aborting due to errors{consts.RESET_ESCAPE}")
        sys.exit(1)
        

def compile(code: str, output_obj: str, mode: str, os: str, dialect: str = "inteldialect"):
    """
    Top-level compile: generate IR, run llc to get object, and return ctx.context.libs_to_link for the caller
    to perform linking (so you can link against kernel32/user32 etc without libc).
    - output_obj should be a path like 'main.obj' or 'main.o' depending on your platform.
    - mode and os_target are preserved for compatibility but not assumed by this generator.
    """
    global asm_dialect
    asm_dialect = dialect
    print("Compiling...")
    # produce .ll path adjacent to output_obj
    if output_obj.endswith(".o") or output_obj.endswith(".obj"):
        ll_path = output_obj.rsplit(".",1)[0] + ".ll"
    else:
        ll_path = output_obj + ".ll"
    generate_ir(preproc.PreProcess(code), ll_path, save=True)
    return ctx.context.libs_to_link

