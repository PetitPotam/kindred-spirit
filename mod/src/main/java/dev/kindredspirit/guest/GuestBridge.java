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
    /** Friends touching your Pip (hit / petted), for her brain: who, and what (in Heard.text). */
    private static final Deque<Heard> touches = new ArrayDeque<>();
    private static boolean cleaned;

    /** What the client hands over: whether guests are on, her name, and where she floats. */
    public static Supplier<Boolean> enabled = () -> true;
    public static Supplier<String> name = () -> "Pip";
    public static Supplier<double[]> where = () -> null;
    /** Her state for friends who have the mod (light mode: they draw her themselves, see SharedPip). */
    public static Supplier<String> state = () -> null;
    /** Pips visiting from friends' games may act in this world (the host's setting lanVisitors). */
    public static Supplier<Boolean> acceptVisitors = () -> true;
    private static int ticks;

    // a visiting Pip: her brain lives in a friend's game, this world is yours (see visit())
    private static volatile com.google.gson.JsonObject visitor;
    private static volatile UUID visitorOwner;
    private static volatile long visitorAt;

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
        boolean own = enabled.get() && at != null;
        com.google.gson.JsonObject v = visiting();
        ServerPlayer owner = host;
        String pipName = name.get();
        if (!own && v != null) { // no Pip of yours here: a friend's Pip visits
            at = new double[]{v.get("x").getAsDouble(), v.get("y").getAsDouble(), v.get("z").getAsDouble()};
            owner = server.getPlayerList().getPlayer(visitorOwner);
            pipName = v.has("name") ? v.get("name").getAsString() : "Pip";
        }
        boolean want = host != null && owner != null && server.isPublished() && (own || v != null)
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
        String n = pipName;
        if (pip.getCustomName() == null || !pip.getCustomName().getString().equals(n)) {
            pip.setCustomName(Component.literal(n).withStyle(ChatFormatting.LIGHT_PURPLE));
            pip.setCustomNameVisible(true);
        }
        float yaw = (float) Math.toDegrees(Math.atan2(-(owner.getX() - at[0]), owner.getZ() - at[2]));
        pip.moveTo(at[0], at[1] - 0.3, at[2], yaw, 0); // she looks at the one she lives with
        pip.setYHeadRot(yaw);
        if (++ticks % 2 == 0) share(server, owner, own ? null : v); // (10 times a second)
    }

    /** A visiting Pip's latest state, if she's here and allowed (it came in the last 3 seconds). */
    private static com.google.gson.JsonObject visiting() {
        com.google.gson.JsonObject v = visitor;
        return v != null && acceptVisitors.get() && System.currentTimeMillis() - visitorAt < 3000 && v.has("x") ? v : null;
    }

    /**
     * Ten times a second, to each player whose game has the mod (except the one she lives with):
     * her state, so they see her as that player does. Yours, or the visiting Pip's.
     */
    private static void share(MinecraftServer server, ServerPlayer owner, com.google.gson.JsonObject visiting) {
        if (visiting != null && hidden != null // the visitor's own game hides the stand-in too (they see their Pip)
                && net.fabricmc.fabric.api.networking.v1.ServerPlayNetworking.canSend(owner, PipPayload.TYPE)) {
            net.fabricmc.fabric.api.networking.v1.ServerPlayNetworking.send(owner,
                    new PipPayload("{\"type\":\"standin\",\"standIn\":\"" + hidden + "\"}"));
        }
        String json = null;
        for (ServerPlayer p : server.getPlayerList().getPlayers()) {
            if (p == owner || !net.fabricmc.fabric.api.networking.v1.ServerPlayNetworking.canSend(p, PipPayload.TYPE)) continue;
            if (json == null) {
                if (visiting != null) {
                    com.google.gson.JsonObject o = visiting.deepCopy();
                    if (hidden != null) o.addProperty("standIn", hidden.toString());
                    json = o.toString();
                } else {
                    json = state.get();
                }
            }
            if (json == null) return;
            net.fabricmc.fabric.api.networking.v1.ServerPlayNetworking.send(p, new PipPayload(json));
        }
    }

    /**
     * A visiting Pip's game talks to this world (you host; her brain is in your friend's game):
     * her state (shown to the others, with a stand-in for those without the mod), her words (in their
     * chat), and the powers she uses here, done for her owner as if in their own world. Server thread.
     */
    public static void visit(MinecraftServer server, ServerPlayer from, String json) {
        com.google.gson.JsonObject m;
        try {
            m = com.google.gson.JsonParser.parseString(json).getAsJsonObject();
        } catch (RuntimeException e) {
            return;
        }
        String kind = m.has("kind") ? m.get("kind").getAsString() : "";
        switch (kind) {
            case "state" -> {
                if (!m.has("state")) return;
                visitor = m.getAsJsonObject("state");
                visitorOwner = from.getUUID();
                visitorAt = System.currentTimeMillis();
            }
            case "say" -> {
                if (!acceptVisitors.get() || !m.has("text")) return;
                String who = visitor != null && visitor.has("name") ? visitor.get("name").getAsString() : "Pip";
                Component line = Component.literal("[" + who + "] ").withStyle(ChatFormatting.LIGHT_PURPLE)
                        .append(Component.literal(m.get("text").getAsString()).withStyle(ChatFormatting.WHITE));
                for (ServerPlayer p : server.getPlayerList().getPlayers()) if (p != from) p.sendSystemMessage(line);
            }
            case "act" -> {
                com.google.gson.JsonObject res;
                var a = dev.kindredspirit.act.Abilities.ability(m.has("action") ? m.get("action").getAsString() : "");
                var power = dev.kindredspirit.act.Abilities.power(m.has("power") ? m.get("power").getAsString() : "");
                var style = dev.kindredspirit.act.Abilities.style(m.has("style") ? m.get("style").getAsString() : "");
                if (!acceptVisitors.get()) {
                    res = dev.kindredspirit.act.Actions.error("This world's host doesn't let visiting Pips change things here.");
                } else if (a == null || !dev.kindredspirit.act.Abilities.allowed(a, power, style)) {
                    res = dev.kindredspirit.act.Actions.error("That isn't allowed.");
                } else {
                    var args = m.has("args") && m.get("args").isJsonObject() ? m.getAsJsonObject("args") : new com.google.gson.JsonObject();
                    args.addProperty("_power", power.name());
                    res = dev.kindredspirit.act.Actions.serverSide(server, from, a, args, style);
                }
                res.addProperty("type", "done");
                res.addProperty("id", m.has("id") ? m.get("id").getAsString() : "");
                net.fabricmc.fabric.api.networking.v1.ServerPlayNetworking.send(from, new PipPayload(res.toString()));
            }
            case "touch" -> touch(server, from, m.has("what") ? m.get("what").getAsString() : "");
            case "glow" -> { // a visiting Pip's light, placed by this world's game where she floats
                if (!acceptVisitors.get()) return;
                net.minecraft.core.BlockPos at = m.has("x") ? new net.minecraft.core.BlockPos(m.get("x").getAsInt(),
                        m.get("y").getAsInt(), m.get("z").getAsInt()) : null;
                dev.kindredspirit.act.Glow.visitorLight(server, from, at, m.has("level") ? m.get("level").getAsInt() : 12);
            }
            default -> { }
        }
    }

    /**
     * Someone hit or petted the Pip they see (on their screen with the mod, or her stand-in without it). Whose
     * Pip is she? Yours: her brain hears it from your game. A visiting Pip: her owner's game is told.
     */
    public static void touch(MinecraftServer server, ServerPlayer from, String what) {
        if (!what.equals("hit") && !what.equals("petted")) return;
        Minecraft mc = Minecraft.getInstance();
        boolean own = enabled.get() && where.get() != null && mc.player != null;
        if (own) {
            if (from.getUUID().equals(mc.player.getUUID())) return; // (yours are seen by your own game)
            synchronized (touches) {
                touches.add(new Heard(from.getGameProfile().getName(), what));
                while (touches.size() > 10) touches.removeFirst();
            }
            return;
        }
        UUID ownerId = visitorOwner;
        if (visiting() == null || ownerId == null || from.getUUID().equals(ownerId)) return;
        ServerPlayer owner = server.getPlayerList().getPlayer(ownerId);
        if (owner == null || !net.fabricmc.fabric.api.networking.v1.ServerPlayNetworking.canSend(owner, PipPayload.TYPE)) return;
        // (as a "done" with id "touch": an older Kindred ignores it instead of taking it for her state)
        com.google.gson.JsonObject o = new com.google.gson.JsonObject();
        o.addProperty("type", "done");
        o.addProperty("id", "touch");
        o.addProperty("what", what);
        o.addProperty("by", from.getGameProfile().getName());
        net.fabricmc.fabric.api.networking.v1.ServerPlayNetworking.send(owner, new PipPayload(o.toString()));
    }

    /** A friend's touch on your Pip since last time (who, and "hit" or "petted" in text). */
    public static Heard nextTouch() {
        synchronized (touches) {
            return touches.poll();
        }
    }

    /** The stand-in is hit or petted by someone without the mod: it's a touch (and the Allay keeps nothing). */
    public static boolean standIn(net.minecraft.world.entity.Entity e) {
        return e != null && e.getTags().contains(TAG);
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
        visitor = null;
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
