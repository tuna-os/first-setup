# install_confirm.py
#
# Confirmation step for install mode.
# Auto-detects the image from podman storage.

import json
import os

from gi.repository import Gtk, GLib, Adw

_ = __builtins__["_"]

import tunaos_first_setup.core.backend as backend


@Gtk.Template(resource_path="/org/tunaos/FirstSetup/gtk/install-confirm.ui")
class VanillaInstallConfirm(Adw.Bin):
    __gtype_name__ = "VanillaInstallConfirm"

    device_label = Gtk.Template.Child()
    fs_label = Gtk.Template.Child()
    fde_label = Gtk.Template.Child()
    hostname_label = Gtk.Template.Child()
    image_label = Gtk.Template.Child()
    confirm_checkbox = Gtk.Template.Child()
    cancel_button = Gtk.Template.Child()

    def __init__(self, window, **kwargs):
        super().__init__(**kwargs)
        self.__window = window
        self.__confirm_checked = False
        self.__image_ref = self.__detect_image()
        self.__target_imgref = self.__detect_target_imgref()

        try:
            self.confirm_checkbox.connect("toggled", self.__on_input_changed)
            self.cancel_button.connect("clicked", self.__on_cancel_clicked)
        except Exception:
            pass
        # Find the confirmation row by walking up from the checkbox
        try:
            self.__confirm_row = self.confirm_checkbox.get_parent()
            self.__confirm_row.add_css_class("warning")
        except Exception:
            self.__confirm_row = None

    def __detect_image(self):
        """Return the containers-storage ref to install from.

        Scans podman storage for a tuna-os/ image visible via unified storage
        (bootc images are directly accessible in podman's container storage).
        """
        import subprocess
        import json as _json
        try:
            result = subprocess.run(
                ["podman", "images", "--format", "json"],
                capture_output=True, text=True
            )
            images = _json.loads(result.stdout)
            for img in images:
                for tag in (img.get("Names") or img.get("RepoTags") or []):
                    if "tuna-os/" in tag and "localhost/" not in tag:
                        return f"containers-storage:{tag}"
        except Exception:
            pass
        return None

    def __detect_target_imgref(self):
        """Return the upstream ref for --target-imgref (no transport prefix).

        Since the image is already in podman storage as its upstream ref
        (e.g. ghcr.io/tuna-os/yellowfin:gnome-hwe), strip containers-storage:
        to get the bare ref bootc expects for update tracking.
        """
        if self.__image_ref and "localhost/" not in self.__image_ref:
            return self.__image_ref.replace("containers-storage:", "", 1)
        return None

    def set_page_active(self):
        hostname = getattr(self.__window, 'install_hostname', '')
        try:
            self.hostname_label.set_label(hostname or _('(not set)'))
        except Exception:
            pass
        device = getattr(self.__window, "install_target_device", None)
        fs = getattr(self.__window, "install_target_fs", None)
        fde_enabled = getattr(self.__window, "install_fde_enabled", False)

        if getattr(self, 'device_label', None) is not None:
            self.device_label.set_text(device if device else _("<no device selected>"))
        if getattr(self, 'fs_label', None) is not None:
            self.fs_label.set_text(fs if fs else _("<none>"))
        if getattr(self, 'fde_label', None) is not None:
            if fde_enabled:
                tpm_enabled = getattr(self.__window, "install_tpm_enabled", False)
                if tpm_enabled:
                    self.fde_label.set_text(_("Enabled (TPM auto-unlock)"))
                else:
                    self.fde_label.set_text(_("Enabled"))
            else:
                self.fde_label.set_text(_("Disabled"))

        # Show detected image
        if getattr(self, 'image_label', None) is not None:
            if self.__image_ref:
                # Display a friendly version of the ref
                display = self.__image_ref.replace("containers-storage:", "")
                self.image_label.set_text(display)
            else:
                self.image_label.set_text(_("Auto-detected"))

        try:
            self.confirm_checkbox.set_active(False)
            if self.__confirm_row: self.__confirm_row.add_css_class("warning")
        except Exception:
            pass
        self.__confirm_checked = False
        self.__window.set_ready(False)

    def set_page_inactive(self):
        return

    def __on_input_changed(self, *args):
        try:
            self.__confirm_checked = self.confirm_checkbox.get_active()
        except Exception:
            self.__confirm_checked = False
        # Apply/remove warning highlight based on checkbox state
        try:
            if self.__confirm_checked:
                if self.__confirm_row: self.__confirm_row.remove_css_class("warning")
            else:
                if self.__confirm_row: self.__confirm_row.add_css_class("warning")
        except Exception:
            pass
        self.__validate()

    def __validate(self):
        ok = self.__confirm_checked and self.__image_ref is not None
        self.__window.set_ready(ok)

    def finish(self):
        device = getattr(self.__window, "install_target_device", None)
        fs = getattr(self.__window, "install_target_fs", None)

        if not device or not fs or not self.__image_ref:
            return False

        self.__window.install_target_image = self.__image_ref
        self.__window.install_target_imgref = self.__target_imgref
        self.__window.install_root_password = None
        return True

    def __on_cancel_clicked(self, *args):
        app = self.__window.get_application()
        if app:
            app.quit()
