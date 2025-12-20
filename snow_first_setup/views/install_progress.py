# install_progress.py

import json
import threading
import time

from gi.repository import Gtk, Adw, GLib, Gio

_ = __builtins__["_"]

import snow_first_setup.core.backend as backend

@Gtk.Template(resource_path="/org/frostyard/FirstSetup/gtk/install-progress.ui")
class VanillaInstallProgress(Adw.Bin):
    __gtype_name__ = "VanillaInstallProgress"

    status_page = Gtk.Template.Child()
    progress_bar = Gtk.Template.Child()
    detail_label = Gtk.Template.Child()

    def __init__(self, window, **kwargs):
        super().__init__(**kwargs)
        self.__window = window
        self.__started = False
        self.__finished = False
        self.__success = False
        self.__current_step = 0
        self.__total_steps = 0
        self.__has_progress = False  # True when we have percentage-based progress

        # Debug: verify resource presence and child realization
        try:
            data = Gio.resources_lookup_data("/org/frostyard/FirstSetup/gtk/install-progress.ui", Gio.ResourceLookupFlags.NONE)
            print("[DEBUG] install-progress.ui resource size:", len(data.get_data()))
        except Exception as e:
            print("[DEBUG] Failed to lookup install-progress.ui resource:", e)
        print("[DEBUG] VanillaInstallProgress init: status_page=", bool(self.status_page), "progress_bar=", bool(self.progress_bar), "detail_label=", bool(self.detail_label))

    def set_page_active(self):
        print("[DEBUG] set_page_active called for VanillaInstallProgress; started=", self.__started)
        # Disable next until finished
        self.__window.set_ready(False)
        if not self.__started:
            self.__started = True
            try:
                self.detail_label.set_text(_("Starting installation…"))
            except Exception as e:
                print("[DEBUG] Failed setting initial detail label:", e)
            self.__start_install_thread()
            GLib.timeout_add(120, self.__pulse_progress)

    def set_page_inactive(self):
        return

    def finish(self):
        # Allow moving forward only when finished successfully
        print("[DEBUG] finish called; finished=", self.__finished, "success=", self.__success)
        return self.__finished and self.__success

    def __pulse_progress(self):
        # Only pulse if we don't have percentage-based progress
        if not self.__finished and not self.__has_progress:
            try:
                self.progress_bar.pulse()
            except Exception as e:
                print("[DEBUG] pulse failed:", e)
            return True
        return not self.__finished  # Keep running but don't pulse if we have percentage

    def __start_install_thread(self):
        print("[DEBUG] Starting install thread")
        thread = threading.Thread(target=self.__run_install, daemon=True)
        thread.start()

    def __handle_json_line(self, line: str):
        """Parse and handle a single JSON line from nbc install output."""
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            # Not valid JSON, just log it
            print(f"[DEBUG] Non-JSON output: {line}")
            return

        event_type = event.get("type", "")

        if event_type == "step":
            step = event.get("step", 0)
            total = event.get("total_steps", 0)
            step_name = event.get("step_name", "")
            self.__current_step = step
            self.__total_steps = total

            # Update progress bar based on steps if no percentage progress
            if total > 0 and not self.__has_progress:
                fraction = step / total
                GLib.idle_add(self.progress_bar.set_fraction, fraction)

            # Update detail label with step info
            detail_text = f"[{step}/{total}] {step_name}"
            GLib.idle_add(self.detail_label.set_text, detail_text)

        elif event_type == "progress":
            percent = event.get("percent", 0)
            message = event.get("message", "")
            self.__has_progress = True

            # Update progress bar with percentage
            fraction = percent / 100.0
            GLib.idle_add(self.progress_bar.set_fraction, fraction)

            # Update detail with progress message
            if message:
                if self.__total_steps > 0:
                    detail_text = f"[{self.__current_step}/{self.__total_steps}] {message} ({percent}%)"
                else:
                    detail_text = f"{message} ({percent}%)"
                GLib.idle_add(self.detail_label.set_text, detail_text)

        elif event_type == "message":
            message = event.get("message", "")
            if message:
                GLib.idle_add(self.detail_label.set_text, message)

        elif event_type == "warning":
            message = event.get("message", "")
            print(f"[WARNING] nbc: {message}")
            # Optionally show warning in UI
            if message:
                GLib.idle_add(self.detail_label.set_text, f"⚠ {message}")

        elif event_type == "error":
            message = event.get("message", "")
            details = event.get("details", {})
            error_detail = details.get("error", "")
            print(f"[ERROR] nbc: {message} - {error_detail}")
            error_text = message
            if error_detail:
                error_text = f"{message}: {error_detail}"
            GLib.idle_add(self.__mark_finished, False, error_text)

        elif event_type == "complete":
            message = event.get("message", _("Installation complete."))
            GLib.idle_add(self.progress_bar.set_fraction, 1.0)
            GLib.idle_add(self.__mark_finished, True, message)

    def __run_install(self):
        device = getattr(self.__window, "install_target_device", None)
        fs = getattr(self.__window, "install_target_fs", None)
        image = getattr(self.__window, "install_target_image", None)
        fde_enabled = getattr(self.__window, "install_fde_enabled", False)
        print("[DEBUG] __run_install params:", device, fs, image, "fde_enabled:", fde_enabled)

        if not device or not fs or not image:
            GLib.idle_add(self.__mark_finished, False, _("Missing installation parameters."))
            return

        GLib.idle_add(self.detail_label.set_text, _("Preparing installation…"))

        # Build script arguments with FDE parameters
        script_args = [image, fs, device, "true" if fde_enabled else "false"]

        # Use streaming script runner to get real-time JSON updates
        success = backend.run_script_streaming(
            "install-to-disk",
            script_args,
            root=True,
            line_callback=self.__handle_json_line
        )

        # Handle Snowfield image special case
        if success and "snowfield" in image:
            print("[DEBUG] __run_install: Snowfield image selected, importing Surface Linux secure boot key")
            backend.run_script("enroll-key", ["/usr/share/linux-surface-secureboot/surface.cer"], root=True)

        # If we didn't get a complete event but the process succeeded, mark as finished
        if not self.__finished:
            GLib.idle_add(self.__mark_finished, success, _("Installation complete." if success else _("Installation failed.")))

    def __mark_finished(self, success: bool, message: str):
        print("[DEBUG] __mark_finished called; success=", success, "message=", message)
        self.__finished = True
        self.__success = success
        try:
            self.detail_label.set_text(message)
            if success:
                self.progress_bar.set_fraction(1.0)
        except Exception as e:
            print("[DEBUG] Failed to set finish message:", e)
        self.__window.set_ready(success)
        if success:
            self.__window.set_focus_on_next()
        return False
