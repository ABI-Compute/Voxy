class DefStack:
    def __init__(self):
        self.stack = []

    def push(self, item):
        self.stack.append(item)

    def pop(self):
        return self.stack.pop()
    
    def peek(self):
        if len(self.stack) == 0:
            return None
        return self.stack[-1]

class CompilerContext:
    def __init__(self):
        self.const_map = {}  # name: [type, value]
        self.var_map = {}  # name: type
        self.functions = {}  # name: [Funtion, is_extern]
        self.libs_to_link = []  #
        self.Vmain = ""  #
        self.pre_entry = ""  #
        self.asm_mode = False  #
        self.unsafe_mode = False  #
        self.lineN = 0  #
        self.line_content = ""  #
        self.ifdef_defs = []  #
        self.fn_call_num = 0
        self.ptr_count = 0  #
        self.has_errors = False  #
        self.exit_code = 0  #
        self.imports = ""  #
        self.Vmain_exit = "\n  ret i32 0\n}\n"  #
        self.Vmain_header = "define i32 @Vmain( ) {\nentry:\n"  #
        self.asm_dialect = ""  #
        self.current_function = None  ## None => in Vmain scope
        self.structs = {}  ## name: VoxStruct
        self.aliases = {}  ## name: Type
        self.in_dyn_fn_import = False
        self.current_dyn_fn_import = ""
        self.def_stack = DefStack()
        self.current_PRE = ""
        self.if_num = 0

context = CompilerContext()
_llvm_id_counter = 0
