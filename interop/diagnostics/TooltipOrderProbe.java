import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.HashSet;
import net.fabricmc.fabric.impl.item.VanillaTooltipProviderOrder;
import net.minecraft.SharedConstants;
import net.minecraft.core.component.DataComponentType;
import net.minecraft.core.component.DataComponents;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.item.ItemStack;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;

public final class TooltipOrderProbe {
    public static void main(String[] args) throws Exception {
        var output = System.out;
        SharedConstants.tryDetectVersion();
        Bootstrap.bootStrap();
        var itemStack = new ClassNode();
        try (var in = ItemStack.class.getResourceAsStream("ItemStack.class")) {
            new ClassReader(in).accept(itemStack, ClassReader.SKIP_DEBUG);
        }
        var target = itemStack.methods.stream().filter(method -> method.name.equals("addDetailsToTooltip"))
                .findFirst().orElseThrow();
        var expected = new ArrayList<DataComponentType<?>>();
        var seen = new HashSet<String>();
        for (var instruction : target.instructions) {
            if (instruction instanceof FieldInsnNode field && field.getOpcode() == Opcodes.GETSTATIC
                    && field.owner.equals("net/minecraft/core/component/DataComponents")
                    && field.desc.equals("Lnet/minecraft/core/component/DataComponentType;")
                    && seen.add(field.name)) {
                Field component = DataComponents.class.getField(field.name);
                expected.add((DataComponentType<?>) component.get(null));
            } else if (instruction instanceof MethodInsnNode call
                    && call.owner.equals(itemStack.name) && call.name.equals("addAttributeTooltips")) {
                expected.add(DataComponents.ATTRIBUTE_MODIFIERS);
            }
        }
        var actual = VanillaTooltipProviderOrder.getVanillaOrder();
        if (expected.isEmpty() || !actual.equals(expected)) throw new AssertionError("Component order differs");
        try {
            actual.clear();
            throw new AssertionError("Tooltip order is mutable");
        } catch (UnsupportedOperationException expectedFailure) {
            output.println("Tooltip components: " + expected.size());
            output.println("TOOLTIP_ORDER_RUNTIME_PASS");
        }
    }
}
