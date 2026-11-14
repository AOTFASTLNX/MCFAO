package fabricaot.graphics;
import java.nio.ByteBuffer;
import org.lwjgl.glfw.*;
import org.lwjgl.system.*;
import static org.lwjgl.glfw.GLFW.*;

/** Host test of the real LWJGL Java API against first-party JNI and C window state. */
public final class LwjglProbe {
    public static void main(String[] args){
        if(Platform.get()!=Platform.IOS)throw new AssertionError("explicit iOS platform missing");
        ByteBuffer b=MemoryUtil.memAlloc(32);
        long address=MemoryUtil.memAddress(b);
        MemoryUtil.memPutInt(address,0x12345678);
        if(b.getInt(0)!=0x12345678)throw new AssertionError("Unsafe/native buffer view mismatch");
        ByteBuffer aligned=MemoryUtil.memAlignedAlloc(64,128);
        if(MemoryUtil.memAddress(aligned)%64!=0)throw new AssertionError("alignment");
        MemoryUtil.memAlignedFree(aligned);MemoryUtil.memFree(b);
        org.lwjgl.PointerBuffer pointers=MemoryUtil.memCallocPointer(2);
        org.lwjgl.PointerBuffer other=MemoryUtil.memCallocPointer(2);
        try{
            if(ThreadLocalUtil.setupAddressBuffer(pointers).get(0)!=0)throw new AssertionError("missing pointers must remain checked zero values");
            pointers.put(0,123);other.put(0,456);
            if(!ThreadLocalUtil.areCapabilitiesDifferent(pointers,other))throw new AssertionError("different dispatch tables accepted");
            other.put(0,0);
            if(ThreadLocalUtil.areCapabilitiesDifferent(pointers,other))throw new AssertionError("optional missing pointer comparison");
            boolean missing=false;try{JNI.invokeV(0L);}catch(UnsatisfiedLinkError expected){missing=true;}
            if(!missing)throw new AssertionError("zero native pointer was not rejected");
        }finally{MemoryUtil.memFree(pointers);MemoryUtil.memFree(other);}
        int[] errors={0};
        GLFWErrorCallback error=GLFWErrorCallback.create((code,text)->{if(code!=0)errors[0]++;});
        glfwSetErrorCallback(error);
        if(!glfwInit())throw new AssertionError("init");
        glfwDefaultWindowHints();
        if(glfwCreateWindow(10,10,"reject GL",0,0)!=0)throw new AssertionError("GL incorrectly accepted");
        if(errors[0]!=1)throw new AssertionError("native -> Java error callback");
        glfwGetError(null);
        glfwWindowHint(GLFW_CLIENT_API,GLFW_NO_API);
        long window=glfwCreateWindow(10,10,"host fixture",0,0);
        if(window==0)throw new AssertionError("window");
        if(GLFW.getLibrary().getFunctionAddress("glfwGetMouseButton")==0)
            throw new AssertionError("malilib mouse polling symbol missing");
        // Exercise the exact Java -> invokePI(JIJ)I -> GLFW boundary from the
        // device crash. The C state fixture separately covers press/release.
        for(int tick=0;tick<300;tick++){
            for(int button=0;button<=GLFW_MOUSE_BUTTON_LAST;button++)
                if(glfwGetMouseButton(window,button)!=GLFW_RELEASE)
                    throw new AssertionError("unexpected initial mouse state");
            if(glfwGetKey(window,GLFW_KEY_W)!=GLFW_RELEASE)
                throw new AssertionError("unexpected initial key state");
        }
        System.out.println("LWJGL_INPUT_POLL_PASS ticks=300 buttons=8");
        int[] x={0},y={0};glfwGetFramebufferSize(window,x,y);
        if(x[0]!=1170||y[0]!=2532)throw new AssertionError("array JNI ABI");
        int[] calls={0};
        GLFWFramebufferSizeCallback resized=GLFWFramebufferSizeCallback.create((w,width,height)->{if(w==window&&width==1170&&height==2532)calls[0]++;});
        glfwSetFramebufferSizeCallback(window,resized);glfwPollEvents();
        if(calls[0]!=1)throw new AssertionError("native -> Java resize callback");
        GLFWFramebufferSizeCallback previous=glfwSetFramebufferSizeCallback(window,null);
        if(previous.address()!=resized.address())throw new AssertionError("callback address identity");
        previous.free();
        GLFWErrorCallback[] slots=new GLFWErrorCallback[31];
        for(int i=0;i<slots.length;i++)slots[i]=GLFWErrorCallback.create((a,c)->{});
        boolean rejected=false;
        try{GLFWErrorCallback.create((a,c)->{});}catch(IllegalStateException expected){rejected=true;}
        if(!rejected)throw new AssertionError("static callback capacity was not enforced");
        for(GLFWErrorCallback callback:slots)callback.free();
        rejected=false;
        try{glfwWaitEvents();}catch(UnsupportedOperationException expected){rejected=true;}
        if(!rejected)throw new AssertionError("unsupported API must fail explicitly");
        glfwDestroyWindow(window);glfwTerminate();error.free();
        System.out.println("LWJGL_STATIC_BRIDGE_PASS");
    }
}
