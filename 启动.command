#!/bin/zsh
set -eu
cd "$(dirname "$0")"
if [[ ! -x '题间.app/Contents/MacOS/QuestionSpace' ]]; then
 ./scripts/build_app.sh
fi
open '题间.app'
