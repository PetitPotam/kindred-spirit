package dev.kindredspirit.render;

import com.mojang.blaze3d.vertex.PoseStack;
import com.mojang.blaze3d.vertex.VertexConsumer;
import com.mojang.math.Axis;
import dev.kindredspirit.Companion;
import dev.kindredspirit.KindredConfig;
import dev.kindredspirit.life.Behavior;
import dev.kindredspirit.life.Emote;
import dev.kindredspirit.skin.Skin;
import dev.kindredspirit.skin.SkinRegistry;
import dev.kindredspirit.util.Mood;
import dev.kindredspirit.util.Quality;
import dev.kindredspirit.util.Smooth;
import dev.kindredspirit.util.Mc;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.Font;
//? if >=26.1 {
import net.minecraft.client.renderer.SubmitNodeCollector;
import net.minecraft.client.renderer.rendertype.RenderType;
import net.minecraft.client.renderer.rendertype.RenderTypes;
//?} else {
/*import net.minecraft.client.renderer.MultiBufferSource;
import net.minecraft.client.renderer.RenderType;
*///?}
import net.minecraft.client.renderer.texture.OverlayTexture;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.Identifier;
import net.minecraft.util.FormattedCharSequence;
import net.minecraft.world.phys.Vec3;
import org.joml.Matrix4f;
import org.joml.Quaternionf;

import java.util.List;

/**
 * Draws the companion from its skin (shape, texture, colors) and its life (where it is, where it
 * looks, its gestures): a body, an optional glassy shell over a darker core, eyes whose pupils
 * look first while the head follows, a mouth that moves with its voice, and cheeks that blush.
 * Meshes are built once per shape and quality level; drawing a frame allocates nothing of ours.
 *
 * <p>She is drawn in four layers (the solid parts, a textured body or a glassy shell, wings), each from the
 * same pose. Up to 1.21.x a layer is drawn straight into the game's buffers; from 26.1 on the game collects
 * what to draw first and draws it later, so each layer is handed over as a small callback.
 */
public final class CompanionRenderer {
    private static final float RADIUS = 0.2f;
    private static final Identifier WHITE = SkinRegistry.WHITE;
    private static final Identifier WING = Identifier.fromNamespaceAndPath("kindredspirit", "textures/companion/wing.png");

    private final ShapeMesh[] meshes = new ShapeMesh[Skin.Shape.values().length * Quality.Level.values().length];
    /** A tiny low-poly ball for the strokes of her face (smiles, closed eyes, brows) and her leaves. */
    private final ShapeMesh bead = new ShapeMesh(Skin.Shape.BALL, 8, 6);
    // her expression, eased toward her mood so her face never snaps from one look to the next
    private double smile = 0.6, worry, curious, wide;
    private long faceAt;
    private final Quaternionf lean = new Quaternionf();
    private String wrappedFor = null;
    private List<FormattedCharSequence> wrapped = List.of();

    private enum Layer { SOLID, BODY, GLASS, WINGS }

    // what this frame draws, set by render() for the layers (one companion per frame)
    private Companion c;
    private Skin skin;
    private ShapeMesh m;
    private float r;
    private int tint, light;
    private boolean shell;
    private long nowMs;
    //? if >=26.1 {
    private final PoseStack scratch = new PoseStack();
    private final SubmitNodeCollector.CustomGeometryRenderer solidLayer = (p, vc) -> layer(Layer.SOLID, from(p), vc);
    private final SubmitNodeCollector.CustomGeometryRenderer bodyLayer = (p, vc) -> layer(Layer.BODY, from(p), vc);
    private final SubmitNodeCollector.CustomGeometryRenderer glassLayer = (p, vc) -> layer(Layer.GLASS, from(p), vc);
    private final SubmitNodeCollector.CustomGeometryRenderer wingsLayer = (p, vc) -> layer(Layer.WINGS, from(p), vc);

    private PoseStack from(PoseStack.Pose p) {
        while (!scratch.isEmpty()) scratch.popPose();
        scratch.setIdentity();
        scratch.last().set(p);
        return scratch;
    }
    //?}

