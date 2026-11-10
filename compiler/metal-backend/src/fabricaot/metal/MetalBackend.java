package fabricaot.metal;
import com.mojang.blaze3d.GLFWErrorCapture;
import com.mojang.blaze3d.shaders.*;
import com.mojang.blaze3d.systems.*;
import static org.lwjgl.glfw.GLFW.*;

/** Experimental blaze3d backend using build-time compiled vanilla Metal shaders. */
public final class MetalBackend implements GpuBackend {
    private MetalDevice device;
    public String getName(){return "FabricAOT Metal (experimental)";}
    public void setWindowHints(){glfwWindowHint(GLFW_CLIENT_API,GLFW_NO_API);}
    public void handleWindowCreationErrors(GLFWErrorCapture.Error error)throws BackendCreationException{
        if(error!=null)throw new BackendCreationException("GLFW-lite: "+error);
    }
    public GpuDevice createDevice(long window,ShaderSource source,GpuDebugOptions options){
        if(device!=null)throw new IllegalStateException("Metal device already created");
        device=new MetalDevice(window,source);return new GpuDevice(device);
    }
    /** Convert the GL-oriented sampling coordinates of the already rendered GUI item atlas. */
    public static float guiItemAtlasV(float glV) {
        return "Metal".equals(RenderSystem.getDevice().getBackendName()) ? 1.0f-glV : glV;
    }
    /** Integration probe only: Metal load-action clear, without a Minecraft render pipeline. */
    public void clearDiagnosticFrame(){
        if(device==null)throw new IllegalStateException("Metal device not created");
        device.clearDiagnosticFrame();
    }
}
