"""Native desktop app for agentcli — a real Tkinter window over the same Agent
engine. Zero extra deps (Tkinter ships with Python).

Threading model (the correct Tk pattern):
  • Tk mainloop owns the main thread and all widget access.
  • The agent runs on a worker thread; it pushes events into a queue.
  • The UI drains that queue on a periodic `after()` tick — so widgets are only
    ever touched from the main thread.
  • Approvals: the worker blocks on a queue the UI fills when you click a button.
"""
from __future__ import annotations

import queue
import threading

# palette (matches the CLI's violet/cyan theme)
BG = "#0e0f13"; PANEL = "#16181f"; PANEL2 = "#1c1f28"; LINE = "#2a2e3a"
TEXT = "#e6e8ee"; MUTE = "#8a90a0"; FAINT = "#5a5f70"
ACCENT = "#a78bfa"; CYAN = "#60cdff"; MINT = "#86efac"; AMBER = "#facc15"; RED = "#f87171"
MONO = ("SF Mono", "Menlo", "Consolas", "monospace")


def launch(ctx, state_fn, slash_fn) -> int:
    import tkinter as tk
    from tkinter import font as tkfont

    app = _App(ctx, state_fn, slash_fn)
    app.run()
    return 0


class _App:
    def __init__(self, ctx, state_fn, slash_fn):
        import tkinter as tk
        self.ctx = ctx
        self.agent = ctx.agent
        self.state_fn = state_fn
        self.slash_fn = slash_fn
        self.events: queue.Queue = queue.Queue()
        self._approval: queue.Queue = queue.Queue()
        self._cur_tool = None            # (start_index) of the tool line being run
        self._streaming = False

        # route the agent's events + approvals into our queues (thread-safe)
        self.agent.on_event = lambda k, p: self.events.put((k, p))
        self.agent.approver = self._approver

        self.tk = tk
        self.root = tk.Tk()
        self.root.title("agentcli")
        self.root.configure(bg=BG)
        self.root.geometry("920x680")
        self._build()
        self.root.after(50, self._drain)
        self._refresh_status()

    # ---- UI construction ------------------------------------------------
    def _build(self):
        tk = self.tk
        # top bar
        top = tk.Frame(self.root, bg=PANEL, height=44)
        top.pack(fill="x", side="top")
        tk.Label(top, text="◈ agentcli", bg=PANEL, fg=ACCENT,
                 font=("Helvetica", 15, "bold")).pack(side="left", padx=14, pady=8)
        tk.Label(top, text="beta", bg=AMBER, fg="#1a1a1a",
                 font=("Helvetica", 8, "bold")).pack(side="left", pady=12)
        self.status = tk.Label(top, text="", bg=PANEL, fg=MUTE,
                               font=("Helvetica", 11))
        self.status.pack(side="right", padx=14)

        # chat transcript
        chat_frame = tk.Frame(self.root, bg=BG)
        chat_frame.pack(fill="both", expand=True)
        self.chat = tk.Text(chat_frame, bg=BG, fg=TEXT, wrap="word", bd=0,
                            font=("Helvetica", 13), padx=16, pady=12,
                            insertbackground=TEXT, state="disabled",
                            spacing1=2, spacing3=6)
        sb = tk.Scrollbar(chat_frame, command=self.chat.yview, bg=PANEL)
        self.chat.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.chat.pack(side="left", fill="both", expand=True)
        self._init_tags()

        # controls rail (buttons -> slash commands)
        rail = tk.Frame(self.root, bg=PANEL)
        rail.pack(fill="x")
        for label, cmd in [("Status", "/status"), ("Model…", "__model"),
                           ("Mode…", "__mode"), ("Plan", "/plan on"),
                           ("Reasoning…", "__reasoning"), ("Audit", "/audit"),
                           ("Sandbox…", "__sandbox")]:
            b = tk.Button(rail, text=label, bg=PANEL2, fg=TEXT, bd=0,
                          activebackground=LINE, activeforeground=TEXT,
                          font=("Helvetica", 10), padx=10, pady=3,
                          command=lambda c=cmd: self._chip(c))
            b.pack(side="left", padx=3, pady=6)

        # composer
        comp = tk.Frame(self.root, bg=PANEL)
        comp.pack(fill="x", side="bottom")
        self.input = tk.Text(comp, height=2, bg=PANEL2, fg=TEXT, bd=0,
                             font=("Helvetica", 13), wrap="word", padx=12, pady=10,
                             insertbackground=ACCENT)
        self.input.pack(side="left", fill="both", expand=True, padx=(12, 6), pady=10)
        self.input.bind("<Return>", self._on_return)
        self.input.bind("<Shift-Return>", lambda e: None)
        self.send_btn = tk.Button(comp, text="Send", bg=ACCENT, fg="#12121a", bd=0,
                                  font=("Helvetica", 12, "bold"), padx=18,
                                  activebackground=CYAN, command=self._send)
        self.send_btn.pack(side="right", padx=(0, 12), pady=10)
        self.input.focus_set()

    def _init_tags(self):
        c = self.chat
        c.tag_configure("role", foreground=FAINT, font=("Helvetica", 9),
                        spacing1=8)
        c.tag_configure("user", foreground=TEXT, background=PANEL2,
                        font=("Helvetica", 13), lmargin1=8, lmargin2=8,
                        rmargin=8, spacing1=4, spacing3=4)
        c.tag_configure("bot", foreground=TEXT, font=("Helvetica", 13))
        c.tag_configure("tool", foreground=AMBER, font=MONO + (11,))
        c.tag_configure("tool_ok", foreground=MINT, font=MONO + (10,))
        c.tag_configure("tool_err", foreground=RED, font=MONO + (10,))
        c.tag_configure("code", foreground=CYAN, background="#12141b",
                        font=MONO + (12,))
        c.tag_configure("retry", foreground=FAINT, font=("Helvetica", 10, "italic"))
        c.tag_configure("security", foreground=AMBER, font=("Helvetica", 11))
        c.tag_configure("error", foreground=RED, font=("Helvetica", 11))
        c.tag_configure("bold", font=("Helvetica", 13, "bold"))

    # ---- writing to the transcript --------------------------------------
    def _w(self, text, *tags):
        self.chat.configure(state="normal")
        self.chat.insert("end", text, tags)
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def _line(self, text, *tags):
        self._w(text + "\n", *tags)

    def _md(self, text):
        """Very light markdown -> tagged inserts (bold, `code`, fenced code)."""
        import re
        self.chat.configure(state="normal")
        i = 0
        for m in re.finditer(r"\*\*(.+?)\*\*|`([^`]+)`", text):
            self.chat.insert("end", text[i:m.start()], "bot")
            if m.group(1):
                self.chat.insert("end", m.group(1), "bold")
            else:
                self.chat.insert("end", " " + m.group(2) + " ", "code")
            i = m.end()
        self.chat.insert("end", text[i:] + "\n\n", "bot")
        self.chat.configure(state="disabled")
        self.chat.see("end")

    # ---- event pump (main thread) ---------------------------------------
    def _drain(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                self._handle(kind, payload)
        except queue.Empty:
            pass
        self.root.after(50, self._drain)

    def _handle(self, kind, payload):
        if kind == "thinking":
            return
        if kind == "delta":
            if not self._streaming:
                self._w("◆ ", "role"); self._streaming = True
            self._w(payload, "bot")
        elif kind == "preamble":
            self._w("◆ ", "role"); self._md(payload)
        elif kind == "tool_call":
            from . import ui
            if isinstance(payload, tuple):
                g, _c, summary = ui.format_action(payload[0], payload[1])
            else:
                g, summary = "▸", str(payload)
            self._line(f"  {g} {summary}", "tool")
        elif kind == "tool_result":
            err = payload.strip()[:1] == "[" or payload.lower().startswith(
                ("error", "denied", "not found", "no such"))
            head = payload.splitlines()[0][:80] if payload else "(no output)"
            self._line(f"    {'✗' if err else '✓'} {head}",
                       "tool_err" if err else "tool_ok")
        elif kind == "reply":
            if self._streaming:
                self._w("\n\n", "bot"); self._streaming = False
            else:
                self._w("◆ ", "role"); self._md(payload)
        elif kind == "retry":
            self._line("  ↻ " + str(payload), "retry")
        elif kind in ("security", "monitor", "denied"):
            self._line("  ⚠ " + str(payload), "security")
        elif kind in ("intent", "locked", "error"):
            self._line("  ✗ " + str(payload), "error")
        elif kind == "reply_done":
            self._streaming = False
            self.send_btn.configure(state="normal")
            self._refresh_status()

    # ---- sending --------------------------------------------------------
    def _on_return(self, event):
        if event.state & 0x1:              # shift held -> newline
            return
        self._send()
        return "break"

    def _send(self):
        text = self.input.get("1.0", "end").strip()
        if not text:
            return
        self.input.delete("1.0", "end")
        if text.startswith("/"):
            self._run_command(text)
            return
        self._w("\nyou\n", "role"); self._line(text, "user")
        self.send_btn.configure(state="disabled")

        def run():
            try:
                from . import images, redact, render
                t, imgs = images.extract(text)
                clean, hidden = redact.redact(t)
                if hidden:
                    self.events.put(("security", f"hid {len(hidden)} secret(s)"))
                out = self.agent.send(clean, images=imgs)
                self.events.put(("reply", render.render(out)
                                 if self.ctx.args.render else out))
            except Exception as e:
                self.events.put(("error", str(e)))
            finally:
                self.events.put(("reply_done", ""))
        threading.Thread(target=run, daemon=True).start()

    # ---- slash commands + chips -----------------------------------------
    def _run_command(self, cmd):
        import contextlib
        import io
        import re
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            try:
                self.slash_fn(cmd, self.ctx)
            except Exception as e:
                self._line("  ✗ " + str(e), "error"); return
        out = re.sub(r"\x1b\[[0-9;]*m", "", buf.getvalue()).strip()
        if out:
            self._line(out, "retry")
        self._refresh_status()

    def _chip(self, cmd):
        if cmd.startswith("__"):
            self._prompt_pick(cmd[2:])
        else:
            self._run_command(cmd)

    def _prompt_pick(self, kind):
        """Simple popup pickers for model/mode/reasoning/sandbox."""
        tk = self.tk
        opts = {
            "mode": ["read-only", "approve", "auto"],
            "reasoning": ["brief", "balanced", "thorough"],
            "sandbox": ["off", "workspace", "strict"],
        }
        if kind == "model":
            self._ask_text("Switch model to:", lambda v: self._run_command(f"/model {v}"))
            return
        win = tk.Toplevel(self.root); win.title(kind); win.configure(bg=PANEL)
        win.geometry("260x180")
        tk.Label(win, text=f"Select {kind}:", bg=PANEL, fg=TEXT,
                 font=("Helvetica", 12)).pack(pady=10)
        for o in opts.get(kind, []):
            tk.Button(win, text=o, bg=PANEL2, fg=TEXT, bd=0, width=20, pady=4,
                      activebackground=ACCENT,
                      command=lambda v=o: (self._run_command(f"/{kind} {v}"),
                                           win.destroy())).pack(pady=2)

    def _ask_text(self, prompt, cb):
        tk = self.tk
        win = tk.Toplevel(self.root); win.title(prompt); win.configure(bg=PANEL)
        win.geometry("360x120")
        tk.Label(win, text=prompt, bg=PANEL, fg=TEXT).pack(pady=8)
        ent = tk.Entry(win, bg=PANEL2, fg=TEXT, insertbackground=TEXT, width=36)
        ent.pack(pady=4); ent.focus_set()
        tk.Button(win, text="OK", bg=ACCENT, fg="#12121a", bd=0,
                  command=lambda: (cb(ent.get().strip()), win.destroy())).pack(pady=6)
        ent.bind("<Return>", lambda e: (cb(ent.get().strip()), win.destroy()))

    # ---- approvals (worker blocks until UI answers) ---------------------
    def _approver(self, tool, args, reason):
        self.events.put(("__approval__", (tool, args, reason)))
        return self._approval.get()        # blocks the worker thread

    def _show_approval(self, tool, args, reason):
        tk = self.tk
        win = tk.Toplevel(self.root); win.title("needs approval")
        win.configure(bg=PANEL); win.geometry("480x220")
        tk.Label(win, text="⚠ needs approval", bg=PANEL, fg=AMBER,
                 font=("Helvetica", 13, "bold")).pack(pady=10)
        detail = str(args.get("command") or args.get("path") or args)[:200]
        tk.Label(win, text=f"{tool}\n{detail}", bg=PANEL2, fg=TEXT, wraplength=440,
                 justify="left", font=MONO + (11,)).pack(padx=16, pady=8, fill="x")
        row = tk.Frame(win, bg=PANEL); row.pack(pady=10)
        for label, ans, col in [("Approve", "yes", MINT), ("Always", "always", CYAN),
                                ("Deny", "no", RED)]:
            tk.Button(row, text=label, bg=col, fg="#12121a", bd=0, padx=14, pady=4,
                      command=lambda a=ans: (self._approval.put(a), win.destroy())
                      ).pack(side="left", padx=5)
        win.protocol("WM_DELETE_WINDOW", lambda: (self._approval.put("no"), win.destroy()))

    # ---- status ---------------------------------------------------------
    def _refresh_status(self):
        try:
            s = self.state_fn(self.ctx)
            self.status.configure(
                text=f"● {s['mode']}   {s['provider']}:{s['model']}   "
                     f"{s['tokens']} tok   {s['tools']} tools")
        except Exception:
            pass

    def run(self):
        # hook approval events (they can't open windows from the worker thread)
        orig = self._handle
        def handle(kind, payload):
            if kind == "__approval__":
                self._show_approval(*payload)
            else:
                orig(kind, payload)
        self._handle = handle
        self._line("Welcome to agentcli — type a message, or /help for commands.",
                   "retry")
        self.root.mainloop()
