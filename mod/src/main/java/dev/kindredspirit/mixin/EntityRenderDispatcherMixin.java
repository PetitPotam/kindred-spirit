package dev.kindredspirit.mixin;

import dev.kindredspirit.guest.GuestBridge;
import net.minecraft.client.renderer.culling.Frustum;
import net.minecraft.client.renderer.entity.EntityRenderDispatcher;
import net.minecraft.world.entity.Entity;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/** Pip's stand-in for LAN guests (see GuestBridge) isn't drawn on your own screen: you see your Pip. */
@Mixin(EntityRenderDispatcher.class)
public abstract class EntityRenderDispatcherMixin {
    @Inject(method = "shouldRender", at = @At("HEAD"), cancellable = true)
    //? if >=26.1 {
    private <E extends Entity> void kindredspirit$hideStandIn(E entity, Frustum frustum, double x, double y, double z,
                                                            float partialTicks, CallbackInfoReturnable<Boolean> cir) {
    //?} else {
    /*private <E extends Entity> void kindredspirit$hideStandIn(E entity, Frustum frustum, double x, double y, double z,
                                                            CallbackInfoReturnable<Boolean> cir) {
    *///?}
        if (GuestBridge.hidden != null && GuestBridge.hidden.equals(entity.getUUID())) cir.setReturnValue(false);
    }
}
