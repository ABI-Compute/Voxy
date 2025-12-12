import compiler_modules.ctx as ctx
import os
import sys
import platform
import re
import compiler_modules.errors as errors
import json

# -------------------------
# Operating System
# -------------------------
if os.name == "nt":
    ctx.context.ifdef_defs.append("WIN32")
elif os.name == "posix":
    if 'darwin' in sys.platform:   
        ctx.context.ifdef_defs.append("MAC")
    else:
        ctx.context.ifdef_defs.append("LINUX")
elif os.name == "sunos":
    ctx.context.ifdef_defs.append("SOLARIS")
elif os.name.startswith("bsd"):
    ctx.context.ifdef_defs.append("BSD")

# -------------------------
# CPU Architecture
# -------------------------
arch = platform.machine().lower()
if 'x86_64' in arch or 'amd64' in arch:
    ctx.context.ifdef_defs.append("X86_64")
elif 'arm' in arch or 'aarch64' in arch:
    ctx.context.ifdef_defs.append("ARM")
elif 'i386' in arch or 'i686' in arch:
    ctx.context.ifdef_defs.append("X86")
elif 'ppc' in arch or 'powerpc' in arch:
    ctx.context.ifdef_defs.append("PPC")

# -------------------------
# Endianness
# -------------------------
if sys.byteorder == "little":
    ctx.context.ifdef_defs.append("LITTLE_ENDIAN")
else:
    ctx.context.ifdef_defs.append("BIG_ENDIAN")

# -------------------------
# Optional: Python version
# (or any other runtime/library version)
# -------------------------
py_major = sys.version_info.major
py_minor = sys.version_info.minor
ctx.context.ifdef_defs.append(f"PYTHON_{py_major}_{py_minor}")

print(ctx.context.ifdef_defs)

def remove_comments(line: str) -> str:
    """Remove comments from a line."""
    comment_re = re.compile(r'#.*')
    return comment_re.sub('', line)

def read_file(path: str) -> str:
    """Read a file and return its content."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        errors.err(f"Module '{path}' not found.")
        return ""

def process_global_import(module_name: str) -> str:
    """Process a global import by reading from vox_path.json paths."""
    try:
        with open("vox_path.json", "r", encoding="utf-8") as pf:
            paths = json.load(pf)
    except FileNotFoundError:
        errors.err("vox_path.json not found.")
        return ""

    final_code = ""
    for path in paths:
        full_path = os.path.join(path, module_name)
        code = read_file(full_path)
        if code:
            final_code += PreProcess(code) + "\n"
    return final_code

def process_local_import(module_name: str) -> str:
    """Process a local import by reading the file directly."""
    code = read_file(module_name)
    return PreProcess(code) + "\n" if code else ""

def HLocalPre(lines_no_comments, lpc, m_local, m_global):
    final = ""
    in_ifdef = False
    if lines_no_comments[lpc - 1].startswith("d_if"):
        in_ifdef = True
    elif lines_no_comments[lpc - 1].startswith("d_endif"):
        in_ifdef = False
    if in_ifdef:
        # resolve ifdef
        while lpc < len(lines_no_comments) and not lines_no_comments[lpc].startswith("d_endif"):
            ifdef_line = lines_no_comments[lpc]
        condition = ifdef_line.replace(":", "").split(" ")[1]
        if handle_ifdef(condition):
            final += process_local_import(m_global.group(1))
            lpc += 1
    else:
        final += process_local_import(m_local.group(1))
        lpc += 1

    return final

def HGlobalPre(lines_no_comments, lpc, m_global):
    final = ""
    in_ifdef = False
    if lines_no_comments[lpc - 1].startswith("d_if"):
        in_ifdef = True
    elif lines_no_comments[lpc - 1].startswith("d_endif"):
        in_ifdef = False
    if in_ifdef:
        # resolve ifdef
        while lpc < len(lines_no_comments) and not lines_no_comments[lpc].startswith("d_endif"):
            ifdef_line = lines_no_comments[lpc]
        condition = ifdef_line.replace(":", "").split(" ")[1]
        if handle_ifdef(condition):
            final += process_global_import(m_global.group(1))
            lpc += 1
    else:
        final += process_global_import(m_global.group(1))
        lpc += 1

    return final

def get_ifdef_condition(tokens: list) -> str:
    ret = ""
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if i == 0:
            i += 1
        else:
            ret += tok
            i += 1

    return ret

def PreProcess(code: str) -> str:
    final = ""
    
    # Remove comments first
    lines_no_comments = [remove_comments(line) for line in code.splitlines()]
    in_ifdef = False
    # Compile regexes once
    import_re_global = re.compile(r'import\s+<([\w\d_.-]+)>')
    import_re_local = re.compile(r'import\s+"([\w\d_.-]+)"')
    lpc = 0
    while lpc < len(lines_no_comments):
        line = lines_no_comments[lpc]
        stripped = line.strip()
        m_global = import_re_global.match(stripped)
        m_local = import_re_local.match(stripped)

        if m_global:
            final += HGlobalPre(lines_no_comments, lpc, m_global)
            lpc += 1
        elif m_local:
            final += HLocalPre(lines_no_comments, lpc, m_local, m_global)
            lpc += 1
        elif stripped.startswith("d_if") or stripped.startswith("d_elif"):
            in_ifdef = True
            condition = get_ifdef_condition(stripped.replace(":", "").split(" "))
            lpc += 1
        elif stripped.startswith("d_endif"):
            in_ifdef = False
            lpc += 1

        elif stripped.startswith("d_else") and not handle_ifdef(condition):
            final += lines_no_comments[lpc] + "\n"
            lpc += 1
            

        if in_ifdef and handle_ifdef(condition):
            final += lines_no_comments[lpc] + "\n"
            lpc += 1

        elif not in_ifdef and lpc < len(lines_no_comments):
            final += lines_no_comments[lpc] + "\n"
            lpc += 1

        else:
            lpc += 1
        
    return final
 
def handle_ifdef(condition: str) -> bool:
    return condition in ctx.context.ifdef_defs
