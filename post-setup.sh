#!/usr/bin/env bash
HYPR="$HOME/.config/hypr"

sed -i '/^listener {/,/^}/d' "$HYPR/hypridle.conf"
sed -i 's/env = TERMINAL,.*/env = TERMINAL,ghostty/' "$HYPR/hyprland/env.conf"
sed -i '/launch_first_available.sh.*File manager/s/"dolphin"/"thunar" &/' "$HYPR/hyprland/keybinds.conf"
sed -i '/launch_first_available.sh.*Browser/s/"google-chrome-stable" //' "$HYPR/hyprland/keybinds.conf"
sed -i '/launch_first_available.sh.*Task manager/s/"gnome-system-monitor"/"missioncenter" &/' "$HYPR/hyprland/keybinds.conf"
sed -i 's/fg:245/fg:#FFAF00/g; s/bg:252/bg:#FFAF00/g; s/bg:255/bg:#FFAF00/g' ~/.config/starship.toml
echo "alias hx='helix'" >> ~/.config/fish/config.fish
