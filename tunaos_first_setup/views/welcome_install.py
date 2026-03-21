# welcome_install.py
#
# Copyright 2024 mirkobrombin
# Copyright 2025 TunaOS contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation at version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import threading

_ = __builtins__["_"]

from gi.repository import Gtk, GLib, Adw

import tunaos_first_setup.core.backend as backend

@Gtk.Template(resource_path="/org/tunaos/FirstSetup/gtk/welcome-install.ui")
class VanillaWelcomeInstall(Adw.Bin):
    __gtype_name__ = "VanillaWelcomeInstall"

    btn_next = Gtk.Template.Child()
    btn_access = Gtk.Template.Child()
    status_page = Gtk.Template.Child()

    def __init__(self, window, **kwargs):
        super().__init__(**kwargs)
        self.__window = window

        self.btn_next.connect("clicked", self.__on_btn_next_clicked)
        self.btn_access.connect("clicked", self.__on_btn_access_clicked)

        # Apply variant-specific branding
        variant = backend.get_variant_info()
        pretty = variant["pretty_name"]
        emoji = variant["emoji"]

        self.status_page.set_title(f"Welcome to {pretty}")
        self.status_page.set_description(f"Let's install {pretty} on your computer")
        self.status_page.set_icon_name("org.tunaos.FirstSetup-fish")

    def set_page_active(self):
        self.__window.set_ready(True)
        self.btn_next.grab_focus()

    def set_page_inactive(self):
        return

    def finish(self):
        return True

    def __on_btn_next_clicked(self, widget):
        self.__window.finish_step()

    def __on_btn_access_clicked(self, widget):
        thread = threading.Thread(target=backend.open_accessibility_settings)
        thread.start()
