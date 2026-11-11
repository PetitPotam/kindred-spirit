package dev.kindredspirit.util;

/**
 * A unit sphere as a list of quads (4 corners each), built once per quality level so drawing a
 * frame allocates nothing. Corners are ordered counter-clockwise seen from outside, so back faces
 * can be culled.
 */
public final class SphereMesh {
    /** x, y, z for each corner; on a unit sphere the position is also the normal. */
    public final float[] xyz;
    /** u, v texture coordinates for each corner. */
    public final float[] uv;
    public final int quads;

    public SphereMesh(int slices, int stacks) {
        quads = slices * stacks;
        xyz = new float[quads * 4 * 3];
        uv = new float[quads * 4 * 2];
        int p = 0, t = 0;
        for (int i = 0; i < stacks; i++) {
            double th0 = Math.PI * i / stacks, th1 = Math.PI * (i + 1) / stacks;
            for (int j = 0; j < slices; j++) {
                double ph0 = 2 * Math.PI * j / slices, ph1 = 2 * Math.PI * (j + 1) / slices;
                // counter-clockwise from outside: (th0,ph0) (th0,ph1) (th1,ph1) (th1,ph0)
                double[][] corners = {{th0, ph0}, {th0, ph1}, {th1, ph1}, {th1, ph0}};
                for (double[] c : corners) {
                    double s = Math.sin(c[0]);
                    xyz[p++] = (float) (s * Math.cos(c[1]));
                    xyz[p++] = (float) Math.cos(c[0]);
                    xyz[p++] = (float) (s * Math.sin(c[1]));
                    uv[t++] = (float) (c[1] / (2 * Math.PI));
                    uv[t++] = (float) (c[0] / Math.PI);
                }
            }
        }
    }
}
