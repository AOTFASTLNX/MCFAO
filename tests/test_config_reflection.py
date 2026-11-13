import io
from pathlib import Path
import struct
import sys
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from config_reflection import (class_shape, config_entries, reflection_from_jar,
                              json_config_roots, yacl_config_roots)


def shape(**overrides):
    """One scanned-class record, defaulted so a test only states what it is about."""
    record = {"name": "mod/Unnamed", "parent": "java/lang/Object", "interfaces": [],
              "fieldTypes": [], "access": 0x21, "declaredFields": [], "methods": [],
              "constructors": [], "reflection": [], "forName": [],
              "factories": [], "classLiterals": []}
    record.update(overrides)
    return record


def u2(value):
    return struct.pack(">H", value)


def class_bytes(name, parent="java/lang/Object", interfaces=(), fields=(), methods=(),
                constructors=()):
    pool = []

    def utf(value):
        raw = value.encode()
        pool.append(b"\x01" + u2(len(raw)) + raw)
        return len(pool)

    def cls(value):
        if value is None:
            return 0
        index = utf(value)
        pool.append(b"\x07" + u2(index))
        return len(pool)

    own, base = cls(name), cls(parent)
    supers = [cls(value) for value in interfaces]
    members = []
    for flags, descriptor, signature in fields:
        indices = [flags, utf("field" + str(len(members))), utf(descriptor)]
        attributes = b""
        if signature:
            key, value = utf("Signature"), utf(signature)
            attributes = u2(key) + struct.pack(">I", 2) + u2(value)
        members.append(b"".join(map(u2, indices)) + u2(bool(signature)) + attributes)
    method_entries = [b"".join(map(u2, (1, utf(method), utf("()V")))) + u2(0)
                      for method in methods]
    method_entries += [b"".join(map(u2, (1, utf("<init>"), utf(descriptor)))) + u2(0)
                       for descriptor in constructors]
    return (b"\xca\xfe\xba\xbe" + u2(0) + u2(69) + u2(len(pool) + 1) + b"".join(pool)
            + u2(0x21) + u2(own) + u2(base) + u2(len(supers)) + b"".join(map(u2, supers))
            + u2(len(members)) + b"".join(members)
            + u2(len(method_entries)) + b"".join(method_entries) + u2(0))


