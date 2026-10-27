#!/bin/zsh
set -eu
cd "$(dirname "$0")/.."
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
"$PYTHON_BIN" -c 'import fitz; import sys,json,pathlib; pathlib.Path("runtime.json").write_text(json.dumps({"python":sys.executable}))'
mkdir -p '题间.app/Contents/MacOS' '题间.app/Contents/Resources'
mkdir -p data/swift-cache
swiftc -module-cache-path "$PWD/data/swift-cache" native/main.swift -o '题间.app/Contents/MacOS/QuestionSpace' -framework Cocoa -framework WebKit
cat > '题间.app/Contents/Info.plist' <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><dict><key>CFBundleExecutable</key><string>QuestionSpace</string><key>CFBundleIdentifier</key><string>local.question-space.chemistry</string><key>CFBundleName</key><string>题间</string><key>CFBundleDisplayName</key><string>题间</string><key>CFBundleVersion</key><string>1</string><key>CFBundleShortVersionString</key><string>0.1.0</string><key>NSHighResolutionCapable</key><true/><key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict></dict></plist>
PLIST
printf 'Built: %s/题间.app\n' "$PWD"
