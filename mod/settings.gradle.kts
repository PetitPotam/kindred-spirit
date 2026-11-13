pluginManagement {
    repositories {
        maven("https://maven.fabricmc.net/") { name = "Fabric" }
        maven("https://maven.kikugie.dev/releases") { name = "KikuGie Releases" }
        mavenCentral()
        gradlePluginPortal()
    }
}

plugins {
    // One source tree, one jar per Minecraft version: version-specific lines live in //? comments
    // (https://stonecutter.kikugie.dev, LGPL-3.0, build time only).
    id("dev.kikugie.stonecutter") version "0.10"
    // Picks Fabric Loom with remapping for the obfuscated versions (1.21.x) and without it for 26.1 and
    // later, from one build script (https://codeberg.org/KikuGie/loom-back-compat, Unlicense, build time only).
    id("dev.kikugie.loom-back-compat") version "0.4.3"
}

stonecutter {
    create(rootProject) {
        // Each version gets its own folder in versions/ with a gradle.properties (Minecraft, Fabric API).
        versions("1.21.1", "26.3")
        // The code in src/ is written for this version; the others are made from it at build time.
        vcsVersion = "26.3"
    }
}

rootProject.name = "kindred-spirit"
