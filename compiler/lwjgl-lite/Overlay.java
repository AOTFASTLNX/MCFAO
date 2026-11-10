package fabricaot.graphics;
import org.objectweb.asm.*;
import java.nio.file.*;
import java.util.*;
import java.util.zip.*;

/** Offline patcher: removes the FFM multi-release core and libffi descriptor initialization. */
public final class Overlay {
    public static void main(String[] args)throws Exception{
        if(args.length!=4)throw new IllegalArgumentException("input.jar output.jar overlay-classes supported-c-symbols");
        Path classes=Path.of(args[2]);
        Set<String> supported=new HashSet<>(Files.readAllLines(Path.of(args[3])));
        Set<String> replacement=new TreeSet<>();
        try(var paths=Files.walk(classes)){paths.filter(Files::isRegularFile).forEach(p->replacement.add(classes.relativize(p).toString().replace('\\','/')));}
        int descriptors=0,versions=0;
        try(ZipFile in=new ZipFile(args[0]);ZipOutputStream out=new ZipOutputStream(Files.newOutputStream(Path.of(args[1])))){
            var entries=in.entries();
            while(entries.hasMoreElements()){
                ZipEntry entry=entries.nextElement();String name=entry.getName();
                if(entry.isDirectory()||replacement.contains(name))continue;
                if(name.startsWith("META-INF/versions/")){versions++;continue;}
                if(name.matches("(?i)META-INF/[^/]+\\.(SF|RSA|DSA|EC)")||name.startsWith("META-INF/SIG-"))continue;
                byte[] data=in.getInputStream(entry).readAllBytes();
                if(name.equals("org/lwjgl/openal/ALC.class")){
                    ClassReader reader=new ClassReader(data);ClassWriter writer=new ClassWriter(0);
                    reader.accept(new ClassVisitor(Opcodes.ASM9,writer){
                        public MethodVisitor visitMethod(int access,String method,String desc,String sig,String[] ex){
                            MethodVisitor mv=super.visitMethod(access,method,desc,sig,ex);
                            if(!method.equals("create")||!desc.equals("()V"))return mv;
                            mv.visitCode();mv.visitLdcInsn("openal");
                            mv.visitMethodInsn(Opcodes.INVOKESTATIC,"org/lwjgl/openal/ALC","create","(Ljava/lang/String;)V",false);
                            mv.visitInsn(Opcodes.RETURN);mv.visitMaxs(1,0);mv.visitEnd();return null;
                        }
                    },0);data=writer.toByteArray();
                }
                if((name.startsWith("org/lwjgl/glfw/")||name.startsWith("org/lwjgl/stb/"))&&name.endsWith("CallbackI.class")){
                    ClassReader reader=new ClassReader(data);ClassWriter writer=new ClassWriter(0);
                    reader.accept(new ClassVisitor(Opcodes.ASM9,writer){
                        public MethodVisitor visitMethod(int access,String method,String desc,String sig,String[] ex){
                            MethodVisitor mv=super.visitMethod(access,method,desc,sig,ex);
                            if(!method.equals("<clinit>"))return mv;
                            mv.visitCode();mv.visitInsn(Opcodes.ACONST_NULL);
                            mv.visitFieldInsn(Opcodes.PUTSTATIC,reader.getClassName(),"DESCRIPTOR","Lorg/lwjgl/system/Callback$Descriptor;");
                            mv.visitInsn(Opcodes.RETURN);mv.visitMaxs(1,0);mv.visitEnd();return null;
                        }
                    },0);data=writer.toByteArray();descriptors++;
                }
                if(name.equals("org/lwjgl/glfw/GLFW.class")||name.equals("org/lwjgl/glfw/GLFW$Functions.class")){
                    ClassReader reader=new ClassReader(data);ClassWriter writer=new ClassWriter(0);
                    reader.accept(new ClassVisitor(Opcodes.ASM9,writer){
                        public MethodVisitor visitMethod(int access,String method,String desc,String sig,String[] ex){
                            MethodVisitor mv=super.visitMethod(access,method,desc,sig,ex);
                            String cName=method.startsWith("nglfw")?method.substring(1):method;
                            if(name.equals("org/lwjgl/glfw/GLFW.class")&&cName.startsWith("glfw")&&!supported.contains(cName)){
                                mv.visitCode();mv.visitTypeInsn(Opcodes.NEW,"java/lang/UnsupportedOperationException");
                                mv.visitInsn(Opcodes.DUP);mv.visitLdcInsn("GLFW-lite unsupported API: "+cName);
                                mv.visitMethodInsn(Opcodes.INVOKESPECIAL,"java/lang/UnsupportedOperationException","<init>","(Ljava/lang/String;)V",false);
                                mv.visitInsn(Opcodes.ATHROW);
                                int locals=(access&Opcodes.ACC_STATIC)!=0?0:1;for(Type t:Type.getArgumentTypes(desc))locals+=t.getSize();
                                mv.visitMaxs(3,locals);mv.visitEnd();return null;
                            }
                            return new MethodVisitor(Opcodes.ASM9,mv){
                                public void visitMethodInsn(int op,String owner,String target,String descriptor,boolean itf){
                                    if(owner.equals("org/lwjgl/system/APIUtil")&&target.equals("apiGetFunctionAddress")){
                                        super.visitMethodInsn(op,owner,"apiGetFunctionAddressOptional","(Lorg/lwjgl/system/SharedLibrary;Ljava/lang/String;)J",itf);
                                    }else super.visitMethodInsn(op,owner,target,descriptor,itf);
                                }
                            };
                        }
                    },0);data=writer.toByteArray();
                }
                ZipEntry copy=new ZipEntry(name);copy.setTime(0);out.putNextEntry(copy);out.write(data);out.closeEntry();
            }
            for(String name:replacement){ZipEntry e=new ZipEntry(name);e.setTime(0);out.putNextEntry(e);out.write(Files.readAllBytes(classes.resolve(name)));out.closeEntry();}
        }
        System.out.println("OVERLAY_PASS descriptors="+descriptors+" removedMultiReleaseEntries="+versions);
    }
}
