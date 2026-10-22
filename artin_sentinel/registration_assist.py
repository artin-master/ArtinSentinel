"""Explain observed identity versus model knowledge without inventing access."""
def registration_conflicts(known,device):
    """IP reuse never overrides contradictory unit identifiers automatically."""
    conflicts=list(device.metadata.get('identity_conflicts') or [])
    if known is not None:
        from .config_portability import _serial,_mac,_uuid
        for key,label,normalizer in (('serial','serial',_serial),('mac','MAC',_mac),('uuid','UUID',_uuid)):
            try:
                first=normalizer(str(known[key] or ''))
                second=normalizer(str(getattr(device,key,'') or ''))
            except (ValueError,KeyError,IndexError):continue
            if first and second and first!=second:
                conflicts.append('Conflito de '+label+' entre descoberta e cadastro; revisar a identidade física.')
    return list(dict.fromkeys(conflicts))

def evidence_summary(metadata):
    if not isinstance(metadata,dict):metadata={}
    evidence=metadata.get('identity_evidence_v1') or {}
    if not isinstance(evidence,dict) or not evidence:
        manual=metadata.get('manual_akdb_reference') or {}
        if isinstance(manual,dict) and manual.get('stable_id'):
            return 'Cadastro manual • referência AKDB escolhida pelo operador: '+str(manual['stable_id'])+'\nAcesso e recursos deste aparelho exigem verificação.'
        return 'Origem detalhada não registrada nesta versão da descoberta; consulte evidências anteriores.'
    observed=evidence.get('observed') or {}
    if not isinstance(observed,dict):observed={}
    source_values=evidence.get('sources') or []
    if not isinstance(source_values,list):source_values=[]
    sources=', '.join(str(v)[:100] for v in source_values[:16] if v) or 'Origem não individualizada'
    stamp=evidence.get('observed_at') or 'horário não registrado'
    values=' / '.join(str(observed.get(k) or '') for k in ('manufacturer','model') if observed.get(k)) or 'Sem fabricante/modelo observados'
    lines=[f'Evidência da descoberta ({stamp}): {values}',f'Fontes: {sources}']
    suggestion=metadata.get('registration_suggestions') or {}
    if not isinstance(suggestion,dict):suggestion={}
    if suggestion:
        lines.append(f"Referência AKDB: {suggestion.get('stable_id','')} • {suggestion.get('confidence',0)}% • "+('identificação aplicada' if suggestion.get('applied') else 'sugestão para revisão'))
        if suggestion.get('ports_candidates'):lines.append('Portas candidatas, não confirmadas: '+', '.join(map(str,suggestion['ports_candidates'])))
        if suggestion.get('channel_capacity'):lines.append('Capacidade de referência do modelo: '+str(suggestion['channel_capacity'])+'; canais reais exigem leitura.')
    lines.extend(str(v) for v in (metadata.get('identity_conflicts') or []) if v)
    lines.append('Conhecimento de modelo não confirma senha, acesso, canais ou recursos deste aparelho.')
    return '\n'.join(lines)

def add_reference_picker(form,parent,manufacturer,model,kind,protocol):
    """An explicit optional choice fills empty identification fields only."""
    from types import SimpleNamespace
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QComboBox,QPushButton,QLabel,QCompleter
    from .model_catalog import catalog_models
    from artin_akdb.brands import current_registry,canonical_manufacturer,normalize
    brands=current_registry()
    manufacturer.setCompleter(QCompleter([p.name for p in brands.all()],manufacturer))
    choice=QComboBox();choice.addItem('Opcional • escolher modelo conhecido…',None)
    choice.setMinimumContentsLength(25);choice.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    models=[r for r in catalog_models() if r['model'] and r['type']!='unknown']
    for row in models:choice.addItem(row['manufacturer']+' · '+row['model'],row)
    state={'applied':None}
    notice=QLabel('A referência preenche somente campos vazios. IP, URLs, senhas e recursos não são confirmados pela AKDB.')
    notice.setWordWrap(True);notice.setTextFormat(Qt.PlainText)
    def apply():
        row=choice.currentData()
        if not row:return
        different_brand=manufacturer.text().strip() and normalize(canonical_manufacturer(manufacturer.text()))!=normalize(canonical_manufacturer(row['manufacturer']))
        different_model=model.text().strip() and normalize(model.text()).replace(' ','')!=normalize(row['model']).replace(' ','')
        if different_brand or different_model:
            notice.setText('A identificação preenchida diverge da referência escolhida. Nenhum campo foi alterado. Revise o perfil ou limpe os campos que deseja preencher.')
            return
        if not manufacturer.text().strip():manufacturer.setText(row['manufacturer'])
        if not model.text().strip():model.setText(row['model'])
        if kind.currentData()=='unknown':
            canonical=row['type'];value='camera' if canonical.startswith('camera') else canonical
            index=kind.findData(value)
            if index>=0:kind.setCurrentIndex(index)
        if not protocol.currentData():
            provider=row['provider'];value='hikvision' if provider in {'hikvision','jfl'} else 'intelbras' if provider=='intelbras' else ''
            index=protocol.findData(value)
            if index>=0:protocol.setCurrentIndex(index)
        state['applied']={'stable_id':row['id'],'source':'operator-selected-akdb','requires_verification':True}
        notice.setText('Referência escolhida: '+row['id']+'\nCampos já preenchidos foram preservados. Confirme o modelo, protocolo e recursos no aparelho.')
    choice.currentIndexChanged.connect(lambda:state.update(applied=None))
    button=QPushButton('Preencher campos vazios');button.clicked.connect(apply)
    form.addRow('Referência AKDB',choice);form.addRow('',button);form.addRow('',notice)
    return SimpleNamespace(choice=choice,apply=apply,notice=notice,state=state)
