; linux_runtime.asm
; Minimal NASM runtime for Linux x64, no libc
; Expects Vmain to return an int in RAX

global _start
extern Vmain

section .text
_start:
    ; Call Vmain
    call Vmain

    ; Exit with Vmain return value
    mov rdi, rax       ; exit code in RDI
    mov rax, 60        ; syscall number for exit
    syscall
