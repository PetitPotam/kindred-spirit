package dev.kindredspirit.settings;

import com.terraformersmc.modmenu.api.ConfigScreenFactory;
import com.terraformersmc.modmenu.api.ModMenuApi;
import dev.kindredspirit.KindredSpiritClient;

/** Mod Menu's "Configure" button opens her settings screen (#5). Loaded only when Mod Menu is installed. */
public final class ModMenuEntry implements ModMenuApi {
    @Override
    public ConfigScreenFactory<?> getModConfigScreenFactory() {
        return KindredSpiritClient::settingsScreen;
    }
}
