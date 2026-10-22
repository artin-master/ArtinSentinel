"""Paint only the manufacturer suffix; names/channels and status icons stay intact."""
from PySide6.QtCore import Qt,QPointF
from PySide6.QtGui import QColor,QPalette,QTextLayout,QTextCharFormat
from PySide6.QtWidgets import QStyledItemDelegate,QStyleOptionViewItem,QStyle,QApplication
from artin_akdb.brands import BrandRegistry,NEUTRAL
from .device_intelligence import device_visual_name,_value

BRAND_ROLE=int(Qt.UserRole)+29
_registry=None

def registry(reload=False):
    from artin_akdb.brands import current_registry
    return current_registry(reload)

def brand_presentation(device,brands=None):
    brands=brands or registry()
    name=device_visual_name(device)
    brand=str(_value(device,'manufacturer','') or '').strip()
    unknown={'','unknown','generic','genérico','não identificado','não identificada','desconhecido','desconhecida'}
    if brand.casefold() in unknown:brand=str(_value(device,'detected_manufacturer','') or '').strip()
    if brand.casefold() in unknown:return name,None
    profile=brands.resolve(brand)
    brand=profile.name if profile else brand
    if brand.casefold() in name.casefold():return name,None
    text=f'{name} · {brand}'
    return text,(len(name)+3,len(brand),profile.color if profile else NEUTRAL)

def decorate_device_item(item,device,brands=None):
    text,span=brand_presentation(device,brands)
    item.setText(0,text);item.setData(0,BRAND_ROLE,span)

class BrandDelegate(QStyledItemDelegate):
    def paint(self,painter,option,index):
        span=index.data(BRAND_ROLE)
        if not span:return super().paint(painter,option,index)
        opt=QStyleOptionViewItem(option);self.initStyleOption(opt,index)
        style=opt.widget.style() if opt.widget else QApplication.style()
        text=opt.text
        rect=style.subElementRect(QStyle.SE_ItemViewItemText,opt,opt.widget)
        text=opt.fontMetrics.elidedText(text,opt.textElideMode,rect.width())
        opt.text='';style.drawControl(QStyle.CE_ItemViewItem,opt,painter,opt.widget)
        painter.save();painter.setClipRect(rect)
        foreground=opt.palette.color(QPalette.HighlightedText if opt.state & QStyle.State_Selected else QPalette.Text)
        painter.setPen(foreground);painter.setFont(opt.font)
        layout=QTextLayout(text,opt.font)
        fmt=QTextCharFormat();fmt.setForeground(QColor(span[2]))
        run=QTextLayout.FormatRange();run.start=span[0];run.length=max(0,min(span[1],len(text)-span[0]));run.format=fmt
        if run.length:layout.setFormats([run])
        layout.beginLayout();line=layout.createLine();line.setLineWidth(rect.width());layout.endLayout()
        layout.draw(painter,QPointF(rect.x(),rect.y()+(rect.height()-line.height())/2))
        painter.restore()

def install(tree):tree.setItemDelegate(BrandDelegate(tree))
