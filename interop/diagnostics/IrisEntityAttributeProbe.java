package fabricaot.gl41;

import java.nio.file.*;
import java.util.*;
import java.util.zip.ZipFile;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import io.github.douira.glsl_transformer.ast.transform.SingleASTTransformer;
import it.unimi.dsi.fastutil.objects.Object2ObjectOpenHashMap;
import net.irisshaders.iris.pipeline.transform.Patch;
import net.irisshaders.iris.pipeline.transform.PatchShaderType;
import net.irisshaders.iris.pipeline.transform.parameter.VanillaParameters;
import net.irisshaders.iris.pipeline.transform.transformer.EntityPatcher;
import net.irisshaders.iris.gl.state.ShaderAttributeInputs;
import net.irisshaders.iris.gl.blending.AlphaTest;

public final class IrisEntityAttributeProbe {
    public static void main(String[] args) throws Exception {
        if (args[0].equals("lower")) {
            byte[] original;
            try (var jar = new ZipFile(args[1])) {
                original = jar.getInputStream(jar.getEntry(PatchDevice.IRIS_ENTITY)).readAllBytes();
            }
            byte[] fixed = PatchDevice.fixIrisEntityAttribute(original);
            var a = new ClassNode(); var b = new ClassNode();
            new ClassReader(original).accept(a, 0); new ClassReader(fixed).accept(b, 0);
            for (int m = 0; m < a.methods.size(); m++) {
                MethodNode before = a.methods.get(m), after = b.methods.get(m);
                var x = before.instructions.toArray(); var y = after.instructions.toArray();
                if (x.length != y.length) throw new AssertionError("instruction count");
                int changes = 0;
                for (int i = 0; i < x.length; i++) {
                    if (x[i].getOpcode() != y[i].getOpcode()) throw new AssertionError("opcode");
                    if (x[i] instanceof LdcInsnNode l && y[i] instanceof LdcInsnNode r
                            && !Objects.equals(l.cst, r.cst)) changes++;
                }
                if (changes != (before.name.equals("patchEntityId") ? 2 : 0))
                    throw new AssertionError("unexpected changed method " + before.name);
            }
            byte[] unknown = original.clone(); unknown[unknown.length - 1] ^= 1;
            try {
                PatchDevice.fixIrisEntityAttribute(unknown);
                throw new AssertionError("unaudited bytes accepted");
            } catch (IllegalArgumentException expected) {
                if (!expected.getMessage().contains("Unverified Iris")) throw expected;
            }
            Path output = Path.of(args[2]).resolve(PatchDevice.IRIS_ENTITY);
            Files.createDirectories(output.getParent()); Files.write(output, fixed);
            System.out.println("IRIS_ENTITY_LOWERING_PASS changed literals=2");
            return;
        }
        var parameters = new VanillaParameters(Patch.VANILLA, new Object2ObjectOpenHashMap<>(),
                AlphaTest.ALWAYS, false, false, false,
                new ShaderAttributeInputs(true, true, true, true, true), false, false);
        parameters.type = PatchShaderType.VERTEX;
        var transformer = new SingleASTTransformer<VanillaParameters>();
        transformer.setTransformation((tree, root) ->
                EntityPatcher.patchEntityId(transformer, tree, root, parameters));
        String shader = transformer.transform("#version 330 core\n"
                + "uniform int entityId; uniform int blockEntityId; uniform int currentRenderedItemId;\n"
                + "void main() { gl_Position = vec4(float(entityId + blockEntityId + currentRenderedItemId)); }\n");
        String compact = shader.replaceAll("\s+", "");
        boolean fixed = args[0].equals("fixed");
        if (!compact.contains(fixed ? "inuvec3iris_Entity;" : "inivec3iris_Entity;"))
            throw new AssertionError(shader);
        if (!compact.contains(fixed ? "iris_entityInfo=ivec3(iris_Entity);" : "iris_entityInfo=iris_Entity;"))
            throw new AssertionError(shader);
        if (!compact.contains("flatoutivec3iris_entityInfo;")) throw new AssertionError(shader);
        for (int value = 0; value <= 65535; value++) {
            int vertexFetch = Short.toUnsignedInt((short)value);
            if (vertexFetch != value) throw new AssertionError("entity ID changed");
        }
        System.out.println(shader);
        System.out.println("IRIS_ENTITY_AST_PASS fixed=" + fixed + " exactIDs=65536");
    }
}