    private ShapeMesh mesh(Skin.Shape shape, Quality.Level level) {
        int i = shape.ordinal() * Quality.Level.values().length + level.ordinal();
        if (meshes[i] == null) meshes[i] = new ShapeMesh(shape, level.slices, level.stacks);
        return meshes[i];
    }

    //? if >=26.1 {
    public void render(PoseStack pose, SubmitNodeCollector out, Vec3 cp, Quaternionf camRot, Companion c, Identifier bodyTexture,
                       KindredConfig cfg, Quality.Level level, long nowMs) {
    //?} else {
    /*public void render(PoseStack pose, MultiBufferSource out, Vec3 cp, Quaternionf camRot, Companion c, Identifier bodyTexture,
                       KindredConfig cfg, Quality.Level level, long nowMs) {
    *///?}
        Minecraft mc = Minecraft.getInstance();
        if (out == null || pose == null || mc.level == null) return;
        Behavior b = c.life;
        if (b.presence < 0.02) return; // gone for now
        Emote.Pose g = b.pose;
        Skin skin = c.skin;
        float r = (float) (RADIUS * cfg.size * skin.size() * b.presence);

        double bx = b.x + b.shiver, by = b.y + b.lift + g.lift, bz = b.z;
        int light = Mc.light(mc.level, BlockPos.containing(bx, by, bz));
        // never fully dark: it should stay cute (and findable) in caves; glowing skins ignore darkness
        light = skin.glow() ? Mc.FULL_BRIGHT : Mc.light(Math.max(Mc.lightBlock(light), 9), Mc.lightSky(light));

        this.c = c;
        this.skin = skin;
        this.r = r;
        this.light = light;
        this.nowMs = nowMs;
        this.tint = switch (skin.tint()) {
            case MOOD -> c.rgb;
            case FIXED -> skin.color();
            case NONE -> 0xFFFFFF;
        };
        this.m = mesh(skin.shape(), level);
        this.shell = skin.shell() && level.shell;
        expression(c, nowMs);

        pose.pushPose();
        pose.translate(bx - cp.x, by - cp.y, bz - cp.z);
        if (b.leanAngle > 1e-3) rotate(pose, lean.identity().rotateAxis((float) b.leanAngle, (float) b.leanAxisX, 0, (float) b.leanAxisZ));
        float s = (float) (b.squish + g.squish);
        float sc = (float) g.scale;
        pose.scale(sc * (1 + s * 0.6f), sc * (1 - s), sc * (1 + s * 0.6f));
        rotate(pose, Axis.YP.rotation((float) (b.headYaw + g.yaw)));
        rotate(pose, Axis.XP.rotation((float) -(b.headPitch + g.pitch)));
        if (g.roll != 0) rotate(pose, Axis.ZP.rotation((float) g.roll));

        // the body after her face: glassy when the skin and quality allow it, textured if the skin has one
        //? if >=26.1 {
        out.submitCustomGeometry(pose, RenderTypes.entityCutout(WHITE), solidLayer);
        if (shell) out.submitCustomGeometry(pose, RenderTypes.entityTranslucentCull(bodyTexture), glassLayer);
        else out.submitCustomGeometry(pose, RenderTypes.entityCutout(bodyTexture), bodyLayer);
        if (skin.wings()) out.submitCustomGeometry(pose, RenderTypes.entityTranslucent(WING), wingsLayer);
        //?} else {
        /*layer(Layer.SOLID, pose, out.getBuffer(RenderType.entityCutoutNoCull(WHITE)));
        if (shell) layer(Layer.GLASS, pose, out.getBuffer(RenderType.entityTranslucentCull(bodyTexture)));
        else layer(Layer.BODY, pose, out.getBuffer(RenderType.entityCutoutNoCull(bodyTexture)));
        if (skin.wings()) layer(Layer.WINGS, pose, out.getBuffer(RenderType.entityTranslucent(WING)));
        *///?}
        pose.popPose();

        if (cfg.worldSubtitles && Hud.visible(Mc.hudHidden(mc), cfg.subtitlesWithHiddenHud)) {
            String text = c.activity == Behavior.Activity.LISTENING ? "♪ ..."
                    : c.activity == Behavior.Activity.THINKING ? dots(nowMs)
                    : c.showSubtitle(nowMs) ? c.subtitle
                    : b.mode == Behavior.Mode.GUIDE ? guideText(b)
                    : b.dozing() ? zzz(nowMs) : null;
            if (text != null) subtitle(pose, out, camRot, mc.font, text, bx - cp.x, by - cp.y + r + 0.15 + (skin.hasSprout() ? r * 0.35 : 0), bz - cp.z);
        }
    }

