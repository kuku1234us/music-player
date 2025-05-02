"""
A FlowLayout implementation for PyQt6.
Similar to Qt Designer's Flow Layout example but adapted for PyQt6.
"""

from PyQt6.QtCore import Qt, QSize, QRect, QPoint
from PyQt6.QtWidgets import QLayout, QLayoutItem, QWidgetItem, QStyle


class FlowLayout(QLayout):
    """A flow layout that arranges widgets in a wrap-around grid pattern."""
    
    def __init__(self, parent=None, margin=0, spacing=-1):
        """Initialize the flow layout."""
        super().__init__(parent)
        
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        
        self.setSpacing(spacing)
        
        self.items = []
    
    def __del__(self):
        """Delete all items in the layout."""
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)
    
    def addItem(self, item):
        """Add an item to the layout."""
        self.items.append(item)
    
    def count(self):
        """Return the number of items in the layout."""
        return len(self.items)
    
    def itemAt(self, index):
        """Return the item at the given index."""
        if 0 <= index < len(self.items):
            return self.items[index]
        return None
    
    def takeAt(self, index):
        """Remove and return the item at the given index."""
        if 0 <= index < len(self.items):
            return self.items.pop(index)
        return None
    
    def expandingDirections(self):
        """Return the expanding directions of the layout."""
        return Qt.Orientation(0)
    
    def hasHeightForWidth(self):
        """Return whether the layout has a preferred height for a given width."""
        return True
    
    def heightForWidth(self, width):
        """Calculate the preferred height for the given width."""
        return self._doLayout(QRect(0, 0, width, 0), True)
    
    def setGeometry(self, rect):
        """Set the geometry of the layout items."""
        super().setGeometry(rect)
        self._doLayout(rect, False)
    
    def sizeHint(self):
        """Return the preferred size of the layout."""
        return self.minimumSize()
    
    def minimumSize(self):
        """Return the minimum size of the layout."""
        size = QSize()
        
        for item in self.items:
            size = size.expandedTo(item.minimumSize())
        
        margin = self.contentsMargins()
        size += QSize(margin.left() + margin.right(), margin.top() + margin.bottom())
        
        return size
    
    def _doLayout(self, rect, testOnly):
        """Perform the layout calculations.
        
        Args:
            rect: The rectangle to lay out in
            testOnly: If True, only calculate the height; if False, actually set item geometries
            
        Returns:
            The required height for the layout
        """
        x = rect.x()
        y = rect.y()
        lineHeight = 0
        spacing = self.spacing()
        margin = self.contentsMargins()
        
        # Adjust for margins
        x += margin.left()
        y += margin.top()
        
        # Calculate effective width (width minus margins)
        effectiveWidth = rect.width() - margin.left() - margin.right()
        
        for item in self.items:
            wid = item.widget()
            
            # Get item size (use sizeHint if it's a widget, otherwise minimumSize)
            if wid:
                nextWidth = wid.sizeHint().width()
                nextHeight = wid.sizeHint().height()
            else:
                nextWidth = item.sizeHint().width()
                nextHeight = item.sizeHint().height()
            
            # If adding this item would exceed the width, move to the next row
            if x + nextWidth > effectiveWidth and lineHeight > 0:
                x = rect.x() + margin.left()
                y = y + lineHeight + spacing
                lineHeight = 0
            
            # Set the item's geometry (if not just testing)
            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            
            # Update position and line height
            x = x + nextWidth + spacing
            lineHeight = max(lineHeight, nextHeight)
        
        # Calculate total height including the last row
        totalHeight = y + lineHeight - rect.y() + margin.bottom()
        
        return totalHeight
    
    def removeWidget(self, widget):
        """Remove a widget from the layout."""
        for i in range(len(self.items) - 1, -1, -1):
            item = self.items[i]
            if item.widget() == widget:
                self.takeAt(i)
                widget.setParent(None)
                self.update()
                return 