class ConfigReflectionTests(unittest.TestCase):
    def test_parse_serializable_fields_and_generic_members(self):
        data = class_bytes("mod/config/Data", interfaces=["me/shedaniel/autoconfig/ConfigData"],
                           fields=[(0, "Ljava/util/List;", "Ljava/util/List<Lmod/config/Mode;>;"),
                                   (0x8, "Lmod/config/Static;", None),
                                   (0x80, "Lmod/config/Transient;", None)])
        shape = class_shape(data)
        self.assertEqual(shape["name"], "mod/config/Data")
        self.assertEqual(shape["fieldTypes"], ["java/util/List", "mod/config/Mode"])

    def test_inheritance_nested_config_and_game_boundary(self):
        fixtures = [
            class_bytes("mod/config/Base", interfaces=["me/shedaniel/autoconfig/ConfigData"]),
            class_bytes("mod/config/Data", parent="mod/config/Base", fields=[
                (0, "[Lmod/config/Mode;", None), (0, "Lnet/minecraft/Game;", None)]),
            class_bytes("mod/config/Mode"), class_bytes("net/minecraft/Game"),
            class_bytes("mod/Unrelated"),
        ]
        shapes = {shape["name"]: shape for shape in map(class_shape, fixtures)}
        names = [entry["name"] for entry in config_entries(shapes)]
        self.assertEqual(names, ["mod.config.Base", "mod.config.Data", "mod.config.Mode"])

    def test_cycles_do_not_hang_or_register_unrelated_types(self):
        shapes = {}
        for data in [class_bytes("mod/A", parent="mod/B"), class_bytes("mod/B", parent="mod/A")]:
            shape = class_shape(data)
            shapes[shape["name"]] = shape
        self.assertEqual(config_entries(shapes), [])

    def test_jar_scan_rejects_class_path_mismatch(self):
        memory = io.BytesIO()
        with zipfile.ZipFile(memory, "w") as jar:
            jar.writestr("other.class", class_bytes("mod/Data"))
        memory.seek(0)
        with self.assertRaisesRegex(ValueError, "path mismatch"):
            reflection_from_jar(memory)

    def test_truncated_class_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Truncated"):
            class_shape(class_bytes("mod/Data")[:20])

    def test_serialization_roots_register_non_autoconfig_data(self):
        memory = io.BytesIO()
        with zipfile.ZipFile(memory, "w") as jar:
            jar.writestr("mod/config/Data.class", class_bytes("mod/config/Data"))
            jar.writestr("mod/Other.class", class_bytes("mod/Other"))
            jar.writestr("META-INF/native-image/mcfao/fabric/serialization-roots.json",
                         '["mod/config/Data"]')
        memory.seek(0)
        self.assertEqual([entry["name"] for entry in reflection_from_jar(memory)],
                         ["mod.config.Data"])

    def test_records_include_reflective_accessors(self):
        record = class_shape(class_bytes("mod/config/Stamp", parent="java/lang/Record"))
        entries = config_entries({record["name"]: record}, [record["name"]])
        self.assertTrue(entries[0]["allDeclaredMethods"])

    def test_types_without_a_no_arg_constructor_get_unsafe_allocation(self):
        # Gson falls back to Unsafe when a config class only has argument-taking constructors,
        # and the closed world refuses that unless the type is registered as unsafe-allocatable.
        shapes = {}
        for data in (class_bytes("mod/config/Plain",
                                 interfaces=["me/shedaniel/autoconfig/ConfigData"],
                                 constructors=["()V"]),
                     class_bytes("mod/config/Args",
                                 interfaces=["me/shedaniel/autoconfig/ConfigData"],
                                 constructors=["(I)V"]),
                     class_bytes("mod/config/Guarded",
                                 interfaces=["me/shedaniel/autoconfig/ConfigData"],
                                 constructors=["()V", "(I)V"])):
            shape = class_shape(data)
            shapes[shape["name"]] = shape
        entries = {entry["name"]: entry for entry in config_entries(shapes)}
        self.assertNotIn("unsafeAllocated", entries["mod.config.Plain"])
        self.assertNotIn("unsafeAllocated", entries["mod.config.Guarded"])
        self.assertTrue(entries["mod.config.Args"]["unsafeAllocated"])

    def test_sodium_dependency_injection_implementations_are_registered(self):
        import json
        root = Path(__file__).resolve().parents[1]
        config = json.loads((root / "compiler/reflection-config.json").read_text())
        by_name = {entry["name"]: entry for entry in config}
        expected = (
            "net.caffeinemc.mods.sodium.client.render.chunk.BlockEntityRenderHandlerImpl",
            "net.caffeinemc.mods.sodium.client.render.texture.SpriteUtilImpl",
            "net.caffeinemc.mods.sodium.client.render.vertex.VertexFormatRegistryImpl",
            "net.caffeinemc.mods.sodium.client.render.vertex.serializers.VertexSerializerRegistryImpl",
        )
        for name in expected:
            self.assertIn(name, by_name)
            self.assertTrue(by_name[name].get("allDeclaredConstructors"),
                            f"{name} needs a reflective no-arg constructor")
        jar = root / ("artifacts/mcfao/incompatible-01/"
                      "sodium-fabric-0.8.11+mc26.1.2.jar")
        if jar.is_file():
            with zipfile.ZipFile(jar) as archive:
                entries = set(archive.namelist())
            for name in expected:
                self.assertIn(name.replace(".", "/") + ".class", entries)

    def test_yacl_config_roots_require_handler_field_and_clinit(self):
        handler = "Ldev/isxander/yacl3/config/v2/api/ConfigClassHandler;"
        shapes = {
            "mod/YaclOptions": class_shape(class_bytes(
                "mod/YaclOptions", fields=[(0x8, handler, None), (0, "Z", None)],
                methods=["<clinit>"])),
            "mod/PlainManager": class_shape(class_bytes(
                "mod/PlainManager", fields=[(0, "Ljava/lang/String;", None)],
                methods=["<clinit>"])),
            "mod/HandlerOnly": class_shape(class_bytes(
                "mod/HandlerOnly", fields=[(0x8, handler, None)])),
        }
        roots = yacl_config_roots(shapes)
        self.assertEqual(roots, {"mod/YaclOptions"})
        entries = {entry["name"]: entry
                   for entry in config_entries(shapes, sorted(roots))}
        self.assertTrue(entries["mod.YaclOptions"]["allDeclaredConstructors"])
        self.assertTrue(entries["mod.YaclOptions"]["allDeclaredFields"])
        self.assertNotIn("mod.PlainManager", entries)
        self.assertNotIn("mod.HandlerOnly", entries)

    def test_yacl_config_is_registered_in_shipped_metal_jar(self):
        root = Path(__file__).resolve().parents[1]
        jars = sorted(root.glob(
            "artifacts/mcfao/fabric-pack-*/metal-injection/*/product/client-26.1.2-metal.jar"))
        if not jars:
            self.skipTest("No shipped metal jar available")
        entries = {entry["name"]: entry for entry in reflection_from_jar(jars[-1])}
        config = entries.get("dev.isxander.yacl3.platform.YACLConfig")
        self.assertIsNotNone(config, "YACL v2 config handler must be reflectively registered")
        self.assertTrue(config["allDeclaredConstructors"])
        self.assertTrue(config["allDeclaredFields"])


