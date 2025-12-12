# ============================================================ #
# VOX STANDARD LIBRARY (Vstdl) c Calam 2025                    #
# This is the Vox standard library module for basic I/O        #
# tasks like stdout, stdin, stderr, etc                        #
# Currently under development                                  #
# =============================================================#


lib dyn <kernel32.dll>

const STD_OUTPUT_HANDLE: int = -11
const STD_INPUT_HANDLE: int = -10



using LPCSTR = ptr[buff[char]]

dyn_import fn void ExitProcess(code: int)
dyn_import fn int64 GetStdHandle(a: int).
dyn_import fn bool WriteConsoleA(
    hConsole: int64,
    lpBuffer: LPCSTR,
    nNumberOfCharsToWrite: int,
    lpNumberOfCharsWritten: ptr[int],
    lpReserved: LPCSTR
).
dyn_import fn LPCSTR GetCommandLineA().
dyn_import fn bool ReadConsoleA(
    hConsole: int64,
    lpBuffer: LPCSTR,
    nNumberOfCharsToRead: int,
    lpNumberOfCharsRead: ptr[int],
    pInputControl: int
).
dyn_import fn int lstrlenA(a: LPCSTR).


const stdout: int64 = GetStdHandle(STD_OUTPUT_HANDLE)
const stdin: int64 = GetStdHandle(STD_INPUT_HANDLE)
var written: int = 0
var read: int = 0

namespace cmd:

fn void echo(message: LPCSTR):
    const len: int = lstrlenA(message)
    WriteConsoleA(stdout, message, len, addr written, null)
    return
endfn

fn void input(in: LPCSTR, len: int):
    ReadConsoleA(stdin, in, len, addr read, null)
    return
endfn

fn void exit(code: int):
    ExitProcess(code)
    return
endfn

fn char GetChar():
    var x: char = 0
    input(addr x, 1)
    return x
endfn

fn void err(msg: LPCSTR, code: int):
    echo(msg)
    GetChar()
    exit(code)
endfn

nmend

# end of io.vpy