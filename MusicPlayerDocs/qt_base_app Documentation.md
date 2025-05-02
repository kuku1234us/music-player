# qt_base_app Framework Documentation

## Introduction

The `qt_base_app` framework provides a foundational structure for building desktop applications using PyQt6. Its primary goal is to offer a reusable toolkit that simplifies common application development tasks, such as configuration management, theming, persistent settings, logging, and establishing a standard window layout. By handling these boilerplate aspects, the framework allows developers to focus more on the unique features and logic of their specific application, promoting code reuse and faster development cycles across multiple projects.

This document serves as a guide for understanding the architecture, components, and usage patterns of the `qt_base_app` framework. It is geared towards developers who will be building applications on top of this base, providing explanations and examples to facilitate rapid development.

## Architecture and Structure

The framework is organized into several key directories, each responsible for a distinct aspect of the application's base functionality:

*   `/qt_base_app`
    *   `app.py`: The main application setup script. Contains the crucial `create_application` function which initializes the Qt application instance (`QApplication`), manages the setup of core services like `SettingsManager` and `Logger`, handles configuration loading, applies styling, loads fonts, and creates the main application window instance.
    *   `/components`: Contains reusable UI components that are not specific to a particular application but provide common UI patterns (e.g., `SidebarWidget`, `BaseCard`).
    *   `/models`: Contains non-UI logic, data management, and utility classes (e.g., `SettingsManager`, `ThemeManager`, `ResourceLocator`, `Logger`). These are typically singletons providing services across the application.
    *   `/theme`: Handles visual styling. Contains the default theme configuration (`theme.yaml`) and the `ThemeManager` class responsible for loading and providing theme properties (colors, fonts, dimensions, stylesheets).
    *   `/window`: Contains base window implementations. `BaseWindow` provides a standard layout with a sidebar and a central content area, designed to be subclassed by specific applications.
    *   `/config`: (This directory is often empty in the base framework but might be used for internal framework configuration if needed in the future. Application-specific configuration resides within the application's own structure, typically in a `resources` folder).

This modular structure promotes separation of concerns, making the framework easier to understand, maintain, and extend.

## Core Components and Helpers

### 1. Models (`qt_base_app/models/`)

This directory houses the backbone services and data handling classes.

*   **`SettingsManager` (`settings_manager.py`)**
    *   **Purpose:** Provides a centralized, singleton interface for managing application settings. It acts as a unified access point for both persistent user settings (like window size or user preferences) and static application configuration loaded from a YAML file (like UI structure or default paths).
    *   **Initialization (Crucial Step):** Before the `SettingsManager` can be used anywhere in the application, it **must** be initialized *once* at the very beginning of the application startup. This is done by calling the class method `SettingsManager.initialize(organization_name, application_name)`.
        *   **Why is this mandatory?** This step configures the underlying `QSettings` object, which handles persistent storage. `QSettings` needs the `organization_name` and `application_name` to store data in the correct, application-specific location (e.g., a specific registry path on Windows, or standard config files on macOS/Linux). Providing these names prevents different applications built with this framework from interfering with each other's settings.
        *   **Where does it happen?** This initialization is performed automatically within the `qt_base_app.app.create_application` function. The `organization_name` and `application_name` must be passed as arguments to `create_application` from your application's entry point script (e.g., `run.py`).
        *   **Consequences of Skipping:** Attempting to call `SettingsManager.instance()` *before* `create_application` has called `initialize()` will result in a runtime error.
    *   **Functionality - Two Types of Settings:**
        1.  **Persistent Settings (via `get`/`set`):**
            *   **What:** Stores user-specific preferences and application state that need to persist between sessions (e.g., window size/position saved by `BaseWindow`, sidebar expanded/collapsed state saved by `SidebarWidget`, application-specific choices like default directories, toggle states, etc.).
            *   **How:** Uses PyQt6's `QSettings` backend (Registry, `.plist`, `.ini`).
            *   **Access:** Read using `SettingsManager.instance().get(key, default, type)` and write using `SettingsManager.instance().set(key, value, type)`. Remember to call `SettingsManager.instance().sync()` after `set` if you need the change to be written immediately.
            *   **Keys & Defaults:** The framework's `SettingsManager` itself only defines truly generic defaults (like `'ui/sidebar/expanded'`). Your specific application is responsible for defining its *own* keys (as constants, see `Defining Application Settings` section below) and registering its desired default values for these persistent settings using `SettingsManager.instance().set_defaults(my_app_defaults_dict)` *after* `create_application` has run.
        2.  **Static Application Configuration (via `get_yaml_config`):**
            *   **What:** Holds the application's structural definition and initial setup parameters loaded from a YAML file (e.g., `myapp_config.yaml`). This includes things like the window title (`app.title`), initial dimensions (`app.window.width`), logging settings (`logging.*`), and the sidebar structure (`sidebar.sections`).
            *   **How:** The YAML file path is passed to `create_application`. Inside `create_application`, `SettingsManager.instance().load_yaml_config(path)` is called, loading the data into an internal dictionary within the `SettingsManager` instance. This data is typically treated as *read-only* after startup.
            *   **Access:** Read using `SettingsManager.instance().get_yaml_config(key_path, default)`. The `key_path` uses dot notation to navigate the YAML structure (e.g., `'app.window.width'`, `'sidebar.sections'`).
    *   **Generic Nature:** The `SettingsManager` within `qt_base_app` is application-agnostic. It contains no hardcoded knowledge of application-specific settings like AI paths or browser preferences. Its role is to provide the *mechanism* for storing and retrieving settings.
    *   **Key Methods Recap:**
        *   `initialize(org, app)`: (Class method) Called first by `create_application`. **Do not call directly.**
        *   `instance()`: Access the initialized singleton instance.
        *   `load_yaml_config(path)`: Called by `create_application`. **Do not call directly.**
        *   `get_yaml_config(key_path, default)`: Reads from the loaded YAML data.
        *   `get(key, default, type)`: Reads a persistent setting (QSettings).
        *   `set(key, value, type)`: Writes/updates a persistent setting (QSettings).
        *   `set_defaults(defaults_dict)`: Registers application-specific defaults for persistent settings. Called by application code after `create_application`.
        *   `sync()`: Flushes persistent setting changes to storage.

*   **`Logger` (`logger.py`)**
    *   **Purpose:** Provides a standard, singleton logging service for the application.
    *   **Initialization:** The `Logger` singleton is obtained via `Logger.instance()`. However, it needs to be configured *once* at startup before meaningful logging can occur. This is handled automatically within `qt_base_app.app.create_application` *after* the `SettingsManager` has loaded the YAML configuration. `create_application` retrieves the `logging` section from the YAML via `SettingsManager` and calls `Logger.instance().configure(logging_config_dict)`.
    *   **Configuration (via YAML):** Your application's YAML configuration file should include a `logging` section to control the logger's behavior:
        *   `logging.level`: Minimum severity level (e.g., `"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`). Case-insensitive.
        *   `logging.log_to_file`: `true` or `false` to enable/disable logging to a file.
        *   `logging.log_to_console`: `true` or `false` to enable/disable outputting logs to the console/terminal.
        *   `logging.clear_on_startup`: If `true`, the log file is wiped clean each time the application starts. If `false`, new logs are appended.
        *   `app.title` (from YAML): The value of `app.title` in your YAML config is used to automatically name the log file (e.g., `MyApp.log`).
    *   **Log File Location:** Automatically determined. If running from source code, the log file appears in the project's root directory (where `run.py` is). If running from a bundled executable (created by PyInstaller), the log file appears in the same directory as the executable.
    *   **Usage:** Get the instance once (e.g., `self.logger = Logger.instance()` in your class `__init__`). Then, call the logging methods, **providing the caller's context** as the first argument.
        ```python
        from qt_base_app.models import Logger

        class MyWidget:
            def __init__(self):
                self.logger = Logger.instance()
                self.caller_name = self.__class__.__name__ # Good practice

            def do_something(self, user_id):
                self.logger.debug(self.caller_name, f"Starting process for user {user_id}")
                try:
                    # ... risky operation ...
                    result = 10 / 0
                    self.logger.info(self.caller_name, "Process completed successfully.")
                except Exception as e:
                    # Log error with exception details and traceback
                    self.logger.error(self.caller_name, f"Process failed for user {user_id}: {e}", exc_info=True)
                    # Alternative for just the exception traceback:
                    # self.logger.exception(self.caller_name, f"Process failed for user {user_id}:")
        ```
    *   **Methods:** `debug(caller, msg, ...)`, `info(caller, msg, ...)`, `warn(caller, msg, ...)`, `error(caller, msg, exc_info=False, ...)`, `exception(caller, msg, ...)`

*   **`ResourceLocator` (`resource_locator.py`)**
    *   **Purpose:** Provides a reliable way to find resource files (like images, configuration files, fonts) regardless of whether the application is running from source code or as a bundled executable (e.g., created with PyInstaller). Crucial for ensuring your application can find its assets after being packaged.
    *   **Functionality:** Automatically detects if running bundled (`sys._MEIPASS` exists) or from source (`sys.argv[0]`) and constructs the correct absolute path based on a relative path provided.
    *   **Usage Example:** Always use `ResourceLocator.get_path()` when you need the absolute path to a file that ships with your application, especially if it might be bundled later.
        ```python
        # Get path for myapp/resources/images/logo.png
        logo_relative = "myapp/resources/images/logo.png"
        logo_absolute = ResourceLocator.get_path(logo_relative)
        # Now use logo_absolute with QPixmap, file opening, etc.

        # Get path for the theme file within the framework itself
        theme_path = ResourceLocator.get_path("qt_base_app/theme/theme.yaml")
        ```

### 2. Theme (`qt_base_app/theme/`)

Handles the visual appearance of the application.

*   **`theme.yaml`:** Defines the framework's *default* theme properties: colors, typography (using the framework's default fonts like Geist Sans), dimensions, and base stylesheets. An application built on the framework can potentially provide its own `theme.yaml` to override the defaults, although the mechanism for loading an alternative theme isn't explicitly built into `ThemeManager` currently (it always loads the one inside `qt_base_app/theme/`).
*   **`ThemeManager` (`theme_manager.py`)**
    *   **Purpose:** A singleton service that loads the default `theme.yaml` and provides convenient access to theme properties.
    *   **Functionality:** Uses `ResourceLocator` to find the default `theme.yaml`. Provides methods like `get_color()`, `get_dimension()`, `get_typography()`, `get_stylesheet()` to retrieve theme values, with safe fallbacks if a value isn't found.
    *   **Usage Example:** Use this in your custom widgets and pages to ensure visual consistency.
        ```python
        from qt_base_app.theme import ThemeManager

        theme = ThemeManager.instance()
        # Set background based on theme
        bg_color = theme.get_color('background', 'content') # e.g., gets colors.background.content
        self.setStyleSheet(f"background-color: {bg_color};")
        # Style a button
        primary_color = theme.get_color('primary')
        text_color = theme.get_color('text', 'on_primary') # Example hypothetical color
        button.setStyleSheet(f"background-color: {primary_color}; color: {text_color};")
        ```

