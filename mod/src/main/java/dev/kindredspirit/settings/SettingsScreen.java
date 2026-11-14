package dev.kindredspirit.settings;

import com.google.gson.JsonElement;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Her settings, in the game (#5): the same sections and settings as her dashboard's Settings page, each with its
 * explanation and default (hover), changed at once; and her profiles, to switch or save. Opened with the settings key,
 * {@code /kindred settings} or Mod Menu. Only vanilla buttons and text boxes, a page at a time: light on the game.
 */
public final class SettingsScreen extends Screen {
    private static final int ROW = 22, TOP = 62;
    private static final long TYPING_PAUSE_MS = 900; // (a typed value is saved once you stop typing)

    private final Screen parent;
    private final SettingsStore store;
    private List<SettingsModel.Entry> entries = new ArrayList<>();
    private List<String> profiles = List.of();
    private String group = "who";
    private int page;
    private String status = "Loading her settings…";
    private boolean failed, started;
    private volatile boolean dirty; // (answers arrive between frames: the screen is redrawn on its next tick)

    private final Map<SettingsModel.Entry, EditBox> typing = new HashMap<>();
    private final Map<SettingsModel.Entry, Long> typedAt = new HashMap<>();
    private final List<Object[]> labels = new ArrayList<>(); // {text, x, y, colour}
    private EditBox profileName;

    public SettingsScreen(Screen parent, SettingsStore store, String herName) {
        super(Component.literal(herName + "'s settings"));
        this.parent = parent;
        this.store = store;
    }

    private void reload() {
        store.load().whenComplete((list, err) -> Minecraft.getInstance().execute(() -> {
            if (err != null) {
                failed = true;
                status = "Couldn't read her settings: " + SettingsStore.message(err);
            } else {
                entries = list;
                List<String> gs = SettingsModel.groups(entries);
                if (!gs.contains(group) && !gs.isEmpty()) group = gs.get(0);
                status = store.where();
                failed = false;
            }
            dirty = true;
        }));
        store.profiles().whenComplete((list, err) -> Minecraft.getInstance().execute(() -> {
            if (err == null) {
                profiles = list;
                dirty = true;
            }
        }));
    }

    private int perPage() {
        return Math.max(3, (height - TOP - 78) / ROW);
    }

    @Override
    protected void init() {
        if (!started) {
            started = true;
            reload();
        }
        typing.clear();
        labels.clear();
        int w = Math.min(width - 20, 420), left = (width - w) / 2, right = left + w;
        List<String> gs = SettingsModel.groups(entries);
        if (!gs.isEmpty()) { // the section: < Her voice (3 of 8) >
            int i = Math.max(0, gs.indexOf(group));
            addRenderableWidget(Button.builder(Component.literal("<"), b -> section(gs, i - 1)).bounds(left, 34, 20, 20).build());
            addRenderableWidget(Button.builder(Component.literal(SettingsModel.title(group) + "  (" + (i + 1) + " of " + gs.size() + ")"),
                    b -> section(gs, i + 1)).bounds(left + 22, 34, w - 44, 20)
                    .tooltip(Tooltip.create(Component.literal("Saved in " + SettingsModel.appliesWhen(group)))).build());
            addRenderableWidget(Button.builder(Component.literal(">"), b -> section(gs, i + 1)).bounds(right - 20, 34, 20, 20).build());
        }
        int ctrlW = Math.min(140, w / 3), ctrlX = right - ctrlW - 22, y = TOP;
        for (SettingsModel.Entry e : SettingsModel.page(entries, group, page, perPage())) {
            labels.add(new Object[]{font.plainSubstrByWidth(e.label, ctrlX - left - 6), left, y + 6, e.isDefault() ? 0xFFE0E0E0 : 0xFFFFE08A});
            Tooltip tip = Tooltip.create(Component.literal(e.label + (e.help.isEmpty() ? "" : "\n\n" + e.help)
                    + (e.fallback == null ? "" : "\n\nDefault: " + SettingsModel.show(e, e.fallback))));
            switch (e.type) {
                case "bool" -> addRenderableWidget(Button.builder(Component.literal(SettingsModel.show(e, e.value)),
                        b -> save(e, new com.google.gson.JsonPrimitive(!(e.value != null && !e.value.isJsonNull() && e.value.getAsBoolean())))).bounds(ctrlX, y, ctrlW, 20).tooltip(tip).build());
                case "choice" -> addRenderableWidget(Button.builder(Component.literal(font.plainSubstrByWidth(SettingsModel.show(e, e.value), ctrlW - 8)),
                        b -> save(e, new com.google.gson.JsonPrimitive(SettingsModel.nextChoice(e, false)))).bounds(ctrlX, y, ctrlW, 20).tooltip(tip).build());
                case "int", "float" -> {
                    addRenderableWidget(Button.builder(Component.literal("-"), b -> save(e, SettingsModel.step(e, -1))).bounds(ctrlX, y, 20, 20).build());
                    box(e, ctrlX + 22, y, ctrlW - 44, SettingsModel.show(e, e.value), tip);
                    addRenderableWidget(Button.builder(Component.literal("+"), b -> save(e, SettingsModel.step(e, 1))).bounds(ctrlX + ctrlW - 20, y, 20, 20).build());
                }
                default -> box(e, ctrlX, y, ctrlW, e.value == null || e.value.isJsonNull() ? "" : e.value.getAsString(), tip);
            }
            Button reset = addRenderableWidget(Button.builder(Component.literal("↺"), b -> save(e, null)).bounds(right - 20, y, 20, 20)
                    .tooltip(Tooltip.create(Component.literal(e.fallback == null ? "No default" : "Back to the default: " + SettingsModel.show(e, e.fallback)))).build());
            reset.active = e.fallback != null && !e.isDefault();
            y += ROW;
        }
        int pages = SettingsModel.pages(entries, group, perPage()), bottom = height - 50;
        if (pages > 1) {
            addRenderableWidget(Button.builder(Component.literal("< Page " + (page + 1) + " of " + pages + " >"), b -> {
                page = (page + 1) % pages;
                dirty = true;
            }).bounds(width / 2 - 60, bottom - 24, 120, 20).build());
        }
        // her profiles: switch to one, or save what's set now as one (shared with the dashboard's)
        int x = left;
        for (String p : profiles.subList(0, Math.min(3, profiles.size()))) {
            boolean on = p.startsWith("*");
            String name = on ? p.substring(1) : p;
            Button b = addRenderableWidget(Button.builder(Component.literal((on ? "✓ " : "") + font.plainSubstrByWidth(name, 70)),
                    btn -> profile("apply", name)).bounds(x, bottom, 84, 20)
                    .tooltip(Tooltip.create(Component.literal(on ? "Profile in use: " + name : "Switch to the profile \"" + name + "\""))).build());
            b.active = !on;
            x += 86;
        }
        if (store instanceof SettingsStore.Dashboard) {
            profileName = addRenderableWidget(new EditBox(font, x, bottom, Math.max(60, right - x - 92), 20, Component.literal("Profile name")));
            profileName.setMaxLength(40);
            profileName.setHint(Component.literal("new profile name"));
            addRenderableWidget(Button.builder(Component.literal("Save profile"), b -> {
                String n = profileName.getValue().trim();
                if (!n.isEmpty()) profile("save", n);
            }).bounds(right - 88, bottom, 88, 20).tooltip(Tooltip.create(Component.literal("Saves everything set now under this name"))).build());
        }
        addRenderableWidget(Button.builder(Component.literal("Done"), b -> onClose()).bounds(width / 2 - 50, height - 26, 100, 20).build());
    }

    private void box(SettingsModel.Entry e, int x, int y, int w, String text, Tooltip tip) {
        EditBox box = addRenderableWidget(new EditBox(font, x, y, w, 20, Component.literal(e.label)));
        box.setMaxLength(e.type.equals("longtext") ? 2000 : 80);
        box.setValue(text);
        box.setTooltip(tip);
        box.setResponder(s -> typedAt.put(e, System.currentTimeMillis()));
        typing.put(e, box);
    }

    /** A section by its key ("mod", "voice"...): for dev scripts. */
    public void showSection(String key) {
        group = key;
        page = 0;
        dirty = true;
    }

    private void section(List<String> gs, int i) {
        group = gs.get(Math.floorMod(i, gs.size()));
        page = 0;
        dirty = true;
    }

    /** A typed value is saved once you pause (no Enter needed, nothing lost when you close the screen). */
    @Override
    public void tick() {
        super.tick();
        if (dirty) {
            dirty = false;
            rebuildWidgets();
        }
        long now = System.currentTimeMillis();
        for (var it = typedAt.entrySet().iterator(); it.hasNext(); ) {
            var t = it.next();
            if (now - t.getValue() < TYPING_PAUSE_MS) continue;
            it.remove();
            saveTyped(t.getKey());
        }
    }

    private void saveTyped(SettingsModel.Entry e) {
        EditBox box = typing.get(e);
        if (box == null) return;
        JsonElement v = SettingsModel.parse(e, box.getValue());
        if (v == null) {
            status = "\"" + box.getValue() + "\" isn't a number: " + e.label + " stays " + SettingsModel.show(e, e.value);
            failed = true;
        } else if (!v.equals(e.value)) {
            save(e, v);
        }
    }

    private void save(SettingsModel.Entry e, JsonElement value) {
        JsonElement before = e.value;
        e.value = value != null ? value : e.fallback; // (shown at once; put back if it isn't saved)
        boolean redraw = !typing.containsKey(e) || value == null;
        if (redraw) dirty = true;
        store.set(e, value).whenComplete((err, x) -> Minecraft.getInstance().execute(() -> {
            String problem = x != null ? SettingsStore.message(x) : err;
            failed = !problem.isEmpty();
            status = failed ? "Not saved: " + problem : e.label + ": " + SettingsModel.show(e, e.value) + " (saved)";
            if (failed) {
                e.value = before;
                dirty = true;
            }
        }));
    }

    private void profile(String action, String name) {
        status = (action.equals("save") ? "Saving the profile " : "Switching to ") + name + "…";
        store.profile(action, name).whenComplete((err, x) -> Minecraft.getInstance().execute(() -> {
            String problem = x != null ? SettingsStore.message(x) : err;
            failed = !problem.isEmpty();
            status = failed ? "Not done: " + problem : action.equals("save") ? "Saved the profile " + name : "Now using " + name;
            reload();
        }));
    }

    @Override
    public void onClose() {
        for (SettingsModel.Entry e : new ArrayList<>(typedAt.keySet())) saveTyped(e);
        typedAt.clear();
        dev.kindredspirit.util.Mc.setScreen(Minecraft.getInstance(), parent);
    }

    //? if >=26.1 {
    @Override
    public void extractRenderState(GuiGraphicsExtractor g, int mouseX, int mouseY, float delta) {
        super.extractRenderState(g, mouseX, mouseY, delta);
        draw(g);
    }
    //?} else {
    /*@Override
    public void render(GuiGraphicsExtractor g, int mouseX, int mouseY, float delta) {
        super.render(g, mouseX, mouseY, delta);
        draw(g);
    }
    *///?}

    private void draw(GuiGraphicsExtractor g) {
        String t = getTitle().getString();
        g.text(font, t, (width - font.width(t)) / 2, 10, 0xFFFFFFFF);
        String s = font.plainSubstrByWidth(status, width - 20);
        g.text(font, s, (width - font.width(s)) / 2, 22, failed ? 0xFFFF8080 : 0xFFA0A0A0);
        for (Object[] l : labels) g.text(font, (String) l[0], (int) l[1], (int) l[2], (int) l[3]);
    }
}
