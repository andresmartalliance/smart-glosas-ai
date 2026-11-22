import type {SyntheticObjection} from './syntheticImport'

export type TriageAction =
  'REVISAR_CAUSAL' | 'VERIFICAR_SOPORTES' | 'VERIFICAR_CONTRATO' |
  'AUDITORIA_CLINICA' | 'SEGUIMIENTO_CONJUNTO' | 'REVISAR_DEVOLUCION'
export type SyntheticReview = {
  ref: string
  action: TriageAction
  actionLabel: string
  evidenceState: string
  priority: 'ALTA' | 'MEDIA'
  needs: string[]
  steps: string[]
  draft: string
  warning: string
}

const evidenceNeeds:Record<string,string> = {
  FA:'Factura detallada, registros de servicios y soportes del cobro',
  TA:'Contrato vigente, anexo tarifario y detalle del ítem facturado',
  SO:'Soporte pertinente y constancia de entrega a la EPS',
  AU:'Autorización cuando sea exigible y su correspondencia con el servicio',
  CO:'Información de afiliación, responsable de pago y cobertura aplicable',
  CL:'Historia clínica pertinente y criterio de auditor clínico',
  SA:'Contrato, nota técnica, actas e indicadores del seguimiento conjunto',
  DE:'Factura, constancia de radicación y documentos relacionados con la devolución'
}
const actionByFamily:Record<string,{key:TriageAction;label:string;steps:string[]}> = {
  FA:{key:'REVISAR_CAUSAL',label:'Conciliar lo facturado',steps:[
    'Comparar cantidades y conceptos de la factura contra los servicios documentados.',
    'Identificar diferencias comprobables antes de aceptar o controvertir la objeción.'
  ]},
  TA:{key:'VERIFICAR_CONTRATO',label:'Verificar condiciones tarifarias',steps:[
    'Localizar versión y vigencia del contrato y del anexo tarifario.',
    'Contrastar precio, unidad, paquete y eventuales excepciones pactadas.'
  ]},
  SO:{key:'VERIFICAR_SOPORTES',label:'Revisar soportes',steps:[
    'Determinar si el soporte objetado es exigible para esta atención.',
    'Verificar integridad del documento y constancia de entrega, sin asumir que su referencia acredita contenido.'
  ]},
  AU:{key:'REVISAR_CAUSAL',label:'Verificar autorización',steps:[
    'Confirmar si el servicio exige autorización y las excepciones aplicables.',
    'Contrastar fechas, cantidades, procedimientos y número de autorización.'
  ]},
  CO:{key:'REVISAR_CAUSAL',label:'Verificar cobertura y pagador',steps:[
    'Verificar responsable de pago y cobertura en la fecha de atención.',
    'Revisar fuentes y excepciones antes de concluir procedencia de la objeción.'
  ]},
  CL:{key:'AUDITORIA_CLINICA',label:'Remitir a auditoría clínica',steps:[
    'Reunir historia clínica pertinente, órdenes y evolución asistencial.',
    'Solicitar revisión por auditor clínico competente y documentar su criterio.'
  ]},
  SA:{key:'SEGUIMIENTO_CONJUNTO',label:'Revisar seguimiento contractual',steps:[
    'Verificar modalidad de pago, contrato, nota técnica y actas de seguimiento.',
    'Tramitar las desviaciones en el procedimiento de seguimiento conjunto que corresponda; no tratarlas como glosa inicial ordinaria.'
  ]},
  DE:{key:'REVISAR_DEVOLUCION',label:'Validar devolución y plazos',steps:[
    'Verificar causal, fecha de radicación, fecha de comunicación y oportunidad.',
    'Diferenciar controversia de la devolución, corrección documental y nueva radicación según proceda.'
  ]}
}
function makeDraft(item:SyntheticObjection, action:string, gaps:string[]):string {
  return [
    'BORRADOR INTERNO — NO RADICAR SIN VALIDACIÓN',
    'Referencia de la objeción: '+item.ref,
    'Cuenta: '+item.account+' | Pagador: '+(item.payer||'Por verificar'),
    'Tipo: '+(item.kind==='GLOSA'?'Glosa':'Devolución')+' | Código informado: '+item.code,
    '',
    'Objeto de la revisión:',
    item.description,
    '',
    'Actuación a evaluar: '+action+'.',
    'Se requiere contrastar la causal comunicada con los documentos, las condiciones aplicables y los términos legales vigentes.',
    'Evidencia pendiente de verificación: '+gaps.join('; ')+'.',
    '',
    '[A COMPLETAR POR AUDITOR: hechos comprobados, referencias exactas, fundamento aplicable y decisión motivada.]',
    '[A COMPLETAR: soportes adjuntos y constancia del canal autorizado.]',
    '',
    'ESTADO: borrador de trabajo pendiente de decisión de la IPS. No constituye una aceptación, controversia ni contestación enviada.'
  ].join('\n')
}
export function prepareSyntheticReview(item:SyntheticObjection):SyntheticReview {
  const family=item.code.slice(0,2).toUpperCase()
  const scenario=actionByFamily[family]??{
    key:'REVISAR_CAUSAL' as const,label:'Revisar causal no catalogada',
    steps:['Confirmar que el código informado corresponda al catálogo y versión aplicables.']
  }
  const support=item.support.trim().toUpperCase()
  const needs=[evidenceNeeds[family]??'Fuentes verificables de la cuenta y de la causal']
  let evidenceState='Evidencia referenciada, no verificada'
  switch(support){
    case 'FALTANTE':
      evidenceState='Soporte faltante'
      needs.push('Obtener el documento faltante y verificar si resulta exigible')
      break
    case 'CONTRADICTORIO':
      evidenceState='Evidencia contradictoria'
      needs.push('Conciliar versiones, fechas y cantidades de las fuentes contradictorias')
      break
    case 'PARCIAL':
      evidenceState='Evidencia parcial'
      needs.push('Completar la fuente documental antes de concluir')
      break
    case 'SIN_CONTRATO':
      evidenceState='Contrato o anexo no disponible'
      needs.push('Obtener versión contractual aplicable, sin presumir obligaciones pactadas')
      break
    case 'DISPONIBLE':
      needs.push('Abrir el documento original; la marca de disponible no verifica su contenido')
      break
    default:
      evidenceState='Disponibilidad no comprobada'
      needs.push('Confirmar qué soportes efectivamente existen')
  }
  if(family==='CL')needs.push('Concepto de pertinencia por profesional competente')
  if(family==='SA')needs.push('Resultado documentado del seguimiento conjunto')
  if(family==='DE')needs.push('Constancia de radicación y fechas efectivas para calcular términos')
  const priority: 'ALTA'|'MEDIA' =
    (family==='DE'||family==='CL'||family==='SA'||['FALTANTE','CONTRADICTORIO'].includes(support))?'ALTA':'MEDIA'
  return {
    ref:item.ref,
    action:scenario.key,
    actionLabel:scenario.label,
    evidenceState,
    priority,
    needs,
    steps:scenario.steps,
    draft:makeDraft(item,scenario.label,needs),
    warning:'Clasificación preliminar por familia del código y metadatos sintéticos. No se ha verificado normativa, contrato, documento ni plazo. Sin IA ni envío a EPS.'
  }
}
export function reviewCsv(items:SyntheticObjection[],drafts:Record<string,string>):string {
  const quote=(input:unknown)=>{
    let value=String(input??'')
    if(/^[=+@\-\t\r]/.test(value.trimStart()))value="'"+value
    return '"'+value.replace(/"/g,'""')+'"'
  }
  const headers=['objecion','cuenta','tipo','codigo','eps','valor_objetado_COP',
    'revision_preliminar','estado_soporte','prioridad','informacion_por_verificar','borrador_interno','estado']
  const records=items.map(item=>{
    const review=prepareSyntheticReview(item)
    return [item.ref,item.account,item.kind,item.code,item.payer,item.amount,
      review.actionLabel,review.evidenceState,review.priority,review.needs.join(' | '),
      drafts[item.ref]??review.draft,'PENDIENTE_REVISION_HUMANA']
  })
  return '\uFEFF'+[headers,...records].map(row=>row.map(quote).join(',')).join('\r\n')+'\r\n'
}
