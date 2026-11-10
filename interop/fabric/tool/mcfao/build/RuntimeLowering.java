package mcfao.build;

import java.util.List;
import java.util.Set;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.AnnotationNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.InsnNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;

final class RuntimeLowering implements Opcodes {
    private static final String LOADER = "net/fabricmc/loader/api/FabricLoader";
    private static final String EVENTS = "net/fabricmc/fabric/impl/base/event/EventFactoryImpl";
    private static final String EVENTS_SHA256 = "065be26b910ddcf78f27e48d2808eb7ecbacfbcdc38292459ca2c8f496ae7d79";
    private static final Set<String> ACCESSOR_ANNOTATIONS = Set.of(
            "Lorg/spongepowered/asm/mixin/gen/Accessor;", "Lorg/spongepowered/asm/mixin/gen/Invoker;");

    private RuntimeLowering() {}

    static boolean isAccessorInterface(ClassNode node) {
        return (node.access & ACC_INTERFACE) != 0
                && hasAnnotation(node.visibleAnnotations, node.invisibleAnnotations,
                        Set.of("Lorg/spongepowered/asm/mixin/Mixin;"))
                && !node.methods.isEmpty()
                && node.methods.stream().allMatch(method -> (method.access & ACC_ABSTRACT) != 0
                        && hasAnnotation(method.visibleAnnotations, method.invisibleAnnotations, ACCESSOR_ANNOTATIONS));
    }

    private static boolean hasAnnotation(List<AnnotationNode> visible, List<AnnotationNode> invisible,
            Set<String> descriptors) {
        return (visible != null && visible.stream().anyMatch(a -> descriptors.contains(a.desc)))
                || (invisible != null && invisible.stream().anyMatch(a -> descriptors.contains(a.desc)));
    }

    static void lowerQueries(ClassNode node, Set<String> loadedIds, List<String> adaptations) {
        for (var method : node.methods) {
            for (var instruction : method.instructions.toArray()) {
                if (!(instruction instanceof MethodInsnNode instance)
                        || !instance.owner.equals(LOADER) || !instance.name.equals("getInstance")
                        || !instance.desc.equals("()L" + LOADER + ";") || instance.getOpcode() != INVOKESTATIC) continue;
                var next = instance.getNext();
                String location = node.name + "#" + method.name + " ";
                if (isQuery(next, "isDevelopmentEnvironment", "()Z")) {
                    method.instructions.set(instance, new InsnNode(ICONST_0));
                    method.instructions.remove(next);
                    adaptations.add(location + "isDevelopmentEnvironment=false");
                } else if (isQuery(next, "getEnvironmentType", "()Lnet/fabricmc/api/EnvType;")) {
                    method.instructions.set(instance, new FieldInsnNode(GETSTATIC, "net/fabricmc/api/EnvType",
                            "CLIENT", "Lnet/fabricmc/api/EnvType;"));
                    method.instructions.remove(next);
                    adaptations.add(location + "getEnvironmentType=CLIENT");
                } else if (next instanceof LdcInsnNode constant && constant.cst instanceof String id
                        && isQuery(next.getNext(), "isModLoaded", "(Ljava/lang/String;)Z")) {
                    boolean loaded = loadedIds.contains(id);
                    method.instructions.set(instance, new InsnNode(loaded ? ICONST_1 : ICONST_0));
                    method.instructions.remove(next.getNext());
                    method.instructions.remove(next);
                    adaptations.add(location + "isModLoaded(" + id + ")=" + loaded);
                }
            }
            for (var instruction : method.instructions) {
                if (instruction instanceof MethodInsnNode call && call.owner.startsWith("net/fabricmc/loader/")) {
                    throw new IllegalArgumentException("Unsupported runtime Loader call " + node.name + "#"
                            + method.name + " -> " + call.owner + "." + call.name + call.desc);
                }
            }
        }
    }

    private static boolean isQuery(org.objectweb.asm.tree.AbstractInsnNode instruction, String name, String descriptor) {
        return instruction instanceof MethodInsnNode call && call.owner.equals(LOADER)
                && call.name.equals(name) && call.desc.equals(descriptor) && call.getOpcode() == INVOKEINTERFACE;
    }

    static void removeUnusedEventProxy(String mod, String sourceHash, ClassNode node, List<String> adaptations) {
        if (!mod.equals("fabric-api-base") || !node.name.equals(EVENTS) || !sourceHash.equals(EVENTS_SHA256)) return;
        // This exact upstream class has no references to the private proxy helper.
        // Retain createArrayBacked and its normal invoker factory unchanged.
        int count = node.methods.size();
        node.methods.removeIf(method -> (method.access & ACC_PRIVATE) != 0
                && (method.name.equals("buildEmptyInvoker") || method.name.equals("lambda$buildEmptyInvoker$0")));
        if (count - node.methods.size() != 2) throw new IllegalStateException("Unexpected Fabric API event factory");
        adaptations.add(node.name + " removed two unused private dynamic-proxy methods");
    }
}
