"""NEXVARY Voice Windows/Linux Studio — Tkinter UI for real live and video engines.

Run: python -m voice_engine.desktop_gui. Optional audio and model dependencies
must be installed separately. All long-running work runs in a child process.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path


def main() -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from tkinter.scrolledtext import ScrolledText

    bg, panel, silver, gold, teal, muted = (
        "#0B1322", "#17263D", "#E8EDF6", "#E6BE76", "#4EE0C4", "#9AACBF"
    )
    root = tk.Tk()
    root.title("NEXVARY Voice Studio • Windows")
    root.geometry("920x715")
    root.minsize(720, 570)
    root.configure(bg=bg)
    root.option_add("*Font", "Segoe UI 11")
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    style.configure("TNotebook", background=bg, borderwidth=0)
    style.configure("TNotebook.Tab", background=panel, foreground=silver, padding=(18, 13))
    style.map("TNotebook.Tab", background=[("selected", "#2D4260")])
    style.configure("TFrame", background=bg)
    style.configure("TLabel", background=bg, foreground=silver)
    style.configure("TEntry", fieldbackground=panel, foreground=silver)
    style.configure("TButton", padding=(9, 8))
    style.configure("TCombobox", fieldbackground=panel)
    processes: dict[str, subprocess.Popen] = {}
    log_queue = __import__("queue").Queue()

    tk.Label(root, text="◉  NEXVARY VOICE", font=("Segoe UI", 24, "bold"),
             bg=bg, fg=gold, anchor="w").pack(fill="x", padx=24, pady=(18, 4))
    tk.Label(root, text="VOICE INTERPRETER  •  LIVE COMMENTARY  •  VIDEO DUBBING",
             bg=bg, fg=teal, anchor="w").pack(fill="x", padx=24, pady=(0, 14))

    tabs = ttk.Notebook(root)
    tabs.pack(fill="both", expand=True, padx=22, pady=8)
    live_tab, dub_tab = ttk.Frame(tabs), ttk.Frame(tabs)
    tabs.add(live_tab, text="الترجمة الصوتية المباشرة")
    tabs.add(dub_tab, text="دبلجة الفيديو")

    def row(parent, label, value="", secret=False):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", padx=14, pady=7)
        ttk.Label(frame, text=label, width=24, anchor="e").pack(side="left", padx=8)
        variable = tk.StringVar(value=value)
        entry = ttk.Entry(frame, textvariable=variable, show="●" if secret else "")
        entry.pack(side="left", fill="x", expand=True)
        return variable

    def combo(parent, label, values, default):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", padx=14, pady=7)
        ttk.Label(frame, text=label, width=24, anchor="e").pack(side="left", padx=8)
        variable = tk.StringVar(value=default)
        field = ttk.Combobox(frame, textvariable=variable, values=values, state="readonly")
        field.pack(side="left", fill="x", expand=True)
        return variable

    names = ["ar", "en", "hi", "tr", "fr", "de", "es", "it"]
    host = row(live_tab, "رابط بث صوت WebSocket", "wss://your-domain/v1/live/audio")
    token = row(live_tab, "رمز المصادقة", secret=True)
    live_from = combo(live_tab, "لغة المتحدث", names, "hi")
    live_to = combo(live_tab, "لغة المستمع", names, "ar")
    ttk.Label(live_tab, text="يلزم الخادم مجهزًا بنماذج Whisper + Argos + Piper، وسماعات لمنع الصدى.",
              foreground=muted).pack(fill="x", padx=18, pady=10)
    ttk.Label(live_tab, text="الصوت يخرج إلى جهاز الصوت المحدد في Windows؛ يمكن التقاطه في OBS إذا سمح النظام بذلك.",
              foreground=muted).pack(fill="x", padx=18)

    video = row(dub_tab, "الفيديو الأصلي (MP4)")
    output = row(dub_tab, "الفيديو المترجم الجديد")
    dub_from = combo(dub_tab, "اللغة الأصلية", names, "ar")
    dub_to = combo(dub_tab, "لغة الدبلجة", names, "en")
    whisper = row(dub_tab, "نموذج Whisper المحلي", "small")
    piper = row(dub_tab, "نموذج صوت Piper (ONNX)")
    voice = row(dub_tab, "الصوت السحابي (اختياري)", "en-US-JennyNeural")
    cloud = tk.BooleanVar(value=False)
    ttk.Checkbutton(dub_tab, text="أوافق على إرسال نصوص الدبلجة لخدمة TTS سحابية",
                    variable=cloud).pack(anchor="w", padx=22, pady=7)

    def choose_video():
        chosen = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mov *.mkv"), ("All", "*.*")])
        if chosen:
            video.set(chosen)
            output.set(str(Path(chosen).with_name(Path(chosen).stem + "-dubbed.mp4")))

    def choose_model():
        chosen = filedialog.askopenfilename(filetypes=[("Piper voice", "*.onnx"), ("All", "*.*")])
        if chosen: piper.set(chosen)

    ttk.Button(dub_tab, text="اختر فيديو", command=choose_video).pack(anchor="w", padx=24, pady=4)
    ttk.Button(dub_tab, text="اختر نموذج الصوت", command=choose_model).pack(anchor="w", padx=24, pady=4)

    def launch(name, argv, env=None):
        if name in processes and processes[name].poll() is None:
            messagebox.showwarning("NEXVARY", "هذه المهمة تعمل بالفعل.")
            return
        try:
            process = subprocess.Popen(
                [sys.executable, "-m"] + argv,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                env=env, bufsize=1
            )
        except OSError as exc:
            messagebox.showerror("NEXVARY", str(exc))
            return
        processes[name] = process

        def read_output():
            for line in process.stdout:
                log_queue.put(name + ": " + line.rstrip())
            code = process.wait()
            log_queue.put(name + ": " + ("نجاح" if code == 0 else f"انتهى بخطأ {code}"))
        threading.Thread(target=read_output, daemon=True).start()

    def start_live():
        if live_from.get() == live_to.get():
            messagebox.showerror("NEXVARY", "اختر لغتين مختلفتين")
            return
        if not host.get().startswith("wss://") and not host.get().startswith("ws://127.0.0.1:"):
            messagebox.showerror("NEXVARY", "استخدم رابط wss:// آمنًا")
            return
        args = ["voice_engine.live_client", "--url", host.get(),
                "--source", live_from.get(), "--target", live_to.get()]
        if host.get().startswith("ws://"):
            args.append("--allow-insecure-localhost")
        env = os.environ.copy()
        env["NEXVARY_API_TOKEN"] = token.get()
        launch("LIVE", args, env)

    def start_dub():
        if dub_from.get() == dub_to.get():
            messagebox.showerror("NEXVARY", "اختر لغتين مختلفتين")
            return
        if not Path(video.get()).is_file():
            messagebox.showerror("NEXVARY", "اختر ملف فيديو موجودًا")
            return
        if not output.get():
            messagebox.showerror("NEXVARY", "اختر اسمًا لملف الإخراج")
            return
        if Path(output.get()).exists():
            messagebox.showerror("NEXVARY", "ملف الإخراج موجود؛ اختر اسمًا جديدًا")
            return
        argv = ["voice_engine.dubbing", video.get(), output.get(),
                "--source", dub_from.get(), "--target", dub_to.get(),
                "--whisper-model", whisper.get()]
        if cloud.get():
            argv += ["--tts", "edge", "--allow-cloud-tts", "--voice", voice.get()]
        else:
            if not Path(piper.get()).is_file():
                messagebox.showerror("NEXVARY", "اختر ملف صوت Piper المحلي .onnx")
                return
            argv += ["--tts", "piper", "--piper-model", piper.get()]
        launch("DUB", argv)

    def stop(name):
        proc = processes.get(name)
        if proc and proc.poll() is None:
            proc.terminate()
            log_queue.put(name + ": جاري الإيقاف")

    frame = ttk.Frame(live_tab)
    frame.pack(padx=14, pady=18, anchor="w")
    ttk.Button(frame, text="ابدأ الترجمة الصوتية", command=start_live).pack(side="left", padx=6)
    ttk.Button(frame, text="إيقاف", command=lambda: stop("LIVE")).pack(side="left", padx=6)
    frame = ttk.Frame(dub_tab)
    frame.pack(padx=14, pady=12, anchor="w")
    ttk.Button(frame, text="ابدأ دبلجة MP4", command=start_dub).pack(side="left", padx=6)
    ttk.Button(frame, text="إيقاف", command=lambda: stop("DUB")).pack(side="left", padx=6)

    ttk.Label(root, text="سجل العمليات", foreground=gold).pack(anchor="w", padx=24)
    logs = ScrolledText(root, height=8, bg=panel, fg=silver, insertbackground=silver,
                        font=("Consolas", 10), relief="flat")
    logs.pack(fill="x", padx=24, pady=(6, 22))

    def poll_logs():
        try:
            while True:
                logs.insert("end", log_queue.get_nowait() + "\n")
                logs.see("end")
        except __import__("queue").Empty:
            pass
        root.after(150, poll_logs)

    def on_close():
        for item in processes.values():
            if item.poll() is None:
                item.terminate()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    poll_logs()
    root.mainloop()


if __name__ == "__main__":
    main()
