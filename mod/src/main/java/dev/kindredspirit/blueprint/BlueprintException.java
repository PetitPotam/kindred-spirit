package dev.kindredspirit.blueprint;

/** A blueprint that can't be read or built, with a reason a person can understand (it may be shown to her). */
public class BlueprintException extends RuntimeException {
    public BlueprintException(String message) {
        super(message);
    }

    public BlueprintException(String message, Throwable cause) {
        super(message, cause);
    }
}