def lookup_bytes(caller, target, member, *, sink="getDeclaredMethod", owner="java/lang/Class",
                 descriptor="(Ljava/lang/String;[Ljava/lang/Class;)Ljava/lang/reflect/Method;",
                 opcode=0xB6):
    """A class whose ``<clinit>`` performs ``Class.getDeclaredMethod``-style lookup on constants."""
    pool = []

    def utf(value):
        raw = value.encode()
        pool.append(b"\x01" + u2(len(raw)) + raw)
        return len(pool)

    def cls(value):
        index = utf(value)
        pool.append(b"\x07" + u2(index))
        return len(pool)

    def string(value):
        index = utf(value)
        pool.append(b"\x08" + u2(index))
        return len(pool)

    own, base = cls(caller), cls("java/lang/Object")
    target_index = cls(target)
    member_index = string(member)
    owner_index = cls(owner)
    name_index, descriptor_index = utf(sink), utf(descriptor)
    name_and_type = len(pool) + 1
    pool.append(b"\x0c" + u2(name_index) + u2(descriptor_index))
    reference_index = len(pool) + 1
    pool.append(b"\x0a" + u2(owner_index) + u2(name_and_type))
    code_name, clinit, void = utf("Code"), utf("<clinit>"), utf("()V")
    code = bytes([0x12, target_index, 0x12, member_index, opcode]) + u2(reference_index) + b"\xb1"
    body = u2(2) + u2(0) + struct.pack(">I", len(code)) + code + u2(0) + u2(0)
    method = (b"".join(map(u2, (0x8, clinit, void))) + u2(1) + u2(code_name)
              + struct.pack(">I", len(body)) + body)
    return (b"\xca\xfe\xba\xbe" + u2(0) + u2(69) + u2(len(pool) + 1) + b"".join(pool)
            + u2(0x21) + u2(own) + u2(base) + u2(0) + u2(0)
            + u2(1) + method + u2(0))


