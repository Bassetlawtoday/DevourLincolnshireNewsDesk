import customtkinter as ctk
import threading
import time

from services.roadworks_engine import run_weekly_download
from modules.roadworks_report import open_roadworks_report


class RoadworksWindow:
    def __init__(self):
        self.window = ctk.CTkToplevel()
        self.window.title("Roadworks and Travel Intelligence")
        self.window.geometry("900x840")
        self.window.resizable(False, False)

        self.running = False
        self.started_at = None
        self.report_data = None

        self.build()

    def build(self):
        title = ctk.CTkLabel(
            self.window,
            text="🚧 Roadworks and Travel Intelligence",
            font=("Arial", 30, "bold"),
        )
        title.pack(pady=(18, 12))

        stats = ctk.CTkFrame(self.window)
        stats.pack(fill="x", padx=20)

        self.status = ctk.CTkLabel(
            stats,
            text="Status : Ready",
            font=("Arial", 18, "bold"),
        )
        self.status.pack(anchor="w", padx=20, pady=(12, 5))

        self.current_item = ctk.CTkLabel(
            stats,
            text="Current Record : Waiting",
            font=("Arial", 16),
        )
        self.current_item.pack(anchor="w", padx=20, pady=5)

        self.elapsed = ctk.CTkLabel(
            stats,
            text="Elapsed Time : 00:00",
            font=("Arial", 16),
        )
        self.elapsed.pack(anchor="w", padx=20, pady=5)

        self.last_run = ctk.CTkLabel(
            stats,
            text="Last Download : Never",
            font=("Arial", 16),
        )
        self.last_run.pack(anchor="w", padx=20, pady=5)

        self.downloaded = ctk.CTkLabel(
            stats,
            text="Records Downloaded : 0",
            font=("Arial", 16),
        )
        self.downloaded.pack(anchor="w", padx=20, pady=5)

        self.newsworthiness = ctk.CTkLabel(
            stats,
            text="Newsworthy Stories : 0",
            font=("Arial", 16),
        )
        self.newsworthiness.pack(anchor="w", padx=20, pady=(5, 12))

        progress_frame = ctk.CTkFrame(self.window)
        progress_frame.pack(fill="x", padx=20, pady=(16, 8))

        progress_header = ctk.CTkFrame(progress_frame, fg_color="transparent")
        progress_header.pack(fill="x", padx=18, pady=(12, 4))

        self.progress_stage = ctk.CTkLabel(
            progress_header,
            text="Overall Progress",
            font=("Arial", 15, "bold"),
        )
        self.progress_stage.pack(side="left")

        self.progress_percent = ctk.CTkLabel(
            progress_header,
            text="0%",
            font=("Arial", 15, "bold"),
        )
        self.progress_percent.pack(side="right")

        self.progress = ctk.CTkProgressBar(progress_frame, width=800)
        self.progress.pack(padx=18, pady=(4, 10))
        self.progress.set(0)

        self.list_progress_label = ctk.CTkLabel(
            progress_frame,
            text="Current List Progress : Waiting",
            font=("Arial", 14),
        )
        self.list_progress_label.pack(anchor="w", padx=18, pady=(2, 4))

        self.list_progress = ctk.CTkProgressBar(progress_frame, width=800)
        self.list_progress.pack(padx=18, pady=(4, 14))
        self.list_progress.set(0)

        button_frame = ctk.CTkFrame(self.window, fg_color="transparent")
        button_frame.pack(pady=10)

        self.download_button = ctk.CTkButton(
            button_frame,
            text="📥 Download Roadworks and Travel Data",
            width=390,
            height=50,
            command=self.download,
        )
        self.download_button.pack(side="left", padx=6)

        self.report_button = ctk.CTkButton(
            button_frame,
            text="📰 Open Editor's Briefing",
            width=260,
            height=50,
            state="disabled",
            command=self.open_report,
        )
        self.report_button.pack(side="left", padx=6)

        self.log = ctk.CTkTextbox(self.window, width=820, height=270)
        self.log.pack(pady=(10, 18))

        self.write_log("Roadworks and Travel Intelligence Ready.")

    def write_log(self, message):
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.window.update_idletasks()

    def set_status(self, message):
        self.status.configure(text=f"Status : {message}")
        self.window.update_idletasks()

    def set_current_application(self, message):
        self.current_item.configure(text=f"Current Record : {message}")
        self.window.update_idletasks()

    def set_progress(self, value, stage=None):
        safe_value = max(0.0, min(1.0, value))
        self.progress.set(safe_value)
        self.progress_percent.configure(text=f"{round(safe_value * 100)}%")

        if stage:
            self.progress_stage.configure(text=stage)

        self.window.update_idletasks()

    def set_list_progress(self, list_name, counter, total):
        if total > 0:
            value = counter / total
            text = f"{list_name} : {counter} of {total}"
        else:
            value = 0
            text = f"{list_name} : No records found"

        self.list_progress.set(value)
        self.list_progress_label.configure(
            text=f"Current List Progress : {text}"
        )
        self.window.update_idletasks()

    def set_report_data(self, report_data):
        self.report_data = report_data
        self.report_button.configure(state="normal")
        self.window.update_idletasks()

    def open_report(self):
        if not self.report_data:
            return

        open_roadworks_report(self.window, self.report_data)

    def reset_display(self):
        self.report_data = None
        self.report_button.configure(state="disabled")
        self.set_progress(0, "Overall Progress")
        self.list_progress.set(0)
        self.list_progress_label.configure(
            text="Current List Progress : Preparing..."
        )
        self.set_current_application("Connecting...")
        self.elapsed.configure(text="Elapsed Time : 00:00")
        self.downloaded.configure(text="Records Downloaded : 0")
        self.newsworthiness.configure(text="Newsworthy Stories : 0")

    def format_elapsed(self, seconds):
        total_seconds = max(0, int(seconds))
        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)

        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        return f"{minutes:02d}:{seconds:02d}"

    def update_elapsed_clock(self):
        if not self.running or self.started_at is None:
            return

        elapsed_seconds = time.monotonic() - self.started_at
        self.elapsed.configure(
            text=f"Elapsed Time : {self.format_elapsed(elapsed_seconds)}"
        )
        self.window.after(1000, self.update_elapsed_clock)

    def download(self):
        if self.running:
            return

        self.running = True
        self.started_at = time.monotonic()

        self.download_button.configure(
            state="disabled",
            text="Roadworks Download Running...",
        )

        self.reset_display()
        self.set_status("Connecting...")
        self.last_run.configure(text="Last Download : Running")
        self.update_elapsed_clock()

        thread = threading.Thread(target=self.start_download, daemon=True)
        thread.start()

    def start_download(self):
        self.write_log("")
        self.write_log("Connecting to roadworks and travel sources...")

        try:
            total = run_weekly_download(self)

        except Exception as error:
            import traceback

            self.running = False
            elapsed_text = self.format_elapsed(
                time.monotonic() - self.started_at
            )

            self.set_progress(0, "Download Failed")
            self.set_status("Failed")
            self.set_current_application("Stopped")
            self.last_run.configure(
                text=f"Last Download : Failed after {elapsed_text}"
            )
            self.write_log("")
            self.write_log(
                "Roadworks and Travel Intelligence stopped because of an error:"
            )
            self.write_log(str(error))
            self.write_log(
                "See the VS Code terminal for full technical details."
            )
            self.download_button.configure(
                state="normal",
                text="📥 Download Roadworks and Travel Data",
            )
            traceback.print_exc()
            return

        self.running = False
        elapsed_text = self.format_elapsed(
            time.monotonic() - self.started_at
        )

        self.set_progress(1, "Download Complete")
        self.set_status("Complete")
        self.set_current_application("Finished")
        self.downloaded.configure(
            text=f"Records Downloaded : {total}"
        )
        self.elapsed.configure(text=f"Elapsed Time : {elapsed_text}")
        self.last_run.configure(
            text=f"Last Download : Complete in {elapsed_text}"
        )
        self.download_button.configure(
            state="normal",
            text="📥 Download Roadworks and Travel Data",
        )
        self.write_log(f"Download complete in {elapsed_text}.")

        if self.report_data:
            self.window.after(250, self.open_report)


def open_roadworks():
    RoadworksWindow()


