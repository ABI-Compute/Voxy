class VoxStruct:
    def __init__(self, name: str, fields: dict):
        self.name = name
        self.fields = fields  # name: type

    def get_feild_types(self) -> list[str]:
        return [self.fields[field] for field in self.fields]

def llvm_struct_to_Vox_struct(llvm_struct_str: str) -> VoxStruct:
    """
    Converts an LLVM struct string to a VoxStruct.
    
    Example input: "%MyStruct = type { i32, float }"
    """
    # Split the name and the rest
    name_part, type_part = llvm_struct_str.split("=", 1)
    name = name_part.strip().lstrip('%')  # remove % and whitespace

    # Extract the field types between { and }
    fields_str = type_part[type_part.find("{")+1:type_part.find("}")]
    field_types = [f.strip() for f in fields_str.split(",") if f.strip()]

    # Create dictionary with auto-generated field names
    fields_dict = {f"field{i}": ftype for i, ftype in enumerate(field_types)}

    return VoxStruct(name, fields_dict)
