package dev.kindredspirit.guest;

import dev.kindredspirit.ChatRoute;
import net.minecraft.ChatFormatting;
import net.minecraft.client.Minecraft;
import net.minecraft.network.chat.Component;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.animal.allay.Allay;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.UUID;
import java.util.function.Supplier;

/**
 * Friends on your LAN world, without the mod, can see Pip and talk to her.
 *
 * <ul>
 *   <li>They see her as a stand-in the plain game knows how to draw: an Allay named after her that
 *       follows where she floats. It can't be hurt, makes no sound, does nothing on its own, is
 *       hidden on your own screen (you see your Pip), and is removed when you close the world to
 *       LAN or leave (any one left behind by a crash is cleaned up next time).</li>
 *   <li>Their chat messages that call her ("Pip, ...") go to her brain, with who said them.</li>
 *   <li>What she says appears in their chat ("[Pip] ..."). Her voice stays on your computer.</li>
 * </ul>
 * Only while you host and the world is open to LAN, and only if the setting lanGuests is on.
 */
public final class GuestBridge {
    private GuestBridge() {}

    public static final String TAG = "kindredspirit_stand_in";

    /** The stand-in's id, so this computer doesn't draw it (see EntityRenderDispatcherMixin). */
    public static volatile UUID hidden;

    public record Heard(String who, String text) {}

    private static final Deque<Heard> heard = new ArrayDeque<>();
    private static boolean cleaned;

    /** What the client hands over: whether guests are on, her name, and where she floats. */
    public static Supplier<Boolean> enabled = () -> true;
    public static Supplier<String> name = () -> "Pip";
    public static Supplier<double[]> where = () -> null;

    /** Every server tick (your integrated server): keep the stand-in where she is, or remove it. */
    public static void tick(MinecraftServer server) {
        Minecraft mc = Minecraft.getInstance();
        ServerPlayer host = mc.player == null ? null : server.getPlayerList().getPlayer(mc.player.getUUID());
        ServerLevel level = host == null ? null : host.serverLevel();
        if (!cleaned && level != null) { // a stand-in left behind by a crash
            cleaned = true;
            for (ServerLevel l : server.getAllLevels()) {
                for (var e : l.getAllEntities()) if (e.getTags().contains(TAG)) e.discard();
            }
        }
        double[] at = where.get();
        boolean want = host != null && server.isPublished() && enabled.get() && at != null
                && server.getPlayerList().getPlayerCount() > 1;
        Allay pip = hidden == null || level == null ? null : (Allay) find(server, hidden);
        if (!want) {
            if (pip != null) pip.discard();
            hidden = null;
            return;
        }
        if (pip == null || pip.level() != level) {
            if (pip != null) pip.discard();
            pip = EntityType.ALLAY.create(level);
            if (pip == null) return;
            pip.addTag(TAG);
            pip.setNoAi(true);
            pip.setNoGravity(true);
            pip.setInvulnerable(true);
            pip.setSilent(true);
            pip.setPersistenceRequired();
            pip.moveTo(at[0], at[1] - 0.3, at[2], 0, 0);
            level.addFreshEntity(pip);
            hidden = pip.getUUID();
        }
        String n = name.get();
        if (pip.getCustomName() == null || !pip.getCustomName().getString().equals(n)) {
            pip.setCustomName(Component.literal(n).withStyle(ChatFormatting.LIGHT_PURPLE));
            pip.setCustomNameVisible(true);
        }
        float yaw = (float) Math.toDegrees(Math.atan2(-(host.getX() - at[0]), host.getZ() - at[2]));
        pip.moveTo(at[0], at[1] - 0.3, at[2], yaw, 0); // she looks at you
        pip.setYHeadRot(yaw);
    }

    private static net.minecraft.world.entity.Entity find(MinecraftServer server, UUID id) {
        for (ServerLevel l : server.getAllLevels()) {
            var e = l.getEntity(id);
            if (e != null) return e;
        }
        return null;
    }

    /** The world closes: no stand-in left in it. */
    public static void stopping(MinecraftServer server) {
        if (hidden != null) {
            var e = find(server, hidden);
            if (e != null) e.discard();
        }
        hidden = null;
        cleaned = false;
    }

    /** A chat message on your server: from a guest, calling her? Then it's for her brain. */
    public static void chat(MinecraftServer server, ServerPlayer sender, String text) {
        Minecraft mc = Minecraft.getInstance();
        if (!enabled.get() || !server.isPublished() || mc.player == null || sender.getUUID().equals(mc.player.getUUID())) return;
        if (!ChatRoute.forCompanion("name", false, name.get(), text)) return;
        synchronized (heard) {
            heard.add(new Heard(sender.getGameProfile().getName(), text));
            while (heard.size() > 10) heard.removeFirst();
        }
    }

    /** What guests said to her since last time (the client sends it to her brain). */
    public static Heard next() {
        synchronized (heard) {
            return heard.poll();
        }
    }

    /** What she says, in your guests' chat (not yours: you hear her and see her subtitles). */
    public static void say(MinecraftServer server, String text) {
        if (server == null || !server.isPublished() || !enabled.get() || text == null || text.isBlank()) return;
        Minecraft mc = Minecraft.getInstance();
        UUID me = mc.player == null ? null : mc.player.getUUID();
        Component line = Component.literal("[" + name.get() + "] ").withStyle(ChatFormatting.LIGHT_PURPLE)
                .append(Component.literal(text).withStyle(ChatFormatting.WHITE));
        server.execute(() -> {
            for (ServerPlayer p : server.getPlayerList().getPlayers()) {
                if (!p.getUUID().equals(me)) p.sendSystemMessage(line);
            }
        });
    }
}
