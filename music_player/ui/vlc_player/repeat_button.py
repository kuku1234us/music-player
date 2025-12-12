"""
Repeat Button component for the music player application.
Toggles between Repeat-All, Repeat-1 and Repeat-Random modes.
"""
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QPainterPath
from PyQt6.QtCore import Qt, QRectF, QSize, pyqtSignal, QByteArray
from PyQt6.QtSvg import QSvgRenderer
from qt_base_app.models.logger import Logger

from qt_base_app.theme.theme_manager import ThemeManager

# Define state constants locally for this component
# REPEAT_NONE = "repeat_none" # Removed
REPEAT_ALL = "repeat_all"
REPEAT_ONE = "repeat_one"
REPEAT_RANDOM = "repeat_random"


class RepeatButton(QWidget):
    """
    Button that toggles between Repeat-All, Repeat-1 and Repeat-Random icons.
    Displays as just the SVG icon, but shows a circular background on hover.
    """
    
    # Signal emitted when state changes
    state_changed = pyqtSignal(str)  # Emits "repeat_all", "repeat_one", "repeat_random"
    clicked = pyqtSignal()
    
    # SVG data for icons
    REPEAT_ONE_SVG = """<svg fill="white" width="800px" height="800px" viewBox="0 0 56 56" xmlns="http://www.w3.org/2000/svg"><path d="M 51.0625 22.4102 C 52.5160 22.4102 53.3128 21.6133 53.3128 20.1133 L 53.3128 9.2149 C 53.3128 7.5273 52.2347 6.4023 50.5940 6.4023 C 49.2112 6.4023 48.4144 6.8476 47.3128 7.6914 L 44.3126 10.0117 C 43.7735 10.4336 43.5626 10.9023 43.5626 11.4180 C 43.5626 12.1680 44.1251 12.8008 45.0860 12.8008 C 45.4609 12.8008 45.8363 12.6836 46.1641 12.4023 L 48.5780 10.4570 L 48.7657 10.4570 L 48.7657 20.1133 C 48.7657 21.6133 49.5860 22.4102 51.0625 22.4102 Z M 2.3829 26.4180 C 2.3829 27.8476 3.5314 28.9961 4.9611 28.9961 C 6.4142 28.9961 7.5626 27.8476 7.5626 26.4180 L 7.5626 24.8711 C 7.5626 21.1445 10.1173 18.6836 13.9611 18.6836 L 26.6173 18.6836 L 26.6173 23.5820 C 26.6173 24.8476 27.4376 25.6445 28.7267 25.6445 C 29.2892 25.6445 29.8751 25.4336 30.3204 25.0586 L 39.1798 17.7461 C 40.2345 16.8789 40.2111 15.4961 39.1798 14.6055 L 30.3204 7.2461 C 29.8751 6.8945 29.2892 6.6602 28.7267 6.6602 C 27.4376 6.6602 26.6173 7.4805 26.6173 8.7461 L 26.6173 13.5976 L 14.4532 13.5976 C 7.0938 13.5976 2.3829 17.8398 2.3829 24.4961 Z M 24.3438 32.6992 C 24.3438 31.4336 23.5470 30.6367 22.2579 30.6367 C 21.6954 30.6367 21.1095 30.8476 20.6642 31.1992 L 11.8048 38.5117 C 10.7501 39.3789 10.7501 40.7617 11.8048 41.6523 L 20.6642 49.0117 C 21.1095 49.3867 21.6954 49.5977 22.2579 49.5977 C 23.5470 49.5977 24.3438 48.8008 24.3438 47.5352 L 24.3438 42.6367 L 41.5470 42.6367 C 48.9064 42.6367 53.6171 38.3711 53.6171 31.7383 L 53.6171 29.8164 C 53.6171 28.3633 52.4689 27.2149 51.0160 27.2149 C 49.5860 27.2149 48.4374 28.3633 48.4374 29.8164 L 48.4374 31.3633 C 48.4374 35.0664 45.8828 37.5508 42.0392 37.5508 L 24.3438 37.5508 Z"/></svg>"""
    
    REPEAT_ALL_SVG = """<svg fill="white" height="800px" width="800px" version="1.1" id="_x32_" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" 
	 viewBox="0 0 512 512" xml:space="preserve">
<style type="text/css">
	.st0{fill:white;}
</style>
<g>
	<path class="st0" d="M499.795,195.596c-11.804-27.884-31.438-51.515-56.186-68.24c-24.717-16.724-54.739-26.526-86.773-26.518
		h-44.222l10.195-24.234c1.335-3.176,0.531-6.834-1.994-9.158c-2.541-2.316-6.255-2.798-9.295-1.19l-108.932,57.578
		c-2.67,1.399-4.342,4.173-4.326,7.18c0,3.015,1.656,5.797,4.326,7.189l108.932,57.585c3.023,1.608,6.738,1.126,9.279-1.181
		c2.541-2.324,3.344-5.991,2.01-9.158l-10.211-24.266h44.238c13.187,0.008,25.569,2.654,36.906,7.438
		c16.982,7.172,31.518,19.24,41.746,34.389c10.228,15.172,16.161,33.248,16.177,52.994c-0.016,13.17-2.653,25.569-7.445,36.89
		c-7.172,16.982-19.232,31.518-34.381,41.746c-15.18,10.228-33.255,16.161-53.003,16.177v60.344c21.34,0,41.827-4.342,60.416-12.206
		c27.869-11.803,51.508-31.438,68.231-56.178c16.725-24.732,26.534-54.748,26.518-86.773
		C512,234.665,507.658,214.178,499.795,195.596z"/>
	<path class="st0" d="M309.413,373.796l-108.932-57.585c-3.023-1.608-6.738-1.126-9.278,1.182c-2.541,2.324-3.345,5.998-2.01,9.158
		l10.211,24.265h-44.238c-13.187-0.008-25.569-2.653-36.906-7.437c-16.982-7.172-31.518-19.24-41.746-34.389
		c-10.228-15.164-16.161-33.247-16.178-52.986c0.016-13.178,2.654-25.576,7.445-36.897c7.172-16.982,19.234-31.519,34.381-41.747
		c15.18-10.227,33.256-16.16,53.003-16.177v-60.344c-21.339,0-41.827,4.342-60.416,12.205
		c-27.869,11.804-51.508,31.439-68.231,56.187C9.793,193.956-0.016,223.971,0,256.004c0,21.34,4.342,41.818,12.205,60.4
		c11.804,27.885,31.438,51.516,56.187,68.24c24.716,16.724,54.74,26.526,86.773,26.518h44.222l-10.195,24.234
		c-1.335,3.176-0.53,6.842,1.994,9.158c2.541,2.315,6.256,2.798,9.295,1.19l108.932-57.57c2.669-1.407,4.342-4.181,4.326-7.188
		C313.739,377.97,312.082,375.188,309.413,373.796z"/>
</g>
</svg>"""
    
    REPEAT_RANDOM_SVG = """<svg fill="white" width="800px" height="800px" viewBox="0 0 14 14" role="img" focusable="false" aria-hidden="true" xmlns="http://www.w3.org/2000/svg"><path d="M 5.459789,4.64957 Q 5.058009,5.26564 4.542379,6.4777 4.395059,6.17636 4.294609,5.9922 4.194169,5.80805 4.023409,5.56698 3.852649,5.32591 3.681889,5.18863 3.511129,5.05136 3.260009,4.95426 3.008899,4.85716 2.714259,4.85716 H 1.214255 q -0.09375,0 -0.154018,-0.0603 Q 0.999969,4.73666 0.999969,4.64287 V 3.35716 q 0,-0.0937 0.06027,-0.15402 0.06027,-0.0603 0.154018,-0.0603 h 1.500004 q 1.6741,0 2.74553,1.5067 z m 7.54018,5.35045 q 0,0.0937 -0.0603,0.15402 l -2.14285,2.14285 q -0.0603,0.0603 -0.15402,0.0603 -0.0871,0 -0.15067,-0.0636 -0.0636,-0.0636 -0.0636,-0.15067 v -1.28571 q -0.21428,0 -0.5692,0.003 -0.35491,0.003 -0.54241,0.007 -0.1875,0.003 -0.48884,-0.007 -0.30133,-0.0101 -0.47544,-0.0335 -0.17411,-0.0234 -0.42857,-0.0703 -0.25447,-0.0469 -0.42188,-0.12388 -0.16741,-0.077 -0.38839,-0.19085 -0.22098,-0.11384 -0.39509,-0.26786 -0.17411,-0.15401 -0.3683,-0.35825 -0.1942,-0.20425 -0.375,-0.46541 0.39509,-0.62276 0.91071,-1.82812 0.14732,0.30134 0.24777,0.48549 0.10044,0.18415 0.2712,0.42522 0.17076,0.24107 0.34152,0.37835 0.17076,0.13728 0.42188,0.23438 0.25111,0.0971 0.54576,0.0971 h 1.71428 V 7.85687 q 0,-0.0937 0.0603,-0.15402 0.0603,-0.0603 0.15402,-0.0603 0.0803,0 0.16071,0.067 l 2.13616,2.13616 q 0.0603,0.0603 0.0603,0.15402 z m 0,-6 q 0,0.0937 -0.0603,0.15401 l -2.14285,2.14286 q -0.0603,0.0603 -0.15402,0.0603 -0.0871,0 -0.15067,-0.0636 -0.0636,-0.0636 -0.0636,-0.15067 V 4.85721 h -1.71428 q -0.32143,0 -0.58259,0.10045 -0.26116,0.10044 -0.46206,0.30134 -0.20089,0.20089 -0.34152,0.41183 -0.14062,0.21093 -0.30133,0.51897 -0.21429,0.41518 -0.52233,1.14509 -0.19419,0.44196 -0.33147,0.7433 -0.13728,0.30134 -0.36161,0.70313 -0.22433,0.40178 -0.42857,0.66964 -0.20424,0.26786 -0.49553,0.5558 -0.2913,0.28795 -0.60268,0.45871 -0.31139,0.17076 -0.71317,0.28125 -0.40179,0.11049 -0.85714,0.11049 H 1.214245 q -0.09375,0 -0.154018,-0.0603 -0.060258,-0.0603 -0.060258,-0.15404 V 9.35716 q 0,-0.0937 0.06027,-0.15402 0.06027,-0.0603 0.154018,-0.0603 h 1.500004 q 0.32142,0 0.58258,-0.10044 0.26117,-0.10045 0.46206,-0.30134 0.20089,-0.20089 0.34152,-0.41183 0.14062,-0.21094 0.30134,-0.51898 0.21428,-0.41517 0.52232,-1.14508 0.19419,-0.44197 0.33147,-0.74331 0.13728,-0.30134 0.36161,-0.70312 0.22433,-0.40179 0.42857,-0.66965 0.20424,-0.26785 0.49553,-0.5558 0.2913,-0.28795 0.60268,-0.45871 0.31139,-0.17075 0.71317,-0.28124 0.40179,-0.1105 0.85715,-0.1105 h 1.71428 V 1.85713 q 0,-0.0937 0.0603,-0.15402 0.0603,-0.0603 0.15402,-0.0603 0.0803,0 0.16071,0.067 l 2.13616,2.13616 q 0.0603,0.0603 0.0603,0.15402 z"/></svg>"""
    
    def __init__(self, parent=None, size=24):
        super().__init__(parent)
        
        self.theme = ThemeManager.instance()
        
        # Button state - start with repeat_all by default
        self.repeat_state = REPEAT_ALL # Default to REPEAT_ALL
        self.is_hovered = False
        self.is_pressed = False
        
        self._setup_svg_renderers()
        
        self.setFixedSize(int(size * 1.2), int(size * 1.2))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        
    def _setup_svg_renderers(self):
        """Set up the SVG renderers for all icons"""
        self.repeat_one_renderer = QSvgRenderer()
        self.repeat_all_renderer = QSvgRenderer()
        self.repeat_random_renderer = QSvgRenderer() # Added
        
        # Load SVG data
        self.repeat_one_renderer.load(QByteArray(self.REPEAT_ONE_SVG.encode()))
        self.repeat_all_renderer.load(QByteArray(self.REPEAT_ALL_SVG.encode()))
        self.repeat_random_renderer.load(QByteArray(self.REPEAT_RANDOM_SVG.encode())) # Added
        
    def paintEvent(self, event):
        """Paint the button with appropriate icon based on state"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Determine which renderer and color to use based on state
        if self.repeat_state == REPEAT_ONE:
            renderer = self.repeat_one_renderer
            fill_color = self.theme.get_color('accent', 'primary') 
        elif self.repeat_state == REPEAT_RANDOM:
            renderer = self.repeat_random_renderer
            fill_color = self.theme.get_color('accent', 'primary')
        else:  # REPEAT_ALL (Default)
            renderer = self.repeat_all_renderer
            # Use default text color for REPEAT_ALL state (visually less active)
            fill_color = self.theme.get_color('text', 'primary')
            
        # Get button dimensions
        size = min(self.width(), self.height())
        rect = QRectF(0, 0, size, size)
        
        # Draw background if hovered
        if self.is_hovered:
            # Get background color
            if self.is_pressed:
                bg_color = QColor(self.theme.get_color('background', 'quaternary'))
            else:
                bg_color = QColor(self.theme.get_color('background', 'tertiary'))
            
            # Draw rounded background
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(bg_color))
            painter.drawEllipse(rect)
        
        # Calculate padding for icon inside button
        padding = size * 0.2  # 20% padding on all sides
        icon_rect = rect.adjusted(padding, padding, -padding, -padding)
        
        # Dynamically change SVG fill color
        try:
            current_svg_data = ""
            original_fill = ''
            if self.repeat_state == REPEAT_RANDOM:
                current_svg_data = self.REPEAT_RANDOM_SVG
                original_fill = 'fill="#FFFFFF"' # Check SVG source if this is correct
            elif self.repeat_state == REPEAT_ONE:
                current_svg_data = self.REPEAT_ONE_SVG
                original_fill = 'fill="#FFFFFF"'
            else: # REPEAT_ALL
                current_svg_data = self.REPEAT_ALL_SVG
                original_fill = 'fill="#FFFFFF"'

            if current_svg_data and original_fill:
                 colored_svg = current_svg_data.replace(original_fill, f'fill="{fill_color}"')
                 if not renderer.load(QByteArray(colored_svg.encode('utf-8'))):
                      Logger.instance().error(caller="repeat_button", msg=f"Error reloading SVG for state {self.repeat_state} with color {fill_color}")
            elif not renderer.isValid(): # Fallback if color replacement fails or not needed
                 # Ensure *something* is loaded if the renderer became invalid
                 if self.repeat_state == REPEAT_RANDOM: renderer.load(QByteArray(self.REPEAT_RANDOM_SVG.encode()))
                 elif self.repeat_state == REPEAT_ONE: renderer.load(QByteArray(self.REPEAT_ONE_SVG.encode()))
                 else: renderer.load(QByteArray(self.REPEAT_ALL_SVG.encode()))
                 
        except Exception as e:
             Logger.instance().error(caller="repeat_button", msg=f"Error processing SVG color: {e}")
             # Ensure a default is loaded on error
             if not renderer.isValid(): renderer.load(QByteArray(self.REPEAT_ALL_SVG.encode()))

        renderer.render(painter, icon_rect)
        
    def sizeHint(self):
        """Provide a size hint for the widget"""
        return QSize(int(24 * 1.2), int(24 * 1.2))
        
    def mousePressEvent(self, event):
        """Handle mouse press event"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_pressed = True
            self.update()
            
    def mouseReleaseEvent(self, event):
        """Handle mouse release event to toggle state"""
        if event.button() == Qt.MouseButton.LeftButton and self.is_pressed:
            self.is_pressed = False
            
            # Toggle state only if mouse is still inside the button
            if self.rect().contains(event.position().toPoint()):
                self._toggle_state()
                self.clicked.emit()
                
            self.update()
            
    def enterEvent(self, event):
        """Handle mouse enter event"""
        self.is_hovered = True
        self.update()
        
    def leaveEvent(self, event):
        """Handle mouse leave event"""
        self.is_hovered = False
        self.update()
        
    def _toggle_state(self):
        """Toggle between the three states: repeat_all -> repeat_one -> repeat_random -> repeat_all"""
        if self.repeat_state == REPEAT_ALL:
            self.repeat_state = REPEAT_ONE
        elif self.repeat_state == REPEAT_ONE:
            self.repeat_state = REPEAT_RANDOM
        else:  # Must be REPEAT_RANDOM
            self.repeat_state = REPEAT_ALL
            
        self.state_changed.emit(self.repeat_state)
        self.update() 
        
    def get_state(self):
        """Get the current repeat state"""
        return self.repeat_state
        
    def set_state(self, state):
        """
        Set the repeat state directly.
        
        Args:
            state (str): One of REPEAT_ALL, REPEAT_ONE, REPEAT_RANDOM
        """
        allowed_states = [REPEAT_ALL, REPEAT_ONE, REPEAT_RANDOM]
        # If an invalid state (like the old REPEAT_NONE) is passed, default to REPEAT_ALL
        if state not in allowed_states:
            Logger.instance().warning(caller="repeat_button", msg=f"Warning: Invalid repeat state '{state}' passed to set_state. Defaulting to REPEAT_ALL.")
            state = REPEAT_ALL
             
        if state != self.repeat_state:
            self.repeat_state = state 
            self.state_changed.emit(self.repeat_state) # Emit the actual logical state
            self.update() # Repaint 