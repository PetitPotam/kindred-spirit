package dev.kindredspirit.act;

import dev.kindredspirit.util.Mc;
import com.google.gson.JsonObject;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.Vec3;

import java.util.concurrent.CompletableFuture;

/**
 * Her pranks, always reversible: a sound behind you (only you hear it, nothing happens), or
 * "borrowing" a block you just placed (it goes into your inventory; "put it back" puts it back).
 * Turned off with allowPranks in kindredspirit.json; the brain decides when (brain.toml [heart]).
 */
public final class Pranks {
    private Pranks() {}

    /** The block you placed last and when, tracked on your client. */
    public static volatile BlockPos lastPlaced;
    public static volatile long lastPlacedAt;
    private static volatile BlockPos stolenAt;
    private static volatile BlockState stolenState;

    public static JsonObject sound(Minecraft mc, String kind) {
        LocalPlayer p = mc.player;
        Vec3 look = p.getViewVector(1f);
        double x = p.getX() - look.x * 1.5, y = p.getY() + 0.5, z = p.getZ() - look.z * 1.5; // right behind you
        if ("explosion".equals(kind)) {
            mc.level.playLocalSound(x, y, z, SoundEvents.GENERIC_EXPLODE.value(), SoundSource.BLOCKS, 0.6f, 1.0f, false);
        } else {
            mc.level.playLocalSound(x, y, z, SoundEvents.CREEPER_PRIMED, SoundSource.HOSTILE, 1.0f, 0.5f, false);
        }
        return ok();
    }

    public static CompletableFuture<JsonObject> steal(Minecraft mc) {
        BlockPos pos = lastPlaced;
        if (pos == null || System.currentTimeMillis() - lastPlacedAt > 15000) return done(error("no block placed just now"));
        return onServer(mc, server -> {
            ServerPlayer sp = server.getPlayerList().getPlayer(mc.player.getUUID());
            if (sp == null) return error("not here");
            ServerLevel level = Mc.level(sp);
            BlockState state = level.getBlockState(pos);
            ItemStack item = new ItemStack(state.getBlock().asItem());
            if (state.isAir() || item.isEmpty() || !(item.getItem() instanceof BlockItem)) return error("nothing to borrow");
            String name = item.getHoverName().getString(); // before add(), which empties the stack
            level.removeBlock(pos, false);
            Mc.give(sp, item);
            stolenAt = pos;
            stolenState = state;
            lastPlaced = null;
            JsonObject r = ok();
            r.addProperty("borrowed", name);
            return r;
        });
    }

    public static CompletableFuture<JsonObject> giveBack(Minecraft mc) {
        BlockPos pos = stolenAt;
        BlockState state = stolenState;
        if (pos == null || state == null) return done(error("I haven't borrowed anything"));
        return onServer(mc, server -> {
            ServerPlayer sp = server.getPlayerList().getPlayer(mc.player.getUUID());
            if (sp == null) return error("not here");
            ServerLevel level = Mc.level(sp);
            if (!level.getBlockState(pos).isAir()) return error("something else is there now");
            level.setBlockAndUpdate(pos, state);
            ItemStack want = new ItemStack(state.getBlock().asItem());
            for (int i = 0; i < sp.getInventory().getContainerSize(); i++) { // take back the copy she gave you
                ItemStack s = sp.getInventory().getItem(i);
                if (ItemStack.isSameItem(s, want)) {
                    s.shrink(1);
                    break;
                }
            }
            stolenAt = null;
            stolenState = null;
            return ok();
        });
    }

    /** A playful bonk back: pushes you a little, no damage. */
    public static CompletableFuture<JsonObject> bonk(Minecraft mc, double fromX, double fromZ) {
        return onServer(mc, server -> {
            ServerPlayer sp = server.getPlayerList().getPlayer(mc.player.getUUID());
            if (sp == null) return error("not here");
            Mc.push(sp, 0.6, fromX - sp.getX(), fromZ - sp.getZ());
            Mc.level(sp).playSound(null, sp.blockPosition(), SoundEvents.SLIME_JUMP_SMALL, SoundSource.NEUTRAL, 1f, 1.4f);
            return ok();
        });
    }

    /** A play-hit between close friends: one heart, healed right back a moment later. */
    public static CompletableFuture<JsonObject> playHit(Minecraft mc, double fromX, double fromZ) {
        return onServer(mc, server -> {
            ServerPlayer sp = server.getPlayerList().getPlayer(mc.player.getUUID());
            if (sp == null || sp.getHealth() < sp.getMaxHealth()) return error("not at full health");
            Mc.hurt(sp, sp.damageSources().magic(), 2f);
            Mc.push(sp, 0.4, fromX - sp.getX(), fromZ - sp.getZ());
            Thread t = new Thread(() -> { // and she heals you right back
                try { Thread.sleep(1500); } catch (InterruptedException ignored) { }
                server.execute(() -> {
                    sp.heal(2f);
                    Mc.level(sp).sendParticles(net.minecraft.core.particles.ParticleTypes.HEART, sp.getX(), sp.getY() + 1.8,
                            sp.getZ(), 4, 0.4, 0.3, 0.4, 0);
                });
            }, "kindred-heal");
            t.setDaemon(true);
            t.start();
            return ok();
        });
    }

    /** Her tears bring rain; comfort brings the sun back (the overworld's weather, like /weather). */
    public static CompletableFuture<JsonObject> weather(Minecraft mc, String weather) {
        return onServer(mc, server -> {
            ServerLevel l = server.getLevel(net.minecraft.world.level.Level.OVERWORLD);
            if (l == null) return error("no overworld");
            if ("rain".equals(weather)) {
                if (l.isRaining()) return error("it's already raining");
                Mc.weather(l, 0, 2400, true, false); // two minutes of rain at most
            } else {
                Mc.weather(l, 6000, 0, false, false);
            }
            return ok();
        });
    }

    private static CompletableFuture<JsonObject> onServer(Minecraft mc, java.util.function.Function<MinecraftServer, JsonObject> job) {
        MinecraftServer server = mc.getSingleplayerServer();
        if (server == null) return done(error("only in singleplayer"));
        CompletableFuture<JsonObject> f = new CompletableFuture<>();
        server.execute(() -> {
            try {
                f.complete(job.apply(server));
            } catch (RuntimeException e) {
                f.complete(error(e.toString()));
            }
        });
        return f;
    }

    private static JsonObject ok() {
        JsonObject o = new JsonObject();
        o.addProperty("ok", true);
        return o;
    }

    private static JsonObject error(String why) {
        JsonObject o = new JsonObject();
        o.addProperty("ok", false);
        o.addProperty("error", why);
        return o;
    }

    private static CompletableFuture<JsonObject> done(JsonObject o) {
        return CompletableFuture.completedFuture(o);
    }
}
