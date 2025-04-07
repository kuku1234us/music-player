"""
Album art display component for showing track/album artwork.
"""
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QSizePolicy
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath, QBrush, QColor


class AlbumArtDisplay(QWidget):
    """
    Widget for displaying album artwork with rounded corners and
    placeholder for when no image is available.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("albumArtDisplay")
        
        # Default size
        self.setMinimumSize(200, 200)
        
        # UI Components
        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.image_label.setMinimumSize(200, 200)
        
        # Current pixmap
        self.current_pixmap = None
        
        self._setup_ui()
        self._set_placeholder()
        
    def _setup_ui(self):
        """Set up the album art display layout"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.image_label)
        self.setLayout(layout)
        
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
        """Set a placeholder image when no album art is available"""
        # Create a transparent placeholder pixmap
        size = self.image_label.size()
        if size.width() <= 0 or size.height() <= 0:
            size = QSize(200, 200)
            
        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        # Just set the transparent pixmap without drawing anything
        self.current_pixmap = pixmap
        self._update_display()
        
    def _update_display(self):
        """Update the display with the current pixmap, applying rounded corners"""
        if not self.current_pixmap:
            return
            
        # Get the widget size
        size = self.image_label.size()
        if size.width() <= 0 or size.height() <= 0:
            size = QSize(200, 200)
        
        # Create a new pixmap with the widget's size
        rounded_pixmap = QPixmap(size)
        rounded_pixmap.fill(Qt.GlobalColor.transparent)
        
        # Create a rounded rect path for clipping
        painter = QPainter(rounded_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, size.width(), size.height(), 10, 10)
        painter.setClipPath(path)
        
        # Scale the image to fill (cover) the entire area
        # This will maintain aspect ratio but may clip parts of the image
        source_size = self.current_pixmap.size()
        target_rect = size
        
        # Calculate scaling factors for both dimensions
        scale_width = target_rect.width() / source_size.width()
        scale_height = target_rect.height() / source_size.height()
        
        # Use the larger scaling factor to ensure the image covers the entire area
        scale_factor = max(scale_width, scale_height)
        
        # Calculate the new dimensions
        new_width = source_size.width() * scale_factor
        new_height = source_size.height() * scale_factor
        
        # Calculate position to center the image (ensuring even cropping on both sides)
        pos_x = (target_rect.width() - new_width) / 2
        pos_y = (target_rect.height() - new_height) / 2
        
        # Scale the image and draw it
        scaled_pixmap = self.current_pixmap.scaled(
            int(new_width),
            int(new_height),
            Qt.AspectRatioMode.IgnoreAspectRatio,  # We're handling aspect ratio manually
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
        self._update_display()
        
    def sizeHint(self):
        """Provide a size hint for the widget"""
        return QSize(300, 300) 