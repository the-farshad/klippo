#!/bin/bash
# One-time setup to run Klippo's model server on this machine with llama.cpp. llama.cpp also runs
# on GPUs that vLLM does not support (vLLM needs compute capability 7.0+), and llama-server speaks
# the same OpenAI-style API, so klippo.py works with either server.
#
#   - llama-server: the GGUF model $MODEL on the GPUs in $GPUS,
#     at 127.0.0.1:8000 with model name "klippo" (klippo.py's defaults)
#   - systemd user service "klippo-llm": starts at login, restarts if it crashes
#   - GNOME hotkeys Ctrl+Alt+G (fix) and Ctrl+Alt+F (formal), run with GDK_BACKEND=x11 because
#     on Wayland a background script cannot read the clipboard otherwise
#
# Settings, as environment variables or in an optional local.env file next to this script:
#   MODEL       path to the GGUF model (required)
#   GPUS        CUDA device numbers, comma-separated (default: 0)
#   LLAMA_DIR   folder that holds llama-server (default: found on PATH)
#   CUDART_DIR  folder with the CUDA runtime libraries, if the llama.cpp build needs them
#
#   MODEL=~/models/Qwen3.5-9B-Q4_K_M.gguf GPUS=1 bash setup-local.sh
#
# Undo:  systemctl --user disable --now klippo-llm; rm ~/.config/systemd/user/klippo-llm.service
#        and delete the two Klippo shortcuts in GNOME Settings → Keyboard → Custom Shortcuts
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
if [ -f "$HERE/local.env" ]; then . "$HERE/local.env"; fi
MODEL=$(realpath -e "${MODEL:?set MODEL to the path of a GGUF model}")
GPUS=${GPUS:-0}
if [ -z "${LLAMA_DIR:-}" ]; then
  SERVER=$(command -v llama-server) || { echo "llama-server is not on PATH; set LLAMA_DIR" >&2; exit 1; }
  LLAMA_DIR=$(dirname "$SERVER")
fi
LIBS=$LLAMA_DIR${CUDART_DIR:+:$CUDART_DIR}
KLIPPO=$HERE/klippo.py
UNIT=$HOME/.config/systemd/user/klippo-llm.service

echo "== 1/3 GPUs seen by llama.cpp"
CUDA_DEVICE_ORDER=PCI_BUS_ID LD_LIBRARY_PATH=$LIBS "$LLAMA_DIR/llama-server" --list-devices

echo "== 2/3 server service: $UNIT"
mkdir -p "$(dirname "$UNIT")"
cat > "$UNIT" <<EOF
[Unit]
Description=Klippo local LLM (llama.cpp, $(basename "$MODEL") on GPU $GPUS) at 127.0.0.1:8000

[Service]
Environment=CUDA_DEVICE_ORDER=PCI_BUS_ID
Environment=CUDA_VISIBLE_DEVICES=$GPUS
# Older GPUs compile CUDA kernels on first use; keep that cache between restarts (default is too small).
Environment=CUDA_CACHE_MAXSIZE=4294967296
Environment=LD_LIBRARY_PATH=$LIBS
ExecStart=$LLAMA_DIR/llama-server -m $MODEL --alias klippo --host 127.0.0.1 --port 8000 -c 8192 -ngl 999 -np 1 --jinja
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable klippo-llm.service
systemctl --user restart klippo-llm.service  # restart so a changed model takes effect
echo "started $(basename "$MODEL") on GPU $GPUS; loading takes under a minute"

echo "== 3/3 hotkeys"
# Use the system gsettings: a copy from Anaconda or another environment earlier in PATH may have
# no dconf backend and silently write to a file that GNOME never reads.
G=/usr/bin/gsettings
BASE=org.gnome.settings-daemon.plugins.media-keys
P=/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings
CMD="env GDK_BACKEND=x11 /usr/bin/python3 $KLIPPO"
# Add the two shortcuts to the existing list, keeping any other custom shortcuts.
LIST=$($G get $BASE custom-keybindings | /usr/bin/python3 -c '
import ast, sys
current = ast.literal_eval(sys.stdin.read().strip().removeprefix("@as "))
print([p for p in current if p not in sys.argv[1:]] + sys.argv[1:])' "$P/klippo/" "$P/klippo-formal/")
$G set $BASE custom-keybindings "$LIST"
$G set $BASE.custom-keybinding:$P/klippo/ name 'Klippo: correct'
$G set $BASE.custom-keybinding:$P/klippo/ command "$CMD fix"
$G set $BASE.custom-keybinding:$P/klippo/ binding '<Control><Alt>g'
$G set $BASE.custom-keybinding:$P/klippo-formal/ name 'Klippo: formal'
$G set $BASE.custom-keybinding:$P/klippo-formal/ command "$CMD formal"
$G set $BASE.custom-keybinding:$P/klippo-formal/ binding '<Control><Alt>f'
echo "Ctrl+Alt+G -> fix, Ctrl+Alt+F -> formal"
echo "done. Watch the server with: journalctl --user -u klippo-llm -f"
