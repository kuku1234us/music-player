# BaseTable Documentation

## Introduction: Why a Reusable Table?

In many applications, especially one like a Music Player, we find ourselves needing to display lists of data in a tabular format repeatedly. We might have a table for playlists, another for tracks within a playlist, a table for files in a directory browser, or even search results. Each of these tables shares common needs: displaying data in columns, sorting by clicking headers, maybe some basic styling, and potentially saving user preferences like column widths or sort order.

Creating a separate `QTableWidget` implementation for each scenario leads to a lot of duplicated code, making maintenance difficult and inconsistent. If we want to change the look and feel or fix a sorting bug, we'd have to do it in multiple places.

This is where `BaseTable` comes in. The goal is to create a highly reusable and configurable table component that handles the common functionalities, allowing developers using it to focus only on the specifics of *their* data and how it should be presented. Initially, we might think of building this directly upon `QTableWidget`, but as we consider how data might change or how large datasets might become, a more robust architecture is needed: **Qt's Model/View Architecture**.

## Model/View Architecture Quick Tutorial

Before diving into the `BaseTable` implementation, it's crucial to understand the Model/View pattern, as it's the foundation for building flexible and efficient data display components in Qt. Think of it as separating responsibilities:

1.  **Model (`BaseTableModel`): The Data Guardian**
    *   **What it does:** Holds or provides access to the actual data (like our list of playlist objects, file system entries, etc.). It knows *nothing* about how the data looks on screen (no fonts, colors, or widgets).
    *   **Responsibilities:**
        *   Tells the View how many rows and columns there are.
        *   Provides the raw data for a specific "cell" (identified by a `QModelIndex` - row and column) when the View asks for it. It can provide different *kinds* of data for the same cell based on a "role" (e.g., `DisplayRole` for text shown, `EditRole` for editable data, `ToolTipRole`, `UserRole` for the underlying object).
        *   Handles sorting and potentially filtering (often delegated to a Proxy Model).
        *   Crucially, it **emits signals** (`dataChanged`, `rowsInserted`, `rowsRemoved`, etc.) whenever the underlying data changes. This is how it notifies the View(s) that they need to update.
    *   **Analogy:** Think of the Model as a librarian. The librarian manages the books (data) but doesn't care how you read them or what the cover looks like. They just know where the books are and can fetch information from them when asked. If a new book arrives or one is removed, the librarian updates their catalog and notifies relevant parties.

