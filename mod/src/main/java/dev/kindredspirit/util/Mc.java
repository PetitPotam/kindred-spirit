package dev.kindredspirit.util;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.Holder;
import net.minecraft.core.HolderLookup;
import net.minecraft.core.Registry;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.Identifier;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.tags.TagKey;
import net.minecraft.world.effect.MobEffect;
import net.minecraft.world.effect.MobEffects;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.LightLayer;
import net.minecraft.world.level.biome.Biome;
import net.minecraft.world.level.block.Block;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

/**
 * The small things Minecraft does differently from one version to the next, in one place, so the rest of the
 * mod reads the same for every version. Each method has one line per version family between Stonecutter's
 * {@code //?} comments (see mod/stonecutter.gradle.kts); the code outside them is shared.
 */
public final class Mc {
    private Mc() {}

    // --- players and the server ---

    /** The world a player on the integrated server is in. */
    public static ServerLevel level(ServerPlayer sp) {
        //? if >=26.1 {
        return sp.level();
        //?} else {
        /*return sp.serverLevel();
        *///?}
    }

    public static MinecraftServer server(ServerPlayer sp) {
        return level(sp).getServer();
    }

    public static boolean clientSide(Level level) {
        //? if >=26.1 {
        return level.isClientSide();
        //?} else {
        /*return level.isClientSide;
        *///?}
    }

    /** What the player has in their inventory, hotbar included, without armour and the off hand. */
    public static List<ItemStack> items(Player p) {
        //? if >=26.1 {
        return p.getInventory().getNonEquipmentItems();
        //?} else {
        /*return p.getInventory().items;
        *///?}
    }

    private static final EquipmentSlot[] ARMOR = {EquipmentSlot.FEET, EquipmentSlot.LEGS, EquipmentSlot.CHEST, EquipmentSlot.HEAD};

    /** The four armour slots, feet first (as the inventory always listed them). */
    public static List<ItemStack> armor(Player p) {
        List<ItemStack> out = new ArrayList<>(4);
        for (EquipmentSlot s : ARMOR) out.add(p.getItemBySlot(s));
        return out;
    }

    /** Into the player's inventory, or at their feet when it's full. */
    public static void give(ServerPlayer sp, ItemStack stack) {
        if (sp.getInventory().add(stack)) return;
        //? if >=26.1 {
        sp.drop(stack, false, net.minecraft.util.Prediction.SERVER_ONLY);
        //?} else {
        /*sp.drop(stack, false);
        *///?}
    }

    /** A gentle shove, sent to the player's screen right away. */
    public static void push(LivingEntity e, double power, double dx, double dz) {
        //? if >=26.1 {
        e.knockback(power, dx, dz, e.damageSources().generic(), 0);
        e.needsSync = true;
        //?} else {
        /*e.knockback(power, dx, dz);
        e.hurtMarked = true;
        *///?}
    }

    /** Where someone is put: position and look, no interpolation. */
    public static void place(Entity e, double x, double y, double z, float yaw, float pitch) {
        //? if >=26.1 {
        e.snapTo(x, y, z, yaw, pitch);
        //?} else {
        /*e.moveTo(x, y, z, yaw, pitch);
        *///?}
    }

    public static Set<String> tags(Entity e) {
        //? if >=26.1 {
        return e.entityTags();
        //?} else {
        /*return e.getTags();
        *///?}
    }

    public static void invulnerable(Entity e, boolean on) {
        //? if >=26.1 {
        e.setPermanentlyInvulnerable(on);
        //?} else {
        /*e.setInvulnerable(on);
        *///?}
    }

    //? if >=26.1 {
    public static final net.minecraft.world.entity.EntityType<net.minecraft.world.entity.animal.allay.Allay> ALLAY = net.minecraft.world.entity.EntityTypes.ALLAY;
    //?} else {
    /*public static final net.minecraft.world.entity.EntityType<net.minecraft.world.entity.animal.allay.Allay> ALLAY = net.minecraft.world.entity.EntityType.ALLAY;
    *///?}

    /** A new entity of that type in the world, not yet added to it (null if it can't be made). */
    public static <T extends Entity> T create(net.minecraft.world.entity.EntityType<T> type, ServerLevel level) {
        //? if >=26.1 {
        return type.create(level, net.minecraft.world.entity.EntitySpawnReason.COMMAND);
        //?} else {
        /*return type.create(level);
        *///?}
    }

