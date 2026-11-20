"""Read class structure to register AutoConfig data without loading or initializing Mods."""
from __future__ import annotations

from collections import deque
import json
import re
import struct
import zipfile

from mod_file_policy import is_metadata

YACL_HANDLER = "dev/isxander/yacl3/config/v2/api/ConfigClassHandler"

# Mods look members up by name on purpose: the same jar has to work across mapping sets, so they
# call ``Class.getDeclaredMethod("create", ...)`` or wrap it. A closed world ships no metadata
# unless it is asked for, and the failure is a NoSuchMethodException that reports the requested
# signature exactly like a genuinely missing method would. These are the sinks worth tracking;
# a wrapper that returns Method/Field is tracked by its return type instead of its name.
MEMBER_SINKS = {"getDeclaredMethod": "method", "getMethod": "method",
                "getDeclaredField": "field", "getField": "field"}
REFLECT_RETURNS = {"Ljava/lang/reflect/Method;": "method",
                   "Ljava/lang/reflect/Field;": "field"}
# ``Class.forName`` in a closed world only succeeds for classes registered for reflection.
# Two shapes of call site matter: a plain string literal (visible to any constant scanner) and
# the mrcrayfish-style nested-class trick - ``Example.class.getName() + "$Deserializer"`` - where
# neither the string nor the nested class literal appears anywhere in the bytecode. The literal
# suffix survives in the ``makeConcatWithConstants`` bootstrap recipe, which is why the recipe
# attribute is parsed alongside the code.
FORNAME_DESCRIPTORS = {"(Ljava/lang/String;)Ljava/lang/Class;",
                       "(Ljava/lang/String;ZLjava/lang/ClassLoader;)Ljava/lang/Class;"}
# Parsing 27k class files is already the cost of the scan; only classes that mention reflection at
# all need their bytecode walked. On the 43-Mod pack that is ~80 of 26919 classes.
MEMBER_HINTS = (b"getDeclaredMethod", b"getMethod", b"getDeclaredField", b"getField",
                b"forName", b"makeConcatWithConstants")
# The caller filter exists to keep vanilla's own reflection out of the result: the JDK, Minecraft
# and the shading libraries all reflect on themselves, and none of that is a Mod contract.
PLATFORM_PREFIXES = ("java/", "javax/", "jdk/", "sun/", "com/sun/", "net/minecraft/",
                     "com/mojang/", "org/lwjgl/", "it/unimi/", "com/google/", "org/apache/",
                     "io/netty/", "org/slf4j/", "org/joml/", "org/objectweb/", "oshi/",
                     "net/fabricmc/")

# Lithium decides optimisations with ``Class.getDeclaredMethod(name, ...)`` walked up the
# superclass chain, treating ``NoSuchMethodException`` as "this class does not override it".
# A closed world throws exactly that exception for every unregistered method, so the answer is
# always "no" - and the library's own class-init self-check then trips an ``AssertionError``
# instead of quietly losing an optimisation. The names below are every query it makes; the
# declaring classes are discovered by the scan rather than listed by hand.
OVERRIDE_QUERIES = {"canCollideWith", "canBeCollidedWith", "canHitEntity",
                    "canBeHitByProjectile", "isPickable", "isPushable", "onClimbable"}

# Config holders that take a factory instead of a class literal. ``TConfigHandler`` (traben's
# library, used by Entity Texture Features) receives a ``Supplier`` and learns the type from
# ``supplier.get().getClass()`` inside its constructor, so the config class name appears nowhere
# but the ``X::new`` method handle passed at the call site.
T_CONFIG_HANDLER = "traben/tconfig/TConfigHandler"


def _instruction_length(code, position):
    """Byte length of the instruction at ``position`` (variable-width ones included)."""
    opcode = code[position]
    if opcode in (0xaa, 0xab):  # tableswitch / lookupswitch
        cursor = position + 1 + (3 - position % 4)
        header_size = 12 if opcode == 0xaa else 8
        if cursor + header_size > len(code):
            raise ValueError("Truncated switch instruction")
        if opcode == 0xaa:
            # default(4) + low(4) + high(4) precede the match table, so the header is 12 bytes.
            _default, low, high = struct.unpack(">iii", code[cursor:cursor + 12])
            span = (high - low + 1) * 4
        else:
            pairs = struct.unpack(">i", code[cursor + 4:cursor + 8])[0]
            span = pairs * 8
        if span < 0:
            raise ValueError("Invalid switch instruction table")
        return cursor - position + header_size + span
    if opcode == 0xc4:  # wide
        if position + 1 >= len(code):
            raise ValueError("Truncated wide instruction")
        return 6 if code[position + 1] == 0x84 else 4
    if 0x15 <= opcode <= 0x19 or 0x36 <= opcode <= 0x3a:
        return 2
    if 0x99 <= opcode <= 0xa8 or 0xb2 <= opcode <= 0xb8 or 0xc6 <= opcode <= 0xc7:
        return 3
    if opcode in (0xc8, 0xc9, 0xb9, 0xba):
        return 5
    return {0x10: 2, 0x11: 3, 0x12: 2, 0x13: 3, 0x14: 3, 0x84: 3, 0xa9: 2,
            0xbb: 3, 0xbc: 2, 0xbd: 3, 0xc0: 3, 0xc1: 3, 0xc5: 4}.get(opcode, 1)


