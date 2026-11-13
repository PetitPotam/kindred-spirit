#!/usr/bin/env python3
"""Writes the sample blueprints the tests read: one little cottage in every format we support.

Independent of the Java code on purpose (its own NBT writer, its own varint and bit packing), so the
tests check the readers against files they didn't produce. Standard library only:

    python3 make_samples.py        # in this folder; rewrites cottage.nbt, cottage_v2.schem, ...

The cottage, 5 wide (x) x 4 high x 5 long (z), front (door) on the south side (z = 4):
  y0  cobblestone floor
  y1  oak plank walls, a door at x=2 (lower half), a chest at (1,1,1) holding 3 bread,
      a structure void at (3,1,3) (leave whatever is there), air elsewhere inside
  y2  walls, the door's upper half, glass at (4,2,2), a wall torch at (2,2,1) facing south
  y3  oak slab roof, a double slab in the middle
  an armor stand standing at (1.5, 1, 3.5)
The .litematic adds a second region: a 2-block brick chimney on top at (4, 4..5, 0).
"""
import gzip
import struct

W, H, L = 5, 4, 5

def cottage():
    cells = {}
    for x in range(W):
        for z in range(L):
            cells[(x, 0, z)] = "minecraft:cobblestone"
            cells[(x, 3, z)] = "minecraft:oak_slab[type=bottom,waterlogged=false]"
            for y in (1, 2):
                edge = x in (0, W - 1) or z in (0, L - 1)
                cells[(x, y, z)] = "minecraft:oak_planks" if edge else "minecraft:air"
    cells[(2, 3, 2)] = "minecraft:oak_slab[type=double,waterlogged=false]"
    door = "minecraft:oak_door[facing=north,half={},hinge=left,open=false,powered=false]"
    cells[(2, 1, 4)] = door.format("lower")
    cells[(2, 2, 4)] = door.format("upper")
    cells[(4, 2, 2)] = "minecraft:glass"
    cells[(2, 2, 1)] = "minecraft:wall_torch[facing=south]"
    cells[(1, 1, 1)] = "minecraft:chest[facing=south,type=single,waterlogged=false]"
    cells[(3, 1, 3)] = "minecraft:structure_void"
    return cells

CHEST_ITEMS = [{"Slot": ("byte", 0), "id": "minecraft:bread", "count": ("int", 3)}]
STAND = {"id": "minecraft:armor_stand", "Invisible": ("byte", 0)}
STAND_POS = (1.5, 1.0, 3.5)

# --- a tiny NBT writer: values are str, dict (compound), list, or (type, value) tuples -------------
T = {"byte": 1, "short": 2, "int": 3, "long": 4, "float": 5, "double": 6, "byte_array": 7, "string": 8,
     "list": 9, "compound": 10, "int_array": 11, "long_array": 12}

def tag_type(v):
    if isinstance(v, tuple):
        return T[v[0]]
    if isinstance(v, str):
        return 8
    if isinstance(v, dict):
        return 10
    if isinstance(v, list):
        return 9
    if isinstance(v, bool):
        return 1
    if isinstance(v, int):
        return 3
    if isinstance(v, float):
        return 6
    raise TypeError(v)

def utf(s):
    b = s.encode("utf-8")
    return struct.pack(">H", len(b)) + b

def payload(v):
    t = tag_type(v)
    raw = v[1] if isinstance(v, tuple) else v
    if t == 1: return struct.pack(">b", raw)
    if t == 2: return struct.pack(">h", raw)
    if t == 3: return struct.pack(">i", raw)
    if t == 4: return struct.pack(">q", raw)
    if t == 5: return struct.pack(">f", raw)
    if t == 6: return struct.pack(">d", raw)
    if t == 7: return struct.pack(">i", len(raw)) + struct.pack(">%db" % len(raw), *raw)
    if t == 8: return utf(raw)
    if t == 9:
        et = tag_type(raw[0]) if raw else 0
        return struct.pack(">bi", et, len(raw)) + b"".join(payload(e) for e in raw)
    if t == 10:
        out = b""
        for k, e in raw.items():
            out += struct.pack(">b", tag_type(e)) + utf(k) + payload(e)
        return out + b"\x00"
    if t == 11: return struct.pack(">i", len(raw)) + b"".join(struct.pack(">i", x) for x in raw)
    if t == 12: return struct.pack(">i", len(raw)) + b"".join(struct.pack(">q", x) for x in raw)
    raise TypeError(v)

def save(path, root):
    with open(path, "wb") as f:
        f.write(gzip.compress(b"\x0a" + utf("") + payload(root), mtime=0))

def state_tag(s):
    name, _, props = s.partition("[")
    t = {"Name": name}
    if props:
        t["Properties"] = dict(kv.split("=") for kv in props.rstrip("]").split(","))
    return t

# --- vanilla structure file ------------------------------------------------------------------------
def structure():
    cells = cottage()
    palette, blocks = [], []
    for y in range(H):
        for z in range(L):
            for x in range(W):
                s = cells[(x, y, z)]
                if s == "minecraft:structure_void":
                    continue  # how a structure block saves a void: the cell isn't listed
                if s not in palette:
                    palette.append(s)
                b = {"state": palette.index(s), "pos": [x, y, z]}
                if (x, y, z) == (1, 1, 1):
                    b["nbt"] = {"id": "minecraft:chest", "Items": CHEST_ITEMS}
                blocks.append(b)
    save("cottage.nbt", {
        "DataVersion": 3955, "size": [W, H, L],
        "palette": [state_tag(s) for s in palette], "blocks": blocks,
        "entities": [{"pos": [("double", c) for c in STAND_POS],
                      "blockPos": [int(c) for c in STAND_POS], "nbt": STAND}]})

