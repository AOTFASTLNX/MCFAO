package mcfao.fixture.mixin;

import mcfao.fixture.GameMod;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ClientLevel;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(Minecraft.class)
public abstract class WorldMixin {
    @Inject(method = "getVersionType", at = @At("RETURN"), cancellable = true)
    private void mcfaoVersion(CallbackInfoReturnable<String> result) {
        result.setReturnValue(result.getReturnValue() + "-mcfao-fixture");
        System.out.println("MCFAO_F2_VERSION_MIXIN_PASS");
    }

    @Inject(method = "setLevel", at = @At("RETURN"))
    private void mcfaoWorldJoin(ClientLevel level, CallbackInfo callback) {
        if (level != null) GameMod.onWorldJoined();
    }
}