def _member_ref(reference, pool):
    """(owner, member, descriptor) of a Methodref/InterfaceMethodref constant."""
    owner = pool[pool[reference[1]][1]]
    name_and_type = pool[reference[2]]
    return owner, pool[name_and_type[1]], pool[name_and_type[2]]


def instructions(code, pool, *, bootstrap=None):
    """Decode instruction boundaries and the constants used by the static scanners."""
    offset = 0
    while offset < len(code):
        opcode = code[offset]
        size = _instruction_length(code, offset)
        if offset + size > len(code):
            raise ValueError("Truncated bytecode instruction")
        operand = None
        if opcode == 0x12:
            operand = pool[code[offset + 1]]
        elif opcode in (0x13, 0x14, *range(0xb2, 0xbc), 0xbd, 0xc0, 0xc1, 0xc5):
            operand = pool[int.from_bytes(code[offset + 1:offset + 3], "big")]
        value = operand
        if isinstance(operand, tuple):
            if operand[0] in (7, 8):
                value = (operand[0], pool[operand[1]])
            elif operand[0] in (9, 10, 11):
                value = (operand[0], *_member_ref(operand, pool))
            elif bootstrap is not None:
                value = symbolic_constant(operand, pool, bootstrap)
        yield opcode, value
        offset += size


def symbolic_constant(entry, pool, bootstrap, active=()):
    tag = entry[0]
    if tag in (7, 8):
        return (tag, pool[entry[1]])
    if tag == 15:
        target = pool[entry[2]]
        return (15, entry[1], (target[0], *_member_ref(target, pool)))
    if tag == 16:
        return (16, pool[entry[1]])
    if tag not in (17, 18):
        return entry
    index, name_and_type = entry[1:]
    descriptor = pool[pool[name_and_type][2]]
    if index in active:
        raise ValueError("Circular bootstrap constant")
    arguments = tuple(symbolic_constant(pool[item], pool, bootstrap, (*active, index))
                      for item in bootstrap[index] if isinstance(pool[item], tuple))
    return (tag, descriptor, arguments)


def json_loader_sites(code, pool):
    """Match a class literal passed directly to a newly constructed typed loader.

    Track the straight-line NEW, DUP, Class literal, constant arguments and constructor
    sequence. Consumers are checked separately, so unrelated Class-taking constructors
    do not widen reflection metadata.
    """
    sequence = []
    for opcode, value in instructions(code, pool):
        if opcode == 0xbb:
            sequence = [(opcode, value[1])]
        elif sequence and opcode == 0x59 and len(sequence) == 1:
            sequence.append((opcode, None))
        elif len(sequence) >= 2 and opcode in (0x12, 0x13):
            sequence.append((opcode, value))
        elif sequence and opcode == 0xb7:
            _, owner, member, descriptor = value
            arguments = [item[1] for item in sequence[2:]]
            parameters = re.findall(r"L[^;]+;", descriptor.partition(")")[0][1:])
            if (owner == sequence[0][1] and member == "<init>"
                    and parameters and parameters[0] == "Ljava/lang/Class;"
                    and descriptor == "(" + "".join(parameters) + ")V"
                    and len(arguments) == len(parameters)
                    and all(isinstance(item, tuple) and item[0] == tag
                            for item, tag in zip(arguments, [7] + [8] * (len(parameters) - 1)))
                    and all(param == "Ljava/lang/String;" for param in parameters[1:])):
                yield owner, arguments[0][1]
            sequence.clear()
        else:
            sequence.clear()


