package fabricaot.split;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FieldNode;
import org.objectweb.asm.tree.InsnList;
import org.objectweb.asm.tree.InsnNode;
import org.objectweb.asm.tree.JumpInsnNode;
import org.objectweb.asm.tree.LabelNode;
import org.objectweb.asm.tree.LookupSwitchInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import org.objectweb.asm.tree.TableSwitchInsnNode;
import org.objectweb.asm.tree.TryCatchBlockNode;
import org.objectweb.asm.tree.VarInsnNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.analysis.Analyzer;
import org.objectweb.asm.tree.analysis.AnalyzerException;
import org.objectweb.asm.tree.analysis.BasicValue;
import org.objectweb.asm.tree.analysis.BasicVerifier;
import org.objectweb.asm.tree.analysis.Frame;
import org.objectweb.asm.tree.analysis.Interpreter;
import org.objectweb.asm.tree.analysis.SimpleVerifier;
import org.objectweb.asm.util.CheckClassAdapter;

import java.io.IOException;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.HashMap;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;

/**
 * Build-time splitter for oversized static initialisers and other giant static void methods.
 *
 * <p>Motivation (see docs/WORK_HANDOFF.md): GraalVM's points-to builder keeps a full copy of the
 * node-&gt;flow map for every control split / invoke-with-exception it visits while building one
 * method's type-flow graph, so the retained build-host memory for a single method grows with
 * {@code snapshots x entries-per-snapshot} and is quadratic in that method's size. The controlled
 * first-party fixtures (tools/probe_shaped_methods.py) show that a 4000-call {@code <clinit>}
 * exhausts 512 MiB and still pins at 2 GiB, while the identical work split into 16 methods
 * completes in 512 MiB.
 *
 * <p>This transformer performs that split statically on bytecode: a method's instruction list is
 * cut at boundaries where
 * <ul>
 *   <li>the operand stack is empty,</li>
 *   <li>no jump or switch crosses the boundary in either direction,</li>
 *   <li>no exception table entry straddles it (try start/end/handler stay in one part),</li>
 *   <li>local variables that the following part reads can be carried across (typed synthetic
 *       static fields; {@code null} locals are re-materialised with {@code aconst_null}).</li>
 * </ul>
 * The original method keeps the first segment and then calls the generated parts in order, so
 * {@code <clinit>} still runs exactly once and exception order is unchanged.
 *
 * <p>Safety policy: this tool never guesses. If a candidate boundary cannot be proven safe it is
 * skipped, and a method with no safe boundary is reported as {@code NO_SAFE_BOUNDARY} and left
 * untouched. Every rewritten class is re-verified with ASM's {@code CheckClassAdapter}; a class
 * that fails verification is written back byte-for-byte unchanged and reported as {@code REJECTED}.
 */
public final class MethodSplitter {

    private static final int CLASS_LIMIT = 1 << 20;

    /** Diagnostics for boundary selection; enabled with {@code --debug}. */
    private static boolean debug;

    /** Result of splitting one class. */
    private static final class ClassReport {
        String name;
        String status = "UNCHANGED";
        int methodsSplit;
        int partsCreated;
        int fieldsAdded;
        int finalFieldsUnfinalised;
        int sitesBeforeMax;
        int sitesAfterMax;
        final List<Map<String, Object>> methods = new ArrayList<>();
        String note;
        String verify;
    }

    private MethodSplitter() {
    }

