# ============================================================= #
# VOX STANDARD LIBRARY (Vstdl) c Calam 2025                     #
# This is the Vox standard library module for basic GUI         #
# tasks like Popups, Opening windows, low levl event loops, etc #
# Currently under development                                   #
# ============================================================= #


lib dyn <user32>

dyn_import fn void MessageBoxA(
    hWnd: int,
    message: buff,
    Title: buff,
    setting: int
)

dyn_import fn void MessageBoxW(
    hWnd: int,
    message: buff,
    Title: buff,
    setting: int
)

dyn_import fn int CreateWindowExA(
    dwExStyle: int,
    lpClassName: buff,
    lpWindowName: buff,
    dwStyle: int,
    x: int,
    y: int,
    wWidth: int,
    wHeight: int,
    hWnd: int,
    hMenu: int,
    hInstance: int,
    lpParam: int
)

template GLuint = [v: uint8]
const my_gluint: GLuint = [1]


dyn_import fn void RegisterClassA(cls: buff)

const WS_OVERLAPPEDWINDOW: int = 13565952

const MB_OK: int = 0

const simp_win: buff[uint8; 33] = [83,105,109,112,108,101,87,105,110,100,111,119,0, 222,173,190,239,202,254,186,190, 97,114,114,111,119,0, 119,104,105,116,101,0]      
RegisterClassA(simp_win)
const sm: buff[char; 50] = "SimpleWindow"

fn void TxtPopup(msg: buff, Title: buff):
    MessageBoxA(null, msg, Title, MB_OK)
fnend

fn void UniPopup(msg: buff, Title: buff):
    MessageBoxW(null, msg, Title, MB_OK)
fnend

fn int NewWindow(Title: buff, Width: int, Length: int):
    return CreateWindowExA(0, sm, Title, WS_OVERLAPPEDWINDOW, 0, 0, Width, Length, null, null, 0, 0)
fnend