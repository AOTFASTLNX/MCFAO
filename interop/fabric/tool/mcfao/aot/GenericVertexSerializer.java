package mcfao.aot;

import java.util.ArrayList;
import java.util.List;

import com.mojang.blaze3d.vertex.VertexFormat;
import com.mojang.blaze3d.vertex.VertexFormatElement;

import net.caffeinemc.mods.sodium.api.memory.MemoryIntrinsics;
import net.caffeinemc.mods.sodium.api.vertex.serializer.VertexSerializer;

/**
 * Layout-driven equivalent of Sodium's generated vertex serializer.
 *
 * <p>Sodium emits one class per (source, target) format pair and loads it with
 * {@code MethodHandles.Lookup.defineClass}, which a closed-world image cannot do. Both formats are
 * ordinary objects at run time, so the same copy plan is computed once here: every element the
 * target carries is copied from its source offset to its target offset, and runs that stay
 * adjacent in both formats are merged, exactly like Sodium's generator merges them. A destination
 * element with no source counterpart is refused, which is also what Sodium's generator does.
 *
 * <p>The plan is fixed after construction, so the hot loop only walks three integers per run.
 */
public final class GenericVertexSerializer implements VertexSerializer {
    private final int[] plan;
    private final int sourceStride;
    private final int targetStride;

    public GenericVertexSerializer(VertexFormat source, VertexFormat target) {
        this.sourceStride = source.getVertexSize();
        this.targetStride = target.getVertexSize();
        List<int[]> runs = new ArrayList<>();
        for (VertexFormatElement element : target.getElements()) {
            if (!source.contains(element)) {
                throw new IllegalArgumentException("Source format " + source + " is missing element "
                        + element + " as required by destination format " + target);
            }
            int from = source.getOffset(element);
            int to = target.getOffset(element);
            int length = element.byteSize();
            int[] last = runs.isEmpty() ? null : runs.get(runs.size() - 1);
            if (last != null && last[0] + last[2] == from && last[1] + last[2] == to) {
                last[2] += length;
            } else {
                runs.add(new int[] {from, to, length});
            }
        }
        this.plan = new int[runs.size() * 3];
        for (int index = 0; index < runs.size(); index++) {
            System.arraycopy(runs.get(index), 0, plan, index * 3, 3);
        }
    }

    @Override
    public void serialize(long source, long target, int vertexCount) {
        int[] plan = this.plan;
        int sourceStride = this.sourceStride;
        int targetStride = this.targetStride;
        for (int vertex = 0; vertex < vertexCount; vertex++) {
            for (int step = 0; step < plan.length; step += 3) {
                MemoryIntrinsics.copyMemory(source + plan[step], target + plan[step + 1], plan[step + 2]);
            }
            source += sourceStride;
            target += targetStride;
        }
    }
}
