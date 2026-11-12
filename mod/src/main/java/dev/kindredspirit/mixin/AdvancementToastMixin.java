package dev.kindredspirit.mixin;

import dev.kindredspirit.KindredSpiritClient;
import net.minecraft.advancements.AdvancementHolder;
import net.minecraft.client.gui.components.toasts.AdvancementToast;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** When you earn an advancement (the toast appears), she gets to hear about it. */
@Mixin(AdvancementToast.class)
public abstract class AdvancementToastMixin {
    @Inject(method = "<init>", at = @At("TAIL"))
    private void kindredspirit$earned(AdvancementHolder holder, CallbackInfo ci) {
        holder.value().display().ifPresent(d -> KindredSpiritClient.get().advancement(d.getTitle().getString()));
    }
}