    /** Runs commands as the player, with the rights of an operator (level 2), answers going to {@code out}. */
    public static net.minecraft.commands.CommandSourceStack commandSource(ServerPlayer sp, net.minecraft.commands.CommandSource out) {
        //? if >=26.1 {
        return sp.createCommandSourceStack().withSource(out).withPermission(net.minecraft.server.permissions.LevelBasedPermissionSet.GAMEMASTER);
        //?} else {
        /*return sp.createCommandSourceStack().withSource(out).withPermission(2);
        *///?}
    }

    /** Whether a tamed animal (a dog, a cat, a parrot...) belongs to this player. */
    public static boolean ownedBy(net.minecraft.world.entity.OwnableEntity pet, Player p) {
        //? if >=26.1 {
        var owner = pet.getOwnerReference();
        return owner != null && p.getUUID().equals(owner.getUUID());
        //?} else {
        /*return p.getUUID().equals(pet.getOwnerUUID());
        *///?}
    }

    /** Swinging an arm: mining, fighting or placing. */
    public static boolean swinging(LivingEntity e) {
        //? if >=26.1 {
        return e.isSwinging();
        //?} else {
        /*return e.swinging;
        *///?}
    }

    /** The player's bed or respawn anchor, if it's in the dimension they are in now (else null). */
    public static BlockPos bed(ServerPlayer sp) {
        //? if >=26.1 {
        ServerPlayer.RespawnConfig rc = sp.getRespawnConfig();
        return rc != null && rc.respawnData().dimension() == sp.level().dimension() ? rc.respawnData().pos() : null;
        //?} else {
        /*BlockPos bed = sp.getRespawnPosition();
        return bed != null && sp.getRespawnDimension() == sp.level().dimension() ? bed : null;
        *///?}
    }

    /** The world spawn as the player's own game knows it. */
    public static BlockPos worldSpawn(Level level) {
        //? if >=26.1 {
        return level.getRespawnData().pos();
        //?} else {
        /*return level.getSharedSpawnPos();
        *///?}
    }

    // --- registries ---

    /** The item with that id, or air. */
    public static Item item(Identifier id) {
        //? if >=26.1 {
        return BuiltInRegistries.ITEM.getValue(id);
        //?} else {
        /*return BuiltInRegistries.ITEM.get(id);
        *///?}
    }

    public static HolderLookup<Block> blocks() {
        //? if >=26.1 {
        return BuiltInRegistries.BLOCK;
        //?} else {
        /*return BuiltInRegistries.BLOCK.asLookup();
        *///?}
    }

    public static <T> Registry<T> registry(Level level, ResourceKey<? extends Registry<? extends T>> key) {
        //? if >=26.1 {
        return level.registryAccess().lookupOrThrow(key);
        //?} else {
        /*return level.registryAccess().registryOrThrow(key);
        *///?}
    }

    public static <T> java.util.Optional<? extends net.minecraft.core.HolderSet<T>> tag(Registry<T> reg, TagKey<T> tag) {
        //? if >=26.1 {
        return reg.get(tag);
        //?} else {
        /*return reg.getTag(tag);
        *///?}
    }

    public static <T> java.util.Optional<Holder.Reference<T>> holder(Registry<T> reg, ResourceKey<T> key) {
        //? if >=26.1 {
        return reg.get(key);
        //?} else {
        /*return reg.getHolder(key);
        *///?}
    }

    public static TagKey<Block> blockTag(String vanillaName) {
        return TagKey.create(Registries.BLOCK, Identifier.withDefaultNamespace(vanillaName));
    }

    public static TagKey<Item> itemTag(String vanillaName) {
        return TagKey.create(Registries.ITEM, Identifier.withDefaultNamespace(vanillaName));
    }

    /** The effects she can give, by the names players use. */
    public enum Effect { SPEED, SLOWNESS, HASTE, JUMP_BOOST, STRENGTH, RESISTANCE }

    public static Holder<MobEffect> effect(Effect e) {
        return switch (e) {
            //? if >=26.1 {
            case SPEED -> MobEffects.SPEED;
            case SLOWNESS -> MobEffects.SLOWNESS;
            case HASTE -> MobEffects.HASTE;
            case JUMP_BOOST -> MobEffects.JUMP_BOOST;
            case STRENGTH -> MobEffects.STRENGTH;
            case RESISTANCE -> MobEffects.RESISTANCE;
            //?} else {
            /*case SPEED -> MobEffects.MOVEMENT_SPEED;
            case SLOWNESS -> MobEffects.MOVEMENT_SLOWDOWN;
            case HASTE -> MobEffects.DIG_SPEED;
            case JUMP_BOOST -> MobEffects.JUMP;
            case STRENGTH -> MobEffects.DAMAGE_BOOST;
            case RESISTANCE -> MobEffects.DAMAGE_RESISTANCE;
            *///?}
        };
    }

