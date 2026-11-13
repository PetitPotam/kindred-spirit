// The version the code in src/ is written for right now (switch with ./gradlew "Set active project to 1.21.1",
// and back to the vcsVersion in settings.gradle.kts before committing).
stonecutter active "26.3"

stonecutter parameters {
    replacements {
        // Mojang renamed ResourceLocation to Identifier in 1.21.11.
        string(current.parsed >= "1.21.11") {
            replace("ResourceLocation", "Identifier")
        }
    }
}
