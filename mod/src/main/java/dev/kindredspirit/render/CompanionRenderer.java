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
import net.fabricmc.fabric.api.client.rendering.v1.WorldRenderContext;
import net.minecraft.client.Camera;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.Font;
import net.minecraft.client.renderer.LevelRenderer;
import net.minecraft.client.renderer.LightTexture;
import net.minecraft.client.renderer.MultiBufferSource;
import net.minecraft.client.renderer.RenderType;
import net.minecraft.client.renderer.texture.OverlayTexture;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.util.FormattedCharSequence;
import net.minecraft.world.phys.Vec3;
import org.joml.Matrix4f;
import org.joml.Quaternionf;

import java.util.List;

/**
 * Draws the companion from its skin (shape, texture, colors) and its life (where it is, where it
 * looks, its gestures): a body, an optional glassy shell over a darker core, eyes whose pupils
 * look first while the head follows, a mouth that moves with its voice, and cheeks that blush.
 * Meshes are built once per shape and quality level; drawing a frame allocates nothing.
 */
public final class CompanionRenderer {
    private static final float RADIUS = 0.2f;
    private static final ResourceLocation WHITE = SkinRegistry.WHITE;

    private final ShapeMesh[] meshes = new ShapeMesh[Skin.Shape.values().length * Quality.Level.values().length];
    private final Quaternionf lean = new Quaternionf();
    private String wrappedFor = null;
    private List<FormattedCharSequence> wrapped = List.of();

    private ShapeMesh mesh(Skin.Shape shape, Quality.Level level) {
        int i = shape.ordinal() * Quality.Level.values().length + level.ordinal();
        if (meshes[i] == null) meshes[i] = new ShapeMesh(shape, level.slices, level.stacks);
        return meshes[i];
    }

    public void render(WorldRenderContext ctx, Companion c, ResourceLocation bodyTexture, KindredConfig cfg,
                       Quality.Level level, long nowMs) {
        MultiBufferSource buffers = ctx.consumers();
        PoseStack pose = ctx.matrixStack();
        Minecraft mc = Minecraft.getInstance();
        if (buffers == null || pose == null || mc.level == null) return;
        Behavior b = c.life;
        Emote.Pose g = b.pose;
        Skin skin = c.skin;
        Camera cam = ctx.camera();
        Vec3 cp = cam.getPosition();
        float r = RADIUS * cfg.size * skin.size();

        double bx = b.x + b.shiver, by = b.y + b.lift + g.lift, bz = b.z;
        int light = LevelRenderer.getLightColor(mc.level, BlockPos.containing(bx, by, bz));
        // never fully dark: it should stay cute (and findable) in caves; glowing skins ignore darkness
        light = skin.glow() ? LightTexture.FULL_BRIGHT : LightTexture.pack(Math.max(LightTexture.block(light), 9), LightTexture.sky(light));

        int tint = switch (skin.tint()) {
            case MOOD -> c.rgb;
            case FIXED -> skin.color();
            case NONE -> 0xFFFFFF;
        };
        ShapeMesh m = mesh(skin.shape(), level);

        pose.pushPose();
        pose.translate(bx - cp.x, by - cp.y, bz - cp.z);
        if (b.leanAngle > 1e-3) pose.mulPose(lean.identity().rotateAxis((float) b.leanAngle, (float) b.leanAxisX, 0, (float) b.leanAxisZ));
        float s = (float) (b.squish + g.squish);
        float sc = (float) g.scale;
        pose.scale(sc * (1 + s * 0.6f), sc * (1 - s), sc * (1 + s * 0.6f));
        pose.mulPose(Axis.YP.rotation((float) (b.headYaw + g.yaw)));
        pose.mulPose(Axis.XP.rotation((float) -(b.headPitch + g.pitch)));
        if (g.roll != 0) pose.mulPose(Axis.ZP.rotation((float) g.roll));

        VertexConsumer solid = buffers.getBuffer(RenderType.entityCutoutNoCull(WHITE));
        boolean shell = skin.shell() && level.shell;
        if (shell) {
            int core = skin.glow() ? Mood.blend(tint, 0xFFFFFF, 0.55f) : Mood.shade(tint, 0.72f);
            draw(solid, pose, m, 0, -0.02f * r, 0, r * 0.62f, r * 0.62f, r * 0.62f, core, 255, light);
        }
        if (skin.face()) face(solid, pose, m, c, r, light);

        // the body last: glassy when the skin and quality allow it, textured if the skin has one
        if (shell) {
            VertexConsumer glass = buffers.getBuffer(RenderType.entityTranslucentCull(bodyTexture));
            draw(glass, pose, m, 0, 0, 0, r, r, r, tint, Math.round(skin.shellOpacity() * 255), light);
            if (skin.glow()) { // a soft halo around glowing skins
                draw(glass, pose, m, 0, 0, 0, r * 1.45f, r * 1.45f, r * 1.45f, tint, 38, light);
            }
        } else {
            VertexConsumer body = buffers.getBuffer(RenderType.entityCutoutNoCull(bodyTexture));
            float f = r * 0.97f;
            draw(body, pose, m, 0, 0, 0, f, f, f, tint, 255, light);
        }
        pose.popPose();

        if (cfg.worldSubtitles && !mc.options.hideGui) {
            String text = c.activity == Behavior.Activity.LISTENING ? "♪ ..."
                    : c.activity == Behavior.Activity.THINKING ? dots(nowMs)
                    : c.showSubtitle(nowMs) ? c.subtitle
                    : b.dozing() ? zzz(nowMs) : null;
            if (text != null) subtitle(pose, buffers, cam, mc.font, text, bx - cp.x, by - cp.y + r + 0.12, bz - cp.z);
        }
    }

