# recovery_key.py

from gi.repository import Gtk, GLib, Adw

_ = __builtins__["_"]

import tunaos_first_setup.core.backend as backend


@Gtk.Template(resource_path="/org/tunaos/FirstSetup/gtk/recovery-key.ui")
class VanillaRecoveryKey(Adw.Bin):
    __gtype_name__ = "VanillaRecoveryKey"

    status_page = Gtk.Template.Child()
    output_label = Gtk.Template.Child()

    def __init__(self, window, **kwargs):
        super().__init__(**kwargs)
        self.__window = window
        self.no_back_button = False
        self.no_next_button = False

    def set_page_active(self):
        GLib.idle_add(self.__generate_key)

    def set_page_inactive(self):
        return

    def finish(self):
        # Always allow proceeding after showing the key
        return True

    def __generate_key(self):
        self.__window.set_ready(False)
        try:
            success, output = backend.run_script_with_output("recovery-key", [], root=True)
            if success:
                self.output_label.set_text(output.strip() or _("Recovery key generated."))
                self.__window.set_ready(True)
            else:
                self.output_label.set_text(_("Failed to generate recovery key."))
                self.__window.set_ready(False)
        except Exception as e:
            self.output_label.set_text(_("Error generating recovery key."))
            self.__window.set_ready(False)
        return False
