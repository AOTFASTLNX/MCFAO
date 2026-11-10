package org.lwjgl.system;

import java.nio.ByteBuffer;
import java.nio.file.Path;
import java.util.function.Consumer;
import java.util.function.Supplier;

/** Loads only explicit prebuilt libraries from the host-provided signed Frameworks directory. */
public final class Library {
    public static final String JNI_LIBRARY_NAME="liblwjgl.dylib";
    static final String JAVA_LIBRARY_PATH="org.lwjgl.librarypath";
    static {
        System.load(localPath(JNI_LIBRARY_NAME).toString());
        System.err.println("[LWJGL-lite] explicit iOS JNI backend; static callbacks; no FFM upcalls");
    }
    private Library(){}
    private static Path localPath(String name){
        String directory=System.getProperty(JAVA_LIBRARY_PATH);
        if(directory==null || directory.isBlank())throw new UnsatisfiedLinkError("Missing signed native directory: "+JAVA_LIBRARY_PATH);
        String file=Platform.mapLibraryNameBundled(name);
        if(!file.matches("lib[A-Za-z0-9_-]+\\.dylib"))throw new UnsatisfiedLinkError("Native path is outside the signed library allowlist: "+name);
        return Path.of(directory).toAbsolutePath().normalize().resolve(file);
    }
    public static void initialize(){}
    public static void loadSystem(String module,String name){if(!JNI_LIBRARY_NAME.equals(Platform.mapLibraryNameBundled(name)))System.load(localPath(name).toString());}
    public static void loadSystem(Consumer<String> byName,Consumer<String> byPath,Class<?> context,String module,String name){loadSystem(module,name);}
    public static SharedLibrary loadNative(String module,String name){return loadNative(Library.class,module,name);}
    public static SharedLibrary loadNative(Class<?> context,String module,String name){return new NativeLibrary(localPath(name));}
    public static SharedLibrary loadNative(Class<?> context,String module,String name,boolean bundled){return loadNative(context,module,name);}
    public static SharedLibrary loadNative(Class<?> context,String module,Configuration<String> config,String... names){return loadNative(context,module,config,null,names);}
    public static SharedLibrary loadNative(Class<?> context,String module,Configuration<String> config,Supplier<SharedLibrary> fallback,String... names){
        String configured=config.get();
        if(configured!=null)return loadNative(context,module,configured);
        UnsatisfiedLinkError failure=null;
        for(String name:names)try{return loadNative(context,module,name);}catch(UnsatisfiedLinkError e){failure=e;}
        // The desktop supplier may open system frameworks. iOS never invokes it.
        if(failure!=null)throw failure;
        throw new UnsatisfiedLinkError("No signed library candidates for "+module);
    }
    static void printError(String message){System.err.println("[LWJGL-lite] "+message);}
    private static final class NativeLibrary implements SharedLibrary {
        private final Path path;
        private long handle;
        NativeLibrary(Path path){this.path=path;handle=IOSNative.open(path.toString());if(handle==0)throw new UnsatisfiedLinkError("Cannot open "+path+": "+IOSNative.error());}
        public String getName(){return path.getFileName().toString();}
        public String getPath(){return path.toString();}
        public long address(){return handle;}
        public long getFunctionAddress(ByteBuffer name){return IOSNative.symbol(handle,MemoryUtil.memAddress(name));}
        public void free(){if(handle!=0){IOSNative.close(handle);handle=0;}}
    }
}