### 3. Window (`qt_base_app/window/`)

Provides the main application window structure.

*   **`BaseWindow` (`base_window.py`)**
    *   **Purpose:** A `QMainWindow` subclass providing a standard application window layout, typically featuring a collapsible sidebar (`SidebarWidget`) on the left and a central content area (managed by a `QStackedWidget`). It serves as the primary building block for the application's main user interface.
    *   **Initialization:** `BaseWindow` itself does **not** accept or process `config_path`. It relies on `SettingsManager` having been initialized and the YAML configuration having been loaded by `qt_base_app.app.create_application` *before* the `BaseWindow` (or its subclass) is instantiated.
    *   **Functionality:**
        *   **Window Setup:** Sets the window title, initial size (if not restored from settings), and minimum dimensions based on values retrieved from the YAML configuration via `SettingsManager.instance().get_yaml_config('app.title')`, `SettingsManager.instance().get_yaml_config('app.window.width')`, etc.
        *   **Geometry Persistence:** Automatically saves the window's size and position to persistent settings (`SettingsManager`) shortly after the user stops resizing or moving the window. It restores this geometry when the application starts up again. Uses the key `'window/geometry'`.
        *   **UI Structure:** Creates the `SidebarWidget` (using configuration fetched via `SettingsManager`), the main content area with a header (toggle button, page title `QLabel`), and a `QStackedWidget` (`self.content_stack`) for managing different application pages.
        *   **Page Management:** Provides `add_page(page_id, widget)` and `show_page(page_id)` methods for adding and displaying page widgets in the `content_stack`. `show_page` also attempts to set the header's page title based on the sidebar configuration or the widget's object name.
    *   **Extensibility:** Primarily designed to be subclassed by your application's specific main window (e.g., `myapp.ui.main_window.MainWindow`). Subclassing allows you to:
        *   Implement an `initialize_pages()` (or similar) method in your subclass to create instances of your specific application page widgets (`HomePage`, `SettingsPage`, etc.) and add them using `self.add_page()`.
        *   Optionally override `_assemble_layout()` if you need a fundamentally different core structure (e.g., adding a status bar, a media player panel at the bottom, etc.). You can choose whether or not to call `super()._assemble_layout()` within your override.
        *   Connect signals between pages or other application-specific components.
        *   Add custom methods and properties specific to your application's main window logic.
    *   **`__init__` in Subclasses:** Remember that if you override `__init__` in your subclass, it should **not** accept `config_path`. It should call `super().__init__(**kwargs)` to ensure the `BaseWindow` initialization (including geometry restoration and UI setup) occurs correctly.