    /** One layer of her, drawn from the pose she's in this frame. */
    private void layer(Layer which, PoseStack pose, VertexConsumer vc) {
        switch (which) {
            case SOLID -> {
                if (shell) {
                    int core = skin.glow() ? Mood.blend(tint, 0xFFFFFF, 0.55f) : Mood.shade(tint, 0.72f);
                    draw(vc, pose, m, 0, -0.02f * r, 0, r * 0.62f, r * 0.62f, r * 0.62f, core, 255, light);
                }
                if (skin.face()) face(vc, pose, m, c, r, light);
                if (skin.hasSprout()) sprout(vc, pose, m, c, r, light, nowMs);
            }
            case GLASS -> {
                draw(vc, pose, m, 0, 0, 0, r, r, r, tint, Math.round(skin.shellOpacity() * 255), light);
                if (skin.glow() && !skin.wings()) { // a soft halo around glowing skins (it would hide wings)
                    draw(vc, pose, m, 0, 0, 0, r * 1.45f, r * 1.45f, r * 1.45f, tint, 38, light);
                }
            }
            case BODY -> {
                float f = r * 0.97f;
                draw(vc, pose, m, 0, 0, 0, f, f, f, tint, 255, light);
            }
            case WINGS -> {
                int wingCol = skin.wingColor() == Skin.MOOD_WINGS ? Mood.blend(c.rgb, 0xFFFFFF, 0.45f) : skin.wingColor();
                wings(vc, pose, skin, wingCol, r, (float) c.life.wingAngle, light);
            }
        }
    }

    private static void rotate(PoseStack pose, Quaternionf q) {
        //? if >=26.1 {
        pose.rotate(q);
        //?} else {
        /*pose.mulPose(q);
        *///?}
    }

    /** How her face leans for each mood: smiling or not, worried brows, one curious eye, wide eyes. */
    private void expression(Companion c, long nowMs) {
        double dt = faceAt == 0 ? 1 : Math.min(0.25, Math.max(0, (nowMs - faceAt) / 1000.0));
        faceAt = nowMs;
        double ts, tw = 0, tc = 0, tx = 0;
        switch (c.mood) {
            case HAPPY -> ts = 0.8;
            case EXCITED -> { ts = 1; tx = 0.6; }
            case CALM -> ts = 0.45;
            case CURIOUS -> { ts = 0.15; tc = 1; }
            case WORRIED -> { ts = -0.4; tw = 0.8; }
            case SCARED -> { ts = -0.3; tw = 1; tx = 1; }
            case SAD -> { ts = -0.8; tw = 0.6; }
            case SLEEPY -> ts = 0.15;
            default -> ts = 0;
        }
        double k = 1 - Math.exp(-dt * 5);
        smile += (ts - smile) * k;
        worry += (tw - worry) * k;
        curious += (tc - curious) * k;
        wide += (tx - wide) * k;
    }