class ReflectiveMemberScanTests(unittest.TestCase):
    def test_lookup_on_a_class_literal_is_recorded(self):
        shape = class_shape(lookup_bytes("mod/Caller", "net/minecraft/RenderType", "create"))
        self.assertEqual(shape["reflection"],
                         [{"target": "net/minecraft/RenderType", "member": "create",
                           "kind": "method"}])

    def test_field_lookup_and_wrapper_returning_a_field_are_recorded(self):
        direct = class_shape(lookup_bytes(
            "mod/Caller", "net/minecraft/ModelPart", "cubes", sink="getDeclaredField",
            descriptor="(Ljava/lang/String;)Ljava/lang/reflect/Field;"))
        wrapped = class_shape(lookup_bytes(
            "mod/Caller", "net/minecraft/ModelPart", "children", sink="getFieldReflection",
            owner="mod/Reflect", opcode=0xB8,
            descriptor="(Ljava/lang/Class;Ljava/lang/String;)Ljava/lang/reflect/Field;"))
        self.assertEqual([site["kind"] for site in direct["reflection"]], ["field"])
        self.assertEqual([site["member"] for site in wrapped["reflection"]], ["children"])

    def test_platform_callers_are_not_scanned(self):
        shape = class_shape(lookup_bytes("net/minecraft/Patched", "net/minecraft/RenderType",
                                         "create"))
        self.assertEqual(shape["reflection"], [])

    def test_jar_scan_registers_members_only_for_present_targets(self):
        memory = io.BytesIO()
        with zipfile.ZipFile(memory, "w") as jar:
            jar.writestr("mod/Target.class", class_bytes("mod/Target"))
            jar.writestr("mod/Caller.class",
                         lookup_bytes("mod/Caller", "mod/Target", "create"))
            jar.writestr("mod/Missing.class",
                         lookup_bytes("mod/Missing", "mod/Absent", "gone"))
        memory.seek(0)
        entries = {entry["name"]: entry for entry in reflection_from_jar(memory)}
        self.assertEqual(entries["mod.Target"]["methods"], [{"name": "create"}])
        self.assertNotIn("mod.Absent", entries)

    def test_framework_config_groups_register_their_field_metadata(self):
        memory = io.BytesIO()
        with zipfile.ZipFile(memory, "w") as jar:
            jar.writestr("mod/Config.class", class_bytes("mod/Config"))
            jar.writestr("mod/Config$Backpack.class", class_bytes("mod/Config$Backpack"))
            jar.writestr("mod/Unrelated.class", class_bytes("mod/Unrelated"))
            jar.writestr("META-INF/native-image/mcfao/fabric/framework-config-roots.json",
                         '["mod/Config"]')
        memory.seek(0)
        entries = {entry["name"]: entry for entry in reflection_from_jar(memory)}
        self.assertTrue(entries["mod.Config"]["allDeclaredFields"])
        self.assertTrue(entries["mod.Config$Backpack"]["allDeclaredFields"])
        self.assertNotIn("mod.Unrelated", entries)

    def test_class_analysis_queries_expose_the_overrides_they_ask_about(self):
        memory = io.BytesIO()
        with zipfile.ZipFile(memory, "w") as jar:
            jar.writestr("mod/Minecart.class",
                         class_bytes("mod/Minecart", methods=("canCollideWith", "tick")))
            jar.writestr("mod/Plain.class", class_bytes("mod/Plain", methods=("tick",)))
        memory.seek(0)
        entries = {entry["name"]: entry for entry in reflection_from_jar(memory)}
        self.assertEqual(entries["mod.Minecart"]["methods"], [{"name": "canCollideWith"}])
        self.assertNotIn("mod.Plain", entries)

    def test_config_entries_keep_one_object_per_class(self):
        memory = io.BytesIO()
        with zipfile.ZipFile(memory, "w") as jar:
            jar.writestr("mod/Config.class",
                         class_bytes("mod/Config", interfaces=["me/shedaniel/autoconfig/ConfigData"],
                                     fields=[(0, "Z", None)]))
            jar.writestr("mod/Caller.class",
                         lookup_bytes("mod/Caller", "mod/Config", "value"))
        memory.seek(0)
        entries = reflection_from_jar(memory)
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0]["allDeclaredFields"])

    def test_json_config_roots_need_both_a_class_literal_and_a_factory(self):
        shapes = {
            # Names the type and builds it: the Gson loader receives both a Class and a Supplier.
            "mod/Holder": shape(factories=["mod/Config"], classLiterals=["mod/Config"]),
            "mod/LiteralOnly": shape(classLiterals=["mod/Config"]),
            "mod/FactoryOnly": shape(factories=["mod/Config"]),
            "mod/Config": shape(constructors=["()V"], fieldTypes=["mod/Options"]),
            "mod/Options": shape(constructors=["()V"]),
        }
        self.assertEqual(json_config_roots(shapes), {"mod/Config"})
        entries = {entry["name"]: entry
                   for entry in config_entries(shapes, sorted(json_config_roots(shapes)))}
        self.assertTrue(entries["mod.Config"]["allDeclaredConstructors"])
        self.assertTrue(entries["mod.Config"]["allDeclaredFields"])
        self.assertTrue(entries["mod.Options"]["allDeclaredFields"],
                        "a field type inside the config package carries serialized state too")

    def test_json_config_roots_follow_a_handler_that_learns_its_type_from_a_supplier(self):
        shapes = {
            # TConfigHandler takes the factory and reads the class off the built instance.
            "mod/Mod": shape(declaredFields=["Ltraben/tconfig/TConfigHandler;"],
                             factories=["mod/Config", "mod/Extra"]),
            "mod/Plain": shape(declaredFields=["Ljava/lang/String;"], factories=["mod/Config"]),
            "mod/Config": shape(constructors=["()V"]),
            "mod/Extra": shape(constructors=["()V"]),
        }
        self.assertEqual(json_config_roots(shapes), {"mod/Config", "mod/Extra"})

    def test_open_json_roots_cross_packages_but_stop_at_the_platform(self):
        shapes = {
            "mod/config/Config": shape(constructors=["()V"],
                                       fieldTypes=["mod/pocket/Pocket",
                                                   "net/minecraft/world/item/ItemStack"]),
            "mod/pocket/Pocket": shape(constructors=["(I)V"]),
            "net/minecraft/world/item/ItemStack": shape(constructors=["()V"]),
        }
        entries = {entry["name"]: entry for entry in config_entries(shapes, open_roots=["mod/config/Config"])}
        self.assertTrue(entries["mod.pocket.Pocket"]["allDeclaredFields"],
                        "a JSON document reaches field types outside its own package")
        self.assertTrue(entries["mod.pocket.Pocket"]["unsafeAllocated"],
                        "no no-arg constructor means Gson allocates it with Unsafe")
        self.assertNotIn("net.minecraft.world.item.ItemStack", entries,
                         "platform types must not drag the game graph in")

    def test_closed_seeds_stay_inside_their_package(self):
        shapes = {
            "mod/config/Config": shape(constructors=["()V"],
                                       fieldTypes=["mod/other/Helper"]),
            "mod/other/Helper": shape(constructors=["()V"]),
        }
        entries = {entry["name"]: entry for entry in config_entries(shapes, ["mod/config/Config"])}
        self.assertNotIn("mod.other.Helper", entries)

    def test_json_configs_are_registered_in_shipped_metal_jar(self):
        root = Path(__file__).resolve().parents[1]
        jars = sorted(root.glob(
            "artifacts/mcfao/fabric-pack-*/metal-injection/*/product/client-26.1.2-metal.jar"))
        if not jars:
            self.skipTest("No shipped metal jar available")
        entries = {entry["name"]: entry for entry in reflection_from_jar(jars[-1])}
        for name in ("traben.entity_texture_features.config.ETFConfig",
                     "traben.entity_texture_features.config.screens."
                     "ETFConfigScreenWarnings$WarningConfig",
                     "com.aizistral.nochatreports.common.config.NCRConfigCommon"):
            entry = entries.get(name)
            self.assertIsNotNone(entry, f"{name} must be registered for Gson")
            self.assertTrue(entry["allDeclaredConstructors"], f"{name} needs its no-arg constructor")
            self.assertTrue(entry["allDeclaredFields"], f"{name} needs its declared fields")


