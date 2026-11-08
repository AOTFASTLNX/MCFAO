package fabricaot.b0.mixin;

import net.minecraft.fabricaot_fixture.Target;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(value = Target.class, remap = false)
public abstract class TargetMixin {
    @Inject(method = "mixedResult", at = @At("HEAD"), cancellable = true, remap = false)
    private void nativeFixtureResult(CallbackInfoReturnable<Integer> result) { result.setReturnValue(42); }
}
