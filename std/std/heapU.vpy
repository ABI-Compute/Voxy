# DO NOT USE THIS FILE IN ANY WAY. USE mem.vpy INSTEAD

lib dyn <kernel32.dll>

dyn_import fn int GetProcessHeap()
dyn_import fn intptr HeapAlloc(
    hWnd: int,
    
)
