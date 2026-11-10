package fabricaot.graphics;
import java.util.OptionalInt;
import com.mojang.blaze3d.platform.*;
import com.mojang.blaze3d.systems.*;
import fabricaot.metal.MetalBackend;
import static org.lwjgl.glfw.GLFW.*;
/** Actual Window + RenderSystem initialization, followed by an explicitly diagnostic Metal clear. */
public final class MetalProbe {
    public static void main(String[] args)throws Exception{
        RenderSystem.initRenderThread();GLX._initGlfw(new BackendOptions(false));
        MetalBackend backend=new MetalBackend();
        Window window=new Window(new WindowEventHandler(){public void resizeGui(){}public void cursorEntered(){}},
            new DisplayData(390,844,OptionalInt.empty(),OptionalInt.empty(),false),null,"FabricAOT Metal integration probe",backend);
        GpuDevice device=backend.createDevice(window.handle(),null,null);
        RenderSystem.initRenderer(device);
        System.out.println("MINECRAFT_RENDER_SYSTEM_INITIALIZED backend="+device.getBackendName()+" device="+device.getRenderer());
        backend.clearDiagnosticFrame();
        System.out.println("METAL_INTEGRATION_PROBE_FRAME_READY (diagnostic clear; Minecraft pipelines unavailable)");
        Thread.sleep(20000);
        RenderSystem.getSamplerCache().close();
        device.close();window.close();
        System.out.println("METAL_INTEGRATION_PROBE_PASS");
    }
}