    private void face(VertexConsumer vc, PoseStack pose, ShapeMesh m, Companion c, float r, int light) {
        Behavior b = c.life;
        Emote.Pose g = b.pose;
        Skin skin = c.skin;
        double happy = Math.min(1, g.happyEyes);
        double blink = Math.max(b.blink, 0);
        float eyeH = (float) (0.30 * r * g.eyeScale * (1 - 0.9 * blink) * (1 - 0.7 * happy));
        float eyeW = (float) (0.16 * r * g.eyeScale);
        float lookX = (float) (b.pupilX * 0.08 * r), lookY = (float) (b.pupilY * 0.07 * r);
        for (int side = -1; side <= 1; side += 2) {
            float ex = side * 0.36f * r + lookX, ey = 0.12f * r + lookY + (float) (happy * 0.04 * r);
            float ez = front(m, r, ex, ey) + 0.01f * r;
            draw(vc, pose, m, ex, ey, ez, eyeW, Math.max(0.02f * r, eyeH), 0.08f * r, skin.eyes(), 255, light);
            if (blink < 0.5 && happy < 0.5) { // the shine that makes eyes look alive
                draw(vc, pose, m, ex + 0.05f * r, ey + 0.09f * r * (float) g.eyeScale, ez + 0.06f * r,
                        0.05f * r, 0.05f * r, 0.03f * r, 0xFFFFFF, 255, LightTexture.FULL_BRIGHT);
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
        float mouthH = 0.035f * r + 0.16f * r * c.mouth;
        draw(vc, pose, m, 0, my, front(m, r, 0, my) + 0.005f * r, 0.11f * r * (1 - 0.3f * c.mouth), mouthH, 0.05f * r,
                skin.mouth(), 255, light);
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

    private void subtitle(PoseStack pose, MultiBufferSource buffers, Camera cam, Font font, String text,
                          double x, double y, double z) {
        if (!text.equals(wrappedFor)) {
            wrapped = font.split(Component.literal(text), 170);
            wrappedFor = text;
        }
        pose.pushPose();
        pose.translate(x, y, z);
        pose.mulPose(cam.rotation());
        float scale = 0.0085f;
        pose.scale(scale, -scale, scale);
        Matrix4f mat = pose.last().pose();
        int lineH = font.lineHeight + 1;
        float top = -lineH * wrapped.size();
        int widest = 0;
        for (FormattedCharSequence line : wrapped) widest = Math.max(widest, font.width(line));
        // One background panel, then the letters pushed slightly toward the camera (as vanilla text
        // displays do), so the two never fight over the same depth and letters never flicker away.
        int bg = (int) (Minecraft.getInstance().options.getBackgroundOpacity(0.35f) * 255f) << 24;
        VertexConsumer panel = buffers.getBuffer(RenderType.textBackground());
        float x0 = -widest / 2f - 3, x1 = widest / 2f + 3, y0 = top - 2, y1 = 1;
        panel.addVertex(mat, x0, y0, 0).setColor(bg).setLight(LightTexture.FULL_BRIGHT);
        panel.addVertex(mat, x0, y1, 0).setColor(bg).setLight(LightTexture.FULL_BRIGHT);
        panel.addVertex(mat, x1, y1, 0).setColor(bg).setLight(LightTexture.FULL_BRIGHT);
        panel.addVertex(mat, x1, y0, 0).setColor(bg).setLight(LightTexture.FULL_BRIGHT);
        for (int i = 0; i < wrapped.size(); i++) {
            FormattedCharSequence line = wrapped.get(i);
            font.drawInBatch(line, -font.width(line) / 2f, top + i * lineH, 0xFFFFFFFF, false, mat, buffers,
                    Font.DisplayMode.POLYGON_OFFSET, 0, LightTexture.FULL_BRIGHT);
        }
        pose.popPose();
    }
}
