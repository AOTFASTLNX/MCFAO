package mcfao.build;
import java.util.*;
import java.nio.file.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import net.fabricmc.loader.api.*;
import net.fabricmc.loader.api.metadata.*;
import net.fabricmc.loader.impl.metadata.*;
import mcfao.aot.ModCatalog;
public final class ModSnapshotProbe {
    public static void main(String[] args) throws Exception {
        String descriptor="""
        {"schemaVersion":1,"id":"parity","version":"1.2.3","environment":"client",
         "name":"Parity","description":"Fixture","provides":["alias"],
         "authors":[{"name":"Author","contact":{"homepage":"https://example.org"}}],
         "contact":{"issues":"https://example.org/issues"},"license":["MIT"],
         "depends":{"minecraft":[">=26.1","1.21.1"]},
         "custom":{"null-value":null,"nested":{"array":[true,3,"text"]}},
         "icon":{"16":"small.png","8192":"large.png"}}
        """;
        Files.writeString(Path.of(args[0],"fabric.mod.json"),descriptor);
        var meta=ModMetadataParser.parseMetadata(new ByteArrayInputStream(descriptor.getBytes(StandardCharsets.UTF_8)),
                "fixture",List.of(),new VersionOverrides(),new DependencyOverrides(Path.of(args[0])),false);
        ModContainer source=new ModContainer() {
            public ModMetadata getMetadata(){return meta;}
            public List<Path> getRootPaths(){return List.of(Path.of(args[0]));}
            public Path getRootPath(){return getRootPaths().getFirst();}
            public Path getPath(String p){return getRootPath().resolve(p);}
            public Optional<ModContainer> getContainingMod(){return Optional.empty();}
            public Collection<ModContainer> getContainedMods(){return List.of();}
            public ModOrigin getOrigin(){return new ModOrigin(){
                public Kind getKind(){return Kind.PATH;}
                public List<Path> getPaths(){return getRootPaths();}
                public String getParentModId(){throw new UnsupportedOperationException();}
                public String getParentSubLocation(){throw new UnsupportedOperationException();}
            };}
        };
        var snapshot=ModSnapshot.capture(source,List.of());

        Path file=Path.of(args[0],"mcfao/mod-catalog.json");Files.createDirectories(file.getParent());
        Files.writeString(file,ModSnapshot.json(Map.of("parity",snapshot)));
        var actual=ModCatalog.required("parity").getMetadata();
        if(!Set.copyOf(actual.getProvides()).equals(Set.copyOf(meta.getProvides())) || actual.getEnvironment()!=meta.getEnvironment()
                || !Set.copyOf(actual.getLicense()).equals(Set.copyOf(meta.getLicense())) || !actual.getContact().asMap().equals(meta.getContact().asMap())) throw new AssertionError("metadata parity");
        if(actual.getCustomValue("null-value")==null || actual.getCustomValue("null-value").getType()!=CustomValue.CvType.NULL) throw new AssertionError("null custom");
        for(int size:new int[]{0,1,16,17,8192,8193,Integer.MAX_VALUE})
            if(!actual.getIconPath(size).equals(meta.getIconPath(size))) throw new AssertionError("icon parity "+size);
        var expectedDep=meta.getDependencies().iterator().next();var actualDep=actual.getDependencies().iterator().next();
        for(String v:List.of("26.1.2","1.21.1","1.20.1"))
            if(expectedDep.matches(Version.parse(v))!=actualDep.matches(Version.parse(v)))throw new AssertionError("dependency parity "+v);
        System.out.println("MOD_SNAPSHOT_PARITY_PASS");
    }
}
