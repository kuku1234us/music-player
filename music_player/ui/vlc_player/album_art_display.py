"""
Album art display component for showing track/album artwork.
"""
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QSizePolicy
from PyQt6.QtCore import Qt, QSize, QPointF, QRectF
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath, QBrush, QColor, QPen
from PyQt6.QtSvg import QSvgRenderer
from io import BytesIO


class AlbumArtDisplay(QWidget):
    """
    Widget for displaying album artwork with rounded corners and
    placeholder for when no image is available.
    """
    
    # SVG music icon as a string
    MUSIC_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-music-icon lucide-music"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("albumArtDisplay")
        
        # Default size (but this can be overridden by parent)
        self.setMinimumSize(200, 200)
        
        # UI Components
        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.image_label.setMinimumSize(200, 200)
        
        # Current pixmap
        self.current_pixmap = None
        
        # Create SVG renderer for music icon
        self.svg_renderer = QSvgRenderer(bytes(self.MUSIC_ICON_SVG, encoding='utf-8'))
        
        self._setup_ui()
        self._set_placeholder()
        
    def _setup_ui(self):
        """Set up the album art display layout"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.image_label)
        
        # Apply styling
        self.setStyleSheet("""
            QWidget#albumArtDisplay {
                background-color: #2d2d2d;
                border-radius: 10px;
            }
        """)
        
    def set_image(self, image_path):
        """
        Set the album artwork from a file path.
        
        Args:
            image_path (str): Path to the image file
        """
        pixmap = QPixmap(image_path)
        
        if pixmap.isNull():
            self._set_placeholder()
            return
            
        self.current_pixmap = pixmap
        self._update_display()
        
    def set_image_from_pixmap(self, pixmap):
        """
        Set the album artwork from a QPixmap.
        
        Args:
            pixmap (QPixmap): The pixmap to display
        """
        if pixmap.isNull():
            self._set_placeholder()
            return
            
        self.current_pixmap = pixmap
        self._update_display()
        
    def _set_placeholder(self):
        """Set a placeholder image with an SVG music icon when no album art is available"""
        # Get the widget size
        size = self.size()
        if size.width() <= 0 or size.height() <= 0:
            size = QSize(200, 200)
            
        # Create a placeholder pixmap with gray background
        pixmap = QPixmap(size)
        pixmap.fill(QColor("#383838"))  # Dark gray background
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Set up the music icon color
        icon_color = QColor("#909090")  # Light gray for the icon
        painter.setPen(QPen(icon_color, 2))
        
        # Calculate icon size as 50% of the widget size
        icon_width = size.width() * 0.5
        icon_height = size.height() * 0.5
        
        # Calculate position to center the icon
        x = (size.width() - icon_width) / 2
        y = (size.height() - icon_height) / 2
        
        # Create a target rectangle for the SVG
        target_rect = QRectF(x, y, icon_width, icon_height)
        
        # Special handling for SVG rendering with currentColor
        modified_svg = self.MUSIC_ICON_SVG.replace('currentColor', icon_color.name())
        temp_renderer = QSvgRenderer(bytes(modified_svg, encoding='utf-8'))
        
        # Render the SVG to the pixmap
        temp_renderer.render(painter, target_rect)
        
        painter.end()
        
        # Set the pixmap
        self.current_pixmap = pixmap
        self._update_display()
        
    def _update_display(self):
        """Update the display with the current pixmap, applying rounded corners"""
        if not self.current_pixmap:
            return
            
        # Get the widget size
        size = self.size()
        if size.width() <= 0 or size.height() <= 0:
            size = QSize(200, 200)
        
        # Small thumbnail uses smaller corner radius
        corner_radius = 10
        if size.width() <= 100 or size.height() <= 100:
            corner_radius = 5
        
        # Create a new pixmap with the widget's size
        rounded_pixmap = QPixmap(size)
        rounded_pixmap.fill(Qt.GlobalColor.transparent)
        
        # Create a rounded rect path for clipping
        painter = QPainter(rounded_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, size.width(), size.height(), corner_radius, corner_radius)
        painter.setClipPath(path)
        
        # Scale the image to fill (cover) the entire area
        # This will maintain aspect ratio but may clip parts of the image
        source_size = self.current_pixmap.size()
        
        # Calculate scaling factors for both dimensions
        scale_width = size.width() / source_size.width()
        scale_height = size.height() / source_size.height()
        
        # Use the larger scaling factor to ensure the image covers the entire area
        scale_factor = max(scale_width, scale_height)
        
        # Calculate the new dimensions
        new_width = source_size.width() * scale_factor
        new_height = source_size.height() * scale_factor
        
        # Calculate position to center the image (ensuring even cropping on both sides)
        pos_x = (size.width() - new_width) / 2
        pos_y = (size.height() - new_height) / 2
        
        # Scale the image and draw it
        scaled_pixmap = self.current_pixmap.scaled(
            int(new_width),
            int(new_height),
            Qt.AspectRatioMode.KeepAspectRatio,  # Keep aspect ratio
            Qt.TransformationMode.SmoothTransformation
        )
        
        # Draw the image
        painter.drawPixmap(int(pos_x), int(pos_y), scaled_pixmap)
        painter.end()
        
        # Set the rounded pixmap to the label
        self.image_label.setPixmap(rounded_pixmap)
        
    def resizeEvent(self, event):
        """Handle resize events to update the display"""
        super().resizeEvent(event)
        # Update the image_label size to match our size
        self.image_label.setFixedSize(self.size())
        self._update_display()
        
    def sizeHint(self):
        """Provide a size hint for the widget"""
        return QSize(300, 300) 