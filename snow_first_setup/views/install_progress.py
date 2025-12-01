# install_progress.py

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
        if not self.__finished:
            try:
                self.progress_bar.pulse()
            except Exception as e:
                print("[DEBUG] pulse failed:", e)
            return True
        return False

    def __start_install_thread(self):
        print("[DEBUG] Starting install thread")
        thread = threading.Thread(target=self.__run_install, daemon=True)
        thread.start()

    def __run_install(self):
        device = getattr(self.__window, "install_target_device", None)
        fs = getattr(self.__window, "install_target_fs", None)
        image = getattr(self.__window, "install_target_image", None)
        fde_enabled = getattr(self.__window, "install_fde_enabled", False)
        print("[DEBUG] __run_install params:", device, fs, image, "fde_enabled:", fde_enabled)

        if not device or not fs or not image:
            GLib.idle_add(self.__mark_finished, False, _("Missing installation parameters."))
            return

        GLib.idle_add(self.detail_label.set_text, _("Writing image to disk…"))

        # Build script arguments with FDE parameters
        script_args = [image, fs, device, "true" if fde_enabled else "false"]

        success = backend.run_script("install-to-disk", script_args, root=True)

        if success and "snowfield" in image:
            print("[DEBUG] __run_install: Snowfield image selected, importing Surface Linux secure boot key")
            backend.run_script("enroll-key", ["/usr/share/linux-surface-secureboot/surface.cer"], root=True)

        GLib.idle_add(self.__mark_finished, success, _("Installation complete." if success else _("Installation failed.")))

    def __mark_finished(self, success: bool, message: str):
        print("[DEBUG] __mark_finished called; success=", success, "message=", message)
        self.__finished = True
        self.__success = success
        try:
            self.detail_label.set_text(message)
        except Exception as e:
            print("[DEBUG] Failed to set finish message:", e)
        self.__window.set_ready(success)
        if success:
            self.__window.set_focus_on_next()
        return False
