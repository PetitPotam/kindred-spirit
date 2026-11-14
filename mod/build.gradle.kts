// The build for one Minecraft version (versions/<version>/gradle.properties says which); Stonecutter runs it once
// per version. ./gradlew build makes every jar and copies them to build/libs/.
plugins {
    id("dev.kikugie.loom-back-compat")
}

fun prop(name: String) = project.property(name) as String
val minecraftVersion = prop("minecraft_version")
val javaVersion = prop("java_version").toInt()
val modId = prop("archives_base_name")

version = "${prop("mod_version")}+$minecraftVersion"
base { archivesName = modId }

repositories {
    mavenCentral()
}

dependencies {
    minecraft("com.mojang:minecraft:$minecraftVersion")
    // Mojang's official names, the same names other loaders and most tutorials use (from 26.1 on the game ships
    // with them and nothing is remapped).
    loomx.applyMojangMappings()
    modImplementation("net.fabricmc:fabric-loader:${prop("loader_version")}")
    modImplementation("net.fabricmc.fabric-api:fabric-api:${prop("fabric_version")}")

    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
    testLogging {
        events("failed")
        exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
    }
}

loom {
    runs {
        named("client") {
            // Sandbox test script (see DevScript.java):
            // ./gradlew :26.3:runClient -PdevScript=devscripts/smoke-test.txt
            if (project.hasProperty("devScript"))
                jvmArguments.add("-Dkindredspirit.devScript=${rootProject.file(prop("devScript"))}")
            // window size for demo recordings, e.g. -PvideoSize=960x540 (1920x1080 on a Retina screen)
            if (project.hasProperty("videoSize")) {
                val (w, h) = prop("videoSize").split("x")
                programArguments.addAll("--width", w, "--height", h)
            }
            // the player's name in the dev game (otherwise a random "Player123"), e.g. -PplayerName=Sam
            if (project.hasProperty("playerName")) programArguments.addAll("--username", prop("playerName"))
        }
        // a second game on the same computer, as a friend joining your LAN world (light mode checks):
        // ./gradlew :26.3:runGuest -PguestScript=devscripts/lan-guest.txt
        register("guest") {
            client()
            displayName = "Guest client"
            runDirectory = layout.projectDirectory.dir("run-guest")
            programArguments.addAll("--username", "Robin")
            if (project.hasProperty("guestScript"))
                jvmArguments.add("-Dkindredspirit.devScript=${rootProject.file(prop("guestScript"))}")
            // its window size, like videoSize, e.g. -PguestVideoSize=640x360 (two games recording at once)
            if (project.hasProperty("guestVideoSize")) {
                val (w, h) = prop("guestVideoSize").split("x")
                programArguments.addAll("--width", w, "--height", h)
            }
        }
    }
}

tasks.processResources {
    val props = mapOf(
        "version" to project.version.toString(),
        "minecraft" to prop("minecraft_range"),
        "java" to javaVersion.toString(),
    )
    inputs.properties(props)
    filesMatching(listOf("fabric.mod.json", "*.mixins.json")) { expand(props) }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = javaVersion
    // Every compiler warning on, and a warning fails the build (OpenSSF "warnings"); "classfile" is left out because it
    // only reports things inside third-party jars (JOML, Gson), not Kindred's code.
    options.compilerArgs.addAll(listOf("-Xmaxerrs", "2000", "-Xlint:all,-classfile", "-Werror"))
}

java {
    withSourcesJar()
    sourceCompatibility = JavaVersion.toVersion(javaVersion)
    targetCompatibility = JavaVersion.toVersion(javaVersion)
}

tasks.jar {
    from(rootProject.file("../LICENSE")) { rename { "${it}_$modId" } }
    from(rootProject.file("../NOTICE")) { rename { "${it}_$modId" } } // (the permission to combine it with Minecraft)
}

// Every version's jar in one place, mod/build/libs/, where the scripts and the workflows look for it.
val collectJar = tasks.register<Copy>("collectJar") {
    from(loomx.modJar.flatMap { it.archiveFile })
    into(rootProject.layout.buildDirectory.dir("libs"))
}
tasks.named("build") { finalizedBy(collectJar) }
