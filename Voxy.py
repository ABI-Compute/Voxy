# Vox.py
import sys
import subprocess as sub
import compiler_modules.compy as c
import shutil
import platform
import os
import shlex

def cmd(cmd):
    command = shlex.split(cmd)
    sub.run(command, check=True)


user_objs = []

# --- Argument parsing ---
if len(sys.argv) < 3:
    print("Usage: Vox.py [-c|-r|-v] <file> [-os <OS>] [-o <output>] [-arch <32|64>]")
    sys.exit(1)

debug = False

flag = sys.argv[1]
file = sys.argv[2]

if flag == "-c":
    mode = "CO"
elif flag == "-r":
    mode = "CNR"
elif flag == "-v":
    mode = "VER"
elif flag == "-help":
    print("Usage: Vox.py [-c|-r|-v] <file> [-os <OS>] [--noconsole] [--debug] [-o <output>] [-arch <32|64>]")
    sys.exit(0)
elif flag == "-version":
    print("Verion 0.0.1 by Calam")
    sys.exit(0)
elif flag == "-n":
    mode = "Norm"
elif flag == "-a":
    # Allow adding a path as the primary action: Vox.py -a <path>
    if len(sys.argv) < 3:
        print("Usage: Vox.py -a <path-to-add>")
        sys.exit(1)
    add_path = sys.argv[2]
    import json, os
    vox_path_file = os.path.join(os.getcwd(), 'vox_path.json')
    try:
        if os.path.exists(vox_path_file):
            with open(vox_path_file, 'r', encoding='utf-8') as vf:
                paths = json.load(vf)
        else:
            paths = []
    except Exception:
        paths = []
    add_path_norm = os.path.abspath(add_path)
    if add_path_norm not in paths:
        paths.append(add_path_norm)
        with open(vox_path_file + '.tmp', 'w', encoding='utf-8') as tf:
            json.dump(paths, tf, indent=2)
        os.replace(vox_path_file + '.tmp', vox_path_file)
    print(f"Added '{add_path_norm}' to vox_path.json")
    sys.exit(0)
else:
    print("Invalid flag!")
    sys.exit(1)

# --- Optional OS, output, architecture ---
OS = "win" if sys.platform.startswith("win") else sys.platform
output = "main"
arch = "64"  # default to 64-bit
cons = True

# Parse extra arguments
for i in range(3, len(sys.argv)):
    if sys.argv[i] == "-os" and i+1 < len(sys.argv):
        OS = sys.argv[i+1].lower()
    elif sys.argv[i] == "-o" and i+1 < len(sys.argv):
        output = sys.argv[i+1]
    elif sys.argv[i] == "-arch" and i+1 < len(sys.argv):
        arch = sys.argv[i+1]
    elif sys.argv[i] == "--noconsole":
        cons = False
    elif sys.argv[i] == "-a" and i+1 < len(sys.argv):
        # add path to vox_path.json
        add_path = sys.argv[i+1]
        import json, os
        vox_path_file = os.path.join(os.getcwd(), 'vox_path.json')
        try:
            if os.path.exists(vox_path_file):
                with open(vox_path_file, 'r', encoding='utf-8') as vf:
                    paths = json.load(vf)
            else:
                paths = []
        except Exception:
            paths = []
        # normalize and append if not present
        add_path_norm = os.path.abspath(add_path)
        if add_path_norm not in paths:
            paths.append(add_path_norm)
            with open(vox_path_file + '.tmp', 'w', encoding='utf-8') as tf:
                json.dump(paths, tf, indent=2)
            os.replace(vox_path_file + '.tmp', vox_path_file)
        print(f"Added '{add_path_norm}' to vox_path.json")
        sys.exit(0)
    elif flag == "--debug" and i+1 < len(sys.argv):
        debug = True

    elif flag.endswith(".o") and i+1 < len(sys.argv):
        user_objs.append(sys.argv[i+1])

    elif flag.endswith(".obj") and i+1 < len(sys.argv):
        user_objs.append(sys.argv[i+1])
   

# --- Read and compile ---
with open(file, "r") as f:
    code = f.read()

asm_file = output[:-4] + ".asm"
deps = c.compile(code, asm_file, mode, os=OS)

def readfile(path: str):
    with open(path, "r") as f:
        return f.read()

def writefile(path: str, content: str):
    with open(path, "w") as f:
        f.write(content)

ofile = output[:-4] + ".o"
code = readfile(asm_file + ".ll")

final_ir = f"source_filename = \"{sys.argv[2]}\"\n" + code 
writefile(asm_file + ".ll", final_ir)

if mode == "CO":
    sys.exit(0)

# ---- Assemble & link ----
print(f"OS: {OS}, output: {output}, arch: {arch}")
if OS.startswith("win"):
    # prefer explicit llc path if available (shutil.which may find it)
    llc_exe = shutil.which("llc") or r"C:\\llvm\\bin\\llc.exe"
    if llc_exe and os.path.exists(llc_exe):
        sub.run([llc_exe, "-filetype=obj", "-march=x86-64", "-mtriple=x86_64-w64-mingw32", asm_file + '.ll', "-o", ofile], check=True)
    else:
        # fallback to shell-split invocation (will raise FileNotFoundError if not found)
        cmd(f"llc -filetype=obj -march=x86-64 -mtriple=x86_64-w64-mingw32 {asm_file + '.ll'} -o {ofile}")
    if not output.endswith(".exe"):
        output += ".exe"
    pre = f"ld {ofile} std/VRT_win.a -LC:/Strawberry/c/x86_64-w64-mingw32/lib -lkernel32 -luser32 -e _start"  # include essential libraries here
    deps_sect = " ".join(f"-l{dep}" for dep in deps if dep)     # avoids empty strings
    for dep in user_objs:
        deps_sect += f" {dep}"
    full_cmd = f"{pre} {deps_sect} -o {output}"

    if not cons:
        full_cmd += " --subsystem windows"
    if debug:
        full_cmd += " -g"
        
    cmd(full_cmd)

else:
    cmd(f"llc -filetype=obj -march=x86-64 {asm_file + '.ll'} -o {ofile}")
    pre = f"ld {ofile} std/VRT_linux.a"
    deps_sect = ""
    for dep in deps:
        deps_sect += f" -l{dep}"
    for dep in user_objs:
        deps_sect += f" {dep}"
    cmd(f"{pre} {deps_sect} -o {output} -e _start")