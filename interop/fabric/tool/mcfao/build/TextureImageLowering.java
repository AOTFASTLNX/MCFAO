package mcfao.build;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.BitSet;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.objectweb.asm.Type;
import org.objectweb.asm.tree.*;
import org.objectweb.asm.tree.analysis.*;
import static org.objectweb.asm.Opcodes.*;

final class TextureImageLowering {
    private static final String IMAGE = "java/awt/image/BufferedImage";
    private static final String RASTER = "java/awt/image/Raster";
    private static final String MODEL = "java/awt/image/ColorModel";
    private static final String STREAM = "javax/imageio/stream/ImageInputStream";
    private static final String INPUT = "java/io/InputStream";
    private static final String TEXTURE = "mcfao/aot/TextureImage";
    private static final Map<String, String> REPLACEMENTS = Map.of(
            IMAGE, TEXTURE, RASTER, TEXTURE, MODEL, TEXTURE, STREAM, INPUT);

    private static final BasicValue RESOURCE_VALUE = marker("resource"), STREAM_VALUE = marker("stream"),
            IMAGE_VALUE = marker("image"), RASTER_VALUE = marker("raster"), MODEL_VALUE = marker("model"),
            MIXED_VALUE = marker("mixed"), COMPONENT_COUNT = marker("components"), THREE = marker("three");

    private static BasicValue marker(String name) {
        return new BasicValue(Type.getObjectType("mcfao/textureflow/" + name));
    }

    private static boolean tracked(BasicValue value) {
        return value == STREAM_VALUE || value == IMAGE_VALUE || value == RASTER_VALUE
                || value == MODEL_VALUE || value == MIXED_VALUE;
    }

    static void lower(ClassNode node, List<String> adaptations) {
        for (MethodNode method : node.methods) {
            if (!containsRead(method)) continue;
            var flow = new TextureFlow();
            var graph = new FlowGraph(flow, method.instructions.size());
            try {
                var frames = graph.analyze(node.name, method);
                if (!graph.preservesSampling(method, frames)) continue;
            } catch (AnalyzerException refused) {
                continue; // An unknown image shape stays on the classpath for diagnostics.
            }
            // Do not retag frames in a method that also uses an unrelated desktop image.
            boolean foreign = false;
            for (var insn : method.instructions) {
                if (insn instanceof MethodInsnNode call && desktop(call.owner, call.desc)
                        && !flow.pending.contains(call)
                        || insn instanceof FieldInsnNode field && desktop(field.owner, field.desc)
                        || insn instanceof TypeInsnNode type && desktop(type.desc, "")) {
                    foreign = true;
                    break;
                }
            }
            if (foreign || desktop("", method.desc)) continue;
            for (MethodInsnNode call : flow.pending) {
                if (create(call)) {
                    // Resource.open already leaves an InputStream on the stack.
                    method.instructions.remove(call);
                    continue;
                }
                if (wrapped(call)) call.name = "readWrapped";
                call.owner = call.owner.equals(STREAM) ? INPUT : TEXTURE;
                if (call.getOpcode() == INVOKEINTERFACE) call.setOpcode(INVOKEVIRTUAL);
                call.itf = false;
                call.desc = replaceTypes(call.desc);
            }
            for (var insn : method.instructions) {
                if (insn instanceof FrameNode frame) {
                    retag(frame.local);
                    retag(frame.stack);
                }
            }
            if (method.localVariables != null) {
                for (var local : method.localVariables) local.desc = replaceTypes(local.desc);
            }
            adaptations.add(node.name + "#" + method.name + " ios.texture.png-native-image.v1");
        }
    }

    private static boolean containsRead(MethodNode method) {
        for (var insn : method.instructions) {
            if (insn instanceof MethodInsnNode call && (create(call) || read(call))) return true;
        }
        return false;
    }

    private static boolean desktop(String owner, String desc) {
        return owner.startsWith("javax/imageio/") || owner.startsWith("java/awt/")
                || desc.contains("Ljavax/imageio/") || desc.contains("Ljava/awt/");
    }

    private static String replaceTypes(String descriptor) {
        for (var pair : REPLACEMENTS.entrySet()) {
            descriptor = descriptor.replace("L" + pair.getKey() + ";", "L" + pair.getValue() + ";");
        }
        return descriptor;
    }

    private static void retag(List<Object> frame) {
        if (frame == null) return;
        frame.replaceAll(value -> value instanceof String type ? REPLACEMENTS.getOrDefault(type, type) : value);
    }