### 4. Components (`qt_base_app/components/`)

Contains reusable UI widgets.

*   **`SidebarWidget` (`sidebar.py`)**
    *   **Purpose:** Implements the collapsible sidebar navigation menu.
    *   **Functionality:**
        *   Reads its structure (title, icon, sections, items) from the application's YAML configuration via `SettingsManager.instance().get_yaml_config('sidebar.title')` etc.
        *   Creates `MenuItem` buttons for navigation.
        *   Handles expand/collapse animations.
        *   Saves/restores its expanded/collapsed state using `SettingsManager.instance().get/set('ui/sidebar/expanded', ...)` for persistence across sessions.
        *   Emits an `item_clicked(item_id, page_class_name)` signal when an item is selected, allowing the main window to switch pages.
*   **`BaseCard` (`base_card.py`)**
    *   **Purpose:** Provides a visually styled container (`QFrame`) with optional title, border, and background settings, intended to group related UI elements.
    *   **Functionality:** Uses `ThemeManager` for default styling. Provides `add_widget` and `add_layout` methods to populate its content area.

### 5. Application Setup (`qt_base_app/app.py`)

This module orchestrates the application startup sequence.

*   **`create_application(...)` Function:**
    *   **Purpose:** The primary factory function. Sets up `QApplication`, initializes core services (`SettingsManager`, `Logger`), loads configuration and themes, creates the main window, and applies platform tweaks.
    *   **Key Arguments:**
        *   `window_class`: Your main window class (subclass of `BaseWindow`).
        *   `organization_name`: Your company/developer name (for `QSettings`).
        *   `application_name`: Your specific application's name (for `QSettings`).
        *   `config_path`: Relative path to your application's YAML configuration file (e.g., `"myapp/resources/myapp_config.yaml"`).
        *   `icon_paths`: List of relative paths to application icons (`.ico`, `.png`).
        *   `fonts_dir`, `font_mappings`: For loading custom fonts.
        *   `custom_stylesheet`: Optional extra CSS.
        *   `**window_kwargs`: Any extra keyword arguments are passed directly to your `window_class` constructor.
    *   **Initialization Order:**
        1.  Calls `SettingsManager.initialize(organization_name, application_name)`.
        2.  Loads the YAML specified by `config_path` into `SettingsManager` using `ResourceLocator` to find the file.
        3.  Initializes and configures `Logger` using the `logging` section retrieved from `SettingsManager`.
        4.  Creates the `QApplication` instance.
        5.  Initializes `ThemeManager`.
        6.  Applies platform setup (e.g., dark title bar).
        7.  Loads fonts.
        8.  Applies styles.
        9.  Instantiates your `window_class` (passing `**window_kwargs` but **not** `config_path`).
        10. Sets the application icon.
        11. Returns the `app` and `window` instances.