def forname_bytes(caller, target, suffix=None, *, literal=False, dynamic=False):
    """A class whose ``<clinit>`` calls ``Class.forName`` on a name built one of three ways.

    ``suffix`` builds ``target.getName() + suffix`` through ``makeConcatWithConstants`` -
    the mrcrayfish nested-class pattern, where no constant in the pool contains the looked-up
    name. ``literal`` passes a dotted string constant. ``dynamic`` passes a variable, which
    the scanner must leave alone.
    """
    pool = []

    def utf(value):
        raw = value.encode()
        pool.append(b"\x01" + u2(len(raw)) + raw)
        return len(pool)

    def cls(value):
        index = utf(value)
        pool.append(b"\x07" + u2(index))
        return len(pool)

    def string(value):
        index = utf(value)
        pool.append(b"\x08" + u2(index))
        return len(pool)

    def nat(name, descriptor):
        name_index, descriptor_index = utf(name), utf(descriptor)
        pool.append(b"\x0c" + u2(name_index) + u2(descriptor_index))
        return len(pool)

    def methodref(owner, nat_index):
        owner_index = cls(owner)
        pool.append(b"\x0a" + u2(owner_index) + u2(nat_index))
        return len(pool)

    own, base = cls(caller), cls("java/lang/Object")
    target_index = cls(target)
    getname = methodref("java/lang/Class", nat("getName", "()Ljava/lang/String;"))
    forname = methodref("java/lang/Class",
                        nat("forName", "(Ljava/lang/String;)Ljava/lang/Class;"))
    concat_nat = nat("makeConcatWithConstants", "(Ljava/lang/String;)Ljava/lang/String;")
    indy = len(pool) + 1
    pool.append(struct.pack(">BH", 18, 0) + u2(concat_nat))
    recipe = string("\x01" + (suffix or "")) if suffix is not None else None
    literal_index = string(target.replace("/", ".")) if literal else None
    code_name, clinit, void = utf("Code"), utf("<clinit>"), utf("()V")
    if suffix is not None:
        code = (bytes([0x13]) + u2(target_index)
                + bytes([0xb6]) + u2(getname)
                + bytes([0xba]) + u2(indy) + u2(0)
                + bytes([0xb8]) + u2(forname) + b"\xb1")
    elif literal:
        code = (bytes([0x12, literal_index]) + bytes([0xb8]) + u2(forname) + b"\xb1")
    elif dynamic:
        code = b"\x2a" + bytes([0xb8]) + u2(forname) + b"\xb1"
    else:
        raise ValueError("pick a variant")
    body = u2(1) + u2(1) + struct.pack(">I", len(code)) + code + u2(0) + u2(0)
    method = (b"".join(map(u2, (0x8, clinit, void))) + u2(1) + u2(code_name)
              + struct.pack(">I", len(body)) + body)
    bootstrap = u2(1) + u2(forname) + u2(1) + u2(recipe or 0)
    bootstrap_name = utf("BootstrapMethods")
    attributes = u2(1) + u2(bootstrap_name) + struct.pack(">I", len(bootstrap)) + bootstrap
    return (b"\xca\xfe\xba\xbe" + u2(0) + u2(69) + u2(len(pool) + 1) + b"".join(pool)
            + u2(0x21) + u2(own) + u2(base) + u2(0) + u2(0)
            + u2(1) + method + attributes)


