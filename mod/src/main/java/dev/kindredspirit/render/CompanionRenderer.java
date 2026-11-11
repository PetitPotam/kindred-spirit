package dev.kindredspirit.render;

import com.mojang.blaze3d.vertex.PoseStack;
import com.mojang.blaze3d.vertex.VertexConsumer;
import com.mojang.math.Axis;
import dev.kindredspirit.Companion;
import dev.kindredspirit.KindredConfig;
import dev.kindredspirit.util.Mood;
import dev.kindredspirit.util.Quality;
import dev.kindredspirit.util.SphereMesh;
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

import java.util.List;

/**
 * Draws the slime ball: a glassy shell, a darker core, eyes with a shine, a mouth that moves with
 * its voice, and blushing cheeks. Everything is made of the same precomputed sphere, so there is
 * no model file and no per-frame allocation. Detail follows {@link Quality}.
 */
public final class CompanionRenderer {
    private static final ResourceLocation WHITE = ResourceLocation.fromNamespaceAndPath("kindredspirit", "textures/companion/white.png");
    private static final float RADIUS = 0.2f;

    private final SphereMesh[] meshes = new SphereMesh[Quality.Level.values().length];
    // subtitle line cache: wrapping text every frame would allocate
    private String wrappedFor = null;
    private List<FormattedCharSequence> wrapped = List.of();

    private SphereMesh mesh(Quality.Level level) {
        SphereMesh m = meshes[level.ordinal()];
        if (m == null) m = meshes[level.ordinal()] = new SphereMesh(level.slices, level.stacks);
        return m;
    }

    public void render(WorldRenderContext ctx, Companion c, KindredConfig cfg, Quality.Level level, long now) {
        MultiBufferSource buffers = ctx.consumers();
        PoseStack pose = ctx.matrixStack();
        Minecraft mc = Minecraft.getInstance();
        if (buffers == null || pose == null || mc.level == null) return;
        Camera cam = ctx.camera();
        Vec3 cp = cam.getPosition();
        float r = RADIUS * cfg.size;

        double bx = c.x + c.shiver, by = c.y + c.lift, bz = c.z;
        int light = LevelRenderer.getLightColor(mc.level, BlockPos.containing(bx, by, bz));
        // never fully dark: it should stay cute (and findable) in caves
        light = LightTexture.pack(Math.max(LightTexture.block(light), 9), LightTexture.sky(light));

        pose.pushPose();
        pose.translate(bx - cp.x, by - cp.y, bz - cp.z);
        // squash and stretch in world space, then turn the face toward the camera
        float s = c.squish;
        pose.scale(1 + s * 0.6f, 1 - s, 1 + s * 0.6f);
        double dx = cp.x - bx, dy = cp.y - by, dz = cp.z - bz;
        float yaw = (float) Math.atan2(dx, dz);
        float pitch = (float) Math.atan2(dy, Math.sqrt(dx * dx + dz * dz));
        pitch = Math.max(-0.45f, Math.min(0.45f, pitch));
        pose.mulPose(Axis.YP.rotation(yaw));
        pose.mulPose(Axis.XP.rotation(-pitch));

        SphereMesh m = mesh(level);
        VertexConsumer solid = buffers.getBuffer(RenderType.entityCutoutNoCull(WHITE));
        int body = c.rgb;

        if (level.shell) {
            // darker core inside a glassy shell: reads as "slime" at a glance
            sphere(solid, pose, m, 0, -0.02f * r, 0, r * 0.62f, r * 0.62f, r * 0.62f, Mood.shade(body, 0.72f), 255, light);
        }
        float face = r * 0.97f;
        // eyes
        float eyeH = 0.30f * r * (1 - 0.9f * c.blink);
        for (int side = -1; side <= 1; side += 2) {
            float ex = side * 0.36f * r, ey = 0.12f * r;
            float ez = surface(r, ex, ey) + 0.01f * r;
            sphere(solid, pose, m, ex, ey, ez, 0.16f * r, Math.max(0.02f * r, eyeH), 0.08f * r, 0x1E1A2E, 255, light);
            if (c.blink < 0.5f) {
                sphere(solid, pose, m, ex + 0.05f * r, ey + 0.09f * r, ez + 0.06f * r, 0.05f * r, 0.05f * r, 0.03f * r, 0xFFFFFF, 255, LightTexture.FULL_BRIGHT);
            }
            // cheeks
            float cx = side * 0.6f * r, cy = -0.12f * r;
            sphere(solid, pose, m, cx, cy, surface(r, cx, cy) - 0.01f * r, 0.15f * r, 0.07f * r, 0.05f * r, 0xFF8FAB, 255, light);
        }
        // mouth: a small smile line that opens into an "o" when it talks
        float my = -0.2f * r;
        float mouthH = 0.035f * r + 0.16f * r * c.mouth;
        sphere(solid, pose, m, 0, my, surface(r, 0, my) + 0.005f * r, 0.11f * r * (1 - 0.3f * c.mouth), mouthH, 0.05f * r, 0x3A1A2A, 255, light);

        // the body last, translucent when the quality allows it
        if (level.shell) {
            VertexConsumer glass = buffers.getBuffer(RenderType.entityTranslucentCull(WHITE));
            sphere(glass, pose, m, 0, 0, 0, r, r, r, body, 205, light);
        } else {
            sphere(solid, pose, m, 0, 0, 0, face, face, face, body, 255, light);
        }
        pose.popPose();

        if (cfg.worldSubtitles && !mc.options.hideGui) {
            String text = c.activity == Companion.Activity.LISTENING ? "♪ ..."
                    : c.activity == Companion.Activity.THINKING ? thinkingDots(now)
                    : c.showSubtitle(now) ? c.subtitle : null;
            if (text != null) subtitle(pose, buffers, cam, mc.font, text, bx - cp.x, by - cp.y + r + 0.12, bz - cp.z);
        }
    }

