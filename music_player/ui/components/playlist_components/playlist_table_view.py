from typing import List, Optional, Any
from qt_base_app.models.logger import Logger

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import pyqtSignal

from music_player.ui.components.base_table import BaseTableView

class PlaylistTableView(BaseTableView):
    """
    Subclass of BaseTableView specifically for playlist track display.
    Overrides delete behavior to allow parent widget to handle playlist object updates.
    """
    # Signal emitting the list of source objects the user wants to delete
    delete_requested_from_playlist = pyqtSignal(list)

    def __init__(self, table_name: Optional[str] = None, parent: Optional[QWidget] = None):
        super().__init__(table_name=table_name, parent=parent)
        # No specific delegate needed for playlists currently

    # Override _on_delete_items from BaseTableView
    def _on_delete_items(self):
        """
        Handles Delete key press: Gets selected objects and emits a signal
        instead of directly asking the model to remove rows.
        The connected slot in the parent widget is responsible for:
        1. Updating the underlying Playlist object.
        2. Saving the Playlist.
        3. Adding items to the selection pool (if desired).
        4. *Then* calling model.remove_rows_by_objects() to update the view.
        """
        objects_to_delete = self.get_selected_items_data()
        if objects_to_delete:
            Logger.instance().debug(caller="PlaylistTableView", msg=f"[PlaylistTableView] Delete requested for {len(objects_to_delete)} object(s). Emitting signal.")
            self.delete_requested_from_playlist.emit(objects_to_delete)
        # We do NOT call super()._on_delete_items() or model.remove_rows_by_objects() here.
        # The parent widget handles the actual model update after processing the signal. 