package mcfao.build;

import java.nio.file.Path;
import java.util.Collection;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import net.fabricmc.api.EnvType;
import net.fabricmc.loader.impl.FabricLoaderImpl;
import net.fabricmc.loader.impl.discovery.ClasspathModCandidateFinder;
import net.fabricmc.loader.impl.discovery.DirectoryModCandidateFinder;
import net.fabricmc.loader.impl.discovery.ModCandidateImpl;
import net.fabricmc.loader.impl.discovery.ModDiscoverer;
import net.fabricmc.loader.impl.discovery.ModResolutionException;
import net.fabricmc.loader.impl.discovery.ModResolver;
import net.fabricmc.loader.impl.game.minecraft.MinecraftGameProvider;
import net.fabricmc.loader.impl.launch.knot.Knot;
import net.fabricmc.loader.impl.metadata.BuiltinModMetadata;
import net.fabricmc.loader.impl.metadata.DependencyOverrides;
import net.fabricmc.loader.impl.metadata.VersionOverrides;

final class FabricResolve {
    private FabricResolve() {}

    static Map<String, ?> resolve(Path client, Path work, Path mods) throws ModResolutionException {
        // Construction registers the production launcher and client side. Do not
        // call Knot.init, FabricLoaderImpl.load/freeze, or any game/mod entrypoint.
        new Knot(EnvType.CLIENT);
        FabricLoaderImpl loader = FabricLoaderImpl.INSTANCE;
        loader.setGameProvider(new MinecraftGameProvider() {
            @Override public Path getLaunchDirectory() {
                return work;
            }

            @Override public Collection<BuiltinMod> getBuiltinMods() {
                var metadata = new BuiltinModMetadata.Builder("minecraft", "26.1.2").setName("Minecraft").build();
                return List.of(new BuiltinMod(List.of(client), metadata));
            }
        });
        var discoverer = new ModDiscoverer(new VersionOverrides(), new DependencyOverrides(work.resolve("config")));
        discoverer.addCandidateFinder(new ClasspathModCandidateFinder());
        discoverer.addCandidateFinder(new DirectoryModCandidateFinder(mods, false));
        Map<String, Set<ModCandidateImpl>> disabled = new HashMap<>();
        var candidates = discoverer.discoverMods(loader, disabled);
        try {
            var selected = ModResolver.resolve(candidates, EnvType.CLIENT, disabled);
            return Map.of("status", "RESOLVED", "selected", selected.stream().map(mod -> Map.of(
                    "id", mod.getId(), "version", mod.getVersion().getFriendlyString(),
                    "source", mod.getLocalPath(), "root", mod.isRoot(),
                    "parents", mod.getParentMods().stream().map(ModCandidateImpl::getId).sorted().toList()
            )).toList());
        } catch (ModResolutionException error) {
            return Map.of("status", "UNSATISFIED", "reason", error.getMessage());
        }
    }
}
