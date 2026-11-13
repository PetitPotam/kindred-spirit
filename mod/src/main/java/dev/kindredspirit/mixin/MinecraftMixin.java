package dev.kindredspirit.mixin;

import dev.kindredspirit.record.FrameRecorder;
import net.minecraft.client.Minecraft;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * Hands each finished frame to the demo recorder, right before it is shown. Does nothing unless recording.
 * Optional (require = 0): from 26.1 on the frame is shown differently and recording isn't available there yet.
 */
@Mixin(Minecraft.class)
public abstract class MinecraftMixin {
    @Inject(method = "runTick", at = @At(value = "INVOKE", target = "Lcom/mojang/blaze3d/platform/Window;updateDisplay()V"), require = 0)
    private void kindredspirit$beforeShow(boolean tick, CallbackInfo ci) {
        FrameRecorder.captureFrame();
    }
}