class ForNameScanTests(unittest.TestCase):
    def test_concatenated_nested_class_name_is_resolved(self):
        shape = class_shape(forname_bytes(
            "com/mrcrayfish/Framework",
            "net/minecraft/client/resources/model/cuboid/CuboidModelElement",
            "$Deserializer"))
        self.assertEqual(shape["forName"],
                         [{"target": "net/minecraft/client/resources/model/cuboid/"
                                     "CuboidModelElement$Deserializer", "forName": True}])

    def test_string_literal_lookup_is_recorded(self):
        shape = class_shape(forname_bytes("mod/Caller", "mod/PlainTarget", literal=True))
        self.assertEqual(shape["forName"],
                         [{"target": "mod/PlainTarget", "forName": True}])

    def test_lookup_from_a_variable_is_skipped(self):
        shape = class_shape(forname_bytes("mod/Caller", "mod/AnyTarget", dynamic=True))
        self.assertEqual(shape["forName"], [])

    def test_platform_callers_are_not_scanned(self):
        shape = class_shape(forname_bytes(
            "net/minecraft/Patched",
            "net/minecraft/client/resources/model/cuboid/CuboidModelElement",
            "$Deserializer"))
        self.assertEqual(shape["forName"], [])

    def test_jar_scan_registers_constructors_only_for_present_targets(self):
        memory = io.BytesIO()
        with zipfile.ZipFile(memory, "w") as jar:
            jar.writestr("net/minecraft/Element$Deserializer.class",
                         class_bytes("net/minecraft/Element$Deserializer"))
            jar.writestr("com/Framework.class",
                         forname_bytes("com/Framework", "net/minecraft/Element",
                                       "$Deserializer"))
            jar.writestr("mod/Missing.class",
                         forname_bytes("mod/Missing", "mod/Absent", "$Helper"))
        memory.seek(0)
        entries = {entry["name"]: entry for entry in reflection_from_jar(memory)}
        self.assertTrue(entries["net.minecraft.Element$Deserializer"]["allDeclaredConstructors"])
        self.assertNotIn("mod.Absent$Helper", entries)

    def test_tableswitch_length_includes_the_full_header(self):
        # default(4) + low(4) + high(4) + two entries(8) after the opcode and padding.
        body = b"\xaa\x00\x00\x00" + b"\x00" * 12 + b"\x00" * 8
        from config_reflection import _instruction_length
        self.assertEqual(_instruction_length(body, 0), 20)