# --- Sponge .schem ---------------------------------------------------------------------------------
def varints(values):
    out = bytearray()
    for v in values:
        while v & ~0x7F:
            out.append((v & 0x7F) | 0x80)
            v >>= 7
        out.append(v)
    return [b - 256 if b > 127 else b for b in out]  # NBT bytes are signed

def sponge(version):
    cells = cottage()
    palette, data = {}, []
    # pad the palette so some ids need two varint bytes (>= 128): unused but legal
    for i in range(130):
        palette["minecraft:unused_%d" % i] = i
    for y in range(H):
        for z in range(L):
            for x in range(W):
                s = cells[(x, y, z)]
                if s not in palette:
                    palette[s] = len(palette)
                data.append(palette[s])
    pal = {k: ("int", v) for k, v in palette.items()}
    meta = {"Name": "Cozy cottage", "Author": "Pip's tests"}
    if version == 3:
        body = {"Version": 3, "DataVersion": 3955, "Metadata": meta,
                "Width": ("short", W), "Height": ("short", H), "Length": ("short", L),
                "Offset": ("int_array", [0, 0, 0]),
                "Blocks": {"Palette": pal, "Data": ("byte_array", varints(data)),
                           "BlockEntities": [{"Pos": ("int_array", [1, 1, 1]), "Id": "minecraft:chest",
                                              "Data": {"Items": CHEST_ITEMS}}]},
                "Entities": [{"Pos": [("double", c) for c in STAND_POS], "Id": "minecraft:armor_stand",
                              "Data": {"Invisible": ("byte", 0)}}]}
        save("cottage_v3.schem", {"Schematic": body})
    else:
        body = {"Version": 2, "DataVersion": 3955, "Metadata": meta,
                "Width": ("short", W), "Height": ("short", H), "Length": ("short", L),
                "PaletteMax": len(palette), "Palette": pal, "BlockData": ("byte_array", varints(data)),
                "BlockEntities": [{"Pos": ("int_array", [1, 1, 1]), "Id": "minecraft:chest", "Items": CHEST_ITEMS}],
                "Entities": [{"Pos": [("double", c) for c in STAND_POS], "Id": "minecraft:armor_stand",
                              "Invisible": ("byte", 0)}]}
        save("cottage_v2.schem", body)

# --- Litematica ------------------------------------------------------------------------------------
def pack(values, bits):
    n = (len(values) * bits + 63) // 64
    longs = [0] * n
    for i, v in enumerate(values):
        start = i * bits
        a, off = start // 64, start % 64
        longs[a] |= (v << off) & 0xFFFFFFFFFFFFFFFF
        b = ((i + 1) * bits - 1) // 64
        if b != a:
            longs[b] |= v >> (64 - off)
    return [x - (1 << 64) if x >= 1 << 63 else x for x in longs]  # signed longs

def region(cells, size, position, pad_to=0):
    sx, sy, sz = (abs(s) for s in size)
    palette = ["minecraft:air"]  # Litematica always starts with air
    values = []
    for y in range(sy):
        for z in range(sz):
            for x in range(sx):
                s = cells.get((x, y, z), "minecraft:air")
                if s == "minecraft:structure_void":
                    s = "minecraft:air"  # Litematica has no void: air there
                if s not in palette:
                    palette.append(s)
                values.append(palette.index(s))
    while len(palette) < pad_to:  # more states -> 5 bits per entry, entries running over two longs
        palette.append("minecraft:unused_%d" % len(palette))
    bits = max(2, (len(palette) - 1).bit_length())
    return {"Position": {"x": position[0], "y": position[1], "z": position[2]},
            "Size": {"x": size[0], "y": size[1], "z": size[2]},
            "BlockStatePalette": [state_tag(s) for s in palette],
            "BlockStates": ("long_array", pack(values, bits)),
            "TileEntities": [], "Entities": [], "PendingBlockTicks": [], "PendingFluidTicks": []}

def litematic():
    cells = cottage()
    house = region(cells, (-W, H, -L), (W - 1, 0, L - 1), pad_to=17)  # negative size: reaches back
    house["TileEntities"] = [{"x": 1, "y": 1, "z": 1, "id": "minecraft:chest", "Items": CHEST_ITEMS}]
    # entities are relative to the region's Position (4, 0, 4)
    house["Entities"] = [dict(STAND, Pos=[("double", STAND_POS[0] - 4), ("double", STAND_POS[1]),
                                          ("double", STAND_POS[2] - 4)])]
    chimney = region({(0, 0, 0): "minecraft:bricks", (0, 1, 0): "minecraft:bricks"}, (1, 2, 1), (4, 4, 0))
    save("cottage.litematic", {
        "MinecraftDataVersion": 3955, "Version": 7, "SubVersion": 1,
        "Metadata": {"Name": "Cozy cottage", "Author": "Pip's tests", "RegionCount": 2,
                     "EnclosingSize": {"x": W, "y": H + 2, "z": L}},
        "Regions": {"House": house, "Chimney": chimney}})

if __name__ == "__main__":
    structure()
    sponge(2)
    sponge(3)
    litematic()
