def test_actions_fit_one_line_and_wrap_without_clipping():
    from PySide6.QtWidgets import QApplication,QWidget,QPushButton
    from PySide6.QtCore import QRect
    from artin_sentinel.action_flow import ActionFlowLayout
    app=QApplication.instance() or QApplication([])
    host=QWidget(); flow=ActionFlowLayout(host)
    buttons=[QPushButton(t) for t in ('Alterar senha de acesso…','Analisar desempenho deste PC…','Painel técnico…','Exportar equipamentos…','Importar equipamentos…','Acesso e permissões…')]
    for b in buttons: flow.addWidget(b)
    host.resize(1600,100);host.show();app.processEvents()
    flow.setGeometry(QRect(0,0,1600,100))
    assert len({b.y() for b in buttons})==1
    flow.setGeometry(QRect(0,0,650,200))
    assert len({b.y() for b in buttons})>1
    assert all(b.x()>=0 and b.geometry().right()<650 for b in buttons)
    host.close()

def test_tree_brand_is_original_not_protocol_and_not_repeated():
    from artin_sentinel.device_intelligence import device_tree_label
    assert device_tree_label({'name':'Escritório APR','manufacturer':'Intelbras'})=='Escritório APR · Intelbras'
    assert device_tree_label({'name':'DVR antigo','manufacturer':'Outra Marca','provider':'hikvision'})=='DVR antigo · Outra Marca'
    assert device_tree_label({'name':'Intelbras MHDX','manufacturer':'Intelbras'})=='Intelbras MHDX'
    assert device_tree_label({'name':'Web Viewer','manufacturer':'unknown','provider':'hikvision'})=='Web Viewer'

def test_actual_configuration_page_has_all_seven_actions_on_same_wide_row(tmp_path):
    from PySide6.QtWidgets import QApplication,QWidget,QStackedWidget,QPushButton
    from artin_sentinel.app import MainWindow
    from artin_sentinel.app import QSS
    app=QApplication.instance() or QApplication([])
    old_style=app.styleSheet();app.setStyleSheet(QSS)
    host=QWidget();host.pages=QStackedWidget()
    for name in ('change_app_password','export_portable_configuration','import_portable_configuration',
                 'build_devices_tab','build_events_page','build_health_page','build_akdb_tab','build_updates_tab'):
        setattr(host,name,lambda:None)
    MainWindow.build_configuration_page(host)
    host.pages.resize(1600,500);host.pages.show();app.processEvents()
    page=host.pages.widget(0)
    buttons=[b for b in page.findChildren(QPushButton) if b.isVisible()]
    assert len(buttons)==7
    assert len({b.mapTo(page,b.rect().topLeft()).y() for b in buttons})==1
    if __import__('os').environ.get('SENTINEL_LAYOUT_CAPTURE'):
        page.grab().save(__import__('os').environ['SENTINEL_LAYOUT_CAPTURE'])
    page.close();host.pages.close();host.close()
    app.setStyleSheet(old_style)