    public static Direction nearest(int x, int y, int z) {
        //? if >=26.1 {
        return Direction.getApproximateNearest(x, y, z);
        //?} else {
        /*return Direction.getNearest(x, y, z);
        *///?}
    }

    // --- time, weather, light ---

    /** Ticks since the world began on the day clock (24000 a day). */
    public static long dayTime(Level level) {
        //? if >=26.1 {
        return level.getOverworldClockTime();
        //?} else {
        /*return level.getDayTime();
        *///?}
    }

    public static void setDayTime(ServerLevel level, long ticks) {
        //? if >=26.1 {
        level.getServer().clockManager().setTotalTicks(level.registryAccess().getOrThrow(net.minecraft.world.clock.WorldClocks.OVERWORLD), (int) ticks);
        //?} else {
        /*level.setDayTime(ticks);
        *///?}
    }

    /** Like /weather: clear for {@code clearTicks}, or rain (and thunder) for {@code rainTicks}. */
    public static void weather(ServerLevel level, int clearTicks, int rainTicks, boolean rain, boolean thunder) {
        //? if >=26.1 {
        level.getServer().setWeatherParameters(clearTicks, rainTicks, rain, thunder);
        //?} else {
        /*level.setWeatherParameters(clearTicks, rainTicks, rain, thunder);
        *///?}
    }

    public static Biome.Precipitation precipitation(Level level, Biome biome, BlockPos at) {
        //? if >=26.1 {
        return biome.getPrecipitationAt(at, level.getSeaLevel());
        //?} else {
        /*return biome.getPrecipitationAt(at);
        *///?}
    }

    /** Block and sky light at a spot, packed the way vertex light is. */
    public static int light(Level level, BlockPos at) {
        int block = level.getBrightness(LightLayer.BLOCK, at), sky = level.getBrightness(LightLayer.SKY, at);
        return block << 4 | sky << 20;
    }

    public static int lightBlock(int packed) { return packed >> 4 & 0xF; }

    public static int lightSky(int packed) { return packed >> 20 & 0xF; }

    public static int light(int block, int sky) { return block << 4 | sky << 20; }

    public static final int FULL_BRIGHT = 0xF000F0;

    public static net.minecraft.client.renderer.texture.DynamicTexture texture(String label, com.mojang.blaze3d.platform.NativeImage img) {
        //? if >=26.1 {
        return new net.minecraft.client.renderer.texture.DynamicTexture(() -> label, img);
        //?} else {
        /*return new net.minecraft.client.renderer.texture.DynamicTexture(img);
        *///?}
    }

    /** How far between two game ticks this frame is (0..1), for smooth movement. */
    public static float partialTick(Minecraft mc) {
        //? if >=26.1 {
        return mc.getDeltaTracker().getGameTimeDeltaPartialTick(false);
        //?} else {
        /*return mc.getTimer().getGameTimeDeltaPartialTick(false);
        *///?}
    }

    // --- the player's screen ---

    public static Screen screen(Minecraft mc) {
        //? if >=26.1 {
        return mc.gui.screen();
        //?} else {
        /*return mc.screen;
        *///?}
    }

    public static void setScreen(Minecraft mc, Screen s) {
        //? if >=26.1 {
        mc.gui.setScreen(s);
        //?} else {
        /*mc.setScreen(s);
        *///?}
    }

    public static boolean hudHidden(Minecraft mc) {
        //? if >=26.1 {
        return mc.gui.hud.isHidden();
        //?} else {
        /*return mc.options.hideGui;
        *///?}
    }

    public static void hideHud(Minecraft mc, boolean hidden) {
        //? if >=26.1 {
        if (mc.gui.hud.isHidden() != hidden) mc.gui.hud.toggle();
        //?} else {
        /*mc.options.hideGui = hidden;
        *///?}
    }

    /** A line in the player's chat (only they see it). */
    public static void chat(Minecraft mc, Component line) {
        if (mc.gui == null) return;
        //? if >=26.1 {
        mc.gui.hud.getChat().addClientSystemMessage(line);
        //?} else {
        /*mc.gui.getChat().addMessage(line);
        *///?}
    }
}
