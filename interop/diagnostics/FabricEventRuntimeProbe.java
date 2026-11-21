import java.util.ArrayList;
import java.util.List;
import net.fabricmc.fabric.api.event.EventFactory;

public final class FabricEventRuntimeProbe {
    interface Listener {
        void onEvent(String argument);
    }

    public static void main(String[] args) {
        var events = new ArrayList<String>();
        var event = EventFactory.createArrayBacked(Listener.class,
                listeners -> argument -> {
                    for (var listener : listeners) listener.onEvent(argument);
                });
        event.invoker().onEvent("empty");
        event.register(value -> events.add("first:" + value));
        event.invoker().onEvent("one");
        event.register(value -> events.add("second:" + value));
        event.invoker().onEvent("two");
        var failure = new IllegalStateException("registered listener failure");
        event.register(value -> { throw failure; });
        event.register(value -> events.add("after:" + value));
        try {
            event.invoker().onEvent("error");
            throw new AssertionError("Listener exception was swallowed");
        } catch (IllegalStateException error) {
            if (error != failure) throw error;
        }
        if (!events.equals(List.of("first:one", "first:two", "second:two", "first:error", "second:error"))) {
            throw new AssertionError("Fabric event order differs: " + events);
        }
        System.out.println("FABRIC_EVENT_RUNTIME_PASS " + events);
    }
}