*   **`run_application(app, window)` Function:**
    *   **Purpose:** Shows the main window and starts the Qt event loop.
    *   **Steps:** Calls `window.show()` and `app.exec()`.

## Application Configuration (YAML)

The `qt_base_app` framework relies on a YAML configuration file provided by the specific application being built (e.g., `myapp/resources/myapp_config.yaml`). This file defines static configuration parameters primarily used during application startup to set up the main window, logging, sidebar navigation, and other foundational elements. It\'s loaded once by the `create_application` function and accessed thereafter via `SettingsManager.instance().get_yaml_config(key_path, default)`.

While you can add custom sections to this file for your application\'s specific needs, the framework expects certain sections and keys to be present for its core components to function correctly. Here are the standard sections:

### 1. `app` Section

This section defines global application properties, primarily used by `BaseWindow` for its initial setup.

```yaml
app:
  title: "My Application Name"  # Displayed in the window title bar
  icon: "fa5s.rocket"          # Fallback Font Awesome icon (used if icon_path fails)
  icon_path: "myapp/resources/app_icon.png" # Optional: Path to .png/.ico for window/taskbar
  window:
    width: 1000               # Initial window width
    height: 700              # Initial window height
    min_width: 700           # Minimum allowed window width
    min_height: 500          # Minimum allowed window height
```

*   `title`: Sets the main window title.
*   `icon` (Optional): A Font Awesome icon name (e.g., `fa5s.rocket`, `mdi.database`) used as a fallback if `icon_path` is not provided or invalid.
*   `icon_path` (Optional): The relative path (from the project root) to your application\'s icon file (`.png`, `.ico`). `BaseWindow` attempts to load this first.
*   `window`: A nested section defining the window\'s initial and minimum dimensions.

### 2. `logging` Section

This section controls the behavior of the framework\'s `Logger`.

```yaml
logging:
  level: "DEBUG"             # Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  log_to_file: true          # Enable/disable logging to a file ([app_title].log)
  log_to_console: true       # Enable/disable logging output to the console
  clear_on_startup: true   # If true, clears the log file on each start
```

*   `level`: Sets the minimum severity level for messages to be logged. Case-insensitive.
*   `log_to_file`: Boolean. If true, logs are written to a file named after `app.title` in the executable\'s directory (or project root during development).
*   `log_to_console`: Boolean. If true, log messages are also printed to standard output.
*   `clear_on_startup`: Boolean. If true, the log file is overwritten on each application start; otherwise, new logs are appended.

### 3. `sidebar` Section

This section defines the structure and content of the navigation sidebar managed by `SidebarWidget`.

