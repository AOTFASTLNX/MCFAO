package mcfao.build;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.InvokeDynamicInsnNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.analysis.Analyzer;
import org.objectweb.asm.tree.analysis.AnalyzerException;
import org.objectweb.asm.tree.analysis.BasicInterpreter;
import org.objectweb.asm.tree.analysis.BasicValue;

/** Bounded constant propagation for classpath resource lookups. It never executes Mod code. */
final class ResourceLookup implements Opcodes {
    record Site(String method, String api, String path) {}
    private static final int MAX_PATH_LENGTH = 1024;
    private static final String CLASS = "java/lang/Class";
    private static final String LOADER = "java/lang/ClassLoader";
    private static final String PACK_RESOURCES = "mcfao/aot/ClasspathPackResources";

    static int lowerPackStreams(ClassNode owner) {
        int changed = 0;
        for (var method : owner.methods) {
            for (var instruction : method.instructions) {
                if (!(instruction instanceof MethodInsnNode call) || call.getOpcode() != INVOKEVIRTUAL
                        || !call.owner.equals(CLASS) || !call.name.equals("getResourceAsStream")
                        || !call.desc.equals("(Ljava/lang/String;)Ljava/io/InputStream;")) continue;
                call.setOpcode(INVOKESTATIC);
                call.owner = PACK_RESOURCES;
                call.name = "open";
                call.desc = "(Ljava/lang/Class;Ljava/lang/String;)Ljava/io/InputStream;";
                changed++;
            }
        }
        return changed;
    }

    private ResourceLookup() {}

    static List<Site> scan(ClassNode owner) throws AnalyzerException {
        var result = new ArrayList<Site>();
        for (var method : owner.methods) {
            if (method.instructions.size() == 0) continue;
            var instructions = method.instructions.toArray();
            if (java.util.Arrays.stream(instructions).noneMatch(ResourceLookup::isLookup)) continue;
            var frames = new Analyzer<>(new Constants()).analyzeAndComputeMaxs(owner.name, method);
            for (int index = 0; index < instructions.length; index++) {
                if (!isLookup(instructions[index]) || frames[index] == null) continue;
                var call = (MethodInsnNode) instructions[index];
                var frame = frames[index];
                int size = frame.getStackSize();
                Object argument = constant(frame.getStack(size - 1));
                String path = null;
                if (argument instanceof String literal) {
                    if (call.owner.equals(CLASS)) {
                        if (literal.startsWith("/")) {
                            path = literal.substring(1);
                        } else if (constant(frame.getStack(size - 2)) instanceof Type declaring) {
                            String name = declaring.getInternalName();
                            path = name.substring(0, name.lastIndexOf('/') + 1) + literal;
                        }
                    } else if (call.getOpcode() == INVOKESTATIC
                            || constant(frame.getStack(size - 2)) == Loader.CLASSPATH) {
                        path = literal;
                    }
                }
                result.add(new Site(method.name + method.desc, call.owner + "." + call.name, path));
            }
        }
        return result;
    }

    private static boolean isLookup(AbstractInsnNode instruction) {
        if (!(instruction instanceof MethodInsnNode call) || !call.owner.equals(CLASS) && !call.owner.equals(LOADER)) {
            return false;
        }
        boolean system = call.owner.equals(LOADER) && call.getOpcode() == INVOKESTATIC;
        if (!system && call.getOpcode() != INVOKEVIRTUAL) return false;
        String prefix = system ? "getSystemResource" : "getResource";
        return call.name.equals(prefix) && call.desc.equals("(Ljava/lang/String;)Ljava/net/URL;")
                || call.name.equals(prefix + "AsStream") && call.desc.equals("(Ljava/lang/String;)Ljava/io/InputStream;")
                || call.owner.equals(LOADER) && call.name.equals(prefix + "s")
                && call.desc.equals("(Ljava/lang/String;)Ljava/util/Enumeration;");
    }

    private enum Loader { CLASSPATH }

    private static Object constant(BasicValue value) {
        return value instanceof Constant known ? known.value : null;
    }

    private static final class Constant extends BasicValue {
        final Object value;

