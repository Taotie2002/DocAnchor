#!/usr/bin/env bash
# DocAnchor CLI 启动脚本
# 自动设置 PYTHONPATH、加载 .env、激活本地 venv

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 加载 .env（如存在），将变量 export 到当前 shell
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.env"
    set +a
fi

export PYTHONPATH="$SCRIPT_DIR/src"
exec "$SCRIPT_DIR/.venv/bin/python" -m docanchor.cli "$@"