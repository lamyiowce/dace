from fparser.two.Fortran2008 import *
from fparser.two.Fortran2003 import *
from fparser.two.symbol_table import *

import copy
from typing import Any, List, Tuple, Type, TypeVar, Union, overload

#We rely on fparser to provide an initial ast but want to create a new ast that is more suitable for our purposes

# The node class is the base class for all nodes in the AST. It provides attributes including the line number and fields.
# Attributes are not used when walking the tree, but are useful for debugging and for code generation.
# The fields attribute is a list of the names of the attributes that are children of the node.


class Node(object):
    def __init__(self, *args, **kwargs):  # real signature unknown
        self.integrity_exceptions = []
        self.read_vars = []
        self.written_vars = []
        for k, v in kwargs.items():
            setattr(self, k, v)

    _attributes = ("line_number", )
    _fields = ()
    integrity_exceptions: List
    read_vars: List
    written_vars: List

    def __eq__(self, o: object) -> bool:
        if type(self) is type(o):
            # check that all fields and attributes match
            self_field_vals = list(
                map(lambda name: getattr(self, name, None), self._fields))
            self_attr_vals = list(
                map(lambda name: getattr(self, name, None), self._attributes))
            o_field_vals = list(
                map(lambda name: getattr(o, name, None), o._fields))
            o_attr_vals = list(
                map(lambda name: getattr(o, name, None), o._attributes))

            return self_field_vals == o_field_vals and self_attr_vals == o_attr_vals
        return False


class Program_Node(Node):
    _attributes = ()
    _fields = (
        "main_program",
        "function_definitions",
        "subroutine_definitions",
        "modules",
    )


class Main_Program_Node(Node):
    _attributes = ("name", )
    _fields = ("execution_part", "specification_part")


class Module_Node(Node):
    _attributes = ('name', )
    _fields = (
        'specification_part',
        'execution_part',
        'subroutine_definitions',
        'function_definitions',
    )


class Function_Subprogram_Node(Node):
    _attributes = ('name', 'type', 'ret_name')
    _fields = (
        'args',
        'specification_part',
        'execution_part',
    )


class Subroutine_Subprogram_Node(Node):
    _attributes = ('name', 'type')
    _fields = (
        'args',
        'specification_part',
        'execution_part',
    )


class Program_Stmt_Node(Node):
    _attributes = ('name', )
    _fields = ()


class Subroutine_Stmt_Node(Node):
    _attributes = ('name', )
    _fields = ()


class Name_Node(Node):
    _attributes = ('name', 'type')
    _fields = ()


class Specification_Part_Node(Node):
    _fields = ('specifications', 'symbols', 'typedecls')


class Execution_Part_Node(Node):
    _fields = ('execution', )


class Statement_Node(Node):
    _attributes = ('col_offset', )
    _fields = ()


class Type_Decl_Node(Statement_Node):
    _attributes = (
        'name',
        'type',
    )
    _fields = ()


class Symbol_Decl_Node(Statement_Node):
    _attributes = (
        'name',
        'type',
        'alloc',
    )
    _fields = (
        'sizes',
        'typeref',
        'init',
    )


class Constant_Decl_Node(Statement_Node):
    _attributes = (
        'name',
        'type',
        'alloc',
    )
    _fields = (
        'sizes',
        'typeref',
        'init',
    )


class Var_Decl_Node(Statement_Node):
    _attributes = (
        'name',
        'type',
        'alloc',
        'kind',
    )
    _fields = (
        'sizes',
        'typeref',
        'init',
    )


class Decl_Stmt_Node(Statement_Node):
    _attributes = ()
    _fields = ('vardecl', )


class VarType:
    _attributes = ()


class Void(VarType):
    _attributes = ()


# The following class is used to translate the fparser AST to our own AST of Fortran
# the supported_fortran_types dictionary is used to determine which types are supported by our compiler
# for each entry in the dictionary, the key is the name of the class in the fparser AST and the value is the name of the function that will be used to translate the fparser AST to our AST
# the functions return an object of the class that is the name of the key in the dictionary with _Node appended to it to ensure it is diferentietated from the fparser AST
FASTNode = Any
T = TypeVar('T')


