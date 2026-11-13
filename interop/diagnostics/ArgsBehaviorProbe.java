import java.lang.reflect.Method;
import java.util.Arrays;
import org.spongepowered.asm.mixin.injection.invoke.arg.Args;
import org.spongepowered.asm.mixin.injection.invoke.arg.ArgumentCountException;
import org.spongepowered.asm.mixin.injection.invoke.arg.ArgumentIndexOutOfBoundsException;

/** Runs only the exported, pinned Mixin argument carriers; does not initialize Mod code. */
public final class ArgsBehaviorProbe {
    private static Object value(Class<?> type) {
        if (!type.isPrimitive()) return type == String.class ? "proof" : null;
        return switch (type.getName()) {
            case "boolean" -> true;
            case "byte" -> (byte) 3;
            case "short" -> (short) 4;
            case "char" -> 'a';
            case "int" -> 5;
            case "long" -> 6L;
            case "float" -> 7f;
            case "double" -> 8d;
            default -> throw new AssertionError(type);
        };
    }

    public static void main(String[] names) throws Exception {
        if (names.length == 0) throw new AssertionError("No exported Args classes");
        for (String name : names) {
            Class<?> type = Class.forName(name, false, ArgsBehaviorProbe.class.getClassLoader());
            Method factory = Arrays.stream(type.getDeclaredMethods()).filter(m -> m.getName().equals("of"))
                    .findFirst().orElseThrow();
            Class<?>[] parameters = factory.getParameterTypes();
            Object[] values = Arrays.stream(parameters).map(ArgsBehaviorProbe::value).toArray();
            Args holder = (Args) factory.invoke(null, values);
            if (holder.size() != values.length) throw new AssertionError("Wrong argument count");
            for (int i = 0; i < values.length; i++) {
                if (!java.util.Objects.equals(type.getMethod("$" + i).invoke(holder), values[i])) {
                    throw new AssertionError("Typed getter changed: " + name + ".$" + i);
                }
                holder.set(i, values[i]);
                if (parameters[i].isPrimitive()) {
                    try { holder.set(i, null); throw new AssertionError("Primitive accepted null"); }
                    catch (NullPointerException expected) { }
                } else if (parameters[i] != Object.class && parameters[i] != String.class) {
                    try { holder.set(i, new Object()); throw new AssertionError("Reference type check missing"); }
                    catch (ClassCastException expected) { }
                }
            }
            holder.setAll(values);
            try { holder.set(-1, null); throw new AssertionError("Negative index accepted"); }
            catch (ArgumentIndexOutOfBoundsException expected) { }
            if (values.length > 0) {
                try { holder.setAll(); throw new AssertionError("Wrong argument count accepted"); }
                catch (ArgumentCountException expected) { }
            }
        }
        System.out.println("MCFAO_ARGS_BEHAVIOR_PASS classes=" + names.length);
    }
}