def has_typed_gson_loader(owner, methods, code_bodies, pool):
    """Prove the same Class field is set from the first constructor argument and consumed."""
    assigned, constructed, decoded = set(), set(), set()
    for method, code in zip(methods, code_bodies, strict=True):
        previous = deque(maxlen=3)
        for opcode, value in instructions(code, pool):
            if opcode == 0xb5 and method.startswith("<init>(Ljava/lang/Class;"):
                if list(previous)[-2:] == [(0x2a, None), (0x2b, None)]:
                    assigned.add(value)
            elif opcode == 0xb6 and len(previous) == 3:
                _, called_owner, name, descriptor = value
                if (called_owner == "java/lang/Class" and name == "getConstructor"
                        and descriptor == "([Ljava/lang/Class;)Ljava/lang/reflect/Constructor;"
                        and previous[-2] == (0x03, None)
                        and previous[-1] == (0xbd, (7, "java/lang/Class"))
                        and previous[-3][0] == 0xb4):
                    constructed.add(previous[-3][1])
                if (called_owner == "com/google/gson/Gson" and name == "fromJson"
                        and descriptor.endswith("Ljava/lang/Class;)Ljava/lang/Object;")
                        and previous[-1][0] == 0xb4):
                    decoded.add(previous[-1][1])
            previous.append((opcode, value))
    return any(field_owner == owner and descriptor == "Ljava/lang/Class;"
               for _, field_owner, _, descriptor in assigned & constructed & decoded)


def member_sites(code, pool):
    """Reflective lookups whose target class and member name are both compile-time constants.

    Arguments are pushed left to right, so the class literal is followed by the name string and
    then by the parameter-class varargs. Between them sit only constant loads and array stores,
    which is why the runner keeps the constant stream instead of a single pending pair: Xaero's
    ``getMethodReflection(RenderType.class, "create", String.class, RenderSetup.class)`` pushes
    three class literals, and the pair that matters is the first one. Lookups whose target comes
    from a variable (``x.getClass()``) carry no class literal and are skipped - there is nothing
    to register for a type the build never resolved.
    """
    sites = []
    recent = []
    position = 0
    while position < len(code):
        opcode = code[position]
        if opcode in (0x12, 0x13):
            width = 1 if opcode == 0x12 else 2
            if position + width >= len(code):
                break
            index = (code[position + 1] if width == 1
                     else struct.unpack(">H", code[position + 1:position + 3])[0])
            entry = pool[index] if 0 < index < len(pool) else None
            if isinstance(entry, tuple) and entry[0] == 7:
                recent.append((7, pool[entry[1]]))
            elif isinstance(entry, tuple) and entry[0] == 8:
                recent.append((8, pool[entry[1]]))
            del recent[:-8]
        elif opcode in (0xb6, 0xb7, 0xb8, 0xb9) and position + 2 < len(code):
            index = struct.unpack(">H", code[position + 1:position + 3])[0]
            reference = pool[index] if 0 < index < len(pool) else None
            if isinstance(reference, tuple) and reference[0] in (10, 11):
                _owner, sink, descriptor = _member_ref(reference, pool)
                kind = MEMBER_SINKS.get(sink) or REFLECT_RETURNS.get(descriptor.rpartition(")")[2])
                if kind:
                    for tag, value in zip(recent, recent[1:]):
                        member = value[1]
                        if tag[0] == 7 and value[0] == 8 and member.isidentifier() and not member.startswith("<"):
                            sites.append({"target": tag[1], "member": member, "kind": kind})
                            break
            # A call ends the argument run; stale constants must not pair with the next lookup.
            recent.clear()
        position += _instruction_length(code, position)
    return sites


def bootstrap_recipes(class_attributes, pool):
    """Literal suffixes of ``makeConcatWithConstants`` bootstraps, keyed by attribute index.

    The compiler keeps the recipe - placeholder plus literal text - as the first string
    argument of the bootstrap. A recipe with a single leading placeholder describes
    ``<dynamic> + "literal"`` concatenation, so the literal is exactly the suffix appended
    to a run-time name. Anything with more placeholders or embedded constants depends on
    run-time data and stays unresolved.
    """
    recipes = {}
    for key, body in class_attributes:
        if key != "BootstrapMethods" or len(body) < 2:
            continue
        count = struct.unpack(">H", body[0:2])[0]
        position = 2
        for index in range(count):
            if position + 4 > len(body):
                raise ValueError("Truncated bootstrap method entry")
            _method_ref = struct.unpack(">H", body[position:position + 2])[0]
            argument_count = struct.unpack(">H", body[position + 2:position + 4])[0]
            position += 4
            if position + 2 * argument_count > len(body):
                raise ValueError("Truncated bootstrap method arguments")
            arguments = [struct.unpack(">H", body[position + 2 * offset:
                                           position + 2 * offset + 2])[0]
                         for offset in range(argument_count)]
            position += 2 * argument_count
            for argument in arguments:
                entry = pool[argument] if 0 < argument < len(pool) else None
                if not isinstance(entry, tuple) or entry[0] != 8:
                    continue
                recipe = pool[entry[1]]
                if (isinstance(recipe, str) and recipe.startswith("\x01")
                        and "\x02" not in recipe and recipe.count("\x01") == 1):
                    recipes[index] = recipe[1:]
                break
    return recipes