@overload
def get_child(node: Union[FASTNode, List[FASTNode]],
              child_type: str) -> FASTNode:
    ...


@overload
def get_child(node: Union[FASTNode, List[FASTNode]], child_type: Type[T]) -> T:
    ...


def get_child(node: Union[FASTNode, List[FASTNode]],
              child_type: Union[str, Type[T], list[Type[T]]]):
    if isinstance(node, list):
        children = node
    else:
        children = node.children

    #if child_type.__name__=="Any":
    #    children_of_type = list(filter(lambda x: x is not None, children))
    if not isinstance(child_type, str) and not isinstance(child_type, list):
        child_type = child_type.__name__
        children_of_type = list(
            filter(lambda child: child.__class__.__name__ == child_type,
                   children))

    elif isinstance(child_type, list):
        child_types = [i.__name__ for i in child_type]
        children_of_type = list(
            filter(lambda child: child.__class__.__name__ in child_types,
                   children))

    if len(children_of_type) == 1:
        return children_of_type[0]
    raise ValueError('Expected only one child of type {} but found {}'.format(
        child_type, children_of_type))


@overload
def get_children(node: Union[FASTNode, List[FASTNode]],
                 child_type: str) -> List[FASTNode]:
    ...


@overload
def get_children(node: Union[FASTNode, List[FASTNode]],
                 child_type: Type[T]) -> List[T]:
    ...


def get_children(node: Union[FASTNode, List[FASTNode]],
                 child_type: Union[str, Type[T], list[Type[T]]]):
    if isinstance(node, list):
        children = node
    else:
        children = node.children

    if not isinstance(child_type, str) and not isinstance(child_type, list):
        child_type = child_type.__name__
        children_of_type = list(
            filter(lambda child: child.__class__.__name__ == child_type,
                   children))

    elif isinstance(child_type, list):
        child_types = [i.__name__ for i in child_type]
        children_of_type = list(
            filter(lambda child: child.__class__.__name__ in child_types,
                   children))

    elif isinstance(child_type, str):
        children_of_type = list(
            filter(lambda child: child.__class__.__name__ == child_type,
                   children))

    return children_of_type


