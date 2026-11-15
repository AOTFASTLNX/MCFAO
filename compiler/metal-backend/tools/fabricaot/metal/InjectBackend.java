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
    private static final String FAVICON = "net/minecraft/client/gui/screens/FaviconTexture";
    private static final String PIP = "net/minecraft/client/gui/render/pip/PictureInPictureRenderer";
    private static final String BACKEND = "com/mojang/blaze3d/systems/GpuBackend";
    private static final String GL = "com/mojang/blaze3d/opengl/GlBackend";
    private static final String METAL = "fabricaot/metal/MetalBackend";
    private static final String DIAGNOSTICS = "fabricaot/diag/PlayDiagnostics";
    private static final String LEVEL_TRACKER = "net/minecraft/client/multiplayer/LevelLoadTracker";
    private static final String LEVEL_TRACKER_WAITING = LEVEL_TRACKER + "$WaitingForPlayerChunk";
    private static final String LEVEL_RENDERER = "net/minecraft/client/renderer/LevelRenderer";
    private static final String CHUNK_CACHE = "net/minecraft/client/multiplayer/ClientChunkCache";
    private static final String LOCAL_PLAYER = "net/minecraft/client/player/LocalPlayer";
    private static final String CONNECTION = "net/minecraft/network/Connection";
    private static final String LOGIN_PACKET = "net/minecraft/network/protocol/game/ClientboundLoginPacket";
    private static final String CHUNK_PACKET = "net/minecraft/network/protocol/game/ClientboundLevelChunkWithLightPacket";
    private static final String BATCH_PACKET = "net/minecraft/network/protocol/game/ClientboundChunkBatchFinishedPacket";
    private static final String RADIUS_PACKET = "net/minecraft/network/protocol/game/ClientboundSetChunkCacheRadiusPacket";
    private static final String CENTER_PACKET = "net/minecraft/network/protocol/game/ClientboundSetChunkCacheCenterPacket";
    private static final String POSITION_PACKET = "net/minecraft/network/protocol/game/ClientboundPlayerPositionPacket";

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
        int ticks = 0;
        for (MethodNode method : cls.methods) {
            if (!method.name.equals("runTick") || !method.desc.equals("(Z)V")) continue;
            method.instructions.insert(diag("tick", "()V"));
            ticks++;
        }
        if (ticks != 1) throw new IllegalArgumentException("Expected one Minecraft.runTick, found " + ticks);
        // Neither branches nor stack height at existing labels change. Only recompute max stack.
        ClassWriter writer = new ClassWriter(ClassWriter.COMPUTE_MAXS); cls.accept(writer); return writer.toByteArray();
    }
    private static MethodInsnNode diag(String name, String descriptor) {
        return new MethodInsnNode(INVOKESTATIC, DIAGNOSTICS, name, descriptor, false);
    }
    private static MethodNode require(ClassNode owner, String name, String descriptor) {
        for (MethodNode method : owner.methods) {
            if (method.name.equals(name) && method.desc.equals(descriptor)) return method;
        }
        throw new IllegalArgumentException("Missing " + owner.name + "." + name + descriptor);
    }
    private static void beforeReturns(MethodNode method, InsnList code, int opcode) {
        for (AbstractInsnNode instruction : method.instructions.toArray()) {
            if (instruction.getOpcode() != opcode) continue;
            method.instructions.insertBefore(instruction, code);
        }
    }
    private static InsnList trackerState() {
        InsnList code = new InsnList();
        code.add(new VarInsnNode(ALOAD, 0));
        code.add(new FieldInsnNode(GETFIELD, LEVEL_TRACKER, "clientState",
                "L" + LEVEL_TRACKER + "$ClientState;"));
        code.add(diag("tracker", "(Ljava/lang/Object;)V"));
        return code;
    }
    private static boolean isCall(AbstractInsnNode insn,String owner,String name,String desc) {
        return insn instanceof MethodInsnNode call && call.getOpcode()==INVOKEVIRTUAL
            && call.owner.equals(owner)&&call.name.equals(name)&&call.desc.equals(desc);
    }
    public static byte[] avoidUnneededChatKeyWait(byte[] bytes) {
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
        instrumentPacketListener(cls);
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
    static void instrumentPacketListener(ClassNode cls) {
        MethodNode login = require(cls, "handleLogin", "(L" + LOGIN_PACKET + ";)V");
        InsnList loginHook = new InsnList();
        loginHook.add(new VarInsnNode(ALOAD, 1));
        loginHook.add(new MethodInsnNode(INVOKEVIRTUAL, "java/lang/Object", "toString",
                "()Ljava/lang/String;", false));
        loginHook.add(diag("login", "(Ljava/lang/Object;)V"));
        login.instructions.insert(loginHook);

        MethodNode chunk = require(cls, "handleLevelChunkWithLight", "(L" + CHUNK_PACKET + ";)V");
        InsnList chunkHook = new InsnList();
        chunkHook.add(new VarInsnNode(ALOAD, 1));
        chunkHook.add(new MethodInsnNode(INVOKEVIRTUAL, CHUNK_PACKET, "getX", "()I", false));
        chunkHook.add(new VarInsnNode(ALOAD, 1));
        chunkHook.add(new MethodInsnNode(INVOKEVIRTUAL, CHUNK_PACKET, "getZ", "()I", false));
        chunkHook.add(diag("chunk", "(II)V"));
        chunk.instructions.insert(chunkHook);

        MethodNode batchStart = require(cls, "handleChunkBatchStart",
                "(Lnet/minecraft/network/protocol/game/ClientboundChunkBatchStartPacket;)V");
        batchStart.instructions.insert(diag("batchStart", "()V"));

        MethodNode batch = require(cls, "handleChunkBatchFinished", "(L" + BATCH_PACKET + ";)V");
        InsnList batchHook = new InsnList();
        batchHook.add(new VarInsnNode(ALOAD, 1));
        batchHook.add(new MethodInsnNode(INVOKEVIRTUAL, BATCH_PACKET, "batchSize", "()I", false));
        batchHook.add(diag("batch", "(I)V"));
        batch.instructions.insert(batchHook);

        MethodNode radius = require(cls, "handleSetChunkCacheRadius", "(L" + RADIUS_PACKET + ";)V");
        InsnList radiusHook = new InsnList();
        radiusHook.add(new VarInsnNode(ALOAD, 1));
        radiusHook.add(new MethodInsnNode(INVOKEVIRTUAL, RADIUS_PACKET, "getRadius", "()I", false));
        radiusHook.add(diag("radius", "(I)V"));
        radius.instructions.insert(radiusHook);

        MethodNode center = require(cls, "handleSetChunkCacheCenter", "(L" + CENTER_PACKET + ";)V");
        InsnList centerHook = new InsnList();
        centerHook.add(new VarInsnNode(ALOAD, 1));
        centerHook.add(new MethodInsnNode(INVOKEVIRTUAL, CENTER_PACKET, "getX", "()I", false));
        centerHook.add(new VarInsnNode(ALOAD, 1));
        centerHook.add(new MethodInsnNode(INVOKEVIRTUAL, CENTER_PACKET, "getZ", "()I", false));
        centerHook.add(diag("cacheCenter", "(II)V"));
        center.instructions.insert(centerHook);

        MethodNode position = require(cls, "handleMovePlayer", "(L" + POSITION_PACKET + ";)V");
        InsnList positionHook = new InsnList();
        positionHook.add(new VarInsnNode(ALOAD, 1));
        positionHook.add(new MethodInsnNode(INVOKEVIRTUAL, "java/lang/Object", "toString",
                "()Ljava/lang/String;", false));
        positionHook.add(diag("serverPosition", "(Ljava/lang/String;)V"));
        position.instructions.insert(positionHook);
    }

    public static byte[] instrumentLevelLoadTracker(byte[] bytes) {
        ClassNode cls = new ClassNode(); new ClassReader(bytes).accept(cls, 0);
        if (!cls.name.equals(LEVEL_TRACKER)) throw new IllegalArgumentException("Unexpected level load tracker");
        MethodNode start = require(cls, "startClientLoad", "(Lnet/minecraft/client/player/LocalPlayer;"
                + "Lnet/minecraft/client/multiplayer/ClientLevel;Lnet/minecraft/client/renderer/LevelRenderer;)V");
        start.instructions.insertBefore(lastReturn(start), trackerState());
        MethodNode tick = require(cls, "tickClientLoad", "()V");
        tick.instructions.insertBefore(lastReturn(tick), trackerState());
        MethodNode packets = require(cls, "loadingPacketsReceived", "()V");
        packets.instructions.insertBefore(lastReturn(packets), trackerState());
        MethodNode ready = require(cls, "isLevelReady", "()Z");
        for (AbstractInsnNode instruction : ready.instructions.toArray()) {
            if (instruction.getOpcode() != IRETURN) continue;
            ready.instructions.insertBefore(instruction, new InsnNode(DUP));
            ready.instructions.insertBefore(instruction, diag("ready", "(Z)V"));
        }
        ClassWriter writer = new ClassWriter(ClassWriter.COMPUTE_MAXS); cls.accept(writer); return writer.toByteArray();
    }

    public static byte[] instrumentWaitingForPlayerChunk(byte[] bytes) {
        ClassNode cls = new ClassNode(); new ClassReader(bytes).accept(cls, 0);
        if (!cls.name.equals(LEVEL_TRACKER_WAITING)) throw new IllegalArgumentException("Unexpected waiting chunk state");
        MethodNode ready = require(cls, "isReady", "()Z");
        for (AbstractInsnNode instruction : ready.instructions.toArray()) {
            if (instruction.getOpcode() != IRETURN) continue;
            ready.instructions.insertBefore(instruction, new InsnNode(DUP));
            ready.instructions.insertBefore(instruction, diag("chunkReady", "(Z)V"));
        }
        ClassWriter writer = new ClassWriter(ClassWriter.COMPUTE_MAXS); cls.accept(writer); return writer.toByteArray();
    }

    static byte[] instrumentLevelRenderer(byte[] bytes) {
        ClassNode cls = new ClassNode(); new ClassReader(bytes).accept(cls, 0);
        if (!cls.name.equals(LEVEL_RENDERER)) throw new IllegalArgumentException("Unexpected level renderer");
        MethodNode check = require(cls, "isSectionCompiledAndVisible", "(Lnet/minecraft/core/BlockPos;)Z");
        InsnList entry = new InsnList();
        entry.add(new VarInsnNode(ALOAD, 1));
        entry.add(new MethodInsnNode(INVOKEVIRTUAL, "java/lang/Object", "toString",
                "()Ljava/lang/String;", false));
        entry.add(diag("sectionCheck", "(Ljava/lang/String;)V"));
        check.instructions.insert(entry);
        for (AbstractInsnNode instruction : check.instructions.toArray()) {
            if (instruction.getOpcode() != IRETURN) continue;
            check.instructions.insertBefore(instruction, new InsnNode(DUP));
            check.instructions.insertBefore(instruction, diag("sectionVisible", "(Z)V"));
        }
        ClassWriter writer = new ClassWriter(ClassWriter.COMPUTE_MAXS); cls.accept(writer); return writer.toByteArray();
    }

    public static byte[] instrumentChunkCache(byte[] bytes) {
        ClassNode cls = new ClassNode(); new ClassReader(bytes).accept(cls, 0);
        if (!cls.name.equals(CHUNK_CACHE)) throw new IllegalArgumentException("Unexpected client chunk cache");
        MethodNode decode = require(cls, "replaceWithPacketData", "(IILnet/minecraft/network/FriendlyByteBuf;"
                + "Ljava/util/Map;Ljava/util/function/Consumer;)Lnet/minecraft/world/level/chunk/LevelChunk;");
        InsnList entry = new InsnList();
        entry.add(new VarInsnNode(ILOAD, 1));
        entry.add(new VarInsnNode(ILOAD, 2));
        entry.add(diag("chunkDecode", "(II)V"));
        decode.instructions.insert(entry);
        ClassWriter writer = new ClassWriter(ClassWriter.COMPUTE_MAXS); cls.accept(writer); return writer.toByteArray();
    }

    static byte[] instrumentLocalPlayer(byte[] bytes) {
        ClassNode cls = new ClassNode(); new ClassReader(bytes).accept(cls, 0);
        if (!cls.name.equals(LOCAL_PLAYER)) throw new IllegalArgumentException("Unexpected local player");
        MethodNode send = require(cls, "sendPosition", "()V");
        InsnList entry = new InsnList();
        entry.add(new VarInsnNode(ALOAD, 0));
        entry.add(new MethodInsnNode(INVOKEVIRTUAL, LOCAL_PLAYER, "getX", "()D", false));
        entry.add(new VarInsnNode(ALOAD, 0));
        entry.add(new MethodInsnNode(INVOKEVIRTUAL, LOCAL_PLAYER, "getY", "()D", false));
        entry.add(new VarInsnNode(ALOAD, 0));
        entry.add(new MethodInsnNode(INVOKEVIRTUAL, LOCAL_PLAYER, "getZ", "()D", false));
        entry.add(diag("clientPosition", "(DDD)V"));
        send.instructions.insert(entry);
        ClassWriter writer = new ClassWriter(ClassWriter.COMPUTE_MAXS); cls.accept(writer); return writer.toByteArray();
    }

    public static byte[] instrumentConnection(byte[] bytes) {
        ClassNode cls = new ClassNode(); new ClassReader(bytes).accept(cls, 0);
        if (!cls.name.equals(CONNECTION)) throw new IllegalArgumentException("Unexpected connection class");
        MethodNode failure = require(cls, "exceptionCaught",
                "(Lio/netty/channel/ChannelHandlerContext;Ljava/lang/Throwable;)V");
        InsnList entry = new InsnList();
        entry.add(new VarInsnNode(ALOAD, 2));
        entry.add(diag("connectionFailure", "(Ljava/lang/Throwable;)V"));
        failure.instructions.insert(entry);
        MethodNode inactive = require(cls, "channelInactive",
                "(Lio/netty/channel/ChannelHandlerContext;)V");
        inactive.instructions.insert(diag("channelInactive", "()V"));
        ClassWriter writer = new ClassWriter(ClassWriter.COMPUTE_MAXS); cls.accept(writer); return writer.toByteArray();
    }

    private static AbstractInsnNode lastReturn(MethodNode method) {
        AbstractInsnNode result = null;
        for (AbstractInsnNode instruction : method.instructions.toArray()) {
            if (instruction.getOpcode() == RETURN) result = instruction;
        }
        if (result == null) throw new IllegalArgumentException("Missing return in " + method.name);
        return result;
    }

    static byte[] orientFavicon(byte[] bytes) {
        ClassNode cls=new ClassNode();new ClassReader(bytes).accept(cls,0);
        if(!cls.name.equals(FAVICON))throw new IllegalArgumentException("Unexpected favicon class");
        int matches=0;
        for(MethodNode method:cls.methods){
            if(method.name.equals("upload")&&method.desc.equals("(Lcom/mojang/blaze3d/platform/NativeImage;)V")){
                InsnList patch=new InsnList();patch.add(new VarInsnNode(ALOAD,1));
                patch.add(new MethodInsnNode(INVOKESTATIC,METAL,"orientFavicon","(Lcom/mojang/blaze3d/platform/NativeImage;)V",false));
                method.instructions.insert(patch);matches++;
            }
        }
        if(matches!=1)throw new IllegalArgumentException("Expected one FaviconTexture.upload method");
        ClassWriter writer=new ClassWriter(ClassWriter.COMPUTE_MAXS);cls.accept(writer);return writer.toByteArray();
    }
    static byte[] orientPictureInPicture(byte[] bytes) {
        ClassNode cls=new ClassNode();new ClassReader(bytes).accept(cls,0);
        if(!cls.name.equals(PIP))throw new IllegalArgumentException("Unexpected PIP renderer class");
        int matches=0;
        for(MethodNode method:cls.methods){
            if(!method.name.equals("blitTexture")||!method.desc.equals("(Lnet/minecraft/client/renderer/state/gui/pip/PictureInPictureRenderState;Lnet/minecraft/client/renderer/state/gui/GuiRenderState;)V"))continue;
            List<AbstractInsnNode> code=Arrays.stream(method.instructions.toArray()).filter(n->n.getOpcode()>=0).toList();
            for(int i=0;i+3<code.size();i++){
                if(op(code.get(i),FCONST_0)&&op(code.get(i+1),FCONST_1)&&op(code.get(i+2),FCONST_1)&&op(code.get(i+3),FCONST_0)){
                    // BlitRenderState takes u0, u1, v0, v1: preserve the full U range.
                    method.instructions.insert(code.get(i+2),new MethodInsnNode(INVOKESTATIC,METAL,"guiRenderTargetV","(F)F",false));
                    method.instructions.insert(code.get(i+3),new MethodInsnNode(INVOKESTATIC,METAL,"guiRenderTargetV","(F)F",false));
                    matches++;
                }
            }
        }
        if(matches!=1)throw new IllegalArgumentException("Expected one PIP blit UV sequence");
        ClassWriter writer=new ClassWriter(ClassWriter.COMPUTE_MAXS);cls.accept(writer);return writer.toByteArray();
    }
    static void selfTest() {
        ClassWriter w = new ClassWriter(0); w.visit(V25, ACC_PUBLIC, "Fixture", null, "java/lang/Object", null);
        MethodVisitor m = w.visitMethod(ACC_PUBLIC, "<init>", "()V", null, null); m.visitCode();
        m.visitVarInsn(ALOAD, 0); m.visitMethodInsn(INVOKESPECIAL, "java/lang/Object", "<init>", "()V", false);
        m.visitInsn(ICONST_1); m.visitTypeInsn(ANEWARRAY, BACKEND); m.visitInsn(DUP); m.visitInsn(ICONST_0);
        m.visitTypeInsn(NEW, GL); m.visitInsn(DUP); m.visitMethodInsn(INVOKESPECIAL, GL, "<init>", "()V", false);
        m.visitInsn(AASTORE); m.visitInsn(POP); m.visitInsn(RETURN); m.visitMaxs(5, 1); m.visitEnd();
        MethodVisitor tick = w.visitMethod(ACC_PRIVATE, "runTick", "(Z)V", null, null); tick.visitCode();
        tick.visitInsn(RETURN); tick.visitMaxs(0, 2); tick.visitEnd(); w.visitEnd();
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
        if (args.length != 3) throw new IllegalArgumentException("input.jar output.jar diagnostics-classes");
        int targets = 0, packetTargets = 0, itemTargets = 0, trackerTargets = 0;
        int waitingTargets = 0, rendererTargets = 0, chunkCacheTargets = 0, playerTargets = 0;
        int connectionTargets = 0, faviconTargets = 0, pipTargets = 0;
        Set<String> written = new HashSet<>();
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
                if (name.equals(FAVICON+".class")) { bytes=orientFavicon(bytes);faviconTargets++; }
                if (name.equals(PIP+".class")) { bytes=orientPictureInPicture(bytes);pipTargets++; }
                if (name.equals(LEVEL_TRACKER+".class")) { bytes=instrumentLevelLoadTracker(bytes);trackerTargets++; }
                if (name.equals(LEVEL_TRACKER_WAITING+".class")) { bytes=instrumentWaitingForPlayerChunk(bytes);waitingTargets++; }
                if (name.equals(LEVEL_RENDERER+".class")) { bytes=instrumentLevelRenderer(bytes);rendererTargets++; }
                if (name.equals(CHUNK_CACHE+".class")) { bytes=instrumentChunkCache(bytes);chunkCacheTargets++; }
                if (name.equals(LOCAL_PLAYER+".class")) { bytes=instrumentLocalPlayer(bytes);playerTargets++; }
                if (name.equals(CONNECTION+".class")) { bytes=instrumentConnection(bytes);connectionTargets++; }
                if (!written.add(name)) throw new IllegalArgumentException("Duplicate jar entry: " + name);
                ZipEntry copy = new ZipEntry(name); copy.setTime(0); output.putNextEntry(copy); output.write(bytes); output.closeEntry();
            }
            Path diagnostics = Path.of(args[2]);
            if (!Files.isDirectory(diagnostics)) throw new IllegalArgumentException("Missing diagnostics classes: " + diagnostics);
            try (var paths = Files.walk(diagnostics)) {
                for (Path file : paths.filter(Files::isRegularFile).sorted().toList()) {
                    String relative = diagnostics.relativize(file).toString().replace(File.separatorChar, '/');
                    if (!relative.startsWith("fabricaot/diag/") || !relative.endsWith(".class")) continue;
                    if (!relative.equals("fabricaot/diag/PlayDiagnostics.class"))
                        throw new IllegalArgumentException("Unexpected diagnostics helper: " + relative);
                    if (!written.add(relative)) throw new IllegalArgumentException("Duplicate diagnostics entry: " + relative);
                    ZipEntry copy = new ZipEntry(relative); copy.setTime(0); output.putNextEntry(copy);
                    output.write(Files.readAllBytes(file)); output.closeEntry();
                }
            }
        }
        if (targets != 1 || packetTargets != 1 || itemTargets != 1 || trackerTargets != 1
                || waitingTargets != 1 || rendererTargets != 1 || chunkCacheTargets != 1
                || playerTargets != 1 || connectionTargets != 1)
            throw new IllegalArgumentException("Expected one of each instrumented class; got Minecraft=" + targets
                    + " packet=" + packetTargets + " item=" + itemTargets + " tracker=" + trackerTargets
                    + " waiting=" + waitingTargets + " renderer=" + rendererTargets
                    + " chunkCache=" + chunkCacheTargets + " player=" + playerTargets
                    + " connection=" + connectionTargets);
        if (faviconTargets != 1 || pipTargets != 1)
            throw new IllegalArgumentException("Expected one favicon and PIP class; got favicon=" + faviconTargets + " pip=" + pipTargets);
        System.out.println("BACKEND_INJECTION_PASS arrays=1 order=Metal,OpenGL fallback=preserved");
        System.out.println("CHAT_KEY_SHORT_CIRCUIT_PASS signedValidation=preserved");
        System.out.println("GUI_ITEM_ATLAS_ORIGIN_PASS legacyBackendCoordinates=preserved");
        System.out.println("GUI_PREVIEW_ORIGIN_PASS favicon=top-first pip=metal-render-target");
        System.out.println("PLAY_DIAGNOSTICS_INJECTED classes=1");
    }

}
