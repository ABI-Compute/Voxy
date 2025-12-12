; Robust Windows x64 entry point
; Calls Vmain safely with proper stack setup
; Exits using ExitProcess with Vmain's return code

global _start
extern Vmain
extern ExitProcess
extern FreeConsole
extern SetConsoleCtrlHandler

section .text
_start:
    ; -----------------------------
    ; Step 1: Align stack and reserve shadow space
    ; Windows x64 requires 32 bytes shadow space for called functions
    ; plus ensure 16-byte alignment for the call instruction
    ; -----------------------------
    sub rsp, 40            ; 32 bytes shadow + 8 bytes to align RSP to 16 mod 16

    ; -----------------------------
    ; Step 2: Call user main
    ; -----------------------------
    call Vmain             ; return value in RAX

    ; -----------------------------
    ; Step 3: Exit cleanly
    ; -----------------------------
    mov rcx, rax           ; ExitProcess(exit_code)
    call ExitProcess

    ; -----------------------------
    ; Step 4: Restore stack (optional, unreachable)
    ; -----------------------------
    add rsp, 40
    ret
