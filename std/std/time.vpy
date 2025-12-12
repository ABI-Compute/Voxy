lib dyn <kernel32.dll>

dyn_import fn void Sleep(dwMilliseconds: uint).

fn void t_sleep(ms: uint):
    Sleep(ms)
endfn
