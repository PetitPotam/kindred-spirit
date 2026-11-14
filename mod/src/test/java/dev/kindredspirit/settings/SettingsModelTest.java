package dev.kindredspirit.settings;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.google.gson.JsonPrimitive;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/** #5: her settings in the game, read from the dashboard's list and changed the dashboard's way. */
class SettingsModelTest {
    static final String EDITABLE = """
            {"settings": [
              {"where": "brain", "path": "name", "label": "Her name", "type": "text", "value": "Pip", "default": "Pip", "help": null},
              {"where": "brain", "path": "ai.temperature", "label": "How free her words are", "type": "float", "value": 0.8,
               "default": 0.8, "help": "Low: steady.", "range": [0, 1.5, 0.05]},
              {"where": "brain", "path": "voice.speed", "label": "Speed", "type": "int", "value": 3, "default": 2, "range": [1, 4, 1]},
              {"where": "gateway", "path": "tts.use", "label": "Voice", "type": "choice", "choices": ["local_kokoro", "gemini"],
               "value": "gemini", "default": "local_kokoro"},
              {"where": "mod", "path": "glow", "label": "Glow", "type": "bool", "value": true, "default": true},
              {"where": "mod", "path": "life.wander", "label": "Wander", "type": "bool", "value": false, "default": true},
              {"where": "mod", "path": "skin", "label": "Skin", "type": "choice", "choices": [], "value": "slime"},
              {"where": "brain", "path": "odd", "label": "Odd", "type": "list", "value": []}
            ]}""";

    static List<SettingsModel.Entry> entries() {
        return SettingsModel.fromDashboard(JsonParser.parseString(EDITABLE).getAsJsonObject());
    }

    @Test
    void theDashboardsSectionsInItsOrder() {
        List<SettingsModel.Entry> all = entries();
        assertEquals(6, all.size(), "a choice with no choices, and a type it can't show, are left out");
        assertEquals(List.of("who", "ai", "voice", "gateway", "mod", "life"), SettingsModel.groups(all));
        assertEquals("Her liveliness in game", SettingsModel.title("life"));
        assertEquals(1, SettingsModel.page(all, "mod", 0, 10).size());
    }

    @Test
    void valuesReadPlainly() {
        List<SettingsModel.Entry> all = entries();
        assertEquals("0.8", SettingsModel.show(all.get(1), all.get(1).value));
        assertEquals("on", SettingsModel.show(all.get(4), all.get(4).value));
        assertTrue(all.get(4).isDefault());
        assertFalse(all.get(2).isDefault());
    }

    @Test
    void numbersStepInsideTheirRangeAndTypedOnesAreChecked() {
        SettingsModel.Entry speed = entries().get(2), temp = entries().get(1);
        assertEquals(new JsonPrimitive(4L), SettingsModel.step(speed, 1));
        speed.value = new JsonPrimitive(4);
        assertEquals(new JsonPrimitive(4L), SettingsModel.step(speed, 1), "never past the top");
        assertEquals(new JsonPrimitive(0.85), SettingsModel.step(temp, 1));
        assertEquals(new JsonPrimitive(1.5), SettingsModel.parse(temp, "9"), "typed past the top: the top");
        assertEquals(new JsonPrimitive(0.3), SettingsModel.parse(temp, "0,3"), "a comma works too");
        assertNull(SettingsModel.parse(temp, "lots"), "not a number: left as it was");
    }

    @Test
    void choicesGoRound() {
        SettingsModel.Entry voice = entries().get(3);
        assertEquals("local_kokoro", SettingsModel.nextChoice(voice, false));
        voice.value = new JsonPrimitive("local_kokoro");
        assertEquals("gemini", SettingsModel.nextChoice(voice, false));
    }

    @Test
    void aChangeIsWhatTheDashboardTakes() {
        SettingsModel.Entry glow = entries().get(4);
        JsonObject body = SettingsModel.change(glow, new JsonPrimitive(false));
        assertEquals("{\"changes\":[{\"where\":\"mod\",\"path\":\"glow\",\"value\":false}]}", body.toString());
        assertEquals("{\"changes\":[{\"where\":\"mod\",\"path\":\"glow\",\"default\":true}]}", SettingsModel.change(glow, null).toString());
    }

    static final class Fake {
        public boolean glow = true;
        public float voiceVolume = 1f;
        public String brainHost = "127.0.0.1";
        public transient int notASetting;
        public static int alsoNot;
    }

    @Test
    void aFriendsGameShowsItsOwnSettings() {
        Fake now = new Fake();
        now.glow = false;
        List<SettingsModel.Entry> all = SettingsModel.fromFields(now, new Fake());
        assertEquals(List.of("glow", "voiceVolume"), all.stream().map(e -> e.path).toList(), "where her brain is stays out");
        assertEquals("voice volume", all.get(1).label);
        assertFalse(all.get(0).isDefault());
        assertEquals("mod", all.get(0).group());
    }
}