    private void face(VertexConsumer vc, PoseStack pose, ShapeMesh m, Companion c, float r, int light) {
        Behavior b = c.life;
        Emote.Pose g = b.pose;
        Skin skin = c.skin;
        double happy = Math.min(1, g.happyEyes);
        double blink = Math.max(b.blink, 0);
        double wink = Math.min(1, g.wink), squint = Math.min(1, g.squint);
        boolean asleep = g.eyesClosed > 0.6;
        float lookX = (float) (b.pupilX * 0.08 * r), lookY = (float) (b.pupilY * 0.07 * r);
        double sad = Math.max(0, -smile);
        for (int side = -1; side <= 1; side += 2) {
            // curious: one eye a little bigger than the other (and its brow up); excited or scared: wide eyes
            double sz = g.eyeScale * (1 + 0.12 * wide) * (1 + side * 0.12 * curious);
            float ex = side * 0.36f * r + lookX;
            float ey = 0.12f * r + lookY + (float) (happy * 0.04 * r) - (float) (0.025 * r * sad);
            float ez = front(m, r, ex, ey) + 0.01f * r;
            boolean winking = side == 1 && wink > 0.5;
            if (happy > 0.5 || winking || asleep) {
                // closed eyes as strokes: ^ when smiling or winking, a soft u when asleep
                float half = (float) (0.13 * r * sz);
                arc(vc, pose, m, r, ex, ey - 0.02f * r, half, (asleep && !winking && happy <= 0.5 ? -0.045f : 0.07f) * r,
                        0, 0.032f * r, skin.eyes(), light);
            } else {
                double shut = side == 1 ? Math.max(blink, wink) : blink;
                float eyeH = (float) (0.30 * r * sz * (1 - 0.9 * shut) * (1 - 0.7 * happy) * (1 - 0.5 * squint));
                float eyeW = (float) (0.16 * r * sz);
                draw(vc, pose, m, ex, ey, ez, eyeW, Math.max(0.02f * r, eyeH), 0.08f * r, skin.eyes(), 255, light);
                if (shut < 0.5 && squint < 0.6) { // the shine that makes eyes look alive (two when wide-eyed or teary)
                    float sh = (float) (0.05 * r * (1 + 0.35 * sad));
                    draw(vc, pose, m, ex + 0.05f * r, ey + 0.09f * r * (float) sz, ez + 0.06f * r,
                            sh, sh, 0.03f * r, 0xFFFFFF, 255, Mc.FULL_BRIGHT);
                    if (wide > 0.3 || sad > 0.5) {
                        draw(vc, pose, m, ex - 0.045f * r, ey - 0.07f * r * (float) sz, ez + 0.06f * r,
                                0.025f * r, 0.025f * r, 0.02f * r, 0xFFFFFF, 255, Mc.FULL_BRIGHT);
                    }
                }
            }
            // brows only when they say something: worried (inner ends up), curious (one raised)
            double browAmt = Math.max(worry, curious * (side == 1 ? 1 : 0));
            if (browAmt > 0.12 && !asleep) {
                // just above the eye (whose half-height is 0.3 r), raised further on the curious side
                float bx = side * 0.38f * r, by = ey + (float) (0.3 * r * sz) + 0.075f * r + (float) (side == 1 ? 0.05 * r * curious : 0);
                float len = (float) (0.12 * r * Math.min(1, browAmt * 1.4));
                pose.pushPose();
                pose.translate(bx, by, front(m, r, bx, by) + 0.004f * r);
                rotate(pose, Axis.ZP.rotation((float) (-side * 0.45 * worry + side * 0.12 * curious)));
                draw(vc, pose, bead, 0, 0, 0, len, 0.03f * r, 0.02f * r, skin.eyes(), 255, light);
                pose.popPose();
            }
            // cheeks: the skin's own, plus a blush when shy or happy
            double blush = Math.min(1, g.blush);
            if (skin.cheeks() != Skin.NO_CHEEKS || blush > 0.05) {
                int base = skin.cheeks() != Skin.NO_CHEEKS ? skin.cheeks() : 0xFF8FAB;
                int col = Mood.blend(base, 0xFF5C8A, (float) blush);
                float grow = (float) (1 + 0.45 * blush) * (skin.cheeks() == Skin.NO_CHEEKS ? (float) blush : 1f);
                float cx = side * 0.6f * r, cy = -0.12f * r;
                draw(vc, pose, m, cx, cy, front(m, r, cx, cy) - 0.01f * r, 0.15f * r * grow, 0.07f * r * grow, 0.05f * r,
                        col, 255, light);
            }
        }
        float my = -0.2f * r;
        double smirk = Smooth.clamp(g.smirk, -1, 1);
        if (c.mouth > 0.06) { // talking: the mouth opens with her voice
            float mouthH = 0.035f * r + 0.16f * r * c.mouth;
            draw(vc, pose, m, (float) (0.02 * r * smirk), my, front(m, r, 0, my) + 0.005f * r, 0.11f * r * (1 - 0.3f * c.mouth), mouthH, 0.05f * r,
                    skin.mouth(), 255, light);
        } else if (wide > 0.6 && smile < 0) { // scared: a small round "o"
            draw(vc, pose, m, 0, my, front(m, r, 0, my) + 0.005f * r, 0.045f * r, 0.06f * r, 0.05f * r, skin.mouth(), 255, light);
        } else if (curious > 0.6 && Math.abs(smirk) < 0.3) { // curious: a little "o", off to one side
            float mx = 0.04f * r;
            draw(vc, pose, m, mx, my, front(m, r, mx, my) + 0.005f * r, 0.035f * r, 0.04f * r, 0.05f * r, skin.mouth(), 255, light);
        } else { // a stroke: a smile, a frown, flat, or the lopsided grin of a tease
            float half = (float) (0.095 * r * (0.8 + 0.35 * Math.abs(smile)));
            arc(vc, pose, m, r, 0, my + (float) (0.02 * r * smile), half, (float) (-0.05 * r * smile), (float) (0.045 * r * smirk),
                    0.026f * r, skin.mouth(), light);
        }
    }