def bootstrap_factories(class_attributes, pool):
    """Classes instantiated by a method handle in a bootstrap argument.

    ``X::new`` passed where a ``Supplier`` is expected is how a config holder hands its type to
    a loader without naming it. The ``REF_newInvokeSpecial`` handle is the only constant that
    mentions X, so the bootstrap argument is the evidence a closed world can act on. Only
    no-argument constructors are recorded: a factory that takes arguments cannot be the
    "build me a default config" supplier these loaders use.
    """
    factories = set()
    for key, body in class_attributes:
        if key != "BootstrapMethods" or len(body) < 2:
            continue
        count = struct.unpack(">H", body[0:2])[0]
        position = 2
        for _ in range(count):
            if position + 4 > len(body):
                raise ValueError("Truncated bootstrap method entry")
            argument_count = struct.unpack(">H", body[position + 2:position + 4])[0]
            position += 4
            if position + 2 * argument_count > len(body):
                raise ValueError("Truncated bootstrap method arguments")
            arguments = [struct.unpack(">H", body[position + 2 * offset:
                                           position + 2 * offset + 2])[0]
                         for offset in range(argument_count)]
            position += 2 * argument_count
            for argument in arguments:
                entry = pool[argument] if 0 < argument < len(pool) else None
                if not isinstance(entry, tuple) or entry[0] != 15 or entry[1] != 8:
                    continue  # 15 = MethodHandle; 8 = REF_newInvokeSpecial
                target = pool[entry[2]] if 0 < entry[2] < len(pool) else None
                if not isinstance(target, tuple) or target[0] not in (9, 10, 11):
                    continue
                owner, _member, descriptor = _member_ref(target, pool)
                if owner and descriptor == "()V":
                    factories.add(owner)
    return factories


def class_literals(code, pool):
    """Class names loaded with ``ldc`` in one method body."""
    names = set()
    position = 0
    while position < len(code):
        opcode = code[position]
        if opcode in (0x12, 0x13):
            width = 1 if opcode == 0x12 else 2
            if position + width >= len(code):
                raise ValueError("Truncated ldc instruction")
            index = (code[position + 1] if width == 1
                     else struct.unpack(">H", code[position + 1:position + 3])[0])
            entry = pool[index] if 0 < index < len(pool) else None
            if isinstance(entry, tuple) and entry[0] == 7:
                inner = pool[entry[1]] if 0 < entry[1] < len(pool) else None
                if isinstance(inner, str):
                    names.add(inner)
        position += _instruction_length(code, position)
    return names


def forname_sites(code, pool, recipes):
    """``Class.forName`` call sites, however the target name is produced.

    Tracked shapes: a plain string literal, and ``X.class.getName() + "<suffix>"`` where the
    suffix comes from a ``makeConcatWithConstants`` recipe. A name built either way is the
    whole lookup key - there is no member to pair with - so each site records only the
    resolved target class. Lookups whose argument comes from a variable the build cannot see
    are skipped: there is nothing to register for a name the scanner cannot recover.
    """
    sites = []
    pending_class = named = suffix = literal = None
    position = 0
    while position < len(code):
        opcode = code[position]
        if opcode in (0x12, 0x13):
            width = 1 if opcode == 0x12 else 2
            if position + width >= len(code):
                break
            index = (code[position + 1] if width == 1
                     else struct.unpack(">H", code[position + 1:position + 3])[0])
            entry = pool[index] if 0 < index < len(pool) else None
            if isinstance(entry, tuple) and entry[0] == 7:
                pending_class, literal = pool[entry[1]], None
            elif isinstance(entry, tuple) and entry[0] == 8:
                literal, pending_class = pool[entry[1]], None
        elif opcode == 0xba and position + 4 < len(code):  # invokedynamic
            index = struct.unpack(">H", code[position + 1:position + 3])[0]
            entry = pool[index] if 0 < index < len(pool) else None
            if isinstance(entry, tuple) and entry[0] == 18:
                suffix = recipes.get(entry[1])
        elif opcode in (0xb6, 0xb7, 0xb8, 0xb9) and position + 2 < len(code):
            index = struct.unpack(">H", code[position + 1:position + 3])[0]
            reference = pool[index] if 0 < index < len(pool) else None
            if isinstance(reference, tuple) and reference[0] in (10, 11):
                owner, sink, descriptor = _member_ref(reference, pool)
                if (opcode == 0xb6 and owner == "java/lang/Class"
                        and sink == "getName" and descriptor == "()Ljava/lang/String;"):
                    named, pending_class, literal = pending_class, None, None
                elif (opcode == 0xb8 and owner == "java/lang/Class"
                        and sink == "forName" and descriptor in FORNAME_DESCRIPTORS):
                    if named and suffix is not None:
                        sites.append({"target": named + suffix, "forName": True})
                    elif literal:
                        sites.append({"target": literal.replace(".", "/"), "forName": True})
                    named = suffix = pending_class = literal = None
                else:
                    named = suffix = pending_class = literal = None
            else:
                named = suffix = literal = None
        position += _instruction_length(code, position)
    return sites