    private static boolean call(MethodInsnNode call, int opcode, String owner, String name, String descriptor) {
        return call.getOpcode() == opcode && owner.equals(call.owner) && name.equals(call.name)
                && descriptor.equals(call.desc);
    }

    private static boolean create(MethodInsnNode call) {
        return call(call, INVOKESTATIC, "javax/imageio/ImageIO", "createImageInputStream",
                "(Ljava/lang/Object;)L" + STREAM + ";");
    }

    private static boolean read(MethodInsnNode call) {
        return call(call, INVOKESTATIC, "javax/imageio/ImageIO", "read", "(L" + INPUT + ";)L" + IMAGE + ";");
    }

    private static boolean wrapped(MethodInsnNode call) {
        // This existing helper has the same read-only contract with an explicit caller close.
        // Do not treat arbitrary helpers returning BufferedImage as interchangeable.
        return call(call, INVOKESTATIC, "xaero/lib/common/util/ImageIOUtils", "getImageThroughZipError",
                "(L" + STREAM + ";Ljava/lang/String;)L" + IMAGE + ";");
    }

    private static final class FlowGraph extends Analyzer<BasicValue> {
        private final List<Set<Integer>> successors = new ArrayList<>();
        private final TextureFlow flow;

        FlowGraph(TextureFlow flow, int size) {
            super(flow);
            this.flow = flow;
            for (int i = 0; i < size; i++) successors.add(new HashSet<>());
        }

        @Override protected void newControlFlowEdge(int from, int to) { successors.get(from).add(to); }
        @Override protected boolean newControlFlowExceptionEdge(int from, int to) {
            newControlFlowEdge(from, to);
            return true;
        }

        boolean preservesSampling(MethodNode method, Frame<BasicValue>[] frames) {
            if (flow.pending.stream().filter(call -> read(call) || wrapped(call)).count() != 1
                    || flow.wrap != flow.close) return false;
            var gray = new BitSet();
            var rgb = new BitSet();
            var grayBranch = new HashMap<Integer, Integer>();
            var rgbBranch = new HashMap<Integer, Integer>();
            var instructions = method.instructions.toArray();
            for (int i = 0; i < instructions.length; i++) {
                if (instructions[i] instanceof MethodInsnNode call && flow.pending.contains(call)) {
                    if (call.name.equals("getRGB")) rgb.set(i);
                    if (call.name.equals("getPixel")) gray.set(i);
                }
                if (instructions[i] instanceof JumpInsnNode jump && jump.getOpcode() == IF_ICMPGE && frames[i] != null) {
                    var frame = frames[i];
                    int top = frame.getStackSize();
                    if (frame.getStack(top - 2) == COMPONENT_COUNT && frame.getStack(top - 1) == THREE) {
                        grayBranch.put(i, i + 1);
                        rgbBranch.put(i, method.instructions.indexOf(jump.label));
                    }
                }
            }
            // ImageIO getRGB on grayscale can apply color-space conversion. We can only
            // replace shapes which prove grayscale is read as raw raster samples, and all
            // palette/RGB pixels as ARGB. Keep exception and other alternate paths in the proof.
            return !gray.isEmpty() && !rgb.isEmpty()
                    && !reachableWithout(grayBranch).intersects(gray)
                    && !reachableWithout(rgbBranch).intersects(rgb);
        }

        private BitSet reachableWithout(Map<Integer, Integer> blocked) {
            var seen = new BitSet();
            var todo = new ArrayDeque<Integer>();
            todo.add(0);
            while (!todo.isEmpty()) {
                int from = todo.removeFirst();
                if (seen.get(from)) continue;
                seen.set(from);
                for (int to : successors.get(from)) {
                    if (to != blocked.getOrDefault(from, -1)) todo.add(to);
                }
            }
            return seen;
        }
    }

    /** Track the image and stream through locals/branches; refuse any consumer outside the facade. */
    private static final class TextureFlow extends BasicInterpreter {
        final Set<MethodInsnNode> pending = new HashSet<>();
        boolean wrap, close;

        TextureFlow() { super(ASM9); }

        private void refuse(AbstractInsnNode insn) throws AnalyzerException {
            throw new AnalyzerException(insn, "Desktop image escapes the texture sampler");
        }

        @Override
        public BasicValue newOperation(AbstractInsnNode insn) throws AnalyzerException {
            if (insn.getOpcode() == ACONST_NULL) return new BasicValue(NULL_TYPE);
            if (insn.getOpcode() == ICONST_3) return THREE;
            return super.newOperation(insn);
        }

