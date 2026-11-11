package dev.kindredspirit;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.time.Duration;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;

/**
 * The local WebSocket to the brain (ws://127.0.0.1:47811, bearer token). Reconnects on its own,
 * never blocks the game: connecting, sending and receiving all happen on background threads.
 * Incoming messages are handed to {@code onMessage} on the WebSocket thread; callers move work to
 * the game thread themselves.
 */
public final class BrainLink implements WebSocket.Listener {
    private final URI uri;
    private final String token;
    private final Consumer<JsonObject> onMessage;
    private final Runnable onOpen, onClose;
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build();
    private final ExecutorService sender = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "kindred-brain-send");
        t.setDaemon(true);
        return t;
    });
    private final StringBuilder partial = new StringBuilder();
    private volatile WebSocket ws;
    private volatile boolean connecting;
    private volatile long nextAttempt;
    private int failures;

    public BrainLink(String host, int port, String token, Consumer<JsonObject> onMessage, Runnable onOpen, Runnable onClose) {
        this.uri = URI.create("ws://" + host + ":" + port + "/");
        this.token = token;
        this.onMessage = onMessage;
        this.onOpen = onOpen;
        this.onClose = onClose;
    }

    public boolean connected() {
        return ws != null;
    }

    /** Call often (every tick is fine); it only tries again after a short back-off. */
    public void tick() {
        long now = System.currentTimeMillis();
        if (ws != null || connecting || now < nextAttempt) return;
        connecting = true;
        http.newWebSocketBuilder()
                .header("Authorization", "Bearer " + token)
                .connectTimeout(Duration.ofSeconds(2))
                .buildAsync(uri, this)
                .whenComplete((socket, err) -> {
                    connecting = false;
                    if (err != null) scheduleRetry();
                });
    }

    private void scheduleRetry() {
        failures = Math.min(failures + 1, 5);
        nextAttempt = System.currentTimeMillis() + 1000L * Math.min(10, 2 * failures);
    }

    public void reconnectNow() {
        close();
        failures = 0;
        nextAttempt = 0;
    }

    /** Queues a message; dropped silently when the brain is not connected. */
    public void send(JsonObject msg) {
        WebSocket socket = ws;
        if (socket == null) return;
        sender.execute(() -> {
            try {
                socket.sendText(msg.toString(), true).get(10, TimeUnit.SECONDS);
            } catch (Exception e) {
                KindredSpiritClient.LOG.debug("send failed: {}", e.toString());
            }
        });
    }

    public void close() {
        WebSocket socket = ws;
        ws = null;
        if (socket != null) socket.abort();
    }

    @Override
    public void onOpen(WebSocket webSocket) {
        ws = webSocket;
        failures = 0;
        webSocket.request(1);
        onOpen.run();
    }

    @Override
    public CompletionStage<?> onText(WebSocket webSocket, CharSequence data, boolean last) {
        partial.append(data);
        if (last) {
            String text = partial.toString();
            partial.setLength(0);
            try {
                onMessage.accept(JsonParser.parseString(text).getAsJsonObject());
            } catch (Exception e) {
                KindredSpiritClient.LOG.warn("Bad message from brain: {}", e.toString());
            }
        }
        webSocket.request(1);
        return null;
    }

    @Override
    public CompletionStage<?> onClose(WebSocket webSocket, int statusCode, String reason) {
        lost(webSocket, "closed " + statusCode + " " + reason);
        return null;
    }

    @Override
    public void onError(WebSocket webSocket, Throwable error) {
        lost(webSocket, error.toString());
    }

    private void lost(WebSocket webSocket, String why) {
        if (ws == webSocket) {
            ws = null;
            partial.setLength(0);
            KindredSpiritClient.LOG.info("Brain connection lost: {}", why);
            scheduleRetry();
            onClose.run();
        }
    }
}
