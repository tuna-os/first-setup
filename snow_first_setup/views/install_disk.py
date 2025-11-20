# install_disk.py
#
# Screen to select the physical disk to install to.

import json
import subprocess

from gi.repository import Gtk, GLib, Adw

_ = __builtins__["_"]

import snow_first_setup.core.backend as backend


@Gtk.Template(resource_path="/org/frostyard/FirstSetup/gtk/install-disk.ui")
class VanillaInstallDisk(Adw.Bin):
    __gtype_name__ = "VanillaInstallDisk"

    disks_group = Gtk.Template.Child()
    no_disks_label = Gtk.Template.Child()
    fs_combo = Gtk.Template.Child()

    def __init__(self, window, **kwargs):
        super().__init__(**kwargs)
        self.__window = window
        self.__selected_device = None
        # store tuples of (action_row, radio_button)
        self.__rows = []

    def set_page_active(self):
        # Refresh available disks each time the page becomes active
        GLib.idle_add(self.refresh_drives)

    def set_page_inactive(self):
        return

    def finish(self):
        # Called when the user presses next. Ensure a device is selected and store it on the window.
        if not self.__selected_device:
            self.__window.set_ready(False)
            return False
        # Store chosen device and filesystem on window for later steps
        self.__window.install_target_device = self.__selected_device
        # default to ext4 if somehow missing
        fs = None
        try:
            fs = self.fs_combo.get_active_text()
        except Exception:
            fs = None
        if not fs:
            fs = "ext4"
        self.__window.install_target_fs = fs
        return True

    def refresh_drives(self):
        # Clear previous rows
        for row in self.__rows:
            row.destroy()
        self.__rows = []
        self.__selected_device = None

        try:
            proc = subprocess.run(["lsblk", "-J", "-o", "NAME,SIZE,MODEL,TYPE,PATH"], capture_output=True, text=True, check=True)
            data = json.loads(proc.stdout)
        except Exception:
            # If lsblk is not available or parsing failed, show empty state
            self.no_disks_label.set_visible(True)
            self.__window.set_ready(False)
            return

        disks = []
        for block in data.get("blockdevices", []):
            if block.get("type") == "disk":
                name = block.get("name")
                path = block.get("path") or f"/dev/{name}"
                size = block.get("size") or ""
                model = block.get("model") or ""
                disks.append({"path": path, "name": name, "size": size, "model": model})

        if not disks:
            self.no_disks_label.set_visible(True)
            self.__window.set_ready(False)
            return

        self.no_disks_label.set_visible(False)

        first_radio = None
        for disk in disks:
            title = f"{disk['path']} — {disk['size']}"
            subtitle = disk['model'] or ""

            action_row = Adw.ActionRow()
            action_row.set_title(title)
            if subtitle:
                action_row.set_subtitle(subtitle)

            # create a radio button as prefix so the row is selectable
            radio = Gtk.CheckButton.new()
            radio.set_valign(Gtk.Align.CENTER)
            radio.set_focusable(False)
            if first_radio is None:
                first_radio = radio
            else:
                radio.set_group(first_radio)
            radio.connect("toggled", self.__on_radio_toggled, disk['path'])

            action_row.add_prefix(radio)
            action_row.set_activatable_widget(radio)

            self.disks_group.add(action_row)
            self.__rows.append((action_row, radio))

        # Ensure filesystem combobox has a default
        try:
            if self.fs_combo.get_active() == -1:
                self.fs_combo.set_active(0)
        except Exception:
            pass

        # Allow the window to continue (user can press next after selecting)
        self.__window.set_ready(False)
        return

    def __on_row_activated(self, widget, path):
        # Mark selected device and visually indicate selection
        self.__selected_device = path
        # Update rows to show selection
        # handled via radio toggled handler
        return

    def __on_radio_toggled(self, radio, path):
        if not radio.get_active():
            return
        self.__selected_device = path
        for (row, r) in self.__rows:
            if r is radio:
                row.add_css_class("selected")
            else:
                row.remove_css_class("selected")

        self.__window.set_ready(True)