class InternalFortranAst:
    def __init__(self, ast: Program, tables: SymbolTables):
        self.ast = ast
        self.tables = tables
        self.types = {
            "LOGICAL": "BOOL",
            "CHARACTER": "CHAR",
            "INTEGER": "INTEGER",
            "INTEGER4": "INTEGER",
            "REAL4": "REAL",
            "REAL8": "DOUBLE",
            "DOUBLE PRECISION": "DOUBLE",
            "REAL": "REAL",
        }
        self.supported_fortran_syntax = {
            "str": self.str_node,
            "tuple": self.tuple_node,
            "Program": self.program,
            "Main_Program": self.main_program,
            "Program_Stmt": self.program_stmt,
            "End_Program_Stmt": self.end_program_stmt,
            "Subroutine_Subprogram": self.subroutine_subprogram,
            "Function_Subprogram": self.function_subprogram,
            "Subroutine_Stmt": self.subroutine_stmt,
            "Function_Stmt": self.function_stmt,
            "End_Subroutine_Stmt": self.end_subroutine_stmt,
            "End_Function_Stmt": self.end_function_stmt,
            "Module": self.module,
            "Module_Stmt": self.module_stmt,
            "End_Module_Stmt": self.end_module_stmt,
            "Use_Stmt": self.use_stmt,
            "Implicit_Part": self.implicit_part,
            "Implicit_Stmt": self.implicit_stmt,
            "Implicit_None_Stmt": self.implicit_none_stmt,
            "Implicit_Part_Stmt": self.implicit_part_stmt,
            "Declaration_Construct": self.declaration_construct,
            "Declaration_Type_Spec": self.declaration_type_spec,
            "Type_Declaration_Stmt": self.type_declaration_stmt,
            "Entity_Decl": self.entity_decl,
            "Array_Spec": self.array_spec,
            "Loop_Control": self.loop_control,
            "Block_Nonlabel_Do_Construct": self.block_nonlabel_do_construct,
            "Real_Literal_Constant": self.real_literal_constant,
            "Subscript_Triplet": self.subscript_triplet,
            "Section_Subscript_List": self.section_subscript_list,
            "Explicit_Shape_Spec_List": self.explicit_shape_spec_list,
            "Explicit_Shape_Spec": self.explicit_shape_spec,
            "Type_Attr_Spec": self.type_attr_spec,
            "Attr_Spec": self.attr_spec,
            "Intent_Spec": self.intent_spec,
            "Access_Spec": self.access_spec,
            "Allocatable_Stmt": self.allocatable_stmt,
            "Asynchronous_Stmt": self.asynchronous_stmt,
            "Bind_Stmt": self.bind_stmt,
            "Common_Stmt": self.common_stmt,
            "Data_Stmt": self.data_stmt,
            "Dimension_Stmt": self.dimension_stmt,
            "External_Stmt": self.external_stmt,
            "Intent_Stmt": self.intent_stmt,
            "Intrinsic_Stmt": self.intrinsic_stmt,
            "Optional_Stmt": self.optional_stmt,
            "Parameter_Stmt": self.parameter_stmt,
            "Pointer_Stmt": self.pointer_stmt,
            "Protected_Stmt": self.protected_stmt,
            "Save_Stmt": self.save_stmt,
            "Target_Stmt": self.target_stmt,
            "Value_Stmt": self.value_stmt,
            "Volatile_Stmt": self.volatile_stmt,
            "Execution_Part": self.execution_part,
            "Execution_Part_Construct": self.execution_part_construct,
            "Action_Stmt": self.action_stmt,
            "Assignment_Stmt": self.assignment_stmt,
            "Pointer_Assignment_Stmt": self.pointer_assignment_stmt,
            "Where_Stmt": self.where_stmt,
            "Forall_Stmt": self.forall_stmt,
            "Where_Construct": self.where_construct,
            "Where_Construct_Stmt": self.where_construct_stmt,
            "Masked_Elsewhere_Stmt": self.masked_elsewhere_stmt,
            "Elsewhere_Stmt": self.elsewhere_stmt,
            "End_Where_Stmt": self.end_where_stmt,
            "Forall_Construct": self.forall_construct,
            "Forall_Header": self.forall_header,
            "Forall_Triplet_Spec": self.forall_triplet_spec,
            "Forall_Stmt": self.forall_stmt,
            "End_Forall_Stmt": self.end_forall_stmt,
            "Arithmetic_If_Stmt": self.arithmetic_if_stmt,
            "If_Construct": self.if_construct,
            "If_Then_Stmt": self.if_then_stmt,
            "Else_If_Stmt": self.else_if_stmt,
            "Else_Stmt": self.else_stmt,
            "End_If_Stmt": self.end_if_stmt,
            "Case_Construct": self.case_construct,
            "Select_Case_Stmt": self.select_case_stmt,
            "Case_Stmt": self.case_stmt,
            "End_Select_Stmt": self.end_select_stmt,
            "Do_Construct": self.do_construct,
            "Label_Do_Stmt": self.label_do_stmt,
            "Nonlabel_Do_Stmt": self.nonlabel_do_stmt,
            "End_Do_Stmt": self.end_do_stmt,
            "Interface_Block": self.interface_block,
            "Interface_Stmt": self.interface_stmt,
            "End_Interface_Stmt": self.end_interface_stmt,
            "Generic_Spec": self.generic_spec,
            "Name": self.name,
            "Specification_Part": self.specification_part,
            "Intrinsic_Type_Spec": self.intrinsic_type_spec,
            "Entity_Decl_List": self.entity_decl_list,
            "Int_Literal_Constant": self.int_literal_constant,
            "Actual_Arg_Spec_List": self.actual_arg_spec_list,
            "Attr_Spec_List": self.attr_spec_list,
            "Initialization": self.initialization,
            "Procedure_Declaration_Stmt": self.procedure_declaration_stmt,
            "Type_Bound_Procedure_Part": self.type_bound_procedure_part,
            "Contains_Stmt": self.contains_stmt,
            "Call_Stmt": self.call_stmt,
            "Return_Stmt": self.return_stmt,
            "Stop_Stmt": self.stop_stmt,
            "Dummy_Arg_List": self.dummy_arg_list,
            "Part_Ref": self.part_ref,
        }

    def list_tables(self):
        for i in self.tables._symbol_tables:
            print(i)

    def create_children(self, node):
        return [self.create_ast(child) for child in node] if isinstance(
            node,
            (list,
             tuple)) else [self.create_ast(child) for child in node.children]

    def create_ast(self, node=None):
        if node is not None:
            return self.supported_fortran_syntax[type(node).__name__](node)
        return None

    def program(self, node):
        children = self.create_children(node)

        main_program = get_child(children, Main_Program_Node)

        function_definitions = [
            i for i in children if isinstance(i, Function_Subprogram_Node)
        ]

        subroutine_definitions = [
            i for i in children if isinstance(i, Subroutine_Subprogram_Node)
        ]
        modules = [node for node in children if isinstance(node, Module_Node)]

        return Program_Node(main_program=main_program,
                            function_definitions=function_definitions,
                            subroutine_definitions=subroutine_definitions,
                            modules=modules)

    def main_program(self, node):
        children = self.create_children(node)

        name = get_child(children, Program_Stmt_Node)
        specification_part = get_child(children, Specification_Part_Node)
        execution_part = get_child(children, Execution_Part_Node)

        return Main_Program_Node(name=name,
                                 specification_part=specification_part,
                                 execution_part=execution_part)

    def program_stmt(self, node):
        children = self.create_children(node)
        name = get_child(children, Name_Node)
        return Program_Stmt_Node(name=name, line_number=node.item.span)

    def subroutine_subprogram(self, node):
        children = self.create_children(node)

        name = get_child(children, Subroutine_Stmt_Node)
        specification = get_child(children, Specification_Part_Node)
        execution_part = get_child(children, Execution_Part_Node)

        type = Void
        if node.children[0].children[2] is None:
            return Subroutine_Subprogram_Node(name=name,
                                              specification=specification,
                                              execution=execution_part,
                                              type=type)
        else:
            args = self.create_children(node.children[0].children[2].children)
            return Subroutine_Subprogram_Node(name=name,
                                              args=args,
                                              specification=specification,
                                              execution=execution_part,
                                              type=type)

    def end_program_stmt(self, node):
        return node

    def function_subprogram(self, node):
        return node

    def subroutine_stmt(self, node):
        children = self.create_children(node)
        name = get_child(children, Name_Node)
        return Subroutine_Stmt_Node(name=name, line_number=node.item.span)

    def function_stmt(self, node):
        return node

    def end_subroutine_stmt(self, node):
        return node

    def end_function_stmt(self, node):
        return node

    def module(self, node):
        return node

    def module_stmt(self, node):
        return node

    def end_module_stmt(self, node):
        return node

    def use_stmt(self, node):
        return node

    def implicit_part(self, node):
        return node

    def implicit_stmt(self, node):
        return node

    def implicit_none_stmt(self, node):
        return node

    def implicit_part_stmt(self, node):
        return node

    def declaration_construct(self, node):
        return node

    def declaration_type_spec(self, node):
        return node

    def type_declaration_stmt(self, node):

        #decide if its a intrinsic variable type or a derived type

        type_of_node = get_child(node,
                                 [Intrinsic_Type_Spec, Declaration_Type_Spec])

        if isinstance(type_of_node, Intrinsic_Type_Spec):
            derived_type = False
            basetype = type_of_node.items[0]
        elif isinstance(type_of_node, Declaration_Type_Spec):
            derived_type = True
            basetype = type_of_node.items[1].string
        else:
            raise TypeError(
                "Type of node must be either Intrinsic_Type_Spec or Declaration_Type_Spec"
            )
        kind = None
        if len(type_of_node.items) >= 2:
            if type_of_node.items[1] is not None:
                if not derived_type:
                    kind = type_of_node.items[1].items[1].string
                if derived_type:
                    pass
                    #raise TypeError("Derived type not supported")
        if not derived_type:
            testtype = self.types[basetype]
        else:
            testtype = basetype

        #get the names of the variables being defined
        names_list = get_child(node, [Entity_Decl_List, Component_Decl_List])

        #get the names out of the name list
        names = get_children(names_list, [Entity_Decl, Component_Decl])

        #get the attributes of the variables being defined
        # alloc relates to whether it is statically (False) or dynamically (True) allocated
        # parameter means its a constant, so we should transform it into a symbol
        attributes = get_children(node, "Attr_Spec_List")

        alloc = False
        symbol = False
        for i in attributes:
            if i.string.lower() == "allocatable":
                alloc = True
            if i.string.lower() == "parameter":
                symbol = True

        vardecls = []

        for var in names:
            #first handle dimensions
            size = None
            array_sizes = get_children(var, "Explicit_Shape_Spec_List")

            if len(array_sizes) == 1:
                array_sizes = array_sizes[0]
                size = []
                for dim in array_sizes.children:
                    #sanity check
                    if isinstance(dim, Explicit_Shape_Spec):
                        dim_expr = [i for i in dim.children if i is not None]
                        if len(dim_expr) == 1:
                            dim_expr = dim_expr[0]
                            #now to add the dimension to the size list after processing it if necessary
                            size.append(self.create_ast(dim_expr))
                        else:
                            raise TypeError(
                                "Array dimension must be a single expression")
            #handle initializiation
            init = None

            initialization = get_children(var, Initialization)
            if len(initialization) == 1:
                initialization = initialization[0]
                #if there is an initialization, the actual expression is in the second child, with the first being the equals sign
                if len(initialization.children) < 2:
                    raise ValueError("Initialization must have an expression")
                raw_init = initialization.children[1]
                init = self.create_ast(raw_init)

            if symbol == False:

                vardecls.append(
                    Var_Decl_Node(name=var.string,
                                  type=testtype,
                                  alloc=alloc,
                                  sizes=size,
                                  kind=kind))
            else:
                if size is None:
                    vardecls.append(
                        Constant_Decl_Node(name=var.string,
                                           type=testtype,
                                           alloc=alloc,
                                           init=init))
                else:
                    vardecls.append(
                        Symbol_Decl_Node(name=var.string,
                                         type=testtype,
                                         alloc=alloc,
                                         sizes=size,
                                         kind=kind))

        return Decl_Stmt_Node(vardecl=vardecls)

    def entity_decl(self, node):
        return node

    def array_spec(self, node):
        return node

    def explicit_shape_spec_list(self, node):
        return node

    def explicit_shape_spec(self, node):
        return node

    def type_attr_spec(self, node):
        return node

    def attr_spec(self, node):
        return node

    def intent_spec(self, node):
        return node

    def access_spec(self, node):
        return node

    def allocatable_stmt(self, node):
        return node

    def asynchronous_stmt(self, node):
        return node

    def bind_stmt(self, node):
        return node

    def common_stmt(self, node):
        return node

    def data_stmt(self, node):
        return node

    def dimension_stmt(self, node):
        return node

    def external_stmt(self, node):
        return node

    def intent_stmt(self, node):
        return node

    def intrinsic_stmt(self, node):
        return node

    def optional_stmt(self, node):
        return node

    def parameter_stmt(self, node):
        return node

    def pointer_stmt(self, node):
        return node

    def protected_stmt(self, node):
        return node

    def save_stmt(self, node):
        return node

    def target_stmt(self, node):
        return node

    def value_stmt(self, node):
        return node

    def volatile_stmt(self, node):
        return node

    def execution_part(self, node):
        children = self.create_children(node)
        return Execution_Part_Node(execution=children)

    def execution_part_construct(self, node):
        return node

    def action_stmt(self, node):
        return node

    def assignment_stmt(self, node):
        return node

    def pointer_assignment_stmt(self, node):
        return node

    def where_stmt(self, node):
        return node

    def forall_stmt(self, node):
        return node

    def where_construct(self, node):
        return node

    def where_construct_stmt(self, node):
        return node

    def masked_elsewhere_stmt(self, node):
        return node

    def elsewhere_stmt(self, node):
        return node

    def end_where_stmt(self, node):
        return node

    def forall_construct(self, node):
        return node

    def forall_header(self, node):
        return node

    def forall_triplet_spec(self, node):
        return node

    def forall_stmt(self, node):
        return node

    def end_forall_stmt(self, node):
        return node

    def arithmetic_if_stmt(self, node):
        return node

    def if_construct(self, node):
        return node

    def if_then_stmt(self, node):
        return node

    def else_if_stmt(self, node):
        return node

    def else_stmt(self, node):
        return node

    def end_if_stmt(self, node):
        return node

    def case_construct(self, node):
        return node

    def select_case_stmt(self, node):
        return node

    def case_stmt(self, node):
        return node

    def end_select_stmt(self, node):
        return node

    def do_construct(self, node):
        return node

    def label_do_stmt(self, node):
        return node

    def nonlabel_do_stmt(self, node):
        return node

    def end_do_stmt(self, node):
        return node

    def interface_block(self, node):
        return node

    def interface_stmt(self, node):
        return node

    def end_interface_stmt(self, node):
        return node

    def generic_spec(self, node):
        return node

    def procedure_declaration_stmt(self, node):
        return node

    def type_bound_procedure_part(self, node):
        return node

    def contains_stmt(self, node):
        return node

    def call_stmt(self, node):
        return node

    def return_stmt(self, node):
        return node

    def stop_stmt(self, node):
        return node

    def dummy_arg_list(self, node):
        return node

    def attr_spec_list(self, node):
        return node

    def part_ref(self, node):
        return node

    def loop_control(self, node):
        return node

    def block_nonlabel_do_construct(self, node):
        return node

    def real_literal_constant(self, node):
        return node

    def subscript_triplet(self, node):
        return node

    def section_subscript_list(self, node):
        return node

    def specification_part(self, node):
        others = [
            self.create_ast(i) for i in node.children
            if not isinstance(i, Type_Declaration_Stmt)
        ]

        decls = [
            self.create_ast(i) for i in node.children
            if isinstance(i, Type_Declaration_Stmt)
        ]

        uses = [
            self.create_ast(i) for i in node.children
            if isinstance(i, Use_Stmt)
        ]
        tmp = [self.create_ast(i) for i in node.children]
        typedecls = [i for i in tmp if isinstance(i, Type_Decl_Node)]
        symbols = []
        for i in others:
            if isinstance(i, list):
                symbols.extend(j for j in i if isinstance(j, Symbol_Decl_Node))
            if isinstance(i, Decl_Stmt_Node):
                symbols.extend(j for j in i.vardecl
                               if isinstance(j, Symbol_Decl_Node))
        for i in decls:
            if isinstance(i, list):
                symbols.extend(j for j in i if isinstance(j, Symbol_Decl_Node))
            if isinstance(i, Decl_Stmt_Node):
                symbols.extend(j for j in i.vardecl
                               if isinstance(j, Symbol_Decl_Node))
        names_filtered = []
        for j in symbols:
            for i in decls:
                names_filtered.extend(ii.name for ii in i.vardecl
                                      if j.name == ii.name)
        decl_filtered = []
        for i in decls:
            if vardecl_filtered := [
                    ii for ii in i.vardecl if ii.name not in names_filtered
            ]:
                decl_filtered.append(Decl_Stmt_Node(vardecl=vardecl_filtered))
        return Specification_Part_Node(specifications=decl_filtered,
                                       symbols=symbols,
                                       uses=uses,
                                       typedecls=typedecls)

    def intrinsic_type_spec(self, node):
        return node

    def entity_decl_list(self, node):
        return node

    def int_literal_constant(self, node):
        return node

    def actual_arg_spec_list(self, node):
        return node

    def initialization(self, node):
        return node

    def name(self, node):
        return Name_Node(name=node.string)

    def tuple_node(self, node):
        return node

    def str_node(self, node):
        return node
