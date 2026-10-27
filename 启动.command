#!/bin/zsh
set -eu
cd "$(dirname "$0")"
if [[ ! -x 'dist/题间.app/Contents/MacOS/QuestionSpace' ]]; then
 ./scripts/build_app.sh
fi
open 'dist/题间.app'