```yaml
sidebar:
  title: "MyApp Menu"        # Title displayed at the top of the sidebar
  icon: "fa5s.bars"          # Icon displayed next to the sidebar title
  sections:
    - title: "Main Features"   # Title for the first group of items
      items:
        - id: "home"             # Unique ID for this item/page
          title: "Dashboard"       # Text displayed for the item
          icon: "fa5s.home"      # Icon for the item
          page: "HomePage"       # Class name of the widget in content_stack (Optional but used by BaseWindow default click handler)
    - title: "Tools"
      items:
        - id: "data_entry"
          title: "Data Entry"
          icon: "fa5s.edit"
          page: "DataEntryPage"
        # ... more items ...
    - title: "Settings"
      items:
        - id: "preferences"
          title: "Preferences"
          icon: "fa5s.cog"
          page: "PreferencesPage"
```

*   `title`: The text displayed at the very top of the sidebar.
*   `icon`: The Font Awesome icon displayed next to the sidebar title.
*   `sections`: A list defining groups of navigation items.
    *   Each section has a `title` (displayed as a header for the group) and a list of `items`.
    *   Each `item` represents a clickable navigation link and requires:
        *   `id`: A unique string identifier. This ID is used internally (e.g., when calling `BaseWindow.show_page(id)`) and is emitted by the `SidebarWidget.item_clicked` signal.
        *   `title`: The text label displayed for the item in the sidebar.
        *   `icon`: The Font Awesome icon displayed next to the item title.
        *   `page`: The class name of the corresponding page widget you added to the `content_stack` in your `MainWindow`. While technically optional for the sidebar widget itself, the default `_on_sidebar_item_clicked` handler in `BaseWindow` uses this to help determine the page title to display in the header.

By configuring these sections in your application\'s YAML file, you provide the necessary static information for the `qt_base_app` framework to initialize and structure the basic application environment.

## Defining Application Settings (`settings_defs.py`)

