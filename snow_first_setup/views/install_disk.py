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
    fde_checkbox = Gtk.Template.Child()
    fde_passphrase_entry = Gtk.Template.Child()
    fde_passphrase_confirm_entry = Gtk.Template.Child()
    fde_passphrase_error = Gtk.Template.Child()
    fde_passphrase_confirm_error = Gtk.Template.Child()

    def __init__(self, window, **kwargs):
        super().__init__(**kwargs)
        self.__window = window
        self.__selected_device = None
        # store tuples of (action_row, radio_button)
        self.__rows = []
        # wire up FDE checkbox behavior
        try:
            self.fde_checkbox.connect("toggled", self.__on_fde_toggled)
        except Exception:
            pass
        # validate on change
        try:
            self.fde_passphrase_entry.connect("changed", self.__on_fde_changed)
            self.fde_passphrase_confirm_entry.connect("changed", self.__on_fde_changed)
        except Exception:
            pass
        # ensure entries start disabled
        self.__set_fde_entries_sensitive(False)

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
        # Get selected filesystem from AdwComboRow
        fs = None
        try:
            selected_idx = self.fs_combo.get_selected()
            if selected_idx == 0:
                fs = "ext4"
            elif selected_idx == 1:
                fs = "btrfs"
        except Exception:
            fs = None
        if not fs:
            fs = "btrfs"
        self.__window.install_target_fs = fs

        # Handle Full Disk Encryption selections
        fde_enabled = False
        passphrase = None
        try:
            fde_enabled = bool(self.fde_checkbox.get_active())
        except Exception:
            fde_enabled = False
        if fde_enabled:
            try:
                pw1 = self.fde_passphrase_entry.get_text() or ""
                pw2 = self.fde_passphrase_confirm_entry.get_text() or ""
            except Exception:
                pw1 = ""
                pw2 = ""
            # basic confirmation + length check
            valid = self.__update_fde_errors(pw1, pw2)
            if not valid:
                self.__window.set_ready(False)
                return False
            passphrase = pw1
        # store on window for later steps
        self.__window.install_fde_enabled = fde_enabled
        self.__window.install_fde_passphrase = passphrase
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
            if self.fs_combo.get_selected() == Gtk.INVALID_LIST_POSITION:
                self.fs_combo.set_selected(1)
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


    def __on_fde_toggled(self, checkbox):
        active = checkbox.get_active()
        self.__set_fde_entries_sensitive(active)
        # Clear entries if disabling
        if not active:
            try:
                self.fde_passphrase_entry.set_text("")
                self.fde_passphrase_confirm_entry.set_text("")
                self.fde_passphrase_error.set_visible(False)
                self.fde_passphrase_confirm_error.set_visible(False)
            except Exception:
                pass
        else:
            # when enabling, re-validate current state
            self.__on_fde_changed(None)

    def __set_fde_entries_sensitive(self, sensitive: bool):
        try:
            self.fde_passphrase_entry.set_sensitive(sensitive)
            self.fde_passphrase_confirm_entry.set_sensitive(sensitive)
        except Exception:
            pass

    def __on_fde_changed(self, _entry):
        # live validation when checkbox active
        try:
            if not self.fde_checkbox.get_active():
                return
            pw1 = self.fde_passphrase_entry.get_text() or ""
            pw2 = self.fde_passphrase_confirm_entry.get_text() or ""
        except Exception:
            return
        valid = self.__update_fde_errors(pw1, pw2)
        # Gate navigation if FDE enabled and invalid
        if valid:
            # keep current readiness based on disk selection
            self.__window.set_ready(bool(self.__selected_device))
        else:
            self.__window.set_ready(False)

    def __update_fde_errors(self, pw1: str, pw2: str) -> bool:
        min_len = 8
        too_short = len(pw1) < min_len
        mismatch = pw1 != pw2
        try:
            self.fde_passphrase_error.set_visible(too_short)
            self.fde_passphrase_confirm_error.set_visible(mismatch and not too_short)
        except Exception:
            pass
        return (not too_short) and (not mismatch) and (pw1 != "")