def yacl_config_roots(shapes):
    """Locate YetAnotherConfigLib v2 config classes.

    A YACL v2 config exposes a static ``ConfigClassHandler`` field initialized in ``<clinit>``
    through ``createBuilder(TheConfig.class)...build()``. ConfigClassHandlerImpl then reflects on
    the config's no-arg constructor and declared fields *during that <clinit>*, so every such
    class needs constructor/field metadata in the closed world - not only the first one reached.
    Detecting the handler field keeps this general without loading or initializing Mod code.
    """
    return {name for name, shape in shapes.items()
            if "<clinit>" in shape["methods"]
            and any(YACL_HANDLER in descriptor for descriptor in shape["declaredFields"])}


def class_shape(data, *, graph=False, declarations_only=False):
    position = 0

    def take(count):
        nonlocal position
        if count < 0 or position + count > len(data):
            raise ValueError("Truncated configuration class")
        value = data[position:position + count]
        position += count
        return value

    def u2():
        return struct.unpack(">H", take(2))[0]

    def attributes():
        result = []
        for _ in range(u2()):
            name = pool[u2()]
            body = take(struct.unpack(">I", take(4))[0])
            result.append((name, body))
        return result

    if take(4) != b"\xca\xfe\xba\xbe":
        raise ValueError("Invalid configuration class header")
    take(4)
    pool = [None] * u2()
    index = 1
    while index < len(pool):
        tag = take(1)[0]
        if tag == 1:
            pool[index] = take(u2()).decode("utf-8", "replace")
        elif tag in (7, 8, 16, 19, 20):
            pool[index] = (tag, u2())
        elif tag in (9, 10, 11, 12, 17, 18):
            pool[index] = (tag, u2(), u2())
        elif tag in (3, 4):
            take(4)
        elif tag in (5, 6):
            take(8)
            index += 1
        elif tag == 15:
            # MethodHandle: reference kind plus the member it points at. Kinds matter for the
            # config-factory scan, so the entry is kept instead of skipped.
            pool[index] = (tag, take(1)[0], u2())
        else:
            raise ValueError(f"Unknown constant pool tag {tag}")
        index += 1

    def name(index):
        return pool[pool[index][1]] if index else None

    access = u2()
    this, parent = name(u2()), name(u2())
    interfaces = [name(u2()) for _ in range(u2())]
    field_types = set()
    declared_fields = set()
    declared_field_names = set()
    fields = []
    field_flags = {}
    for _ in range(u2()):
        flags, field_name, descriptor = u2(), u2(), pool[u2()]
        attrs = attributes()
        declared_field_names.add(pool[field_name])
        fields.append((pool[field_name], descriptor))
        field_flags[fields[-1]] = flags
        declared_fields.add(descriptor)
        signature = None
        for key, body in attrs:
            if key == "Signature":
                if len(body) != 2:
                    raise ValueError("Invalid field signature attribute")
                signature = pool[struct.unpack(">H", body)[0]]
                declared_fields.add(signature)
        if flags & (0x0008 | 0x0080):  # static or transient: never serialized
            continue
        field_types.update(re.findall(r"L([^;<]+)", descriptor))
        if signature:
            field_types.update(re.findall(r"L([^;<]+)", signature))
    methods = []
    method_signatures = []
    constructors = set()
    public_no_arg = False
    sites = []
    forname = []
    code_bodies = []
    code_methods = []
    native_methods = []
    method_flags = {}
    handled = set()
    for _ in range(u2()):
        flags, method_name, descriptor = u2(), u2(), u2()
        methods.append(pool[method_name])
        method_signatures.append(pool[method_name] + pool[descriptor])
        method_flags[method_signatures[-1]] = flags
        if pool[method_name] == "<init>":
            constructors.add(pool[descriptor])
            public_no_arg |= pool[descriptor] == "()V" and bool(flags & 0x0001)
        if flags & 0x0100:
            native_methods.append(pool[method_name] + pool[descriptor])
        for key, body in attributes():
            if key != "Code" or declarations_only:
                continue
            # max_stack, max_locals, code_length, code, exception_table, attributes
            length = struct.unpack(">I", body[4:8])[0]
            if length + 10 > len(body):
                raise ValueError("Invalid code attribute")
            code_bodies.append(body[8:8 + length])
            code_methods.append(method_signatures[-1])
            if body[8 + length:10 + length] != b"\x00\x00":
                handled.add(method_signatures[-1])
    # BootstrapMethods is a class-level attribute, so the recipes only exist after the method
    # walk; the code bodies are scanned once both halves are available.
    class_attributes = attributes()
    nest_host = next((name(struct.unpack(">H", body)[0]) for key, body in class_attributes
                      if key == "NestHost"), this)
    declarations = dict(name=this, parent=parent, interfaces=interfaces, access=access,
                        fieldFlags=field_flags, methodFlags=method_flags, nestHost=nest_host)
    if declarations_only:
        return declarations
    scan = not this.startswith(PLATFORM_PREFIXES) and any(hint in data for hint in MEMBER_HINTS)
    recipes = bootstrap_recipes(class_attributes, pool)
    factories = bootstrap_factories(class_attributes, pool)
    if scan:
        for code in code_bodies:
            sites.extend(member_sites(code, pool))
            forname.extend(forname_sites(code, pool, recipes))
    # Class literals only matter for the "names and builds the same type" pattern, so the extra
    # walk is limited to the few classes that own a factory handle.
    literals = set()
    if factories:
        for code in code_bodies:
            literals.update(class_literals(code, pool))
    typed_sites = []
    if not this.startswith(PLATFORM_PREFIXES) and b"(Ljava/lang/Class;" in data and b"<init>" in data:
        for code in code_bodies:
            typed_sites.extend(json_loader_sites(code, pool))
    gson_loader = False
    if (b"com/google/gson/Gson" in data and b"getConstructor" in data
            and "Ljava/lang/Class;" in declared_fields):
        gson_loader = has_typed_gson_loader(this, code_methods, code_bodies, pool)
    shape = {**declarations, "fieldTypes": sorted(field_types),
            "declaredFields": sorted(declared_fields),
            "declaredFieldNames": sorted(declared_field_names), "fields": fields,
            "methods": methods, "methodSignatures": method_signatures,
            "constructors": sorted(constructors), "publicNoArgConstructor": public_no_arg,
            "jsonLoaderSites": typed_sites, "gsonConstructorLoader": gson_loader, "reflection": sites,
            "forName": forname, "factories": sorted(factories),
            "classLiterals": sorted(literals)}
    if graph:
        bootstrap = []
        for key, body in class_attributes:
            if key == "BootstrapMethods":
                words = iter(struct.unpack(f">{len(body) // 2}H", body))
                for _ in range(next(words)):
                    handle, count = next(words), next(words)
                    bootstrap.append([handle, *(next(words) for _ in range(count))])
        shape.update(nativeMethods=native_methods,
                     handledMethods=handled,
                     bytecode=zip(code_methods, (instructions(code, pool, bootstrap=bootstrap)
                                                 for code in code_bodies)),
                     classReferences={pool[ref[1]] for ref in pool
                                      if isinstance(ref, tuple) and ref[0] == 7},
                     memberReferences={_member_ref(ref, pool) for ref in pool
                                       if isinstance(ref, tuple) and ref[0] in (9, 10, 11)})
    return shape


