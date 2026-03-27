# install_confirm.py
#
# Confirmation step for install mode.
# Auto-detects the image from os-release / image-info.json.

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
    image_label = Gtk.Template.Child()
    confirm_row = Gtk.Template.Child()
    confirm_checkbox = Gtk.Template.Child()
    cancel_button = Gtk.Template.Child()

    def __init__(self, window, **kwargs):
        super().__init__(**kwargs)
        self.__window = window
        self.__confirm_checked = False
        self.__image_ref = self.__detect_image()

        try:
            self.confirm_checkbox.connect("toggled", self.__on_input_changed)
            self.cancel_button.connect("clicked", self.__on_cancel_clicked)
        except Exception:
            pass

    def __detect_image(self):
        """Auto-detect the container image reference for installation.

        Reads VARIANT_ID from os-release and image-flavor from image-info.json
        to construct the containers-storage ref.
        """
        variant_id = None
        image_flavor = None

        # Read VARIANT_ID from os-release
        for os_release_path in ["/usr/lib/os-release", "/etc/os-release"]:
            if os.path.exists(os_release_path):
                try:
                    with open(os_release_path, "r") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("VARIANT_ID="):
                                variant_id = line.split("=", 1)[1].strip().strip('"')
                                break
                except Exception:
                    continue
            if variant_id:
                break

        # Read image-flavor from image-info.json
        image_info_path = "/usr/share/ublue-os/image-info.json"
        if os.path.exists(image_info_path):
            try:
                with open(image_info_path, "r") as f:
                    info = json.load(f)
                image_flavor = info.get("image-flavor")
            except Exception:
                pass

        if variant_id and image_flavor:
            return f"containers-storage:localhost/{variant_id}:{image_flavor}"

        # Fallback: try to use image-ref from image-info.json
        if os.path.exists(image_info_path):
            try:
                with open(image_info_path, "r") as f:
                    info = json.load(f)
                image_ref = info.get("image-ref", "")
                image_tag = info.get("image-tag", "latest")
                if image_ref:
                    ref = image_ref.replace("ostree-image-signed:docker://", "")
                    ref = ref.replace("docker://", "")
                    return f"containers-storage:{ref}:{image_tag}"
            except Exception:
                pass

        return None

    def set_page_active(self):
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
                display = self.__image_ref.replace("containers-storage:localhost/", "")
                self.image_label.set_text(display)
            else:
                self.image_label.set_text(_("Auto-detected"))

        try:
            self.confirm_checkbox.set_active(False)
            self.confirm_row.add_css_class("warning")
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
                self.confirm_row.remove_css_class("warning")
            else:
                self.confirm_row.add_css_class("warning")
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
        self.__window.install_root_password = None
        return True

    def __on_cancel_clicked(self, *args):
        app = self.__window.get_application()
        if app:
            app.quit()