    public static void main(String[] argv) throws Exception {
        Map<String, String> options = parseOptions(argv);
        Path input = Paths.get(require(options, "--in"));
        Path output = Paths.get(require(options, "--out"));
        Path reportPath = options.containsKey("--report") ? Paths.get(options.get("--report")) : null;
        int triggerCost = Integer.parseInt(options.getOrDefault("--trigger-cost", "1000000"));
        int minSites = Integer.parseInt(options.getOrDefault("--min-sites", "200"));
        int targetSites = Integer.parseInt(options.getOrDefault("--target-sites", "64"));
        int maxParts = Integer.parseInt(options.getOrDefault("--max-parts", "64"));
        String classFilter = options.getOrDefault("--class", "");
        boolean dryRun = options.containsKey("--dry-run");
        debug = options.containsKey("--debug");
        boolean verify = !options.containsKey("--no-verify");
        List<Path> classpath = new ArrayList<>();
        if (options.containsKey("--classpath")) {
            for (String piece : options.get("--classpath").split(java.io.File.pathSeparator)) {
                if (!piece.isEmpty()) {
                    classpath.add(Paths.get(piece));
                }
            }
        }

        List<URL> urls = new ArrayList<>();
        urls.add(input.toUri().toURL());
        for (Path entry : classpath) {
            urls.add(entry.toUri().toURL());
        }
        ClassLoader loader = new URLClassLoader(urls.toArray(new URL[0]), MethodSplitter.class.getClassLoader());

        List<ClassReport> reports = new ArrayList<>();
        long classesRead = 0;
        int signaturesDropped = 0;
        long classesWritten = 0;
        long classesFailed = 0;
        Path temporary = dryRun ? null : output.resolveSibling(output.getFileName() + ".tmp");
        if (temporary != null) {
            Files.deleteIfExists(temporary);
        }
        try (ZipFile zip = new ZipFile(input.toFile());
             ZipOutputStream sink = dryRun ? null : new ZipOutputStream(Files.newOutputStream(temporary))) {
            Enumeration<? extends ZipEntry> entries = zip.entries();
            while (entries.hasMoreElements()) {
                ZipEntry entry = entries.nextElement();
                byte[] data = read(zip, entry);
                if (isJarSignature(entry.getName())) {
                    // The input client jar is signed; rewriting any class invalidates those digests and
                    // the JVM then refuses to load the class (SHA-384 digest error). The transformed jar
                    // is a local analysis artifact and is deliberately unsigned; the original jar is
                    // never modified.
                    signaturesDropped++;
                    continue;
                }
                if (!entry.getName().endsWith(".class") || entry.isDirectory()) {
                    if (sink != null) {
                        write(sink, entry, data);
                    }
                    continue;
                }
                classesRead++;
                String className = entry.getName().substring(0, entry.getName().length() - 6);
                ClassReport report = new ClassReport();
                report.name = className.replace('/', '.');
                if (!classFilter.isEmpty() && !className.startsWith(classFilter)) {
                    report.status = "SKIPPED_FILTER";
                    if (sink != null) {
                        write(sink, entry, data);
                    }
                    continue;
                }
                byte[] result = data;
                try {
                    byte[] candidate = transform(data, className, report, loader, triggerCost, minSites,
                            targetSites, maxParts, verify);
                    if (candidate != null) {
                        result = candidate;
                    }
                } catch (Throwable failure) {
                    report.status = "ERROR";
                    report.note = failure.getClass().getName() + ": " + failure.getMessage();
                }
                if (result != data) {
                    classesWritten++;
                    reports.add(report);
                } else if (!"UNCHANGED".equals(report.status) && !"SKIPPED_FILTER".equals(report.status)) {
                    // Failed, refused or rejected classes must stay visible in the record.
                    reports.add(report);
                    if ("REJECTED".equals(report.status)) {
                        classesFailed++;
                    }
                }
                if (sink != null) {
                    write(sink, entry, result);
                }
            }
        } finally {
            if (temporary != null && Files.exists(temporary)) {
                Files.move(temporary, output, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
            }
        }

        StringBuilder json = new StringBuilder();
        json.append("{\n");
        json.append("  \"input\": ").append(quote(input.toAbsolutePath().toString())).append(",\n");
        json.append("  \"inputSHA256\": ").append(quote(sha256(input))).append(",\n");
        json.append("  \"output\": ").append(quote(dryRun ? null : output.toAbsolutePath().toString())).append(",\n");
        json.append("  \"outputSHA256\": ").append(quote(dryRun || !Files.exists(output) ? null : sha256(output))).append(",\n");
        json.append("  \"dryRun\": ").append(dryRun).append(",\n");
        json.append("  \"triggerCost\": ").append(triggerCost).append(",\n");
        json.append("  \"minSites\": ").append(minSites).append(",\n");
        json.append("  \"targetSites\": ").append(targetSites).append(",\n");
        json.append("  \"classFilter\": ").append(quote(classFilter.isEmpty() ? null : classFilter)).append(",\n");
        json.append("  \"classesRead\": ").append(classesRead).append(",\n");
        json.append("  \"signatureEntriesDropped\": ").append(signaturesDropped).append(",\n");
        json.append("  \"outputSigned\": false,\n");
        json.append("  \"classesWritten\": ").append(classesWritten).append(",\n");
        json.append("  \"classesRejected\": ").append(classesFailed).append(",\n");
        int splitMethods = 0;
        int parts = 0;
        for (ClassReport report : reports) {
            splitMethods += report.methodsSplit;
            parts += report.partsCreated;
        }
        json.append("  \"methodsSplit\": ").append(splitMethods).append(",\n");
        json.append("  \"partsCreated\": ").append(parts).append(",\n");
        json.append("  \"classes\": [\n");
        for (int i = 0; i < reports.size(); i++) {
            ClassReport report = reports.get(i);
            json.append("    {\"class\": ").append(quote(report.name));
            json.append(", \"status\": ").append(quote(report.status));
            json.append(", \"methodsSplit\": ").append(report.methodsSplit);
            json.append(", \"partsCreated\": ").append(report.partsCreated);
            json.append(", \"fieldsAdded\": ").append(report.fieldsAdded);
            json.append(", \"finalFieldsUnfinalised\": ").append(report.finalFieldsUnfinalised);
            json.append(", \"sitesBeforeMax\": ").append(report.sitesBeforeMax);
            json.append(", \"sitesAfterMax\": ").append(report.sitesAfterMax);
            if (report.note != null) {
                json.append(", \"note\": ").append(quote(report.note));
            }
            if (report.verify != null) {
                json.append(", \"verify\": ").append(quote(report.verify));
            }
            json.append(", \"methods\": [");
            for (int j = 0; j < report.methods.size(); j++) {
                if (j > 0) {
                    json.append(", ");
                }
                json.append(toJson(report.methods.get(j)));
            }
            json.append("]}");
            if (i + 1 < reports.size()) {
                json.append(",");
            }
            json.append("\n");
        }
        json.append("  ],\n");
        json.append("  \"scope\": ").append(quote(
                "build-time bytecode transformation only; no analysis, no code generation, no target "
                        + "execution; part boundaries are proven safe by the listed static conditions and each "
                        + "rewritten class is re-verified, but semantic equivalence for Minecraft is not proven "
                        + "until the transformed client is analysed and run"))
                .append("\n");
        json.append("}\n");
        if (reportPath != null) {
            Files.createDirectories(reportPath.toAbsolutePath().getParent());
            Files.write(reportPath, json.toString().getBytes(StandardCharsets.UTF_8));
        }
        System.out.println(json);
    }

    // ------------------------------------------------------------------ transform

    private static byte[] transform(byte[] data, String className, ClassReport report, ClassLoader loader,
                                    int triggerCost, int minSites, int targetSites, int maxParts,
                                    boolean verify) throws AnalyzerException {
        ClassNode node = new ClassNode();
        new ClassReader(data).accept(node, ClassReader.SKIP_FRAMES);
        List<MethodNode> original = new ArrayList<>(node.methods);
        List<MethodNode> created = new ArrayList<>();
        List<FieldNode> fields = new ArrayList<>();
        boolean touched = false;

        for (MethodNode method : original) {
            if (!isCandidate(method)) {
                continue;
            }
            int sites = sites(method);
            report.sitesBeforeMax = Math.max(report.sitesBeforeMax, sites);
            if (sites < minSites) {
                continue;
            }
            int instructions = instructions(method);
            long cost = (long) sites * instructions;
            if (cost < triggerCost) {
                continue;
            }
            MethodSplit split = splitMethod(node, method, className, loader, targetSites, maxParts, fields);
            Map<String, Object> record = new LinkedHashMap<>();
            record.put("method", method.name + method.desc);
            record.put("sites", sites);
            record.put("instructions", instructions);
            record.put("costProxy", cost);
            if (split == null) {
                record.put("status", "NO_SAFE_BOUNDARY");
                report.methods.add(record);
                report.sitesBeforeMax = Math.max(report.sitesBeforeMax, sites);
                continue;
            }
            record.put("status", "SPLIT");
            record.put("parts", split.parts);
            record.put("spilledSlots", split.spilledSlots);
            record.put("finalFieldsUnfinalised", split.finalFieldsUnfinalised);
            record.put("sitesAfterMax", split.maxSitesAfter);
            record.put("analyser", split.analyser);
            report.methods.add(record);
            report.methodsSplit++;
            report.partsCreated += split.parts;
            report.sitesAfterMax = Math.max(report.sitesAfterMax, split.maxSitesAfter);
            created.addAll(split.methodNodes);
            touched = true;
        }

        if (!touched) {
            report.status = report.methods.isEmpty() ? "UNCHANGED" : "NO_SPLIT";
            return null;
        }

        node.methods.addAll(created);
        node.fields.addAll(fields);
        report.fieldsAdded = fields.size();
        for (Map<String, Object> splitMethod : report.methods) {
            Object value = splitMethod.get("finalFieldsUnfinalised");
            if (value instanceof Integer) {
                report.finalFieldsUnfinalised += (Integer) value;
            }
        }

        ClassWriter writer = new LoaderClassWriter(ClassWriter.COMPUTE_FRAMES | ClassWriter.COMPUTE_MAXS, loader);
        byte[] out;
        try {
            node.accept(writer);
            out = writer.toByteArray();
        } catch (Throwable failure) {
            report.status = "REJECTED";
            report.note = "write failed: " + failure.getClass().getSimpleName() + ": " + failure.getMessage();
            return null;
        }

        if (verify) {
            StringWriter buffer = new StringWriter();
            PrintWriter print = new PrintWriter(buffer);
            try {
                CheckClassAdapter.verify(new ClassReader(out), loader, false, print);
            } catch (Throwable failure) {
                print.println(failure);
            }
            print.flush();
            String text = buffer.toString().trim();
            if (!text.isEmpty()) {
                boolean structural = text.contains("AnalyzerException") || text.contains("VerifyError")
                        || text.contains("Error at instruction");
                report.verify = text.length() > 1500 ? text.substring(0, 1500) : text;
                if (structural) {
                    report.status = "REJECTED";
                    report.note = "bytecode verification failed";
                    return null;
                }
            }
        }
        report.status = "SPLIT";
        return out;
    }

    private static final class MethodSplit {
        int parts;
        int spilledSlots;
        int finalFieldsUnfinalised;
        int maxSitesAfter;
        String analyser;
        final List<MethodNode> methodNodes = new ArrayList<>();
    }

    /** Drop ACC_FINAL from same-class fields this method assigns; returns how many changed. */
    private static int unfinaliseAssignedFinals(ClassNode owner, MethodNode method) {
        int changed = 0;
        for (AbstractInsnNode insn = method.instructions.getFirst(); insn != null; insn = insn.getNext()) {
            if (insn.getOpcode() != Opcodes.PUTSTATIC) {
                continue;
            }
            FieldInsnNode write = (FieldInsnNode) insn;
            if (!write.owner.equals(owner.name)) {
                continue;
            }
            for (FieldNode field : owner.fields) {
                if (field.name.equals(write.name) && field.desc.equals(write.desc)
                        && (field.access & Opcodes.ACC_FINAL) != 0) {
                    field.access &= ~Opcodes.ACC_FINAL;
                    changed++;
                }
            }
        }
        return changed;
    }

    private static boolean isCandidate(MethodNode method) {
        if ((method.access & Opcodes.ACC_STATIC) == 0) {
            return false;
        }
        if ((method.access & (Opcodes.ACC_ABSTRACT | Opcodes.ACC_NATIVE | Opcodes.ACC_SYNCHRONIZED)) != 0) {
            return false;
        }
        if (!"()V".equals(method.desc)) {
            return false;
        }
        return method.instructions != null && method.instructions.size() > 0;
    }

    private static int sites(MethodNode method) {
        int count = 0;
        for (AbstractInsnNode insn = method.instructions.getFirst(); insn != null; insn = insn.getNext()) {
            int opcode = insn.getOpcode();
            if (opcode >= Opcodes.INVOKEVIRTUAL && opcode <= Opcodes.INVOKEDYNAMIC) {
                count++;
            } else if ((opcode >= Opcodes.IFEQ && opcode <= Opcodes.IF_ACMPNE)
                    || opcode == Opcodes.IFNULL || opcode == Opcodes.IFNONNULL
                    || opcode == Opcodes.TABLESWITCH || opcode == Opcodes.LOOKUPSWITCH) {
                count++;
            }
        }
        return count;
    }

    private static int instructions(MethodNode method) {
        int count = 0;
        for (AbstractInsnNode insn = method.instructions.getFirst(); insn != null; insn = insn.getNext()) {
            if (insn.getOpcode() >= 0) {
                count++;
            }
        }
        return count;
    }

    private static MethodSplit splitMethod(ClassNode owner, MethodNode method, String className,
                                           ClassLoader loader, int targetSites, int maxParts,
                                           List<FieldNode> fields) throws AnalyzerException {
        AbstractInsnNode[] insns = method.instructions.toArray();
        int count = insns.length;
        IdentityHashMap<LabelNode, Integer> labelIndex = new IdentityHashMap<>();
        for (int i = 0; i < count; i++) {
            if (insns[i] instanceof LabelNode) {
                labelIndex.put((LabelNode) insns[i], i);
            }
        }

        String analyser;
        Frame<BasicValue>[] frames;
        boolean exactTypes;
        try {
            frames = analyse(owner, method, loader, true);
            analyser = "SimpleVerifier";
            exactTypes = true;
        } catch (Throwable failure) {
            frames = analyse(owner, method, loader, false);
            analyser = "BasicVerifier";
            exactTypes = false;
        }

        // jump targets: prefix maximum and suffix minimum, used for the crossing test.
        int[] prefixMax = new int[count];
        int[] suffixMin = new int[count];
        int running = -1;
        for (int i = 0; i < count; i++) {
            int target = maxTarget(insns[i], labelIndex);
            if (target > running) {
                running = target;
            }
            prefixMax[i] = running;
        }
        running = Integer.MAX_VALUE;
        int[] suffixSites = new int[count];
        int remainingSites = 0;
        for (int i = count - 1; i >= 0; i--) {
            int target = minTarget(insns[i], labelIndex);
            if (target < running) {
                running = target;
            }
            suffixMin[i] = running;
            suffixSites[i] = remainingSites;
            if (isSite(insns[i])) {
                remainingSites++;
            }
        }

        // Even distribution: never let the final part absorb the work that maxParts refused to split.
        int totalSites = sites(insns, 0, count);
        int effectiveTarget = Math.max(1, Math.max(targetSites,
                (totalSites + Math.max(1, maxParts) - 1) / Math.max(1, maxParts)));
        List<Integer> cuts = new ArrayList<>();
        int lastCut = 0;
        int rejectedCrossing = 0, rejectedStack = 0, rejectedTry = 0, rejectedLocals = 0, accepted = 0;
        for (int i = 1; i < count; i++) {
            if (insns[i].getOpcode() < 0) {
                continue;
            }
            if (prefixMax[i - 1] >= i || suffixMin[i] < i) {
                rejectedCrossing++;
                continue;
            }
            if (frames[i] == null || frames[i].getStackSize() != 0) {
                rejectedStack++;
                continue;
            }
            if (straddlesHandler(method, labelIndex, i)) {
                rejectedTry++;
                continue;
            }
            if (!localsTransferable(insns, frames, i, count, exactTypes)) {
                rejectedLocals++;
                continue;
            }
            accepted++;
            // Sites in [lastCut, i) via the suffix table, so the segment cost is O(1) per boundary.
            if (suffixSites[i] > 0 && suffixSites[lastCut] - suffixSites[i] >= effectiveTarget) {
                cuts.add(i);
                lastCut = i;
                if (cuts.size() >= maxParts - 1) {
                    break;
                }
            }
        }
        if (debug) {
            System.err.println("[split] " + method.name + method.desc + " analyser=" + analyser
                    + " instructions=" + count + " accepted=" + accepted + " cuts=" + cuts.size()
                    + " targetSites=" + targetSites
                    + " rejected{stack=" + rejectedStack + ", crossing=" + rejectedCrossing
                    + ", try=" + rejectedTry + ", locals=" + rejectedLocals + "}");
        }
        if (cuts.isEmpty()) {
            return null;
        }

        MethodSplit result = new MethodSplit();
        result.analyser = analyser;
        result.parts = cuts.size() + 1;
        // JVMS 6.5 putstatic: a final field may only be assigned from the <clinit> of its own class.
        // Once the body moves into helper methods that rule fails at run time (IllegalAccessError,
        // observed on SoundEvents.ARMADILLO_PEEK), so the fields this body assigns lose ACC_FINAL.
        // They are not compile-time constants (no ConstantValue, and written here), so call sites still
        // use getstatic and linkage is unchanged.
        result.finalFieldsUnfinalised = unfinaliseAssignedFinals(owner, method);
        result.methodNodes.addAll(build(owner, method, insns, frames, cuts, fields, exactTypes, result));
        int maxAfter = 0;
        int previous = 0;
        for (int cut : cuts) {
            maxAfter = Math.max(maxAfter, sites(insns, previous, cut));
            previous = cut;
        }
        maxAfter = Math.max(maxAfter, sites(insns, previous, count));
        result.maxSitesAfter = maxAfter;
        return result;
    }

    /** One unit of type-flow snapshot pressure: an invoke or a control split. */
    private static boolean isSite(AbstractInsnNode insn) {
        int opcode = insn.getOpcode();
        if (opcode >= Opcodes.INVOKEVIRTUAL && opcode <= Opcodes.INVOKEDYNAMIC) {
            return true;
        }
        return (opcode >= Opcodes.IFEQ && opcode <= Opcodes.IF_ACMPNE)
                || opcode == Opcodes.IFNULL || opcode == Opcodes.IFNONNULL
                || opcode == Opcodes.TABLESWITCH || opcode == Opcodes.LOOKUPSWITCH;
    }

    private static int sites(AbstractInsnNode[] insns, int from, int to) {
        int total = 0;
        for (int i = from; i < to; i++) {
            if (isSite(insns[i])) {
                total++;
            }
        }
        return total;
    }

    private static boolean straddlesHandler(MethodNode method, IdentityHashMap<LabelNode, Integer> labelIndex,
                                            int boundary) {
        for (TryCatchBlockNode block : method.tryCatchBlocks) {
            int start = labelIndex.get(block.start);
            int end = labelIndex.get(block.end);
            int handler = labelIndex.get(block.handler);
            boolean startBefore = start < boundary;
            boolean endBefore = end <= boundary;
            boolean handlerBefore = handler < boundary;
            if (!(startBefore && endBefore && handlerBefore)
                    && !(!startBefore && !endBefore && !handlerBefore)) {
                return true;
            }
        }
        return false;
    }

    private static int maxTarget(AbstractInsnNode insn, IdentityHashMap<LabelNode, Integer> labelIndex) {
        int best = -1;
        if (insn instanceof JumpInsnNode) {
            best = label(labelIndex, ((JumpInsnNode) insn).label);
        } else if (insn instanceof TableSwitchInsnNode) {
            TableSwitchInsnNode node = (TableSwitchInsnNode) insn;
            best = label(labelIndex, node.dflt);
            for (LabelNode target : node.labels) {
                best = Math.max(best, label(labelIndex, target));
            }
        } else if (insn instanceof LookupSwitchInsnNode) {
            LookupSwitchInsnNode node = (LookupSwitchInsnNode) insn;
            best = label(labelIndex, node.dflt);
            for (LabelNode target : node.labels) {
                best = Math.max(best, label(labelIndex, target));
            }
        }
        return best;
    }

    private static int minTarget(AbstractInsnNode insn, IdentityHashMap<LabelNode, Integer> labelIndex) {
        int best = Integer.MAX_VALUE;
        if (insn instanceof JumpInsnNode) {
            best = label(labelIndex, ((JumpInsnNode) insn).label);
        } else if (insn instanceof TableSwitchInsnNode) {
            TableSwitchInsnNode node = (TableSwitchInsnNode) insn;
            best = label(labelIndex, node.dflt);
            for (LabelNode target : node.labels) {
                best = Math.min(best, label(labelIndex, target));
            }
        } else if (insn instanceof LookupSwitchInsnNode) {
            LookupSwitchInsnNode node = (LookupSwitchInsnNode) insn;
            best = label(labelIndex, node.dflt);
            for (LabelNode target : node.labels) {
                best = Math.min(best, label(labelIndex, target));
            }
        }
        return best;
    }

    private static int label(IdentityHashMap<LabelNode, Integer> labelIndex, LabelNode node) {
        Integer index = labelIndex.get(node);
        if (index == null) {
            throw new IllegalStateException("jump target label is not part of the instruction list");
        }
        return index;
    }

    /**
     * A part-local slot may be carried across a boundary when it is either uninitialised (the next
     * part must write it first, exactly as before) or typed. With only {@code BasicVerifier} frames
     * the exact reference type is unavailable, so boundaries whose next part reads an initialised
     * slot are refused instead of guessed.
     */
    private static boolean localsTransferable(AbstractInsnNode[] insns, Frame<BasicValue>[] frames,
                                              int boundary, int count, boolean exactTypes) {
        boolean[] read = new boolean[frames[boundary].getLocals()];
        for (int i = boundary; i < count; i++) {
            int opcode = insns[i].getOpcode();
            if ((opcode >= Opcodes.ILOAD && opcode <= Opcodes.ALOAD) || opcode == Opcodes.IINC) {
                int slot = ((VarInsnNode) insns[i]).var;
                if (slot < read.length) {
                    read[slot] = true;
                }
            }
        }
        for (int slot = 0; slot < read.length; slot++) {
            if (!read[slot]) {
                continue;
            }
            BasicValue value = frames[boundary].getLocal(slot);
            if (value == null || value.getType() == null) {
                continue;
            }
            if (value == BasicValue.UNINITIALIZED_VALUE) {
                return false;
            }
            Type type = value.getType();
            if (isNull(type)) {
                continue;
            }
            if (!exactTypes) {
                return false;
            }
            if (type.getSort() == Type.OBJECT || type.getSort() == Type.ARRAY
                    || type.getSort() == Type.METHOD) {
                continue;
            }
            if (type.getSort() == Type.VOID) {
                return false;
            }
        }
        return true;
    }

    private static List<MethodNode> build(ClassNode owner, MethodNode method, AbstractInsnNode[] insns,
                                          Frame<BasicValue>[] frames, List<Integer> cuts,
                                          List<FieldNode> fields, boolean exactTypes, MethodSplit result) {
        List<MethodNode> parts = new ArrayList<>();
        int[] boundaries = new int[cuts.size() + 2];
        boundaries[0] = 0;
        for (int i = 0; i < cuts.size(); i++) {
            boundaries[i + 1] = cuts.get(i);
        }
        boundaries[boundaries.length - 1] = insns.length;
        int partCount = boundaries.length - 1;
        String prefix = method.name.equals("<clinit>") ? "fabricaot$init$" : "fabricaot$part$";

        // Part 0 keeps the original method's identity and access flags.
        InsnList first = new InsnList();
        for (int i = boundaries[0]; i < boundaries[1]; i++) {
            first.add(insns[i]);
        }
        if (partCount > 1) {
            result.spilledSlots += spill(first, owner, method, frames[boundaries[1]], boundaries[1], fields,
                    exactTypes);
            // The parts form a chain: each one calls the next at its end. <clinit> must therefore enter
            // the chain exactly once - calling every part here as well executed each body twice, which
            // the idempotent fixture tolerated but SoundEvents rejected with a duplicate registry key.
            first.add(new MethodInsnNode(Opcodes.INVOKESTATIC, owner.name, prefix + 1, "()V", false));
        }
        first.add(new InsnNode(Opcodes.RETURN));
        boolean resetLocals = originalHasLocals(method);
        method.instructions = first;
        method.maxStack = 0;
        if (resetLocals) {
            method.localVariables = null;
            method.visibleLocalVariableAnnotations = null;
            method.invisibleLocalVariableAnnotations = null;
        }

        for (int part = 1; part < partCount; part++) {
            MethodNode node = new MethodNode(Opcodes.ACC_PRIVATE | Opcodes.ACC_STATIC | Opcodes.ACC_SYNTHETIC,
                    prefix + part, "()V", null, null);
            InsnList body = new InsnList();
            result.spilledSlots += restore(body, owner, frames[boundaries[part]], boundaries[part], fields,
                    exactTypes);
            for (int i = boundaries[part]; i < boundaries[part + 1]; i++) {
                body.add(insns[i]);
            }
            if (part + 1 < partCount) {
                result.spilledSlots += spill(body, owner, method, frames[boundaries[part + 1]],
                        boundaries[part + 1], fields, exactTypes);
                body.add(new MethodInsnNode(Opcodes.INVOKESTATIC, owner.name, prefix + (part + 1), "()V", false));
            }
            body.add(new InsnNode(Opcodes.RETURN));
            node.instructions = body;
            node.maxLocals = method.maxLocals;
            parts.add(node);
        }
        return parts;
    }

    private static boolean originalHasLocals(MethodNode method) {
        return method.localVariables != null && !method.localVariables.isEmpty();
    }

    private static String spillFieldName(int boundary, int slot) {
        return "fabricaot$spill$" + boundary + "$" + slot;
    }

    private static int spill(InsnList target, ClassNode owner, MethodNode method, Frame<BasicValue> frame,
                             int boundary, List<FieldNode> fields, boolean exactTypes) {
        if (frame == null) {
            return 0;
        }
        int written = 0;
        for (int slot = 0; slot < frame.getLocals(); slot++) {
            BasicValue value = frame.getLocal(slot);
            Type type = value == null ? null : value.getType();
            if (type == null || value == BasicValue.UNINITIALIZED_VALUE) {
                continue;
            }
            if (isNull(type)) {
                continue;
            }
            if (!exactTypes && (type.getSort() == Type.OBJECT || type.getSort() == Type.ARRAY
                    || type.getSort() == Type.METHOD)) {
                continue;
            }
            String descriptor = type.getDescriptor();
            String name = spillFieldName(boundary, slot);
            if (!hasField(owner, fields, name, descriptor)) {
                fields.add(new FieldNode(Opcodes.ACC_PRIVATE | Opcodes.ACC_STATIC | Opcodes.ACC_SYNTHETIC,
                        name, descriptor, null, null));
            }
            target.add(new VarInsnNode(loadOpcode(type), slot));
            target.add(new FieldInsnNode(Opcodes.PUTSTATIC, owner.name, name, descriptor));
            written++;
        }
        return written;
    }

    private static int restore(InsnList target, ClassNode owner, Frame<BasicValue> frame, int boundary,
                               List<FieldNode> fields, boolean exactTypes) {
        if (frame == null) {
            return 0;
        }
        int restored = 0;
        for (int slot = 0; slot < frame.getLocals(); slot++) {
            BasicValue value = frame.getLocal(slot);
            Type type = value == null ? null : value.getType();
            if (type == null || value == BasicValue.UNINITIALIZED_VALUE) {
                continue;
            }
            if (isNull(type)) {
                target.add(new InsnNode(Opcodes.ACONST_NULL));
                target.add(new VarInsnNode(Opcodes.ASTORE, slot));
                restored++;
                continue;
            }
            if (!exactTypes && (type.getSort() == Type.OBJECT || type.getSort() == Type.ARRAY
                    || type.getSort() == Type.METHOD)) {
                continue;
            }
            String descriptor = type.getDescriptor();
            String name = spillFieldName(boundary, slot);
            if (!hasField(owner, fields, name, descriptor)) {
                fields.add(new FieldNode(Opcodes.ACC_PRIVATE | Opcodes.ACC_STATIC | Opcodes.ACC_SYNTHETIC,
                        name, descriptor, null, null));
            }
            target.add(new FieldInsnNode(Opcodes.GETSTATIC, owner.name, name, descriptor));
            target.add(new VarInsnNode(storeOpcode(type), slot));
            restored++;
        }
        return restored;
    }

    private static boolean hasField(ClassNode owner, List<FieldNode> pending, String name, String descriptor) {
        for (FieldNode field : pending) {
            if (field.name.equals(name)) {
                if (!field.desc.equals(descriptor)) {
                    throw new IllegalStateException("conflicting spill types for " + name);
                }
                return true;
            }
        }
        for (FieldNode field : owner.fields) {
            if (field.name.equals(name)) {
                if (!field.desc.equals(descriptor)) {
                    throw new IllegalStateException("conflicting spill types for " + name);
                }
                return true;
            }
        }
        return false;
    }

    private static boolean isNull(Type type) {
        return type.getSort() == Type.OBJECT && "null".equals(type.getInternalName());
    }

    private static int loadOpcode(Type type) {
        switch (type.getSort()) {
            case Type.LONG:
                return Opcodes.LLOAD;
            case Type.FLOAT:
                return Opcodes.FLOAD;
            case Type.DOUBLE:
                return Opcodes.DLOAD;
            case Type.OBJECT:
            case Type.ARRAY:
                return Opcodes.ALOAD;
            default:
                return Opcodes.ILOAD;
        }
    }

    private static int storeOpcode(Type type) {
        switch (type.getSort()) {
            case Type.LONG:
                return Opcodes.LSTORE;
            case Type.FLOAT:
                return Opcodes.FSTORE;
            case Type.DOUBLE:
                return Opcodes.DSTORE;
            case Type.OBJECT:
            case Type.ARRAY:
                return Opcodes.ASTORE;
            default:
                return Opcodes.ISTORE;
        }
    }

    @SuppressWarnings("unchecked")
    private static Frame<BasicValue>[] analyse(ClassNode owner, MethodNode method, ClassLoader loader,
                                               boolean exact) throws AnalyzerException {
        Interpreter<BasicValue> interpreter;
        if (exact) {
            Type current = Type.getObjectType(owner.name);
            Type superClass = owner.superName == null ? Type.getObjectType("java/lang/Object")
                    : Type.getObjectType(owner.superName);
            List<Type> interfaces = new ArrayList<>();
            if (owner.interfaces != null) {
                for (String name : owner.interfaces) {
                    interfaces.add(Type.getObjectType(name));
                }
            }
            SimpleVerifier verifier = new SimpleVerifier(current, superClass, interfaces,
                    (owner.access & Opcodes.ACC_INTERFACE) != 0);
            verifier.setClassLoader(loader);
            interpreter = verifier;
        } else {
            interpreter = new BasicVerifier();
        }
        Analyzer<BasicValue> analyzer = new Analyzer<>(interpreter);
        return analyzer.analyze(owner.name, method);
    }

    // --------------------------------------------------------------------- writer

    private static final class LoaderClassWriter extends ClassWriter {
        private final ClassLoader loader;

        LoaderClassWriter(int flags, ClassLoader loader) {
            super(flags);
            this.loader = loader;
        }

        @Override
        protected String getCommonSuperClass(String left, String right) {
            if (left.equals(right)) {
                return left;
            }
            try {
                Class<?> a = Class.forName(left.replace('/', '.'), false, loader);
                Class<?> b = Class.forName(right.replace('/', '.'), false, loader);
                if (a.isAssignableFrom(b)) {
                    return left;
                }
                if (b.isAssignableFrom(a)) {
                    return right;
                }
                if (a.isInterface() || b.isInterface()) {
                    return "java/lang/Object";
                }
                do {
                    a = a.getSuperclass();
                } while (a != null && !a.isAssignableFrom(b));
                return a == null ? "java/lang/Object" : a.getName().replace('.', '/');
            } catch (Throwable failure) {
                return "java/lang/Object";
            }
        }
    }

    // ----------------------------------------------------------------------- json

    private static String toJson(Object value) {
        if (value == null) {
            return "null";
        }
        if (value instanceof Number || value instanceof Boolean) {
            return String.valueOf(value);
        }
        return quote(String.valueOf(value));
    }

    private static String quote(String value) {
        if (value == null) {
            return "null";
        }
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '"':
                    out.append("\\\"");
                    break;
                case '\\':
                    out.append("\\\\");
                    break;
                case '\n':
                    out.append("\\n");
                    break;
                case '\r':
                    out.append("\\r");
                    break;
                case '\t':
                    out.append("\\t");
                    break;
                default:
                    if (c < 0x20) {
                        out.append(String.format("\\u%04x", (int) c));
                    } else {
                        out.append(c);
                    }
            }
        }
        return out.append('"').toString();
    }

    // ---------------------------------------------------------------------- utils

    private static Map<String, String> parseOptions(String[] argv) {
        Map<String, String> options = new HashMap<>();
        for (int i = 0; i < argv.length; i++) {
            String token = argv[i];
            if (!token.startsWith("--")) {
                throw new IllegalArgumentException("unexpected argument: " + token);
            }
            if (token.equals("--dry-run") || token.equals("--no-verify") || token.equals("--debug")) {
                options.put(token, "true");
            } else {
                if (i + 1 >= argv.length) {
                    throw new IllegalArgumentException("missing value for " + token);
                }
                options.put(token, argv[++i]);
            }
        }
        return options;
    }

    private static String require(Map<String, String> options, String key) {
        String value = options.get(key);
        if (value == null) {
            throw new IllegalArgumentException("missing required " + key);
        }
        return value;
    }

    private static byte[] read(ZipFile zip, ZipEntry entry) throws IOException {
        try (java.io.InputStream stream = zip.getInputStream(entry)) {
            return stream.readAllBytes();
        }
    }

    /** JAR signature side files; their digests would reject every rewritten class. */
    private static boolean isJarSignature(String name) {
        if (!name.startsWith("META-INF/")) {
            return false;
        }
        String tail = name.substring("META-INF/".length()).toUpperCase(java.util.Locale.ROOT);
        if (tail.contains("/")) {
            return false;
        }
        return tail.endsWith(".SF") || tail.endsWith(".DSA") || tail.endsWith(".RSA")
                || tail.endsWith(".EC") || tail.startsWith("SIG-");
    }

    private static void write(ZipOutputStream sink, ZipEntry entry, byte[] data) throws IOException {
        ZipEntry copy = new ZipEntry(entry.getName());
        copy.setTime(entry.getTime());
        sink.putNextEntry(copy);
        sink.write(data);
        sink.closeEntry();
    }

    static String sha256(Path path) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] bytes = digest.digest(Files.readAllBytes(path));
            StringBuilder out = new StringBuilder();
            for (byte value : bytes) {
                out.append(String.format("%02x", value));
            }
            return out.toString();
        } catch (Exception failure) {
            return "unavailable";
        }
    }
}
