#!/usr/bin/python3
"""Correct the text in the clipboard with a local LLM and put the result back.

Usage: klippo.py [style]     (style = a file name in prompts/, default "fix")

Workflow: Ctrl+C some text -> press the hotkey -> wait for the notification -> Ctrl+V.
Inline instruction: end the copied text with ">> <instruction>", e.g.
    "cant come tmrw, kid sick >> write a short email to my manager"
and the model follows the instruction instead of just correcting.
Runs with the *system* python3 (needs python3-gi / GTK 3), not the vLLM venv.
"""
import fcntl
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

HERE = Path(__file__).resolve().parent
API_URL = os.environ.get("KLIPPO_URL", "http://127.0.0.1:8000/v1/chat/completions")
MODEL = os.environ.get("KLIPPO_MODEL", "klippo")
MARKER = os.environ.get("KLIPPO_MARKER", ">>")  # "text >> instruction"
MAX_CHARS = 12000  # keep well inside the server's context window
NOTIFY_ID = 0  # reuse one notification bubble instead of stacking them


def notify(body, summary="Klippo", timeout_ms=4000):
    """Show a GNOME notification via D-Bus (no notify-send needed)."""
    global NOTIFY_ID
    try:
        out = subprocess.run(
            ["gdbus", "call", "--session",
             "--dest", "org.freedesktop.Notifications",
             "--object-path", "/org/freedesktop/Notifications",
             "--method", "org.freedesktop.Notifications.Notify",
             "Klippo", str(NOTIFY_ID), "accessories-text-editor",
             summary, body[:300], "[]", "{}", str(timeout_ms)],
            capture_output=True, text=True, timeout=3,
        ).stdout
        # Reply looks like "(uint32 42,)"
        NOTIFY_ID = int(out.strip("()\n, ").split()[-1])
    except Exception:
        pass


def split_instruction(text):
    """'some text >> summarize it'  ->  ('some text', 'summarize it').

    The instruction is whatever follows the LAST marker, and only counts if it
    is a single non-empty line, so a `>>` in the middle of code is ignored."""
    head, sep, tail = text.rpartition(MARKER)
    instruction = tail.strip()
    if not sep or not instruction or "\n" in instruction:
        return text, None
    if head and not head[-1].isspace():  # require a space/newline before the marker
        return text, None
    return head.strip(), instruction


def run_llm(text, style):
    content, instruction = split_instruction(text)
    if instruction:
        system_prompt = (HERE / "prompts" / "instruct.txt").read_text()
        user_msg = f"Instruction: {instruction}"
        if content:
            user_msg += f"\n\n<text>\n{content}\n</text>"
        temperature = 0.7  # writing/summarizing benefits from a bit more freedom
    else:
        system_prompt = (HERE / "prompts" / f"{style}.txt").read_text()
        user_msg = text
        # Low temperature and no presence penalty keep the output close to the original wording.
        temperature = 0.3
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "temperature": temperature,
        "top_p": 0.8,
        "top_k": 20,
        "max_tokens": max(1024, len(text) // 2),
        # Qwen3.x "thinks" by default; for copy-editing that only adds latency.
        "chat_template_kwargs": {"enable_thinking": False},
    }
    req = urllib.request.Request(
        API_URL, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        out = json.load(resp)["choices"][0]["message"]["content"]
    return out.strip()


def serve_clipboard(clipboard, text):
    """On X11 the clipboard lives in the owning process, so stay alive until
    someone else copies something (or a clipboard manager takes it over)."""
    clipboard.set_text(text, -1)
    clipboard.store()  # hand off to a clipboard manager if one is running
    events = {"n": 0}

    def on_owner_change(*_):
        events["n"] += 1
        if events["n"] > 1:  # first event is our own set_text
            Gtk.main_quit()

    clipboard.connect("owner-change", on_owner_change)
    GLib.timeout_add_seconds(6 * 3600, Gtk.main_quit)
    Gtk.main()


def main():
    style = sys.argv[1] if len(sys.argv) > 1 else "fix"

    # Ignore repeated hotkey presses while a request is in flight.
    lock = open(f"/tmp/klippo-{os.getuid()}.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        notify("Already working on it…")
        return

    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    text = clipboard.wait_for_text()
    if not text or not text.strip():
        notify("Clipboard is empty: copy some text first.")
        return
    if len(text) > MAX_CHARS:
        notify(f"Text too long ({len(text)} chars, max {MAX_CHARS}).")
        return

    notify("Correcting…", timeout_ms=0)
    try:
        fixed = run_llm(text, style)
    except Exception as e:
        notify(f"Failed: {e}\nIs the server running?  systemctl --user status klippo-llm",
               summary="Klippo error", timeout_ms=8000)
        return
    if not fixed:
        notify("Model returned nothing; clipboard unchanged.")
        return

    notify(fixed, summary="✓ Corrected: press Ctrl+V")
    fcntl.flock(lock, fcntl.LOCK_UN)  # done with the model; allow a new run
    serve_clipboard(clipboard, fixed)


if __name__ == "__main__":
    main()
