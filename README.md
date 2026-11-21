# Klippo

Klippo corrects or rewrites the text in your clipboard with a language model running on your own computer, so the text never leaves the machine. Copy some text, press a shortcut, wait for the notification, and paste.

| Shortcut | What it does | System prompt |
|---|---|---|
| Ctrl+Alt+G | Correct: fix spelling, grammar, and phrasing while staying close to your wording | `prompts/fix.txt` |
| Ctrl+Alt+F | Rewrite in a formal, professional tone | `prompts/formal.txt` |

The notification shows the start of the result. The result stays in the clipboard until you copy something else.

## Inline instructions

End the copied text with `>> instruction`, and the model follows the instruction instead of correcting the text:

    cant come tomorow, kid sick >> write a short email to my manager
    <long article text> >> summarize in 3 bullet points
    >> write a polite reminder about the unpaid invoice

The instruction must be on the last line, with a space or line break before the marker, so a `>>` inside code is left alone. Set `KLIPPO_MARKER` to use a different marker.

## Requirements

- Linux with GNOME, which provides the keyboard shortcuts and the notifications.
- The system `python3` with PyGObject and GTK 3 (`python3-gi` and `gir1.2-gtk-3.0` on Debian and Ubuntu). No other Python packages are needed.
- A local server with an OpenAI-compatible chat API: llama.cpp or vLLM, described below.

Klippo has been used with Qwen3.5-9B and Qwen3.8-27B. It turns off the thinking mode of Qwen models, which only adds delay for editing.

## Model server

### llama.cpp (most GPUs, including older ones)

`setup-local.sh` installs `llama-server` as the systemd user service `klippo-llm`, which starts at login, and sets the two shortcuts. Your other custom shortcuts are kept.

    MODEL=~/models/Qwen3.5-9B-Q4_K_M.gguf GPUS=0 bash setup-local.sh

| Setting | Meaning |
|---|---|
| `MODEL` | Path to the GGUF model (required) |
| `GPUS` | CUDA device numbers, comma-separated (default `0`) |
| `LLAMA_DIR` | Folder that holds `llama-server` (default: found on `PATH`) |
| `CUDART_DIR` | Folder with the CUDA runtime libraries, if the llama.cpp build needs them |

The settings can also be kept in a `local.env` file next to the script, which git ignores. Qwen3.5-9B at Q4_K_M (5.7 GB) fits on a 12 GB GPU and is about three times faster than a 27B model.

    systemctl --user status klippo-llm        # server state
    journalctl --user -u klippo-llm -f        # server logs

### vLLM (GPUs with compute capability 7.0 or higher)

`compose.yaml` runs vLLM in a container with Qwen3.8-27B at 4-bit weights (about 18 GiB) on one 24 GB GPU. The weights must already be in `~/.cache/huggingface`, or remove `HF_HUB_OFFLINE=1` to download them on the first start.

    podman-compose up -d          # start the server (a few minutes to load)
    podman-compose down           # stop it and free the GPU
    podman logs -f klippo-vllm    # logs

With vLLM, add the shortcuts yourself in GNOME Settings → Keyboard → Custom Shortcuts:

    env GDK_BACKEND=x11 /usr/bin/python3 /path/to/klippo.py fix
    env GDK_BACKEND=x11 /usr/bin/python3 /path/to/klippo.py formal

`GDK_BACKEND=x11` is needed on Wayland, where a program started from a shortcut cannot read the clipboard otherwise.

## Configuration

`klippo.py` reads these environment variables. GNOME shortcuts do not read your shell profile, so set them in the shortcut command, for example `env GDK_BACKEND=x11 KLIPPO_URL=... /usr/bin/python3 /path/to/klippo.py fix`.

| Variable | Default | Meaning |
|---|---|---|
| `KLIPPO_URL` | `http://127.0.0.1:8000/v1/chat/completions` | Chat API endpoint |
| `KLIPPO_MODEL` | `klippo` | Model name sent to the server |
| `KLIPPO_MARKER` | `>>` | Marker for inline instructions |

Texts longer than 12,000 characters are refused, to stay within the server's context window of 8,192 tokens.

## Adding a style

Add a system prompt as `prompts/<name>.txt` and bind a shortcut to `klippo.py <name>`.

## License

GPL-3.0. See [LICENSE](LICENSE).