    /**
     * A curved stroke of tiny beads on her face. {@code mid} lifts the middle (+ = "^", - = a smile),
     * {@code tilt} lifts the right end and lowers the left (a lopsided grin).
     */
    private void arc(VertexConsumer vc, PoseStack pose, ShapeMesh body, float r, float cx, float cy, float half,
                     float mid, float tilt, float thick, int rgb, int light) {
        int n = Math.max(5, (int) Math.ceil(half * 2 / (thick * 0.85f)) + 1);
        for (int i = 0; i < n; i++) {
            float t = -1 + 2f * i / (n - 1);
            float x = cx + t * half, y = cy + mid * (1 - t * t) + tilt * t;
            draw(vc, pose, bead, x, y, front(body, r, x, y) + 0.004f * r, thick, thick, thick * 0.6f, rgb, 255, light);
        }
    }

    /** Two little leaves on a short stem on top of her head, swaying as she moves. */
    private void sprout(VertexConsumer vc, PoseStack pose, ShapeMesh m, Companion c, float r, int light, long nowMs) {
        int col = c.skin.sprout() == Skin.MOOD_SPROUT ? Mood.blend(c.rgb, 0x6FD45E, 0.7f) : c.skin.sprout();
        int dark = Mood.shade(col, 0.72f);
        double t = nowMs / 1000.0;
        float sway = (float) (0.12 * Math.sin(t * 1.7) - 2.5 * c.life.squish + 0.6 * c.life.pose.roll);
        float top = (c.skin.shape() == Skin.Shape.CUBE ? 0.86f : 1f) * r; // the top of the head
        pose.pushPose();
        pose.translate(0, top - 0.04f * r, -0.05f * r);
        rotate(pose, Axis.ZP.rotation(sway));
        draw(vc, pose, bead, 0, 0.13f * r, 0, 0.035f * r, 0.16f * r, 0.035f * r, dark, 255, light);   // stem
        for (int side = -1; side <= 1; side += 2) {
            pose.pushPose();
            pose.translate(0, 0.27f * r, 0);
            rotate(pose, Axis.ZP.rotation(side * 0.55f + sway * 0.6f));                                 // a little V
            rotate(pose, Axis.XP.rotation(0.25f));
            draw(vc, pose, bead, side * 0.2f * r, 0, 0, 0.22f * r, 0.05f * r, 0.13f * r, side < 0 ? col : Mood.blend(col, dark, 0.25f), 255, light);
            pose.popPose();
        }
        pose.popPose();
    }

