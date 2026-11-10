package fabricaot.metal;
import com.mojang.blaze3d.textures.TextureFormat;
/** Bounds arithmetic regression tests; no native library or game initialization. */
public final class TextureSpecProbe {
    private static void invalid(Runnable operation){try{operation.run();}catch(IllegalArgumentException|ArithmeticException expected){return;}throw new AssertionError("Invalid range accepted");}
    private static void overBudget(Runnable operation){try{operation.run();}catch(OutOfMemoryError expected){return;}throw new AssertionError("Metal resource limit exceeded without error");}
    public static void main(String[] args){
        if(TextureSpec.byteSize(TextureFormat.RGBA8,7,5,1,3,7)!=168)throw new AssertionError("mip allocation");
        if(TextureSpec.byteSize(TextureFormat.RGBA8,4,4,6,1,16)!=384)throw new AssertionError("cubemap allocation");
        invalid(()->TextureSpec.byteSize(TextureFormat.RGBA8,7,5,1,4,7));
        invalid(()->TextureSpec.byteSize(TextureFormat.RGBA8,4,3,6,1,16));
        invalid(()->TextureSpec.byteSize(TextureFormat.RGBA8,4,4,5,1,16));
        invalid(()->TextureSpec.rectangle(16,16,Integer.MAX_VALUE,0,2,2));
        invalid(()->TextureSpec.rectangle(16,16,0,0,-1,2));
        invalid(()->TextureSpec.range(Long.MAX_VALUE,Long.MAX_VALUE-3,4));
        TextureSpec.rectangle(7,5,6,4,1,1);TextureSpec.range(Long.MAX_VALUE,Long.MAX_VALUE-4,4);
        long terrain=416*ResourceBudget.MIB;
        ResourceBudget defaults=new ResourceBudget(null);
        overBudget(()->defaults.reserve(terrain));
        ResourceBudget simulator=new ResourceBudget("768");
        simulator.reserve(terrain);
        overBudget(()->simulator.reserve(Long.MAX_VALUE));
        simulator.reserve(352*ResourceBudget.MIB);
        overBudget(()->simulator.reserve(1));
        simulator.release(terrain);
        simulator.reserve(terrain);
        invalid(()->new ResourceBudget("1025"));
        System.out.println("METAL_TEXTURE_CONTRACT_PASS");
    }
}
