"""Compact action rows that wrap only when their natural widths do not fit."""
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtWidgets import QLayout


class ActionFlowLayout(QLayout):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._items=[]
        self.setContentsMargins(0,0,0,0)
        self.setSpacing(6)

    def addItem(self,item): self._items.append(item)
    def count(self): return len(self._items)
    def itemAt(self,index): return self._items[index] if 0<=index<len(self._items) else None
    def takeAt(self,index): return self._items.pop(index) if 0<=index<len(self._items) else None
    def expandingDirections(self): return Qt.Orientations()
    def hasHeightForWidth(self): return True
    def heightForWidth(self,width): return self._arrange(QRect(0,0,width,0),False)
    def minimumSize(self):
        size=QSize()
        for item in self._items: size=size.expandedTo(item.minimumSize())
        return size
    def sizeHint(self): return self.minimumSize()
    def setGeometry(self,rect):
        super().setGeometry(rect)
        self._arrange(rect,True)
    def _arrange(self,rect,apply):
        x=rect.x(); y=rect.y(); height=0
        for item in self._items:
            if item.isEmpty(): continue
            hint=item.sizeHint()
            width=min(hint.width(),max(1,rect.width()))
            if x>rect.x() and x+width>rect.x()+rect.width():
                x=rect.x();y+=height+self.spacing();height=0
            if apply: item.setGeometry(QRect(x,y,width,hint.height()))
            x+=width+self.spacing();height=max(height,hint.height())
        return y+height-rect.y()