def config_entries(shapes, serialization_roots=(), open_roots=()):
    data = "me/shedaniel/autoconfig/ConfigData"
    derived = {data}
    while True:
        added = {name for name, shape in shapes.items()
                 if shape["parent"] in derived or set(shape["interfaces"]) & derived} - derived
        if not added:
            break
        derived.update(added)
    seeds = ((derived | set(serialization_roots)) & shapes.keys()) - {data}
    # An "open" root is a JSON document whose object graph is not confined to one package: an
    # engine config holds, say, ``environment/pocket/AirPocketGroup[]`` while sitting in
    # ``engine/``. Gson walks that graph as it is, so the closure follows field types across the
    # Mod's own namespaces and stops at the platform prefixes - a Minecraft-valued field must not
    # register the entire game graph.
    open_seeds = set(open_roots) & shapes.keys()
    selected = set()
    for seed in sorted(seeds | open_seeds):
        package = seed.rpartition("/")[0] + "/"
        open_seed = seed in open_seeds
        pending = [seed]
        visited = set()
        while pending:
            name = pending.pop()
            if name in visited or name not in shapes or name == data:
                continue
            visited.add(name)
            selected.add(name)
            shape = shapes[name]
            # Include serialized inherited fields, then descend into the field types this kind of
            # root can reach.
            if shape["parent"] in shapes:
                pending.append(shape["parent"])
            if open_seed:
                pending.extend(type_ for type_ in shape["fieldTypes"]
                               if not type_.startswith(PLATFORM_PREFIXES))
            else:
                pending.extend(type_ for type_ in shape["fieldTypes"] if type_.startswith(package))
    # Gson asks for a declared no-arg constructor first and falls back to sun.misc.Unsafe when the
    # class has none (a config whose only constructor takes arguments, or a protected one). The
    # closed world refuses that fallback unless the type is registered as unsafe-allocatable, so
    # every selected type without a no-arg constructor carries the permission itself. Shapes come
    # from this build's own scan, which keeps the decision tied to the bytecode being registered.
    return [{"name": name.replace("/", "."), "allDeclaredConstructors": True,
             "allDeclaredFields": True,
             **({"allDeclaredMethods": True} if shapes[name]["parent"] == "java/lang/Record" else {}),
             **({"unsafeAllocated": True} if "()V" not in shapes[name]["constructors"] else {})}
            for name in sorted(selected)]