    /**
     * Two pairs of wings hinged on its back (local -Z), a big pair angled up and a small pair
     * angled down. {@code swing} turns them back around the hinge: small = spread, large = folded.
     */
    private static void wings(VertexConsumer vc, PoseStack pose, Skin skin, int col, float r, float swing, int light) {
        int a = Math.round(skin.wingOpacity() * 255);
        for (int side = -1; side <= 1; side += 2) {
            wing(vc, pose, side, r, 1.9f * r, 1.5f * r, 0.45f, swing, 0.15f * r, col, a, light);           // upper
            wing(vc, pose, side, r, 1.25f * r, 0.95f * r, -0.4f, swing * 0.85f + 0.1f, -0.12f * r, col, a, light); // lower
        }
    }

    private static void wing(VertexConsumer vc, PoseStack pose, int side, float r, float len, float height,
                             float tilt, float swing, float hingeY, int rgb, int alpha, int light) {
        pose.pushPose();
        pose.translate(side * 0.15f * r, hingeY, -0.5f * r);          // on its back
        rotate(pose, Axis.YP.rotation(side * -swing));                 // flap around the hinge
        rotate(pose, Axis.ZP.rotation(side * tilt));                   // upper pair up, lower pair down
        PoseStack.Pose p = pose.last();
        int red = (rgb >> 16) & 0xff, green = (rgb >> 8) & 0xff, blue = rgb & 0xff;
        float x1 = side * len, h = height / 2;
        // hinge at u=0, tip at u=1 (the texture is drawn that way); visible from both sides
        float[][] q = {{0, -h, 0, 1}, {x1, -h, 1, 1}, {x1, h, 1, 0}, {0, h, 0, 0}};
        for (float[] c : q) {
            vc.addVertex(p, c[0], c[1], 0).setColor(red, green, blue, alpha).setUv(c[2], c[3])
                    .setOverlay(OverlayTexture.NO_OVERLAY).setLight(light).setNormal(p, 0, 1, 0);
        }
        pose.popPose();
    }

    private static float front(ShapeMesh m, float r, float x, float y) {
        return (float) (m.front(x / r, y / r) * r);
    }

    private static String dots(long now) {
        return switch ((int) (now / 350 % 3)) {
            case 0 -> ".";
            case 1 -> "..";
            default -> "...";
        };
    }

    /** While leading the way: how far, and whether it's up or down from here (in her words, not an arrow that can't turn). */
    private static String guideText(Behavior b) {
        if (b.guideDistance == Double.MAX_VALUE) return "this way!";
        String s = "this way! " + Math.round(b.guideDistance) + " blocks";
        if (b.guideRise > 3) s += "  \u2191" + Math.round(b.guideRise);
        if (b.guideRise < -3) s += "  \u2193" + Math.round(-b.guideRise);
        return s;
    }

    private static String zzz(long now) {
        return switch ((int) (now / 700 % 3)) {
            case 0 -> "z";
            case 1 -> "z z";
            default -> "z z z";
        };
    }

    private static void draw(VertexConsumer vc, PoseStack pose, ShapeMesh m, float cx, float cy, float cz,
                             float rx, float ry, float rz, int rgb, int alpha, int light) {
        PoseStack.Pose p = pose.last();
        int red = (rgb >> 16) & 0xff, green = (rgb >> 8) & 0xff, blue = rgb & 0xff;
        float[] pos = m.pos, nrm = m.nrm, uv = m.uv;
        for (int i = 0, n = m.quads * 4; i < n; i++) {
            vc.addVertex(p, cx + pos[i * 3] * rx, cy + pos[i * 3 + 1] * ry, cz + pos[i * 3 + 2] * rz)
                    .setColor(red, green, blue, alpha)
                    .setUv(uv[i * 2], uv[i * 2 + 1])
                    .setOverlay(OverlayTexture.NO_OVERLAY)
                    .setLight(light)
                    .setNormal(p, nrm[i * 3], nrm[i * 3 + 1], nrm[i * 3 + 2]);
        }
    }

