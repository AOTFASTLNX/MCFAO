import java.security.MessageDigest;
import java.util.HashMap;
import java.util.HexFormat;
import net.fabricmc.fabric.api.resource.v1.pack.ModPackResources;
import net.fabricmc.fabric.impl.resource.pack.ModPackResourcesUtil;
import net.minecraft.resources.Identifier;
import net.minecraft.server.packs.PackType;

/** Exercises the converted repository's real pack enumeration and resource reads on the JVM. */
public final class FabricPackRuntimeProbe {
    public static void main(String[] args) throws Exception {
        for (PackType type : PackType.values()) {
            java.util.List<?> resolved = ModPackResourcesUtil.getModResourcePacks(null, type, null);
            var packs = resolved.stream().map(ModPackResources.class::cast).toList();
            try {
                var byId = new HashMap<String, ModPackResources>();
                for (var pack : packs) {
                    String id = pack.getFabricModMetadata().getId();
                    if (byId.putIfAbsent(id, pack) != null) throw new AssertionError("Duplicate pack " + id);
                    if (pack.getNamespaces(type).isEmpty()) throw new AssertionError("Empty pack " + id);
                }
                for (int i = 0; i < args.length; i += 4) {
                    if (!type.name().equals(args[i])) continue;
                    String mod = args[i + 1];
                    var pack = byId.get(mod);
                    if (pack == null) throw new AssertionError("Missing pack for " + mod);
                    var supplier = pack.getResource(type, Identifier.parse(args[i + 2]));
                    if (supplier == null) throw new AssertionError("Missing resource " + args[i + 2]);
                    try (var in = supplier.get()) {
                        if (!HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                                .digest(in.readAllBytes())).equals(args[i + 3])) {
                            throw new AssertionError("Resource differs in " + mod);
                        }
                    }
                }
                System.out.println("FABRIC_PACKS " + type + " " + packs.stream()
                        .map(pack -> pack.getFabricModMetadata().getId()).toList());
            } finally {
                for (var pack : packs) pack.close();
            }
        }
        System.out.println("FABRIC_PACK_RUNTIME_PASS");
    }
}