        @Override
        public BasicValue merge(BasicValue left, BasicValue right) {
            if (left.equals(right)) return left;
            if (left == BasicValue.UNINITIALIZED_VALUE || right == BasicValue.UNINITIALIZED_VALUE) {
                return BasicValue.UNINITIALIZED_VALUE;
            }
            if (tracked(left) && NULL_TYPE.equals(right.getType())) return left;
            if (tracked(right) && NULL_TYPE.equals(left.getType())) return right;
            if (tracked(left) || tracked(right)) return MIXED_VALUE;
            if (isCount(left) && isCount(right)) return BasicValue.INT_VALUE;
            return super.merge(left, right);
        }

        private boolean isCount(BasicValue value) {
            return value == COMPONENT_COUNT || value == THREE || value == BasicValue.INT_VALUE;
        }

        @Override
        public BasicValue unaryOperation(AbstractInsnNode insn, BasicValue value) throws AnalyzerException {
            if (tracked(value) && insn.getOpcode() != IFNULL && insn.getOpcode() != IFNONNULL) refuse(insn);
            return super.unaryOperation(insn, value);
        }

        @Override
        public BasicValue binaryOperation(AbstractInsnNode insn, BasicValue a, BasicValue b) throws AnalyzerException {
            if (tracked(a) || tracked(b)) refuse(insn);
            return super.binaryOperation(insn, a, b);
        }

        @Override
        public BasicValue ternaryOperation(AbstractInsnNode insn, BasicValue a, BasicValue b, BasicValue c)
                throws AnalyzerException {
            if (tracked(a) || tracked(b) || tracked(c)) refuse(insn);
            return super.ternaryOperation(insn, a, b, c);
        }

        @Override
        public void returnOperation(AbstractInsnNode insn, BasicValue value, BasicValue expected)
                throws AnalyzerException {
            if (tracked(value)) refuse(insn);
        }

        @Override
        public BasicValue naryOperation(AbstractInsnNode insn, List<? extends BasicValue> args)
                throws AnalyzerException {
            if (insn instanceof MethodInsnNode call) {
                if (call(call, INVOKEVIRTUAL, "net/minecraft/server/packs/resources/Resource", "open", "()L" + INPUT + ";")) {
                    return RESOURCE_VALUE;
                }
                BasicValue receiver = args.isEmpty() ? null : args.getFirst();
                BasicValue result = null;
                if (create(call) && receiver == RESOURCE_VALUE) {
                    result = STREAM_VALUE;
                    wrap = true;
                } else if ((read(call) && receiver == RESOURCE_VALUE) || (wrapped(call) && receiver == STREAM_VALUE)) {
                    result = IMAGE_VALUE;
                } else if (receiver == STREAM_VALUE && call(call, INVOKEINTERFACE, STREAM, "close", "()V")) {
                    pending.add(call);
                    close = true;
                    return null;
                } else if (receiver == IMAGE_VALUE) {
                    if (call(call, INVOKEVIRTUAL, IMAGE, "getWidth", "()I")
                            || call(call, INVOKEVIRTUAL, IMAGE, "getHeight", "()I")) result = BasicValue.INT_VALUE;
                    if (call(call, INVOKEVIRTUAL, IMAGE, "getRGB", "(II)I")) result = BasicValue.INT_VALUE;
                    if (call(call, INVOKEVIRTUAL, IMAGE, "getData", "()L" + RASTER + ";")) result = RASTER_VALUE;
                    if (call(call, INVOKEVIRTUAL, IMAGE, "getColorModel", "()L" + MODEL + ";")) result = MODEL_VALUE;
                } else if (receiver == MODEL_VALUE && call(call, INVOKEVIRTUAL, MODEL, "getNumComponents", "()I")) {
                    result = COMPONENT_COUNT;
                } else if (receiver == RASTER_VALUE && call(call, INVOKEVIRTUAL, RASTER, "getPixel", "(II[I)[I")) {
                    result = BasicValue.REFERENCE_VALUE;
                }
                if (result != null) {
                    for (int i = 1; i < args.size(); i++) if (tracked(args.get(i))) refuse(insn);
                    pending.add(call);
                    return result;
                }
            }
            for (BasicValue value : args) if (tracked(value)) refuse(insn);
            return super.naryOperation(insn, args);
        }
    }
}
