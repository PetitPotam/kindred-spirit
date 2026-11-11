package dev.kindredspirit.render;

import dev.kindredspirit.skin.Skin;
import dev.kindredspirit.util.SphereMesh;

/**
 * A body shape as quads with positions, normals and texture coordinates, built once per shape and
 * quality level. Every shape starts from the same sphere, so a skin's texture wraps the same way
 * on all of them; the cube is a "superellipsoid": a sphere pushed out toward a soft-cornered cube.
 */
public final class ShapeMesh {
    public final float[] pos, nrm, uv;
    public final int quads;
    private final Skin.Shape shape;

    public ShapeMesh(Skin.Shape shape, int slices, int stacks) {
        this.shape = shape;
        SphereMesh s = new SphereMesh(slices, stacks);
        quads = s.quads;
        uv = s.uv;
        pos = new float[s.xyz.length];
        nrm = new float[s.xyz.length];
        for (int i = 0; i < s.xyz.length; i += 3) {
            double x = s.xyz[i], y = s.xyz[i + 1], z = s.xyz[i + 2];
            if (shape == Skin.Shape.CUBE) {
                double k = Math.pow(Math.pow(Math.abs(x), 6) + Math.pow(Math.abs(y), 6) + Math.pow(Math.abs(z), 6), 1 / 6.0);
                double px = x / k, py = y / k, pz = z / k;
                double nx = Math.signum(px) * Math.pow(Math.abs(px), 5), ny = Math.signum(py) * Math.pow(Math.abs(py), 5),
                        nz = Math.signum(pz) * Math.pow(Math.abs(pz), 5);
                double nl = Math.sqrt(nx * nx + ny * ny + nz * nz);
                pos[i] = (float) (px * 0.86); pos[i + 1] = (float) (py * 0.86); pos[i + 2] = (float) (pz * 0.86);
                nrm[i] = (float) (nx / nl); nrm[i + 1] = (float) (ny / nl); nrm[i + 2] = (float) (nz / nl);
            } else {
                pos[i] = nrm[i] = (float) x;
                pos[i + 1] = nrm[i + 1] = (float) y;
                pos[i + 2] = nrm[i + 2] = (float) z;
            }
        }
    }

    /** z of the front surface at (x, y), unit size: where eyes and mouth sit. */
    public double front(double x, double y) {
        if (shape == Skin.Shape.CUBE) {
            double s = 0.86;
            double ux = x / s, uy = y / s;
            return s * Math.pow(Math.max(0, 1 - Math.pow(Math.abs(ux), 6) - Math.pow(Math.abs(uy), 6)), 1 / 6.0);
        }
        return Math.sqrt(Math.max(0, 1 - x * x - y * y));
    }
}