    private static String thinkingDots(long now) {
        return switch ((int) (now / 350 % 3)) {
            case 0 -> ".";
            case 1 -> "..";
            default -> "...";
        };
    }

    /** z of the sphere's front surface at (x, y), so features sit on it. */
    private static float surface(float r, float x, float y) {
        return (float) Math.sqrt(Math.max(0, r * r - x * x - y * y));
    }

    private static void sphere(VertexConsumer vc, PoseStack pose, SphereMesh m, float cx, float cy, float cz,
                               float rx, float ry, float rz, int rgb, int alpha, int light) {
        PoseStack.Pose p = pose.last();
        int red = (rgb >> 16) & 0xff, green = (rgb >> 8) & 0xff, blue = rgb & 0xff;
        float[] xyz = m.xyz, uv = m.uv;
        for (int i = 0, n = m.quads * 4; i < n; i++) {
            float nx = xyz[i * 3], ny = xyz[i * 3 + 1], nz = xyz[i * 3 + 2];
            vc.addVertex(p, cx + nx * rx, cy + ny * ry, cz + nz * rz)
                    .setColor(red, green, blue, alpha)
                    .setUv(uv[i * 2], uv[i * 2 + 1])
                    .setOverlay(OverlayTexture.NO_OVERLAY)
                    .setLight(light)
                    .setNormal(p, nx, ny, nz);
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
        int bg = (int) (Minecraft.getInstance().options.getBackgroundOpacity(0.35f) * 255f) << 24;
        int lineH = font.lineHeight + 1;
        float top = -lineH * wrapped.size();
        for (int i = 0; i < wrapped.size(); i++) {
            FormattedCharSequence line = wrapped.get(i);
            float lx = -font.width(line) / 2f;
            font.drawInBatch(line, lx, top + i * lineH, 0xFFFFFFFF, false, mat, buffers,
                    Font.DisplayMode.NORMAL, bg, LightTexture.FULL_BRIGHT);
        }
        pose.popPose();
    }
}
