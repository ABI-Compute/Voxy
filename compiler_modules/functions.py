import compiler_modules.ctx as ctx
import compiler_modules.parsing as parsing
import compiler_modules._types_ as _types_

class Funtion:
    def __init__(self, name: str, args: dict, ret_type: str, body: str):
        self.name = name
        self.args = args # name: type
        self.locals = {} # name: [type, value]
        self.ret_type = _types_.vox_type_to_llvm(ret_type)

        self.body = body

    def is_arg(self, name: str) -> bool:
        return name in self.args
    
    def get_arg_Type(self, name: str) -> str:
        return self.args[name]

    def COOK(self):
        print("Cooking function:", self.name)
        print(self.body)
        print(self.args)
        print("endfn\n")
        BodyCopy: str = self.body
        self.body = ""
        ctx.context.def_stack.push(self.name)
        ctx.context.current_function = self.name
        for line in BodyCopy.split("\n"):
            parsing.parse_line(line, scope=self.name)
        ctx.context.def_stack.pop()
        ctx.context.current_function = ctx.context.def_stack.peek()

    def MakeNonNone(self):
        if self.name is None: self.name = "func"
        if self.args is None: self.args = {}
        if self.ret_type is None: self.ret_type = "void"
        if self.body is None: self.body = "return\n"
        if self.locals is None: self.locals = {}


    def add_local(self, name: str, type_: str, value: str):
        self.locals[name] = [type_, value]

def write_functions(ll_path: str):
    with open(ll_path, "a", encoding="utf-8") as f:  # <-- change "w" to "a"
        for name, fn_pair in ctx.context.functions.items():
            # fn_pair is [Funtion, is_extern]
            func = fn_pair[0]
            is_extern = fn_pair[1]
            if is_extern: continue  # skip externals
            f.write(f"\n; Function {func.name}\n")
            args_str = ", ".join([f"{ _types_.llvm_numbers.get(t, 'i8*')} %{n}" for n, t in func.args.items()])
            ret_type_llvm = _types_.llvm_numbers.get(func.ret_type, "i8*")
            f.write(f"define {ret_type_llvm} @{func.name}({args_str}) {{\nentry:\n")
            f.write(func.body)
            f.write("\n}\n")
