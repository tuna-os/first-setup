# conn_check.py
#
# Copyright 2023 mirkobrombin
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundationat version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import threading
import logging
_ = __builtins__["_"]

from gi.repository import Adw, Gtk, Gio, GLib

import tunaos_first_setup.core.backend as backend

logger = logging.getLogger("FirstSetup::Conn_Check")

# Host to test actual internet connectivity
CONNECTIVITY_CHECK_HOST = "gnome.org"


@Gtk.Template(resource_path="/org/tunaos/FirstSetup/gtk/conn-check.ui")
class VanillaConnCheck(Adw.Bin):
    __gtype_name__ = "VanillaConnCheck"

    status_page = Gtk.Template.Child()
    btn_settings = Gtk.Template.Child()

    __network_monitor = None
    __active = False
    __already_skipped = False
    __checking = False

    def __init__(self, window, **kwargs):
        super().__init__(**kwargs)
        self.__window = window

        self.__network_monitor = Gio.NetworkMonitor.get_default()

        self.__network_monitor.connect("network-changed", self.__on_network_changed)
        self.btn_settings.connect("clicked", self.__on_btn_settings_clicked)

    def set_page_active(self):
        self.__active = True
        # Disable next button until we verify connectivity
        self.__window.set_ready(False)
        self.__check_network_status()

    def set_page_inactive(self):
        self.__active = False

    def finish(self):
        return True

    def __on_network_changed(self, monitor, network_available):
        """Called when network state changes."""
        if not self.__active:
            return
        # Disable next button immediately and recheck
        GLib.idle_add(self.__window.set_ready, False)
        self.__check_network_status()

    def __check_network_status(self):
        """Check actual internet connectivity asynchronously."""
        if self.__checking:
            return
        self.__checking = True

        # First do a quick check - if no network route at all, fail fast
        if self.__network_monitor.get_connectivity() == Gio.NetworkConnectivity.LOCAL:
            self.__checking = False
            GLib.idle_add(self.__set_network_disconnected)
            GLib.idle_add(self.__window.set_ready, False)
            return

        # Do actual reachability test in background
        thread = threading.Thread(target=self.__do_connectivity_check)
        thread.daemon = True
        thread.start()

    def __do_connectivity_check(self):
        """Perform actual connectivity test to verify internet access."""
        try:
            address = Gio.NetworkAddress.new(CONNECTIVITY_CHECK_HOST, 443)
            can_reach = self.__network_monitor.can_reach(address, None)

            if can_reach:
                GLib.idle_add(self.__handle_connected)
            else:
                GLib.idle_add(self.__handle_disconnected)
        except Exception as e:
            logger.warning(f"Connectivity check failed: {e}")
            GLib.idle_add(self.__handle_disconnected)
        finally:
            self.__checking = False

    def __handle_connected(self):
        """Handle successful connectivity check."""
        if not self.__active:
            return
        self.__set_network_connected()
        self.__window.set_ready(True)

    def __handle_disconnected(self):
        """Handle failed connectivity check."""
        if not self.__active:
            return
        self.__set_network_disconnected()
        self.__window.set_ready(False)

    def __set_network_disconnected(self):
        logger.info("Internet connection not available.")
        self.status_page.set_icon_name("network-wired-disconnected-symbolic")
        self.status_page.set_title(_("No Internet Connection!"))
        self.status_page.set_description(_("First Setup requires an active internet connection"))
        self.btn_settings.set_visible(True)

    def __set_network_connected(self):
        logger.info("Internet connection available.")
        self.status_page.set_icon_name("emblem-default-symbolic")
        self.status_page.set_title(_("Connection available"))
        self.status_page.set_description(_("You have a working internet connection"))
        self.btn_settings.set_visible(False)
        if not self.__already_skipped:
            self.__already_skipped = True
            GLib.idle_add(self.__window.finish_step)

    def __on_btn_settings_clicked(self, widget):
        thread = threading.Thread(target=backend.open_network_settings)
        thread.start()
        return
