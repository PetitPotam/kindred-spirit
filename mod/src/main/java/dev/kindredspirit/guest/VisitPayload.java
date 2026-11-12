package dev.kindredspirit.guest;

import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.network.codec.ByteBufCodecs;
import net.minecraft.network.codec.StreamCodec;
import net.minecraft.network.protocol.common.custom.CustomPacketPayload;
import net.minecraft.resources.ResourceLocation;

/**
 * A visiting Pip, from her owner's game to the friend's world they joined (the host's game has
 * Kindred but her brain lives with the visitor): her state, her words for the others, and the
 * powers she uses there (JSON: {"kind": "state" | "say" | "act", ...}).
 */
public record VisitPayload(String json) implements CustomPacketPayload {
    public static final Type<VisitPayload> TYPE = new Type<>(ResourceLocation.fromNamespaceAndPath("kindredspirit", "visit"));
    public static final StreamCodec<RegistryFriendlyByteBuf, VisitPayload> CODEC =
            StreamCodec.composite(ByteBufCodecs.STRING_UTF8, VisitPayload::json, VisitPayload::new);

    @Override
    public Type<? extends CustomPacketPayload> type() {
        return TYPE;
    }
}