A key principle of the `qt_base_app` framework is keeping the framework code itself generic and reusable. This means the framework's `SettingsManager` doesn't know about settings specific to *your* application (like browser paths, AI directories, user preferences specific to your app's domain, etc.).

To manage your application's specific settings effectively and avoid scattering string literals ("magic strings") throughout your code, it's highly recommended to create a dedicated module within your application's structure to define these settings.

**1. Create the File:**
   Create a file, for example, `myapp/models/settings_defs.py` (or `myapp/core/settings_defs.py`).

**2. Define Keys as Constants:**
   Inside this file, define constants for all the keys you will use with `SettingsManager.get()` and `SettingsManager.set()`. This improves readability and makes refactoring much easier.

**3. Define Defaults Dictionary:**
   Create a dictionary (e.g., `MYAPP_APP_DEFAULTS`) that maps your setting keys (the constants you just defined) to their default values and types. This dictionary is specifically for settings you want managed by `QSettings` (persistent settings). The `SettingsManager` will use this dictionary when you call `set_defaults()` to initialize persistent settings *only if they don't already exist* in the user's stored settings.

**Example (`myapp/models/settings_defs.py`):**
```python
# myapp/models/settings_defs.py
from pathlib import Path
# Import SettingType from the framework
from qt_base_app.models.settings_manager import SettingType

# --- Define Keys ---
# Example: Browser settings
BROWSER_EXECUTABLE_KEY = 'browser/executable_path'
BROWSER_PROFILE_DIR_KEY = 'browser/profile_directory'
# Example: Project settings
PROJECT_LAST_OPENED_KEY = 'project/last_opened'
# Example: UI settings
RESULTS_TABLE_COLUMN_WIDTH_KEY = 'ui/results_table/col_width_name'

# --- Define Default Values ---
DEFAULT_BROWSER_PROFILE_DIR = str(Path.home() / ".myapp_browser_profile")
DEFAULT_PROJECT_LAST_OPENED = ""
DEFAULT_RESULTS_TABLE_COLUMN_WIDTH = 150

# --- Define Defaults Dictionary for Persistent Settings ---
MYAPP_APP_DEFAULTS = {
    # Map Key Constant -> (Default Value, SettingType)
    BROWSER_EXECUTABLE_KEY: ('', SettingType.STRING), # No default path, user must set
    BROWSER_PROFILE_DIR_KEY: (DEFAULT_BROWSER_PROFILE_DIR, SettingType.PATH),
    PROJECT_LAST_OPENED_KEY: (DEFAULT_PROJECT_LAST_OPENED, SettingType.STRING),
    RESULTS_TABLE_COLUMN_WIDTH_KEY: (DEFAULT_RESULTS_TABLE_COLUMN_WIDTH, SettingType.INT),
}
```

**4. Register Defaults at Startup:**
   In your application's entry point (`run.py`), *after* calling `create_application`, get the `SettingsManager` instance and register your application's defaults:

   ```python
   # run.py (within main function, after create_application)
   from qt_base_app.models import SettingsManager
   from myapp.models.settings_defs import MYAPP_APP_DEFAULTS # Import your defaults

   # ... (create_application call) ...
   app, window = create_application(...)

   # Register app-specific defaults for persistent settings
   settings = SettingsManager.instance()
   settings.set_defaults(MYAPP_APP_DEFAULTS)

   # ... (run_application call) ...
   ```

**5. Use Constants in Your Code:**
   Throughout your application code (`myapp`), import the key constants from your `settings_defs` module when using `SettingsManager.get()` or `SettingsManager.set()`.

   ```python
   # e.g., in myapp/ui/pages/some_widget.py
   from qt_base_app.models import SettingsManager, SettingType
   from myapp.models.settings_defs import BROWSER_PROFILE_DIR_KEY, DEFAULT_BROWSER_PROFILE_DIR

   class SomeWidget(QWidget):
       def __init__(self):
           self.settings = SettingsManager.instance()
           # ...

       def load_profile_path(self):
           # Use the imported constant for the key
           profile_path = self.settings.get(
               BROWSER_PROFILE_DIR_KEY,
               DEFAULT_BROWSER_PROFILE_DIR, # Can still use defined default here
               SettingType.PATH
           )
           if profile_path:
               print(f"Using profile: {profile_path}")
           else:
               print("Profile path not set or invalid.")
   ```

This approach keeps the framework clean while providing a structured and maintainable way for your application to manage its specific settings and their defaults.

## Packaging with PyInstaller (`.spec` File)

When you want to distribute your application as a standalone executable, you'll typically use a tool like PyInstaller. PyInstaller analyzes your code and bundles it along with Python and necessary libraries. A crucial part of this process is the `.spec` file, which instructs PyInstaller on how to build your application.

Here's how to configure a `.spec` file for an application built with `qt_base_app`, using `master115.spec` as a basis:

**1. Generate Initial `.spec`:**
   You usually generate an initial `.spec` file by running PyInstaller once from your project root:
   ```bash
   pyinstaller --name MyApp --windowed run.py
   ```
   (Replace `MyApp` and `run.py` with your actual names). This creates `MyApp.spec`.

**2. Edit the `.spec` File:**
   Open the generated `.spec` file and modify it. Here's a breakdown of important sections, referencing the `master115.spec` example:

   ```python
   # MyApp.spec (Example based on master115.spec)
   from PyInstaller.building.api import PYZ, EXE
   from PyInstaller.building.build_main import Analysis
   import sys
   from os import path

   block_cipher = None

   a = Analysis(
       ['run.py'], # *** Your application's entry point script ***
       pathex=['.'],    # Search path (usually current dir)
       binaries=[],   # Include external binaries if needed (e.g., DLLs)
       datas=[
           # *** CRITICAL: Bundle your application's resources ***
           # This bundles the entire 'myapp/resources' folder into the executable,
           # preserving its structure. Place your YAML config, icons, etc., here.
           ('myapp/resources', 'myapp/resources'),

           # *** CRITICAL: Bundle the framework's theme file ***
           # Since theme.yaml lives inside qt_base_app, bundle it separately.
           # ResourceLocator will find it inside the bundle.
           ('qt_base_app/theme/theme.yaml', 'qt_base_app/theme'),

           # *** CRITICAL: Bundle your application's fonts (if any) ***
           # If you have custom fonts in 'myapp/resources/fonts'
           ('myapp/resources/fonts', 'myapp/resources/fonts'),
           # Or if using framework default fonts from qt_base_app/fonts
           # ('qt_base_app/fonts', 'qt_base_app/fonts'), # Example if framework fonts were separate
       ],
       hiddenimports=[
           # *** Add libraries PyInstaller might miss ***
           'PyQt6', # Core Qt bindings
           'PyQt6.QtCore',
           'PyQt6.QtGui',
           'PyQt6.QtWidgets',
           'PyQt6.QtSvg', # Often needed for SVG icons used by themes/qtawesome
           'qtawesome',   # Icon library
           'yaml',        # For reading config/theme
           'PIL',         # Pillow, if used for image manipulation
           'requests',    # If your app makes HTTP requests
           'selenium',    # If using Selenium
           'webdriver_manager', # If using WebDriver Manager
           # Add any other libraries your specific app uses!
       ],
       hookspath=[],
       hooksconfig={},
       runtime_hooks=[],
       excludes=[],
       win_no_prefer_redirects=False,
       win_private_assemblies=False,
       cipher=block_cipher,
       noarchive=False,
   )

   pyz = PYZ(
       a.pure,
       a.zipped_data,
       cipher=block_cipher
   )

   exe = EXE(
       pyz,
       a.scripts,
       a.binaries,
       a.zipfiles,
       a.datas, # Ensure 'datas' from Analysis is included here
       [],
       name='MyApp', # *** Name of your final executable ***
       debug=False,
       bootloader_ignore_signals=False,
       strip=False,
       upx=True,
       upx_exclude=[],
       runtime_tmpdir=None,
       console=False, # *** Set to False for GUI apps (no background console) ***
                      # Set to True during development if you need console output for debugging
       disable_windowed_traceback=False,
       argv_emulation=False,
       target_arch=None,
       codesign_identity=None,
       entitlements_file=None,
       icon='myapp/resources/myapp.ico' # *** Path to your app's .ico file for the executable ***
   )
   ```

**Explanation of Key `datas` Entries:**

*   `('myapp/resources', 'myapp/resources')`: This is the standard way to include an entire folder and its contents. PyInstaller copies the `myapp/resources` folder (relative to the `.spec` file location) into the bundled application, placing it at the root level *inside* the bundle but naming the folder `myapp/resources`. Because `ResourceLocator` constructs paths relative to the bundle root, your code using `ResourceLocator.get_path("myapp/resources/myapp_config.yaml")` will correctly find the file inside the bundle. This ensures your YAML config, icons (`.png`), and any other resources in that folder are included.
*   `('qt_base_app/theme/theme.yaml', 'qt_base_app/theme')`: Since the default `theme.yaml` is part of the `qt_base_app` framework code, we need to explicitly include it. This copies the single file `theme.yaml` into a folder named `qt_base_app/theme` inside the bundle. Again, `ResourceLocator` will find this correctly.
*   `('myapp/resources/fonts', 'myapp/resources/fonts')`: Similar to the main resources folder, this bundles your application's custom fonts directory. The `qt_base_app.app.load_custom_fonts` function, using `ResourceLocator`, will find this path inside the bundle.

By carefully configuring the `datas` and `hiddenimports` sections, you ensure that PyInstaller includes all necessary code libraries and resource files for your application to run correctly as a standalone executable.

## Tutorial: Creating a New Application (Revised)

Let's refine the tutorial steps to incorporate our latest framework design.

**1. Project Structure:** (Same as before)

```
/MyProjectRoot
├── /myapp                 <-- Your Application Code
│   ├── /models            <-- Add models dir if it doesn't exist
│   │   └── settings_defs.py <-- App-specific settings definitions
│   ├── /ui
│   │   ├── __init__.py
│   │   ├── pages
│   │   │   └── __init__.py
│   │   │   └── home_page.py
│   │   └── main_window.py
│   ├── /resources         <-- Store app-specific resources here
│   │   ├── myapp_config.yaml  <-- YOUR App Config
│   │   └── rocket.png/ico   <-- Example icon
│   └── __init__.py
├── /qt_base_app           <-- The Framework Code
│   ├── /components
│   ├── /models
│   ├── /theme
│   │   └── theme.yaml     <-- Default Framework Theme
│   ├── /window
│   └── app.py
├── run.py           <-- Your Application Entry Point
├── MyApp.spec             <-- PyInstaller Spec File (after generation/editing)
```

**2. Create Configuration (`myapp/resources/myapp_config.yaml`):** (Same as before, defines UI structure, logging, etc.)

```yaml
# myapp/resources/myapp_config.yaml
app:
  title: "MyApp"
  window:
    width: 900
    height: 650
    min_width: 600
    min_height: 400
logging:
  level: "INFO"
  log_to_file: true
  log_to_console: true
  clear_on_startup: true
sidebar:
  title: "MyApp Menu"
  icon: "fa5s.rocket"
  sections:
    - title: "Main"
      items:
        - id: "home"
          title: "Home"
          icon: "fa5s.home"
          page: "HomePage"
    # Add other sections/items
```

**3. Create Application Settings Definitions (`myapp/models/settings_defs.py`):**
   Define keys and defaults for *persistent* settings specific to MyApp.

   ```python
   # myapp/models/settings_defs.py
   from pathlib import Path
   from qt_base_app.models.settings_manager import SettingType

   # Define Keys
   USER_NAME_KEY = 'user/name'
   AUTO_REFRESH_ENABLED_KEY = 'ui/auto_refresh'
   # ... other MyApp specific keys

   # Define Default Values
   DEFAULT_USER_NAME = ""
   DEFAULT_AUTO_REFRESH_ENABLED = True

   # Define Defaults Dictionary
   MYAPP_APP_DEFAULTS = {
       USER_NAME_KEY: (DEFAULT_USER_NAME, SettingType.STRING),
       AUTO_REFRESH_ENABLED_KEY: (DEFAULT_AUTO_REFRESH_ENABLED, SettingType.BOOL),
       # ... other MyApp defaults
   }
   ```

**4. Create Pages (`myapp/ui/pages/`):** (Same as before)
   Use `SettingsManager.instance().get/set` with keys imported from `myapp.models.settings_defs` for persistent settings, and `get_yaml_config` for static config. Use `ThemeManager` for styling.

**5. Create the Main Window (`myapp/ui/main_window.py`):**
   Subclass `BaseWindow`. **Ensure `__init__` does *not* accept `config_path` and calls `super().__init__(**kwargs)`**. Implement `initialize_pages()` to add your specific page widgets.

   ```python
   # myapp/ui/main_window.py
   from qt_base_app.window import BaseWindow
   from qt_base_app.models import Logger # Import Logger
   # Import your pages
   from .pages.home_page import HomePage
   # from .pages.about_page import AboutPage # Example

   class MainWindow(BaseWindow):
       def __init__(self, **kwargs):
           # Call BaseWindow init first - NO config_path here
           super().__init__(**kwargs)

           # Get logger if needed
           self.logger = Logger.instance()
           self.logger.info("MainWindow", "Main window initializing...")

           # Create and add pages
           self.initialize_pages()

           # Optional: Set initial page (could also read from config/settings)
           self.show_page('home')
           # Optional: Set initial sidebar selection if desired
           # self.sidebar.set_selected_item('home')

           self.logger.info("MainWindow", "Main window initialization complete.")

       def initialize_pages(self):
           """Create instances of all pages and add them."""
           home_widget = HomePage(self)
           # about_widget = AboutPage(self) # Example

           # Use IDs matching your myapp_config.yaml
           self.add_page('home', home_widget)
           # self.add_page('about', about_widget) # Example

       # Override _on_sidebar_item_clicked if needed,
       # but default implementation in BaseWindow often suffices.
       # def _on_sidebar_item_clicked(self, item_id: str, page_class: str):
       #     self.logger.debug("MainWindow", f"Sidebar item clicked: {item_id}")
       #     super()._on_sidebar_item_clicked(item_id, page_class) # Call base implementation

       # Override closeEvent only if you need extra cleanup specific to MainWindow
       # def closeEvent(self, event):
       #     self.logger.info("MainWindow", "Closing...")
       #     # Perform custom cleanup
       #     super().closeEvent(event) # IMPORTANT: Call base class closeEvent
   ```

**6. Create/Update the Entry Point (`run.py`):**
   Pass the required arguments to `create_application` and register your app's defaults.

   ```python
   #!/usr/bin/env python
   # run.py
   import sys
   import os

   project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '.')) # Simplified root path
   if project_root not in sys.path:
       sys.path.insert(0, project_root)

   from qt_base_app.app import create_application, run_application
   from qt_base_app.models import SettingsManager # Need SettingsManager here
   from myapp.ui.main_window import MainWindow
   from myapp.models.settings_defs import MYAPP_APP_DEFAULTS # Import your defaults

   def main():
       # --- Define Application Info ---
       ORG_NAME = "MyCompanyOrName" # Set your organization name
       APP_NAME = "MyApp"           # Set your application name

       # --- Define Resource Paths (relative to run.py) ---
       config_path = os.path.join("myapp", "resources", "myapp_config.yaml")
       icon_base = os.path.join("myapp", "resources", "rocket") # Base name for icons
       # fonts_dir = os.path.join("myapp", "resources", "fonts") # Example path to fonts

       # --- Call the framework's setup function ---
       app, window = create_application(
           window_class=MainWindow,
           organization_name=ORG_NAME,        # Pass organization name
           application_name=APP_NAME,         # Pass application name
           config_path=config_path,           # Pass path to your config YAML
           icon_paths=[
               f"{icon_base}.ico",
               f"{icon_base}.png"
           ],
           # fonts_dir=fonts_dir, # Uncomment if using custom fonts
           # font_mappings={...} # Provide if needed
           # custom_stylesheet="...", # Optional extra CSS
           # **window_kwargs can be added here if MainWindow needs extra args
       )

       # --- Register application-specific defaults ---
       try:
           settings = SettingsManager.instance()
           settings.set_defaults(MYAPP_APP_DEFAULTS)
       except Exception as e:
            # Log this critical error if logger is available, otherwise print
            print(f"[ERROR][run] Failed to set application defaults: {e}", file=sys.stderr)
            # Decide if the app should exit or continue with framework defaults only
            # sys.exit(1)

       # --- Start the application event loop ---
       return run_application(app, window)

   if __name__ == "__main__":
       sys.exit(main())
   ```

**7. Run:**
   Execute `python run.py` from `/MyProjectRoot`. The `create_application` function now handles the correct initialization sequence:
   *   Initializes `SettingsManager` with "MyCompanyOrName" and "MyApp".
   *   Loads `myapp/resources/myapp_config.yaml` into `SettingsManager`.
   *   Configures `Logger` based on the `logging` section of the loaded YAML.
   *   Instantiates `MainWindow` (your subclass).
   *   `MainWindow`'s `__init__` calls `BaseWindow`'s `__init__`.
   *   `BaseWindow` restores geometry (if saved previously), sets up base UI.
   *   `MainWindow` continues its `__init__`, calling `initialize_pages` to add page widgets.
   *   Back in `run.py`, `settings.set_defaults(MYAPP_APP_DEFAULTS)` ensures persistent settings have initial values if not already set by the user.
   *   `run_application` shows the window and starts the event loop.

This revised documentation and tutorial should accurately reflect the framework's current state and provide clear guidance for building new applications.