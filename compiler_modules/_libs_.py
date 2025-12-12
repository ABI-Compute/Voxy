import compiler_modules.ctx as ctx
import os
import subprocess as sub
import tempfile

def remove_ext(filename: str) -> str:
    return filename.split(".")[0]
    
def dyn_to_static(lib_name: str, mingw: bool = False):
    # GOAL: **.dll|**.so -> **.lib|**.a
    raw = remove_ext(lib_name)
    if os.name == "nt":
        if mingw:
            return raw + ".a"
        else:
            return raw + ".lib"
    else:
        return raw + ".a"

def HandleStaticLib(lib_name: str, scope: str):
    if lib_name.startswith("\""):
        lib_name = lib_name.replace("\"", "")
        ctx.context.libs_to_link.append(remove_ext(lib_name))
    elif lib_name.startswith("<"):
        lib_name = lib_name.replace("<", "")
        lib_name = lib_name.replace(">", "")
        ctx.context.libs_to_link.append(remove_ext(lib_name))

def get_exports_from_dll(dll_path):
    """Return list of exported symbols from a DLL using dumpbin."""
    result = sub.run(["dumpbin", "/EXPORTS", dll_path],
                            capture_output=True, text=True, check=True)
    exports = []
    for line in result.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) >= 4 and parts[0].isdigit():
            exports.append(parts[-1])
    return exports

def generate_stub_lib(dll_path, output_lib=None):
    """Generate a stub .lib from a DLL (Windows)."""
    if not os.path.isfile(dll_path):
        raise FileNotFoundError(f"DLL not found: {dll_path}")

    dll_name = os.path.splitext(os.path.basename(dll_path))[0]
    if output_lib is None:
        output_lib = os.path.join(os.path.dirname(dll_path), f"{dll_name}.lib")

    exports = get_exports_from_dll(dll_path)
    if not exports:
        raise RuntimeError("No exported symbols found in the DLL.")

    def_file = os.path.join(os.path.dirname(dll_path), f"{dll_name}.def")
    with open(def_file, "w") as f:
        f.write(f"LIBRARY {dll_name}\nEXPORTS\n")
        for sym in exports:
            f.write(f"{sym}\n")

    sub.run(["lib", f"/DEF:{def_file}", f"/OUT:{output_lib}"], check=True)
    return output_lib

def get_exports_from_so(so_path):
    """Return list of exported symbols from a .so file using nm."""
    result = sub.run(["nm", "-D", "--defined-only", so_path],
                    capture_output=True, text=True, check=True)
    symbols = []
    for line in result.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) == 3:
            _, type_char, name = parts
        if type_char.upper() in ("T", "D", "B", "R") and len(parts) == 3:
            symbols.append(name)
    return symbols

def generate_stub_a(so_path, output_a=None):
    """Generate a stub .a from a .so (Linux)."""
    if not os.path.isfile(so_path):
        raise FileNotFoundError(f"Shared library not found: {so_path}")

    so_name = os.path.splitext(os.path.basename(so_path))[0]
    if output_a is None:
        output_a = os.path.join(os.path.dirname(so_path), f"lib{so_name}.a")

    symbols = get_exports_from_so(so_path)
    if not symbols:
        raise RuntimeError("No exported symbols found in the .so file.")

    with tempfile.TemporaryDirectory() as tmpdir:
        stub_c = os.path.join(tmpdir, "stub.c")
        f = open(stub_c, "w")
        f.write("#include <stdio.h>\n")
        for sym in symbols:
            f.write(f"void {sym}() {{}}\n")
        f.close()

        obj_file = os.path.join(tmpdir, "stub.o")
        sub.run(["gcc", "-fPIC", "-c", stub_c, "-o", obj_file], check=True)
        sub.run(["ar", "rcs", output_a, obj_file], check=True)

    return output_a

def MakeLib(lib_name: str):
    cwd = os.getcwd()
    if lib_name.endswith(".dll"):
        generate_stub_lib(cwd + "/" + lib_name, cwd + "/" + dyn_to_static(lib_name, True))
    else:
        generate_stub_a(cwd + "/" + lib_name, cwd + "/" + dyn_to_static(lib_name))

def HandleDynLib(lib_name: str, scope: str):
    cwd = os.getcwd()

    if lib_name.startswith("\""):
        lib_name = lib_name.replace("\"", "")
        if os.path.exists(cwd + "/" + dyn_to_static(lib_name)):
            ctx.context.libs_to_link.append(remove_ext(lib_name))
        else:
            MakeLib(lib_name)
            ctx.context.libs_to_link.append(remove_ext(lib_name))
    elif lib_name.startswith("<"):
        lib_name = lib_name.replace("<", "")
        lib_name = lib_name.replace(">", "")
        ctx.context.libs_to_link.append(remove_ext(lib_name))