def member_entries(shapes, sites):
    """Reflection entries for the members Mods look up by name at run time.

    Only targets the build actually resolved are registered; a name that matched a class literal
    outside the archive would produce a config entry for a type the image does not contain.
    """
    by_target = {}
    for site in sites:
        if site["target"] in shapes:
            by_target.setdefault(site["target"], {"method": set(), "field": set()})[site["kind"]].add(site["member"])
    entries = []
    for target in sorted(by_target):
        entry = {"name": target.replace("/", ".")}
        for kind, key in (("method", "methods"), ("field", "fields")):
            if by_target[target][kind]:
                entry[key] = [{"name": member} for member in sorted(by_target[target][kind])]
        entries.append(entry)
    return entries


def forname_entries(shapes, sites):
    """Reflection entries for classes looked up by an assembled name.

    The site carries no member names - the class is instantiated through its declared
    constructors - so construction metadata for every resolved target is enough for
    ``Class.forName`` to return the class and ``getDeclaredConstructor().newInstance()``
    to run. Targets the build never resolved are dropped, as with member entries.
    """
    targets = {site["target"] for site in sites}
    return [{"name": target.replace("/", "."), "allDeclaredConstructors": True}
            for target in sorted(targets & shapes.keys())]


def override_entries(shapes):
    """Reflection entries for the overrides Lithium's class analysis asks about.

    Registering a method name (without ``parameterTypes``) exposes every overload of that name
    on the class, which is what ``getDeclaredMethod`` needs to answer with a real ``Method``
    instead of ``NoSuchMethodException``. Only classes that actually declare one of the queried
    names are registered, so the metadata follows the shipped bytecode rather than a list.
    """
    entries = []
    for name in sorted(shapes):
        queries = sorted(set(shapes[name]["methods"]) & OVERRIDE_QUERIES)
        if queries:
            entries.append({"name": name.replace("/", "."),
                            "methods": [{"name": query} for query in queries]})
    return entries


def framework_config_entries(shapes, roots):
    """Reflection entries for the config groups a Mod's ``@FrameworkConfig`` exposes.

    The framework links properties by walking ``getDeclaredFields()`` over the config object and
    every group object it contains, so a closed world needs field metadata for the whole family -
    root class and its ``$``-nested groups. Only fields matter: the scan reads them, never
    constructs or invokes anything.
    """
    selected = set()
    for root in roots:
        # The export records the shape it scanned; a name that did not ship cannot be registered.
        for name in shapes:
            if name == root or name.startswith(root + "$"):
                selected.add(name)
    return [{"name": name.replace("/", "."), "allDeclaredFields": True} for name in sorted(selected)]


def json_config_roots(shapes):
    """Config classes a Gson-based loader instantiates reflectively.

    Gson needs the declared no-arg constructor (or ``Unsafe`` allocation) *and* the declared
    fields of the object it fills: without registration it writes ``{}`` on save and rebuilds an
    all-null instance on the next load. Two holder shapes carry the type without a literal:

    * a class that both names the type (``X.class``) and builds it through a ``Supplier``
      method reference (``X::new``) - NoChatReports' ``loadConfig`` and CreativeCore's packet
      registry;
    * a ``TConfigHandler`` field, whose constructor learns the type from
      ``supplier.get().getClass()`` - Entity Texture Features builds both of its configs that
      way from ``ETF``.

    Both are structural: the intersection is taken per class, and nothing is registered for a
    type the build did not see declared.
    """
    roots = set()
    for shape in shapes.values():
        factories = set(shape["factories"])
        if not factories:
            continue
        roots.update(factories & set(shape["classLiterals"]))
        if any(T_CONFIG_HANDLER in descriptor for descriptor in shape["declaredFields"]):
            roots.update(factories)
    return roots


