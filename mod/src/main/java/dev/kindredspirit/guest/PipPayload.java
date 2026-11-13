package dev.kindredspirit.guest;

import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.network.codec.ByteBufCodecs;
import net.minecraft.network.codec.StreamCodec;
import net.minecraft.network.protocol.common.custom.CustomPacketPayload;
import net.minecraft.resources.Identifier;

/** The host's Pip, as friends with the mod see her (light mode): her state as a small JSON text. */
public record PipPayload(String json) implements CustomPacketPayload {
    public static final Type<PipPayload> TYPE = new Type<>(Identifier.fromNamespaceAndPath("kindredspirit", "pip"));
    public static final StreamCodec<RegistryFriendlyByteBuf, PipPayload> CODEC =
            StreamCodec.composite(ByteBufCodecs.STRING_UTF8, PipPayload::json, PipPayload::new);

    @Override
    public Type<? extends CustomPacketPayload> type() {
        return TYPE;
    }
}
