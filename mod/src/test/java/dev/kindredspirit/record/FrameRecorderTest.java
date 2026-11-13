package dev.kindredspirit.record;

import com.google.gson.JsonObject;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class FrameRecorderTest {
    @Test
    void theStartEventCarriesTheWallClockFrameRateAndSize() {
        JsonObject o = FrameRecorder.startJson(1_763_000_000_123L, 1920, 1080);
        assertEquals("{\"t\":0.0,\"type\":\"start\",\"wall\":1763000000123,\"fps\":30,\"size\":\"1920x1080\"}", o.toString());
    }

    @Test
    void aFriendsLineSaysWhoSaidIt() {
        JsonObject o = FrameRecorder.json(12.5, "line", "friend", null, "Pip, can we have some bread?", "Robin");
        assertEquals("friend", o.get("name").getAsString());
        assertEquals("Robin", o.get("from").getAsString());
        assertEquals("Pip, can we have some bread?", o.get("text").getAsString());
        assertEquals(12.5, o.get("t").getAsDouble());
    }

    @Test
    void herLinesAndMarksHaveNoFrom() {
        assertFalse(FrameRecorder.json(3.0, "line", "pip", null, "Hi!", null).has("from"));
        JsonObject mark = FrameRecorder.json(4.0, "mark", "s03a", null, null, null);
        assertEquals("{\"t\":4.0,\"type\":\"mark\",\"name\":\"s03a\"}", mark.toString());
    }

    @Test
    void linesAreNotWrittenWhenNotRecording() {
        int before = FrameRecorder.pipLines();
        FrameRecorder.line("friend", "Pip, hi", "Robin"); // no recording: nothing to write, no error
        FrameRecorder.line("pip", "Hello!", null);
        assertFalse(FrameRecorder.recording());
        assertEquals(before + 1, FrameRecorder.pipLines(), "only her own lines are counted");
    }
}