def _merge(entries, additions):
    """Fold name-only member metadata into the config entries, keeping one object per class."""
    by_name = {entry["name"]: entry for entry in entries}
    for addition in additions:
        existing = by_name.get(addition["name"])
        if existing is None:
            entries.append(addition)
            by_name[addition["name"]] = addition
            continue
        for key in ("allDeclaredConstructors", "allDeclaredFields",
                    "allDeclaredMethods", "unsafeAllocated"):
            if addition.get(key):
                existing[key] = True
        for key in ("methods", "fields"):
            if key not in addition:
                continue
            if existing.get("allDeclaredMethods" if key == "methods" else "allDeclaredFields"):
                continue  # the config entry already exposes every member of that kind
            present = {item["name"] for item in existing.get(key, ())}
            existing[key] = [*existing.get(key, ()),
                             *(item for item in addition[key] if item["name"] not in present)]
    return entries


def reflection_from_jar(path, *, class_visitor=None, diagnostics=None, include_entry=None, extra_shapes=()):
    shapes = {}
    sites = []
    forname = []

    def retain(shape):
        if class_visitor:
            class_visitor(shape)
            for key in ("bytecode", "classReferences", "memberReferences", "fieldFlags",
                        "methodFlags", "handledMethods", "nativeMethods", "nestHost"):
                del shape[key]
        shapes[shape["name"]] = shape
        sites.extend(shape["reflection"])
        forname.extend(shape["forName"])

    with zipfile.ZipFile(path) as jar:
        entries = jar.infolist()
        # The exporter additionally preserves per-Mod resource roots. Bound those separately
        # instead of counting generated resource copies as new program definitions.
        originals = [item for item in entries if not item.filename.startswith("mcfao/mod-files/")]
        if (len(entries) > 200000 or len(originals) > 100000
                or sum(item.file_size for item in entries) > 2 * 1024**3):
            raise ValueError("Configuration scan archive exceeds budget")
        for item in entries:
            name = item.filename
            if (not name.endswith(".class") or name.startswith(("META-INF/", "mcfao/mod-files/"))
                    or is_metadata(name) or (include_entry and not include_entry(name))):
                continue
            try:
                shape = class_shape(jar.read(item), graph=class_visitor is not None)
            except (ValueError, IndexError, struct.error, StopIteration) as error:
                raise ValueError(f"{error}: {path}!{name}") from error
            if shape["name"] + ".class" != name:
                raise ValueError(f"Configuration scan class path mismatch: {name}")
            retain(shape)
        roots_path = "META-INF/native-image/mcfao/fabric/serialization-roots.json"
        roots = json.loads(jar.read(roots_path)) if roots_path in jar.namelist() else []
        if not isinstance(roots, list) or any(not isinstance(name, str) for name in roots):
            raise ValueError("Invalid serialization roots metadata")
        config_path = "META-INF/native-image/mcfao/fabric/framework-config-roots.json"
        config_roots = json.loads(jar.read(config_path)) if config_path in jar.namelist() else []
        if not isinstance(config_roots, list) or any(not isinstance(name, str) for name in config_roots):
            raise ValueError("Invalid framework config roots metadata")
    for shape in extra_shapes:
        if not shape["name"].startswith(PLATFORM_PREFIXES) or shape["gsonConstructorLoader"]:
            retain(shape)
        elif class_visitor:
            class_visitor(shape)
    typed_roots = set()
    for shape in shapes.values():
        for loader, target in shape["jsonLoaderSites"]:
            if not shapes.get(loader, {}).get("gsonConstructorLoader") or target not in shapes:
                continue
            if shapes[target]["publicNoArgConstructor"]:
                typed_roots.add(target)
            elif diagnostics is not None:
                diagnostics.append({"code": "CONFIG_NO_PUBLIC_NOARG", "severity": "warning",
                                    "location": shape["name"], "target": target})
    if diagnostics is not None:
        diagnostics.extend({"code": "TYPED_GSON_CONFIG", "severity": "fix", "target": target}
                           for target in sorted(typed_roots))
    return _merge(config_entries(shapes, sorted(yacl_config_roots(shapes)),
                                 open_roots=[*roots, *sorted(json_config_roots(shapes) | typed_roots)]),
                  [*member_entries(shapes, sites), *forname_entries(shapes, forname),
                   *override_entries(shapes),
                   *framework_config_entries(shapes, config_roots)])