    //? if >=26.1 {
    private void subtitle(PoseStack pose, SubmitNodeCollector out, Quaternionf camRot, Font font, String text,
                          double x, double y, double z) {
    //?} else {
    /*private void subtitle(PoseStack pose, MultiBufferSource out, Quaternionf camRot, Font font, String text,
                          double x, double y, double z) {
    *///?}
        if (!text.equals(wrappedFor)) {
            wrapped = font.split(Component.literal(text), 170);
            wrappedFor = text;
        }
        pose.pushPose();
        pose.translate(x, y, z);
        rotate(pose, camRot);
        float scale = 0.0085f;
        pose.scale(scale, -scale, scale);
        int lineH = font.lineHeight + 1;
        float top = -lineH * wrapped.size();
        int widest = 0;
        for (FormattedCharSequence line : wrapped) widest = Math.max(widest, font.width(line));
        // One background panel, then the letters pushed slightly toward the camera (as vanilla text
        // displays do), so the two never fight over the same depth and letters never flicker away.
        int bg = (int) (Minecraft.getInstance().options.getBackgroundOpacity(0.35f) * 255f) << 24;
        float x0 = -widest / 2f - 3, x1 = widest / 2f + 3, y0 = top - 2, y1 = 1;
        //? if >=26.1 {
        out.submitTextBackground(pose, x0, y0, x1, y1, bg, Font.DisplayMode.POLYGON_OFFSET, Mc.FULL_BRIGHT);
        // a little tail pointing down at her, so it reads as her speech bubble (in steps, like a pixel arrow)
        for (int i = 0; i < 3; i++) {
            float w = 3.5f - i * 1.2f;
            out.submitTextBackground(pose, -w, y1 + i * 1.2f, w, y1 + (i + 1) * 1.2f, bg, Font.DisplayMode.POLYGON_OFFSET, Mc.FULL_BRIGHT);
        }
        for (int i = 0; i < wrapped.size(); i++) {
            FormattedCharSequence line = wrapped.get(i);
            out.submitText(pose, -font.width(line) / 2f, top + i * lineH, line, false, Font.DisplayMode.POLYGON_OFFSET,
                    Mc.FULL_BRIGHT, 0xFFFFFFFF, 0, 0);
        }
        //?} else {
        /*Matrix4f mat = pose.last().pose();
        VertexConsumer panel = out.getBuffer(RenderType.textBackground());
        panel.addVertex(mat, x0, y0, 0).setColor(bg).setLight(Mc.FULL_BRIGHT);
        panel.addVertex(mat, x0, y1, 0).setColor(bg).setLight(Mc.FULL_BRIGHT);
        panel.addVertex(mat, x1, y1, 0).setColor(bg).setLight(Mc.FULL_BRIGHT);
        panel.addVertex(mat, x1, y0, 0).setColor(bg).setLight(Mc.FULL_BRIGHT);
        // a little tail pointing down at her, so it reads as her speech bubble
        panel.addVertex(mat, -3.5f, y1, 0).setColor(bg).setLight(Mc.FULL_BRIGHT);
        panel.addVertex(mat, 0, y1 + 3.5f, 0).setColor(bg).setLight(Mc.FULL_BRIGHT);
        panel.addVertex(mat, 0, y1 + 3.5f, 0).setColor(bg).setLight(Mc.FULL_BRIGHT);
        panel.addVertex(mat, 3.5f, y1, 0).setColor(bg).setLight(Mc.FULL_BRIGHT);
        for (int i = 0; i < wrapped.size(); i++) {
            FormattedCharSequence line = wrapped.get(i);
            font.drawInBatch(line, -font.width(line) / 2f, top + i * lineH, 0xFFFFFFFF, false, mat, out,
                    Font.DisplayMode.POLYGON_OFFSET, 0, Mc.FULL_BRIGHT);
        }
        *///?}
        pose.popPose();
    }
}
