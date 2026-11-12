package dev.kindredspirit.mixin;

import dev.kindredspirit.KindredSpiritClient;
import net.minecraft.client.multiplayer.MultiPlayerGameMode;
import net.minecraft.core.BlockPos;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/** Counts the blocks you break, so she notices when you've been mining for a while. */
@Mixin(MultiPlayerGameMode.class)
public abstract class GameModeMixin {
    @Inject(method = "destroyBlock", at = @At("RETURN"))
    private void kindredspirit$broke(BlockPos pos, CallbackInfoReturnable<Boolean> cir) {
        if (Boolean.TRUE.equals(cir.getReturnValue())) KindredSpiritClient.get().blockBroken();
    }
}
