package fabricaot.metal;

import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.jar.*;
import java.util.zip.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;

/** Build-time only. Preserve the existing backend fallback loop and prepend Metal. */
public final class InjectBackend implements Opcodes {
    private static final String TARGET = "net/minecraft/client/Minecraft.class";
    private static final String PACKET = "net/minecraft/client/multiplayer/ClientPacketListener";
    private static final String PLAYER_INFO = "net/minecraft/client/multiplayer/PlayerInfo";
    private static final String ENTRY = "net/minecraft/network/protocol/game/ClientboundPlayerInfoUpdatePacket$Entry";
    private static final String CHAT = "net/minecraft/network/chat/RemoteChatSession$Data";
    private static final String SERVICES = "net/minecraft/server/Services";
    private static final String ITEM_ATLAS = "net/minecraft/client/gui/render/GuiItemAtlas";
    private static final String BACKEND = "com/mojang/blaze3d/systems/GpuBackend";
    private static final String GL = "com/mojang/blaze3d/opengl/GlBackend";
    private static final String METAL = "fabricaot/metal/MetalBackend";

    private static AbstractInsnNode next(AbstractInsnNode n) {
        do { n = n.getNext(); } while (n != null && n.getOpcode() < 0);
        return n;
    }
    private static boolean op(AbstractInsnNode n, int opcode) { return n != null && n.getOpcode() == opcode; }
    static byte[] transform(byte[] bytes) {
        ClassNode cls = new ClassNode(); new ClassReader(bytes).accept(cls, 0);
        int matches = 0;
        for (MethodNode method : cls.methods) {
            if (!method.name.equals("<init>")) continue;
            for (AbstractInsnNode n : method.instructions.toArray()) {
                if (!op(n, ICONST_1)) continue;
                AbstractInsnNode a = next(n), d = a == null ? null : next(a), i = d == null ? null : next(d);
                AbstractInsnNode g = i == null ? null : next(i), gd = g == null ? null : next(g);
                AbstractInsnNode init = gd == null ? null : next(gd), store = init == null ? null : next(init);
                if (!(a instanceof TypeInsnNode at) || !op(a, ANEWARRAY) || !at.desc.equals(BACKEND)
                        || !op(d, DUP) || !op(i, ICONST_0) || !(g instanceof TypeInsnNode gt)
                        || !op(g, NEW) || !gt.desc.equals(GL) || !op(gd, DUP)
                        || !(init instanceof MethodInsnNode call) || !op(init, INVOKESPECIAL)
                        || !call.owner.equals(GL) || !call.name.equals("<init>") || !call.desc.equals("()V")
                        || !op(store, AASTORE)) continue;
                matches++;
                method.instructions.set(n, new InsnNode(ICONST_2));
                method.instructions.set(i, new InsnNode(ICONST_1));
                InsnList insert = new InsnList();
                insert.add(new InsnNode(DUP)); insert.add(new InsnNode(ICONST_0));
                insert.add(new TypeInsnNode(NEW, METAL)); insert.add(new InsnNode(DUP));
                insert.add(new MethodInsnNode(INVOKESPECIAL, METAL, "<init>", "()V", false));
                insert.add(new InsnNode(AASTORE));
                method.instructions.insert(a, insert);
            }
        }
        if (matches != 1) throw new IllegalArgumentException("Expected one original backend array, found " + matches);
        // Neither branches nor stack height at existing labels change. Only recompute max stack.
        ClassWriter writer = new ClassWriter(ClassWriter.COMPUTE_MAXS); cls.accept(writer); return writer.toByteArray();
    }
    private static boolean isCall(AbstractInsnNode insn,String owner,String name,String desc) {
        return insn instanceof MethodInsnNode call && call.getOpcode()==INVOKEVIRTUAL
            && call.owner.equals(owner)&&call.name.equals(name)&&call.desc.equals(desc);
    }
    static byte[] avoidUnneededChatKeyWait(byte[] bytes) {
        ClassNode cls=new ClassNode();new ClassReader(bytes).accept(cls,0);
        if(!cls.name.equals(PACKET))throw new IllegalArgumentException("Unexpected packet listener class");
        int predicates=0,sessions=0;
        for(MethodNode method:cls.methods){
            AbstractInsnNode[] instructions=method.instructions.toArray();
            if(method.name.equals("enforcesSecureChat")&&method.desc.equals("()Z")){
                long keyChecks=Arrays.stream(instructions).filter(n->isCall(n,SERVICES,"canValidateProfileKeys","()Z")).count();
                long flags=Arrays.stream(instructions).filter(n->n instanceof FieldInsnNode f && op(f,GETFIELD)
                    && f.owner.equals(PACKET)&&f.name.equals("serverEnforcesSecureChat")&&f.desc.equals("Z")).count();
                if(keyChecks!=1||flags!=1)throw new IllegalArgumentException("Unexpected secure chat predicate");
                // The original tests (keys && flag). A false flag alone determines the result.
                LabelNode original=new LabelNode();
                InsnList guard=new InsnList();guard.add(new VarInsnNode(ALOAD,0));
                guard.add(new FieldInsnNode(GETFIELD,PACKET,"serverEnforcesSecureChat","Z"));
                guard.add(new JumpInsnNode(IFNE,original));guard.add(new InsnNode(ICONST_0));guard.add(new InsnNode(IRETURN));
                guard.add(original);guard.add(new FrameNode(F_SAME,0,null,0,null));method.instructions.insert(guard);
                predicates++;
            }else if(method.name.equals("initializeChatSession")&&method.desc.equals("(L"+ENTRY+";L"+PLAYER_INFO+";)V")){
                long validators=Arrays.stream(instructions).filter(n->isCall(n,SERVICES,"profileKeySignatureValidator","()Lnet/minecraft/util/SignatureValidator;")).count();
                long data=Arrays.stream(instructions).filter(n->isCall(n,ENTRY,"chatSession","()L"+CHAT+";")).count();
                if(validators!=1||data!=1)throw new IllegalArgumentException("Unexpected chat session initializer");
                // With no signed session data the original always clears the session. The
                // non-null path, including its signature validator, remains byte-for-byte intact.
                LabelNode original=new LabelNode();
                InsnList guard=new InsnList();guard.add(new VarInsnNode(ALOAD,1));
                guard.add(new MethodInsnNode(INVOKEVIRTUAL,ENTRY,"chatSession","()L"+CHAT+";",false));
                guard.add(new JumpInsnNode(IFNONNULL,original));guard.add(new VarInsnNode(ALOAD,2));
                guard.add(new VarInsnNode(ALOAD,0));
                guard.add(new MethodInsnNode(INVOKEVIRTUAL,PACKET,"enforcesSecureChat","()Z",false));
                guard.add(new MethodInsnNode(INVOKEVIRTUAL,PLAYER_INFO,"clearChatSession","(Z)V",false));
                guard.add(new InsnNode(RETURN));guard.add(original);guard.add(new FrameNode(F_SAME,0,null,0,null));
                method.instructions.insert(guard);sessions++;
            }
        }
        if(predicates!=1||sessions!=1)throw new IllegalArgumentException("Expected one secure chat predicate and one session initializer");
        ClassWriter writer=new ClassWriter(ClassWriter.COMPUTE_MAXS);cls.accept(writer);return writer.toByteArray();
    }
    static byte[] orientGuiItemAtlas(byte[] bytes) {
        ClassNode cls=new ClassNode();new ClassReader(bytes).accept(cls,0);
        if(!cls.name.equals(ITEM_ATLAS))throw new IllegalArgumentException("Unexpected GUI item atlas class");
        int matches=0;
        for(MethodNode method:cls.methods){
            if(!method.name.equals("getOrUpdate")||!method.desc.endsWith(")L"+ITEM_ATLAS+"$SlotView;"))continue;
            AbstractInsnNode previous=null;
            for(AbstractInsnNode insn:method.instructions.toArray()){
                if(insn.getOpcode()<0)continue;
                if(insn instanceof MethodInsnNode call && op(call,INVOKESPECIAL) && call.owner.equals(ITEM_ATLAS+"$SlotView")
                    && call.name.equals("<init>")&&call.desc.equals("(Lcom/mojang/blaze3d/textures/GpuTextureView;FFFF)V")){
                    // Vanilla constructs (texture, u0, v0, u0+delta, v0-delta).
                    if(!op(previous,FSUB))throw new IllegalArgumentException("Unexpected final GUI item UV");
                    AbstractInsnNode v0=previous;
                    for(int i=0;i<6;i++){do{v0=v0.getPrevious();}while(v0!=null&&v0.getOpcode()<0);if(v0==null)throw new IllegalArgumentException("Truncated GUI item UV");}
                    if(!(v0 instanceof VarInsnNode load)||!op(load,FLOAD)||load.var!=5)
                        throw new IllegalArgumentException("Unexpected initial GUI item V");
                    method.instructions.insert(v0,new MethodInsnNode(INVOKESTATIC,METAL,"guiItemAtlasV","(F)F",false));
                    method.instructions.insert(previous,new MethodInsnNode(INVOKESTATIC,METAL,"guiItemAtlasV","(F)F",false));
                    matches++;
                }
                previous=insn;
            }
        }
        if(matches!=1)throw new IllegalArgumentException("Expected one GUI item atlas SlotView constructor");
        ClassWriter writer=new ClassWriter(ClassWriter.COMPUTE_MAXS);cls.accept(writer);return writer.toByteArray();
    }
    static void selfTest() {
        ClassWriter w = new ClassWriter(0); w.visit(V25, ACC_PUBLIC, "Fixture", null, "java/lang/Object", null);
        MethodVisitor m = w.visitMethod(ACC_PUBLIC, "<init>", "()V", null, null); m.visitCode();
        m.visitVarInsn(ALOAD, 0); m.visitMethodInsn(INVOKESPECIAL, "java/lang/Object", "<init>", "()V", false);
        m.visitInsn(ICONST_1); m.visitTypeInsn(ANEWARRAY, BACKEND); m.visitInsn(DUP); m.visitInsn(ICONST_0);
        m.visitTypeInsn(NEW, GL); m.visitInsn(DUP); m.visitMethodInsn(INVOKESPECIAL, GL, "<init>", "()V", false);
        m.visitInsn(AASTORE); m.visitInsn(POP); m.visitInsn(RETURN); m.visitMaxs(5, 1); m.visitEnd(); w.visitEnd();
        byte[] changed = transform(w.toByteArray()); ClassNode cls = new ClassNode(); new ClassReader(changed).accept(cls, 0);
        List<String> created = new ArrayList<>();
        for (AbstractInsnNode n : cls.methods.get(0).instructions) if (n instanceof TypeInsnNode t && n.getOpcode() == NEW) created.add(t.desc);
        if (!created.equals(List.of(METAL, GL))) throw new AssertionError("Backend order: " + created);
        try { transform(changed); throw new AssertionError("Repeated injection accepted"); }
        catch (IllegalArgumentException expected) { /* exact shape is mandatory */ }
        System.out.println("BACKEND_INJECTION_SELF_TEST_PASS");
    }
    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("--self-test")) { selfTest(); return; }
        if (args.length != 2) throw new IllegalArgumentException("input.jar output.jar");
        int targets = 0, packetTargets = 0, itemTargets = 0;
        try (JarFile input = new JarFile(args[0]); ZipOutputStream output = new ZipOutputStream(Files.newOutputStream(Path.of(args[1])))) {
            for (JarEntry entry : Collections.list(input.entries())) {
                String name = entry.getName(), upper = name.toUpperCase(Locale.ROOT);
                if (upper.startsWith("META-INF/") && (upper.endsWith(".SF") || upper.endsWith(".RSA") || upper.endsWith(".DSA") || upper.endsWith(".EC"))) continue;
                byte[] bytes; try (InputStream stream = input.getInputStream(entry)) { bytes = stream.readAllBytes(); }
                // Entry digests refer to the signed original, and are invalid after transformation.
                // Retain main attributes (including Multi-Release), discard stale signing sections.
                if (upper.equals("META-INF/MANIFEST.MF")) {
                    Manifest old = new Manifest(new ByteArrayInputStream(bytes)), clean = new Manifest();
                    clean.getMainAttributes().putAll(old.getMainAttributes());
                    ByteArrayOutputStream buffer = new ByteArrayOutputStream(); clean.write(buffer); bytes = buffer.toByteArray();
                }
                if (name.equals(TARGET)) { bytes = transform(bytes); targets++; }
                if (name.equals(PACKET+".class")) { bytes=avoidUnneededChatKeyWait(bytes);packetTargets++; }
                if (name.equals(ITEM_ATLAS+".class")) { bytes=orientGuiItemAtlas(bytes);itemTargets++; }
                ZipEntry copy = new ZipEntry(name); copy.setTime(0); output.putNextEntry(copy); output.write(bytes); output.closeEntry();
            }
        }
        if (targets != 1 || packetTargets != 1 || itemTargets != 1)
            throw new IllegalArgumentException("Expected one Minecraft, packet listener and GUI item atlas class");
        System.out.println("BACKEND_INJECTION_PASS arrays=1 order=Metal,OpenGL fallback=preserved");
        System.out.println("CHAT_KEY_SHORT_CIRCUIT_PASS signedValidation=preserved");
        System.out.println("GUI_ITEM_ATLAS_ORIGIN_PASS legacyBackendCoordinates=preserved");
    }
}
