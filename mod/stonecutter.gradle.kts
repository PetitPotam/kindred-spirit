// The version the code in src/ is written for right now. To work on another one in the IDE, switch with the
// Stonecutter task "Set active project to <version>", and switch back to 26.3 before committing.
stonecutter active "26.3"

stonecutter parameters {
    // Renames that are the same everywhere: the code says the new name, older versions get the old one.
    replacements {
        string(current.parsed >= "1.21.11") { // Mojang's ResourceLocation became Identifier
            replace("ResourceLocation", "Identifier")
            replace(".location()", ".identifier()")
        }
        string(current.parsed >= "26.1") {
            replace("ClientCommandManager", "ClientCommands") // Fabric API took Mojang's naming style
            replace("getGameProfile().getName()", "getGameProfile().name()") // GameProfile became a record
            replace("net.minecraft.world.entity.npc.AbstractVillager", "net.minecraft.world.entity.npc.villager.AbstractVillager")
            replace("net.minecraft.world.entity.npc.Villager", "net.minecraft.world.entity.npc.villager.Villager")
            replace("PayloadTypeRegistry.playS2C()", "PayloadTypeRegistry.clientboundPlay()")
            replace("PayloadTypeRegistry.playC2S()", "PayloadTypeRegistry.serverboundPlay()")
            // drawing the HUD
            replace("net.minecraft.client.gui.GuiGraphics;", "net.minecraft.client.gui.GuiGraphicsExtractor;")
            replace("GuiGraphics g", "GuiGraphicsExtractor g")
            replace("g.drawString(font, ", "g.text(font, ")
        }
    }
}
