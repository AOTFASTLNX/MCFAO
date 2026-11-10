package org.lwjgl.system;

/** Target overlay: iOS is explicit; desktop native libraries are never selected. */
public enum Platform {
    FREEBSD("FreeBSD","freebsd"), LINUX("Linux","linux"), MACOSX("macOS","macos"),
    WINDOWS("Windows","windows"), IOS("iOS","ios");
    private final String display, path;
    Platform(String display,String path){this.display=display;this.path=path;}
    public String getName(){return display;}
    String mapLibraryName(String name){
        if(name.contains("/") || name.endsWith(".dylib") || name.endsWith(".so") || name.endsWith(".dll"))return name;
        return this==WINDOWS?name+".dll":"lib"+name+(this==MACOSX||this==IOS?".dylib":".so");
    }
    public static Platform get(){return IOS;}
    public static Architecture getArchitecture(){return Architecture.ARM64;}
    public static String mapLibraryNameBundled(String name){return IOS.mapLibraryName(name);}
    static String mapLibraryPathBundled(String name){return "ios/arm64/"+mapLibraryNameBundled(name);}
    public enum Architecture {
        X64(true),X86(false),ARM64(true),ARM32(false),PPC64LE(true),RISCV64(true);
        final boolean is64Bit;
        static final Architecture current=ARM64;
        Architecture(boolean value){is64Bit=value;}
        public boolean is32Bit(){return !is64Bit;}
        public boolean is64Bit(){return is64Bit;}
    }
}