        Constant(BasicValue type, Object value) {
            super(type.getType());
            this.value = value;
        }

        @Override public boolean equals(Object other) {
            return other instanceof Constant known && super.equals(other) && value.equals(known.value);
        }

        @Override public int hashCode() {
            return Objects.hash(super.hashCode(), value);
        }
    }

    private static final class Constants extends BasicInterpreter {
        Constants() { super(ASM9); }

        @Override public BasicValue newOperation(AbstractInsnNode insn) throws AnalyzerException {
            var base = super.newOperation(insn);
            if (insn instanceof LdcInsnNode ldc && (ldc.cst instanceof String text && text.length() <= MAX_PATH_LENGTH
                    || ldc.cst instanceof Type type && type.getSort() == Type.OBJECT)) {
                return new Constant(base, ldc.cst);
            }
            return base;
        }

        @Override public BasicValue naryOperation(AbstractInsnNode insn, List<? extends BasicValue> values)
                throws AnalyzerException {
            var base = super.naryOperation(insn, values);
            if (insn instanceof MethodInsnNode call) {
                if (call.owner.equals(CLASS) && call.name.equals("getClassLoader")
                        && call.desc.equals("()Ljava/lang/ClassLoader;") && constant(values.getFirst()) instanceof Type) {
                    return new Constant(base, Loader.CLASSPATH);
                }
                if (call.owner.equals(LOADER) && call.name.equals("getSystemClassLoader")
                        && call.desc.equals("()Ljava/lang/ClassLoader;") && call.getOpcode() == INVOKESTATIC) {
                    return new Constant(base, Loader.CLASSPATH);
                }
                if (call.owner.equals("java/lang/String") && call.name.equals("concat")
                        && call.desc.equals("(Ljava/lang/String;)Ljava/lang/String;")
                        && constant(values.get(0)) instanceof String left && constant(values.get(1)) instanceof String right
                        && left.length() + right.length() <= MAX_PATH_LENGTH) {
                    return new Constant(base, left + right);
                }
            }
            if (insn instanceof InvokeDynamicInsnNode dynamic
                    && dynamic.bsm.getOwner().equals("java/lang/invoke/StringConcatFactory")) {
                String value = concat(dynamic, values);
                if (value != null) return new Constant(base, value);
            }
            return base;
        }

        private static String concat(InvokeDynamicInsnNode dynamic, List<? extends BasicValue> values) {
            String recipe = switch (dynamic.bsm.getName()) {
                case "makeConcat" -> "\u0001".repeat(values.size());
                case "makeConcatWithConstants" -> dynamic.bsmArgs.length != 0
                        && dynamic.bsmArgs[0] instanceof String text ? text : null;
                default -> null;
            };
            if (recipe == null || recipe.length() > MAX_PATH_LENGTH) return null;
            var result = new StringBuilder();
            int argument = 0;
            int bootstrap = 1;
            for (int i = 0; i < recipe.length(); i++) {
                char c = recipe.charAt(i);
                if (c == 1 || c == 2) {
                    Object value = c == 1
                            ? (argument < values.size() ? constant(values.get(argument++)) : null)
                            : (bootstrap < dynamic.bsmArgs.length ? dynamic.bsmArgs[bootstrap++] : null);
                    if (!(value instanceof String text)) return null;
                    result.append(text);
                } else {
                    result.append(c);
                }
                if (result.length() > MAX_PATH_LENGTH) return null;
            }
            return argument == values.size() ? result.toString() : null;
        }

        @Override public BasicValue merge(BasicValue left, BasicValue right) {
            if (left instanceof Constant && left.equals(right)) return left;
            var merged = super.merge(new BasicValue(left.getType()), new BasicValue(right.getType()));
            if (!(left instanceof Constant) && !(right instanceof Constant)) return merged;
            // Frame.merge compares its result to the old value. BasicValue.equals would
            // compare only the type and accidentally retain a constant across different paths.
            return new BasicValue(merged.getType()) {
                @Override public boolean equals(Object other) {
                    return !(other instanceof Constant) && super.equals(other);
                }
            };
        }
    }
}
