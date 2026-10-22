import pytest
from PySide6.QtWidgets import QApplication,QMainWindow,QStackedWidget,QWidget,QVBoxLayout
from artin_sentinel.app import MainWindow
import shiboken6

_APP=None

@pytest.fixture
def window():
    global _APP
    _APP=QApplication.instance() or QApplication([])
    win=MainWindow.__new__(MainWindow);QMainWindow.__init__(win)
    root=QWidget();layout=QVBoxLayout(root);win.setCentralWidget(root)
    win.pages=QStackedWidget();win.pages.addWidget(QWidget());win.pages.addWidget(QWidget())
    win.topbar=win.build_topbar();layout.addWidget(win.topbar);layout.addWidget(win.pages)
    win.build_devices_tab=lambda:win.config_tabs.addTab(QWidget(),'Equipamentos')
    win.build_akdb_tab=lambda:win.config_tabs.addTab(QWidget(),'AKDB')
    win.build_updates_tab=lambda:win.config_tabs.addTab(QWidget(),'Atualizações')
    win.build_configuration_page()
    yield win
    shiboken6.delete(win)


def test_main_navigation_opens_configuration_with_embedded_event_and_health(window):
    win=window
    assert [b.text() for b in win.nav_buttons]==['Ao vivo','Reprodução','Configuração']
    assert win.pages.count()==3
    assert [win.config_tabs.tabText(i) for i in range(win.config_tabs.count())]==['Equipamentos','Eventos','Saúde','AKDB','Atualizações']
    win.nav_buttons[-1].click()
    assert win.pages.currentIndex()==win.PAGE_CONFIG and win.nav_buttons[-1].isChecked()
    win.show_page(win.PAGE_EVENTS)
    assert win.config_tabs.currentWidget() is win.events_page
    assert win.events_page.isAncestorOf(win.event_table)
    win.show_page(win.PAGE_HEALTH)
    assert win.config_tabs.currentWidget() is win.health_page
    assert win.health_page.isAncestorOf(win.channel_health_table)
    assert win.nav_buttons[-1].isChecked()
    win.nav_buttons[1].click()
    assert win.pages.currentIndex()==win.PAGE_PLAYBACK and win.nav_buttons[1].isChecked()
