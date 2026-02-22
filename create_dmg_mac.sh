#!/bin/sh

# --- CONFIGURATION ---
APP_NAME="honeychrome"
VERSION="0.6.1"
DMG_NAME="${APP_NAME}-v${VERSION}-macos.dmg"
VOL_NAME="${APP_NAME} Installer"

# Paths
SOURCE_FOLDER="dist/honeychrome"  # Folder containing your .app
APP_BUNDLE="${APP_NAME}.app"      # Name of the app inside source_folder
BACKGROUND="other/honeychrome_installer_background.png"     # The background image we discussed
ICON_FILE="src/honeychrome/view_components/assets/cytkit_web_logo.png"         # Optional: your custom icon file

# Logic: Remove existing DMG if it exists
if [ -f "$DMG_NAME" ]; then
  rm "$DMG_NAME"
fi

# --- EXECUTION ---
create-dmg \
  --volname "$VOL_NAME" \
  --volicon "$ICON_FILE" \
  --background "$BACKGROUND" \
  --window-pos 200 120 \
  --window-size 770 450 \
  --icon-size 100 \
  --icon "$APP_BUNDLE" 140 250 \
  --hide-extension "$APP_BUNDLE" \
  --app-drop-link 620 250 \
  --eula "LICENSE.txt"\
  "$DMG_NAME" \
  "$SOURCE_FOLDER/"
