package dev.kindredspirit.mixin;

import dev.kindredspirit.KindredSpiritClient;
import net.minecraft.client.multiplayer.MultiPlayerGameMode;
import net.minecraft.core.BlockPos;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/** The blocks you break (and which), so she notices when you've been mining, and what. */
@Mixin(MultiPlayerGameMode.class)
public abstract class GameModeMixin {
    @org.spongepowered.asm.mixin.Unique
    private String kindredspirit$breaking;

    @Inject(method = "destroyBlock", at = @At("HEAD"))
    private void kindredspirit$breaking(BlockPos pos, CallbackInfoReturnable<Boolean> cir) {
        net.minecraft.client.Minecraft mc = net.minecraft.client.Minecraft.getInstance();
        kindredspirit$breaking = mc.level == null ? null : net.minecraft.core.registries.BuiltInRegistries.BLOCK
                .getKey(mc.level.getBlockState(pos).getBlock()).toString();
    }

    @Inject(method = "destroyBlock", at = @At("RETURN"))
    private void kindredspirit$broke(BlockPos pos, CallbackInfoReturnable<Boolean> cir) {
        if (Boolean.TRUE.equals(cir.getReturnValue())) KindredSpiritClient.get().blockBroken(kindredspirit$breaking);
    }
}