2.  **View (`BaseTableView`): The Presenter**
    *   **What it does:** Displays the data provided by the Model to the user. It knows *how* to draw the data (using tables, lists, trees) but knows *nothing* about the underlying data structure itself, beyond what the Model tells it.
    *   **Responsibilities:**
        *   Asks the Model for the number of rows/columns.
        *   Asks the Model for the data for each visible cell, specifying the *role* it needs (e.g., `DisplayRole` to get the text to show).
        *   Listens for signals from the Model (`dataChanged`, etc.) and redraws only the necessary parts of the view efficiently.
        *   Handles user interaction like selection and triggers actions like sorting (by telling the Model or Proxy Model to sort).
        *   Uses **Delegates** to customize *how* individual items are rendered or edited (though we won't focus heavily on delegates for `BaseTable` initially).
    *   **Analogy:** Think of the View as the bookshelf and display area in the library. It shows the books arranged according to the librarian's catalog. It doesn't hold the books itself, just displays them. If the librarian signals a change, the bookshelf updates its display accordingly.

3.  **Delegate (Optional but Powerful): The Item Artist/Editor**
    *   **What it does:** Controls how individual items in the View are drawn and edited. The View asks the Delegate to paint items instead of using the default simple text rendering.
    *   **Responsibilities:**
        *   Custom painting of items (e.g., drawing progress bars, star ratings, custom checkboxes).
        *   Providing custom editors (e.g., a dropdown list, a date picker) when an item is edited.
    *   **Analogy:** Think of the Delegate as a specialized display case designer or an interactive kiosk for a specific book. It provides a richer way to view or interact with an item beyond just seeing its title on the shelf.

**Why Model/View for BaseTable?**

*   **Efficiency:** Views only request data for visible items. When data changes, only the affected items are updated, which is much faster than rebuilding an entire `QTableWidget`.
*   **Flexibility:** The same Model can be displayed by multiple Views simultaneously (e.g., a table and a list showing the same data).
*   **Data Independence:** `BaseTableView` doesn't need to know *anything* about the specific type of objects it's displaying (Files, Tracks, etc.). All the logic for accessing and formatting data resides in the `BaseTableModel` and the `ColumnDefinition`s.
*   **Scalability:** Handles large datasets much better than `QTableWidget`.
*   **Maintainability:** Separating data logic (Model) from presentation logic (View) makes the code cleaner and easier to manage.
*   **Dynamic Updates:** Handles external changes to the data source gracefully via the Model's signals. If another part of the application modifies a playlist that the table is showing, the table can update automatically.

## Understanding Qt Item Roles

A key concept in Model/View is "Roles". When the View asks the Model for data about a specific item (identified by its row and column, or `QModelIndex`), it also specifies *what kind* of data it wants using a `role`. Think of roles as different facets of the same piece of data. Common roles include:

*   `Qt.ItemDataRole.DisplayRole`: The text that should be displayed to the user in the cell.
*   `Qt.ItemDataRole.EditRole`: The underlying data used for editing (if editing is enabled). Often useful for storing the raw, sortable value (like a number or timestamp) when the `DisplayRole` shows formatted text.
*   `Qt.ItemDataRole.ToolTipRole`: The text that appears when the user hovers over the item.
*   `Qt.ItemDataRole.TextAlignmentRole`: How the text should be aligned within the cell (e.g., `Qt.AlignmentFlag.AlignRight`).
*   `Qt.ItemDataRole.ForegroundRole`, `Qt.ItemDataRole.BackgroundRole`: Used to specify custom text or background colors (often a `QColor` or `QBrush`).
*   `Qt.ItemDataRole.CheckStateRole`: For items that have a checkbox (value is `Qt.CheckState.Checked` or `Qt.CheckState.Unchecked`).
*   `Qt.ItemDataRole.UserRole`: A generic role used to store application-specific data, often the **original Python object** itself. This is very useful for retrieving the underlying object when the user interacts with a row in the View.

Our `BaseTableModel` uses these roles (configured via `ColumnDefinition`) to provide the correct data to the `BaseTableView`. For instance, it might return a formatted date string for `DisplayRole` but the raw timestamp number for `EditRole` (which we use as the default `sort_role`).

## Proposed `BaseTable` Design (Model/View)

Our reusable table component consists of two main classes built upon Qt's Model/View framework:

1.  `BaseTableModel(QAbstractTableModel)`: Handles the data adaptation.
2.  `BaseTableView(QTableView)`: Handles the presentation and user interaction.

The key to configuring them is the `ColumnDefinition`.

### `ColumnDefinition` - The Blueprint

You, as the user of `BaseTable`, define *how* each column should behave by creating a list of `ColumnDefinition` objects. This class tells the `BaseTableModel` how to get data from your source objects and format it for display and sorting.

```python
from typing import List, Optional, Any, Union, Callable
from dataclasses import dataclass
from PyQt6.QtCore import Qt # For alignment flags and roles

@dataclass
class ColumnDefinition:
    """Defines how a column in BaseTable should be displayed and behave."""
    header: str       # Text shown in the header (e.g., "Filename", "Size")
    data_key: Union[str, Callable[[Any], Any]] # How to get data from your object:
                      # - A string: name of an attribute or dict key (e.g., 'name', 'path').
                      # - A function: takes your object, returns the value (e.g., lambda track: track.get_duration()).
    display_formatter: Optional[Callable[[Any], str]] = None # Optional function to format the value from data_key for display (e.g., format_file_size). Defaults to str().
    sort_key: Optional[Union[str, Callable[[Any], Any]]] = None # Optional: How to get the value used for *sorting*. If None, uses the value from data_key. Allows sorting by raw values (bytes, timestamps) while displaying formatted strings.
    sort_role: int = Qt.ItemDataRole.EditRole # Which Qt role holds the sortable data. EditRole is often convenient.
    width: Optional[int] = None # Optional initial width for the column.
    alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter # Text alignment in the cell.
    tooltip_key: Optional[Union[str, Callable[[Any], Any]]] = None # Optional: How to get data for the tooltip (shown on hover).
    tooltip_role: int = Qt.ItemDataRole.ToolTipRole # Qt role for tooltips.
    stretch: int = 0 # Optional stretch factor for column resizing (0 = interactive, >0 = stretch).
```

**Think of `ColumnDefinition` as the instructions you give to the table:** "For the first column, call the header 'Name', get the value using the object's 'name' attribute, display it as a string, and sort using this 'name' attribute." "For the second column, call it 'Size', get the value using the 'size_bytes' attribute, format it using `format_file_size`, but sort it using the raw 'size_bytes' value assigned to the `EditRole`."

### `BaseTableModel` - The Adaptable Data Source

This class inherits from `QAbstractTableModel`. Its main job is to act as a bridge between your list of Python objects (like file info dictionaries or `Track` objects) and the `BaseTableView`. You don't typically interact with its internal code directly after initialization, but you need to understand its role:

1.  **Holds Data Reference:** It keeps a reference to the list of source objects you provide.
2.  **Uses Column Definitions:** It uses your `ColumnDefinition` list to determine the table structure (column count, headers) and how to retrieve/format data for each cell and role.
3.  **Provides Data:** The `BaseTableView` calls the model's `data()` method frequently to get the necessary information (display text, sort values, tooltips, alignment) for rendering cells.
4.  **Signals Changes:** It provides methods (`set_source_objects`, `insert_rows`, `remove_rows_by_objects`, `update_row_data`, etc.) that modify the underlying data list *and* emit the appropriate Qt signals (`beginResetModel`/`endResetModel`, `beginInsertRows`/`endInsertRows`, `beginRemoveRows`/`endRemoveRows`, `dataChanged`) so that any connected Views update automatically and efficiently.

### `BaseTableView` - The Configurable Display

This class inherits from `QTableView`. It provides the visual table widget. Key features include:

1.  **Standard View Features:** Handles drawing the table grid, rows, columns, and headers. Manages user interactions like row selection and column resizing.
2.  **Sorting Trigger:** Enables sorting when users click column headers. It tells the model (or proxy model) which column to sort by.
3.  **Styling:** Applies consistent visual styling based on the application's theme.
4.  **Persistence:** If given a `table_name`, it automatically saves/loads column widths and the last sort order using `SettingsManager`.
5.  **Model Connection:** You connect it to an instance of `BaseTableModel` (or a proxy model) using `view.setModel(model)`.
6.  **Deletion Handling:** Listens for the `Delete` key press. If detected, it identifies the selected rows and requests the *model* to delete the corresponding data objects using the model's `remove_rows_by_objects` method.

## Architectural Diagram

This diagram shows how the components typically interact, including the highly recommended `QSortFilterProxyModel`:

```
+-----------------+      +-------------------+      +---------------------------+      +-----------------+
| List[MyObject]  |<-----| BaseTableModel    |<-----| (Optional but Recommended)|<-----| BaseTableView   |
| (Your Data)     |----->| (Data Adaptation) |----->| QSortFilterProxyModel     |----->| (Presentation)  |
+-----------------+      +-------------------+      |   (Sorting/Filtering)     |      +-----------------+
                           ^       |                 +---------------------------+         ^       |
                           |       |                                                       |       |
                           +--- notifies View(s) via built-in signals <--------------------+       |
                                (dataChanged, rowsInserted, etc.)                                  |
                                                                                                   |
                                  User interacts with View (e.g., clicks header)-------------------+
                                  View tells Proxy/Model to sort ---------------------------------->
```


## Using `QSortFilterProxyModel` (Highly Recommended)

While you *can* connect `BaseTableView` directly to `BaseTableModel`, it's usually better to insert a `QSortFilterProxyModel` in between.

*   **Why?** It provides robust, efficient sorting and filtering capabilities without requiring complex logic in your `BaseTableModel`. Your `BaseTableModel` can stay simple, just focusing on providing the raw data.
*   **How?**
    1.  Create your `BaseTableModel` instance (`source_model`).
    2.  Create a `QSortFilterProxyModel` instance (`proxy_model`).
    3.  Tell the proxy about your source model: `proxy_model.setSourceModel(source_model)`.
    4.  Tell the `BaseTableView` to use the *proxy* model: `view.setModel(proxy_model)`.
    5.  Enable sorting on the view: `view.setSortingEnabled(True)`.
*   **Result:** When you click a header in the `BaseTableView`, the view tells the `proxy_model` to sort. The proxy model efficiently sorts based on the data it gets from your `source_model` (using the `sort_role` you defined in `ColumnDefinition`) and presents the sorted view to the `BaseTableView`. Your original data in `source_model` remains untouched. Filtering works similarly by setting filter properties on the proxy model.

## Handling Data Changes: Signals are Key

The power of Model/View shines when data changes.

*   **External Changes:** If your list of source objects (e.g., `playlist.tracks`) is modified by some other part of your application, you **must** inform the `BaseTableModel`.
    *   **Full Refresh:** The simplest way is `model.set_source_objects(updated_list)`. Efficient for small lists or infrequent changes.
    *   **Granular Updates:** For better performance, use model methods like `model.insert_rows(...)`, `model.remove_rows_by_objects(...)`, `model.update_row_data(...)`. These methods update the model's internal list *and* emit the precise signals (`rowsInserted`, `rowsRemoved`, `dataChanged`) needed for the view (and proxy model) to update efficiently without redrawing everything.
*   **View Interactions (e.g., Deletion):** When the user presses `Delete` in the `BaseTableView`, the view calls the *model's* `remove_rows_by_objects` method. The model then performs the deletion and emits the `rowsRemoved` signal, causing the view to update automatically. The parent widget usually doesn't need to manually remove rows from the view after a deletion triggered this way.

If the parent widget *does* need to know specifically which items were deleted (perhaps to update another UI element), it can connect to the *model's* signals (like `rowsRemoved`, although getting the specific objects deleted from this standard signal is slightly complex) or potentially a custom signal emitted by the model after deletion.

## Editing Data (Conceptual Overview)

`BaseTableView` and `BaseTableModel` are primarily set up for *displaying* data. To make data editable directly within the table:

1.  **Model:** You would need to implement the `setData(index, value, role)` method in `BaseTableModel`. This method is called by the view/delegate when an edit is finished. It needs to take the `value` from the editor, validate it, update the corresponding underlying source object in your `_source_objects` list, and then emit the `dataChanged` signal for that index.
2.  **Model:** You also need to implement the `flags(index)` method in the model. For editable cells, this method must return the standard flags *plus* `Qt.ItemFlag.ItemIsEditable`.
3.  **View/Delegate:** For basic editing (like text fields), `QTableView` might handle it automatically if the flags are set. For more complex editing (like dropdowns, date pickers), you would create a custom `QStyledItemDelegate`, implement its `createEditor()`, `setEditorData()`, and `setModelData()` methods, and then set this delegate on the specific column of the `BaseTableView` using `view.setItemDelegateForColumn()`.

## Best Practices for Callables in `ColumnDefinition`

When providing functions (like lambdas) for `data_key`, `sort_key`, `display_formatter`, or `tooltip_key`:

*   **Keep them simple:** They will be called frequently during rendering and sorting. Avoid complex logic or I/O operations.
*   **Handle Errors:** Use `.get(key, default)` for dictionaries or `getattr(obj, key, default)` for objects within your lambdas to prevent `KeyError` or `AttributeError` if data is missing. Use `try...except` for operations that might fail (like date parsing or file access). Return a sensible default (like `"N/A"`, `0`, `None`) on error. Errors in these functions can cause rendering issues or sorting failures.

## How to Use `BaseTableView` and `BaseTableModel` - Examples

*(The previous examples demonstrating usage for simple dictionaries and playlist tracks are appropriate here. Ensure they are included below this section without the full class implementations).*

### Example 1: Simple List of Dictionaries (Text Only)

```python
# Your data
users_data = [
    {'id': 101, 'name': 'Alice', 'role': 'Admin'},
    {'id': 102, 'name': 'Bob', 'role': 'User'},
    {'id': 103, 'name': 'Charlie', 'role': 'User'}
]

# --- In your QWidget or QMainWindow ---
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt6.QtCore import Qt, QSortFilterProxyModel
# Assume BaseTableView, BaseTableModel, ColumnDefinition are imported

# 1. Define Columns
col_defs = [
    ColumnDefinition(header="ID", data_key='id', width=50, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, sort_role=Qt.ItemDataRole.EditRole),
    ColumnDefinition(header="Username", data_key='name', width=150, sort_key=lambda u: u.get('name', '').lower()), # Case-insensitive sort
    ColumnDefinition(header="Role", data_key='role', width=100, tooltip_key=lambda u: f"User ID is {u.get('id', 'N/A')}")
]

# 2. Create Model
user_model = BaseTableModel(source_objects=users_data, column_definitions=col_defs)

# 3. Create Proxy Model (Recommended)
proxy_model = QSortFilterProxyModel()
proxy_model.setSourceModel(user_model)

# 4. Create View
user_table_view = BaseTableView(table_name="user_list_view")

# 5. Set Proxy Model on View
user_table_view.setModel(proxy_model)
# user_table_view.setSortingEnabled(True) # Already enabled by default in BaseTableView

# 6. Add View to Layout
# ... layout.addWidget(user_table_view) ...
```

### Example 2: Complex Objects (Playlist Tracks)

```python
# --- Assume Playlist class exists and playlist_object holds a Playlist instance ---
# --- Assume helper functions: format_file_size, format_timestamp, get_file_stat exist ---
from PyQt6.QtCore import Qt, QSortFilterProxyModel
from pathlib import Path
import datetime

# --- Column Definitions for Playlist ---
playlist_col_defs = [
    # ... (definitions as in previous example, using lambdas for data_key,
    #      display_formatter, sort_key, and setting sort_role=Qt.ItemDataRole.EditRole
    #      for columns needing custom sorting like Size, Date Added, Modified) ...
    ColumnDefinition(
        header="Filename",
        data_key=lambda t: Path(t.get('path', '')).name,
        sort_key=lambda t: t.get('path', '').lower(),
        width=250, tooltip_key='path'
    ),
    ColumnDefinition(
        header="Size",
        data_key=lambda t: get_file_stat(t.get('path'), 'size'),
        display_formatter=format_file_size,
        sort_key=lambda t: get_file_stat(t.get('path'), 'size'),
        width=100, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        sort_role=Qt.ItemDataRole.EditRole
    ),
    # ... other columns (Date Added, Modified) ...
]

# --- Usage in a Widget ---
# class PlaylistWidget(QWidget):
#     def __init__(self, playlist_object):
#         # ...
#         self.playlist = playlist_object

#         # 1. Create Model
#         self.track_model = BaseTableModel(
#             source_objects=self.playlist.tracks,
#             column_definitions=playlist_col_defs
#         )
#         # 2. Create Proxy
#         self.proxy_model = QSortFilterProxyModel()
#         self.proxy_model.setSourceModel(self.track_model)

#         # 3. Create View
#         self.track_view = BaseTableView(table_name="playlist_tracks_view")

#         # 4. Set Proxy Model on View
#         self.track_view.setModel(self.proxy_model)

#         # ... layout, connect signals ...

#     def handle_external_playlist_update(self):
#         # Use model methods for updates
#         # self.track_model.set_source_objects(self.playlist.tracks) # Full refresh
#         pass # Or granular updates
```

This revised documentation structure provides a better tutorial flow, explaining the concepts before showing usage examples and omitting the internal implementation details.