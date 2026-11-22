<script setup lang="ts">
import {computed, onMounted, ref} from 'vue'
import {inspectSyntheticFile, type SyntheticImportResult, type SyntheticObjection} from './syntheticImport'

type View = 'resumen'|'prevent'|'respond'|'reglas'|'historial'
type Institute={id:string;name:string;roles:string[]}
type Profile={email:string;institutions:Institute[];can_create_institution:boolean}
type Rule={id:string;rule_key:string;version:number;name:string;phase:string;category:string;scope:Record<string,string>}
type Summary={id:string;phase:string;account_ref:string;payer:string|null;objection_ref?:string|null;summary:string;status:string;counts:{review:number;insufficient:number;passed:number}}
type Finding={rule_key:string;rule_version:number;status:string;category:string;severity:string;message:string;recommendation:string|null;source_ref:string|null}
type Analysis={ai_review?:AIReview|null;id:string;status:string;phase:string;account_ref:string;objection_ref?:string;objection_kind?:string;objection_code?:string;summary:string;counts:{review:number;insufficient:number;passed:number};findings:Finding[];response_draft?:string|null;draft_options?:Array<{action:string;text:string;rule_key:string;source_ref:string;supporting_evidence:Array<{id:string;kind:string;reference?:string}>}>;requires_human_review:boolean}
type AIReview={summary:string;suggested_action:string;draft:string|null;missing_information:string[];warnings:string[];requires_human_review:boolean;model:string}

const API=(import.meta.env.VITE_API_URL||'http://localhost:8080').replace(/\/$/,'')
const HOST_ORIGIN=import.meta.env.VITE_SMART_HOST_ORIGIN||''
const view=ref<View>('resumen')
const credential=ref('')
const preview=ref(false)
const previewAvailable=import.meta.env.VITE_STANDALONE_PREVIEW==='true'
const me=ref<Profile|null>(null)
const tenantId=ref('')
const geminiAvailable=ref(false)
const ready=ref(false)
const error=ref('')
const notification=ref('')
const busy=ref(false)
const records=ref<Summary[]>([])
const rules=ref<Rule[]>([])
const recentResults=ref<Analysis[]>([])
const canWriteRules=computed(()=>me.value?.institutions.find(t=>t.id===tenantId.value)?.roles.some(r=>['ADMIN','CONFIGURADOR'].includes(r))||false)
const institution=computed(()=>me.value?.institutions.find(t=>t.id===tenantId.value))
const nav:{id:View;label:string;num:string}[]=[
  {id:'resumen',label:'Inicio',num:'01'},
  {id:'prevent',label:'Prevenir glosas',num:'02'},
  {id:'respond',label:'Responder glosas',num:'03'},
  {id:'historial',label:'Seguimiento',num:'04'},
  {id:'reglas',label:'Configuración',num:'05'}
]
const preventAccount=ref('')
const preventPayer=ref('')
const preventModality=ref('')
const preventService=ref('')
const preventFacts=ref('{}')
const preventEvidence=ref('')
const respondAccount=ref('')
const respondPayer=ref('')
const respondModality=ref('')
const respondService=ref('')
const objectionRef=ref('')
const objectionKind=ref<'GLOSA'|'DEVOLUCION'>('GLOSA')
const objectionCode=ref('')
const objectionDescription=ref('')
const objectionAmount=ref('')
const respondFacts=ref('{}')
const respondEvidence=ref('')
const upload=ref<File|null>(null)
const syntheticImport=ref<SyntheticImportResult|null>(null)
const selectedSynthetic=ref<SyntheticObjection|null>(null)
const formatCOP=(value:number)=>new Intl.NumberFormat('es-CO',{style:'currency',currency:'COP',maximumFractionDigits:0}).format(value)
const fileColumns=ref<string[]>([])
const mapping=ref<Record<string,string>>({})
const importPhase=ref<'PREVENT'|'RESPOND'>('PREVENT')
const importCount=ref(0)
const importErrors=ref<Array<{row:number;issue:string}>>([])
const newRule=ref({name:'',rule_key:'',phase:'BOTH',category:'',payer:'',modality:'',service_type:'',field:'',operator:'exists',value:'',evidenceKinds:'',severity:'MEDIUM',finding:'',recommendation:'',sourceRef:'',responseAction:'',responseTemplate:''})

async function request<T>(path:string,method='GET',body?:unknown):Promise<T>{
  const headers:Record<string,string>={Authorization:'Bearer '+credential.value}
  if(tenantId.value)headers['X-Tenant-Id']=tenantId.value
  if(body!==undefined&&!(body instanceof FormData))headers['Content-Type']='application/json'
  const response=await fetch(API+path,{method,headers,cache:'no-store',...(body!==undefined?{body:body instanceof FormData?body:JSON.stringify(body)}:{})})
  let data:unknown
  try{data=await response.json()}catch{data={}}
  if(!response.ok){
    const detail=(data as {detail?:unknown}).detail
    throw new Error(typeof detail==='string'?detail:'Error al procesar la solicitud ('+response.status+')')
  }
  return data as T
}
async function loadWorkspace(){
  if(!tenantId.value)return
  const [r,h]=await Promise.all([request<Rule[]>('/api/v1/rules'),request<Summary[]>('/api/v1/analyses')])
  rules.value=r;records.value=h
}
async function attachHostContext(token:string){
  preview.value=false
  busy.value=true;error.value=''
  try{
    credential.value=token
    const user=await request<Profile>('/api/v1/session')
    me.value=user
    tenantId.value=user.institutions[0]?.id||''
    await loadWorkspace()
  }catch(e){credential.value='';me.value=null;tenantId.value='';error.value=message(e)}
  finally{busy.value=false}
}
function message(e:unknown){return e instanceof Error?e.message:'No fue posible completar la operación'}
onMounted(async()=>{
  // Direct standalone access opens the complete product navigation in a
  // safe, read-only state. Live operations still require signed Smart context.
  if(previewAvailable && window.parent===window)preview.value=true
  try{
    const c=await fetch(API+'/api/v1/config').then(r=>r.json()) as {gemini_available:boolean}
    geminiAvailable.value=Boolean(c.gemini_available)
  }catch{error.value='No se pudo conectar con Smart Glosas AI.'}
  ready.value=true
  window.addEventListener('message',(event:MessageEvent)=>{
    if(!HOST_ORIGIN||event.origin!==HOST_ORIGIN||event.source!==window.parent)return
    if(event.data?.type==='SMART_GLOSAS_CONTEXT'&&typeof event.data.token==='string'){
      void attachHostContext(event.data.token)
    }
  })
  if(HOST_ORIGIN&&window.parent!==window)window.parent.postMessage({type:'SMART_GLOSAS_READY'},HOST_ORIGIN)
})
async function selectInstitution(id:string){
  tenantId.value=id;error.value='';notification.value='';recentResults.value=[]
  try{await loadWorkspace()}catch(e){error.value=message(e)}
}
function parseFacts(text:string):Record<string,unknown>{
  const result=JSON.parse(text) as unknown
  if(!result||typeof result!=='object'||Array.isArray(result))throw Error('Los datos adicionales deben ser un objeto JSON.')
  return result as Record<string,unknown>
}
function parseEvidence(text:string){
  return text.split('\n').map((line,i)=>{
    const [kind,reference]=line.split('|').map(x=>x?.trim())
    if(!kind&&!reference)return null
    if(!kind||!reference)throw Error('Cada soporte necesita un tipo y una referencia separados por |.')
    return {id:'ref-'+(i+1),kind,reference}
  }).filter((value):value is {id:string;kind:string;reference:string}=>value!==null)
}
function accountFromInputs(phase:'PREVENT'|'RESPOND'){
  const p=phase==='PREVENT'
  const account_ref=(p?preventAccount.value:respondAccount.value).trim()
  if(!account_ref)throw Error('Indica la referencia de la cuenta.')
  return {account_ref,payer:(p?preventPayer.value:respondPayer.value)||null,
    modality:(p?preventModality.value:respondModality.value)||null,
    service_type:(p?preventService.value:respondService.value)||null,
    facts:parseFacts(p?preventFacts.value:respondFacts.value),
    evidence:parseEvidence(p?preventEvidence.value:respondEvidence.value)}
}
async function runIndividual(phase:'PREVENT'|'RESPOND'){
  busy.value=true;error.value='';notification.value=''
  try{
    let payload:unknown
    if(phase==='PREVENT')payload={accounts:[accountFromInputs(phase)]}
    else{
      if(!objectionRef.value.trim()||!objectionDescription.value.trim())throw Error('Completa la referencia y la descripción de la objeción.')
      payload={objections:[{objection_ref:objectionRef.value,kind:objectionKind.value,
        code:objectionCode.value||null,description:objectionDescription.value,
        amount:objectionAmount.value.trim()?objectionAmount.value.trim():null,
        account:accountFromInputs(phase)}]}
    }
    const path=phase==='PREVENT'?'/api/v1/analyses/prevent':'/api/v1/analyses/respond'
    const result=await request<{analyses:Analysis[]}>(path,'POST',payload)
    recentResults.value=result.analyses
    await loadWorkspace()
    notification.value='Análisis registrado. Revisa los hallazgos y evidencias.'
  }catch(e){error.value=message(e)}finally{busy.value=false}
}
function importTargetFields(phase:'PREVENT'|'RESPOND'){
  return phase==='PREVENT'?['account_ref','payer','modality','service_type','issued_on']:
    ['objection_ref','kind','description','code','amount','account_ref','payer','modality','service_type','issued_on']
}
function selectFile(event:Event,phase:'PREVENT'|'RESPOND'){
  upload.value=(event.target as HTMLInputElement).files?.[0]||null
  importPhase.value=phase;fileColumns.value=[];mapping.value={};importErrors.value=[];importCount.value=0
  syntheticImport.value=null;selectedSynthetic.value=null;error.value='';notification.value=''
  if(preview.value&&phase==='RESPOND'&&upload.value)void inspectFile()
}
async function inspectFile(){
  if(!upload.value)return
  busy.value=true;error.value=''
  try{
    if(preview.value){
      if(importPhase.value!=='RESPOND')throw Error('La importación de prueba está habilitada en Responder glosas.')
      // Parse locally. Do not send uploaded test files to Railway, Gemini or any external service.
      const parsed=await inspectSyntheticFile(upload.value)
      syntheticImport.value=parsed
      selectedSynthetic.value=parsed.items[0]||null
      notification.value='Archivo leído en este navegador. No se ha enviado ni guardado información.'
      return
    }
    const form=new FormData();form.append('file',upload.value)
    const endpoint=importPhase.value==='PREVENT'?'/api/v1/imports/preview':'/api/v1/imports/objections/preview'
    const res=await request<{columns:string[];rows_detected:number}>(endpoint,'POST',form)
    fileColumns.value=res.columns;importCount.value=res.rows_detected
  }catch(e){syntheticImport.value=null;error.value=message(e)}finally{busy.value=false}
}
async function processImport(){
  if(preview.value||!upload.value)return
  busy.value=true;error.value='';notification.value=''
  try{
    const form=new FormData();form.append('file',upload.value)
    const chosen=Object.fromEntries(Object.entries(mapping.value).filter(([,v])=>v))
    form.append('mapping_json',JSON.stringify(chosen))
    const endpoint=importPhase.value==='PREVENT'?'/api/v1/imports/preview':'/api/v1/imports/objections/preview'
    const parsed=await request<{rows:unknown[];errors:Array<{row:number;issue:string}>;accepted:number}>(endpoint,'POST',form)
    importErrors.value=parsed.errors
    if(!parsed.accepted)throw Error('Ninguna fila pudo normalizarse. Revisa los campos.')
    const path=importPhase.value==='PREVENT'?'/api/v1/analyses/prevent':'/api/v1/analyses/respond'
    const payload=importPhase.value==='PREVENT'?{accounts:parsed.rows}:{objections:parsed.rows}
    const finished=await request<{analyses:Analysis[]}>(path,'POST',payload)
    recentResults.value=finished.analyses
    notification.value=finished.analyses.length+' análisis registrados. '+(parsed.errors.length?'Filas con error: '+parsed.errors.length+'.':'')
    await loadWorkspace()
  }catch(e){error.value=message(e)}finally{busy.value=false}
}
async function approve(id:string){
  busy.value=true;error.value=''
  try{
    await request('/api/v1/analyses/'+id+'/approve','POST')
    const current=recentResults.value.find(x=>x.id===id)
    if(current)current.status='APPROVED'
    await loadWorkspace()
    notification.value='Revisión aprobada internamente. No se ha enviado a ninguna EPS.'
  }catch(e){error.value=message(e)}finally{busy.value=false}
}
async function askGemini(item:Analysis){
  busy.value=true;error.value='';notification.value=''
  try{
    const response=await request<{id:string;ai_review:AIReview}>('/api/v1/analyses/'+item.id+'/ai-review','POST')
    item.ai_review=response.ai_review
    notification.value='Clara preparó una propuesta para revisión humana. No se envió a la EPS.'
  }catch(e){error.value=message(e)}finally{busy.value=false}
}
function expectedValue(value:string){
  const t=value.trim()
  if(t==='true')return true
  if(t==='false')return false
  if(t!==''&&!Number.isNaN(Number(t)))return Number(t)
  return value
}
async function createRule(){
  busy.value=true;error.value=''
  try{
    const r=newRule.value
    if(!r.rule_key||!r.name||!r.field||!r.finding||!r.recommendation||!r.category)throw Error('Completa los campos de la regla.')
    const scope:Record<string,string>={}
    if(r.payer.trim())scope.payer=r.payer.trim()
    if(r.modality.trim())scope.modality=r.modality.trim()
    if(r.service_type.trim())scope.service_type=r.service_type.trim()
    const body={rule_key:r.rule_key,name:r.name,phase:r.phase,category:r.category,
      scope,check:{field:r.field,operator:r.operator,...(r.operator!=='exists'?{value:expectedValue(r.value)}:{})},
      severity:r.severity,evidence_kinds:r.evidenceKinds.split(',').map(s=>s.trim()).filter(Boolean),
      finding:r.finding,recommendation:r.recommendation,source_ref:r.sourceRef||null,
      response_action:r.responseAction||null,response_template:r.responseTemplate||null}
    await request('/api/v1/rules','POST',body)
    await loadWorkspace()
    notification.value='Regla guardada y versionada para esta IPS.'
    newRule.value={name:'',rule_key:'',phase:'BOTH',category:'',payer:'',modality:'',service_type:'',field:'',operator:'exists',value:'',evidenceKinds:'',severity:'MEDIUM',finding:'',recommendation:'',sourceRef:'',responseAction:'',responseTemplate:''}
  }catch(e){error.value=message(e)}finally{busy.value=false}
}
async function openHistory(id:string){
  error.value=''
  try{
    const result=await request<Analysis>('/api/v1/analyses/'+id)
    recentResults.value=[result]
    view.value=result.phase==='PREVENT'?'prevent':'respond'
  }catch(e){error.value=message(e)}
}
async function exportHistory(){
  if(preview.value)return
  error.value=''
  try{
    const response=await fetch(API+'/api/v1/exports/analyses.csv',{headers:{Authorization:'Bearer '+credential.value,'X-Tenant-Id':tenantId.value}})
    if(!response.ok)throw Error('No se pudo exportar el histórico.')
    const blob=await response.blob()
    const url=URL.createObjectURL(blob)
    const a=document.createElement('a');a.href=url;a.download='smart_glosas_analisis.csv';a.click()
    URL.revokeObjectURL(url)
  }catch(e){error.value=message(e)}
}
function statusText(s:string){return ({REVIEW_REQUIRED:'Revisión requerida',INSUFFICIENT_EVIDENCE:'Información insuficiente',NO_RULES:'Sin reglas aplicables',NO_ALERTS_DETECTED:'Sin alertas detectadas',PENDING_REVIEW:'Pendiente de auditor',APPROVED:'Aprobado internamente',REVIEW:'Alerta',INSUFFICIENT:'Falta información',PASSED:'Validado'} as Record<string,string>)[s]||s}
</script>

<template>
  <div v-if="!credential && !preview" class="auth-page">
    <div class="auth-card">
      <div class="brand-mark">S</div>
      <div class="brand-eyebrow">SMART ALLIANCE</div>
      <h1>Smart Glosas AI</h1>
      <p class="access-lead">Inteligencia para prevenir glosas y responder devoluciones con evidencia.</p>
      <div class="access-capabilities">
        <div><span class="access-number">01</span><div><strong>Prevenir glosas</strong><small>Revisa cuentas antes de radicar.</small></div></div>
        <div><span class="access-number">02</span><div><strong>Responder objeciones</strong><small>Prepara contestaciones y subsanaciones sustentadas.</small></div></div>
      </div>
      <button v-if="previewAvailable" class="primary access-action" @click="preview=true;error='';view='resumen'">Explorar la plataforma <span aria-hidden="true">→</span></button>
      <p v-if="previewAvailable" class="access-hint">Recorrido visual sin acceso a información institucional.</p>
      <div v-if="!ready||busy" class="muted access-status">Conectando con Smart…</div>
      <div v-if="error" role="alert" class="alert access-status">{{error}}</div>
      <div class="auth-footer">El acceso operativo se realiza desde la plataforma Smart. No requiere otra cuenta.</div>
    </div>
  </div>

  <div v-else class="shell">
    <aside class="sidebar">
      <div class="sidebar-brand"><div class="brand-mark small">S</div><div><b>Smart Glosas AI</b><small>CUENTAS MÉDICAS</small></div></div>
      <div class="nav-caption">PLATAFORMA IPS</div>
      <nav aria-label="Navegación principal">
        <button v-for="item in nav" :key="item.id" :class="['nav-item',{active:view===item.id}]" @click="view=item.id;recentResults=[];error='';notification=''">
          <span class="nav-number">{{item.num}}</span>{{item.label}}
        </button>
      </nav>
      <div class="sidebar-bottom"><span>Smart Glosas AI</span><small>Prevención y respuestas</small></div>
    </aside>
    <main class="main">
      <header class="topbar"><div><span class="top-context">SMART / INTELIGENCIA FINANCIERA</span><h1>{{nav.find(n=>n.id===view)?.label}}</h1></div>
        <div class="session-area">
          <select v-if="me?.institutions.length" :value="tenantId" aria-label="Institución activa" @change="selectInstitution(($event.target as HTMLSelectElement).value)">
            <option v-for="t in me.institutions" :key="t.id" :value="t.id">{{t.name}}</option>
          </select>
          <span v-if="preview" class="session-preview">Recorrido del producto</span>
          <button v-if="preview" class="text-button" @click="preview=false;view='resumen';error='';notification=''">Salir</button>
          <span v-if="me?.email" class="session-user">{{me.email}}</span>
        </div>
      </header>
      <div class="page-content">
        <div v-if="error" role="alert" class="alert"><b>Atención</b> {{error}}</div>
        <div v-if="notification" role="status" class="notice">{{notification}}</div>
        <div v-if="preview" class="preview-banner"><span class="preview-dot"></span><div><b>Explora Smart Glosas AI</b><span>Las pantallas están disponibles para conocer el producto. El análisis de cuentas se habilita al vincular una IPS.</span></div></div>
        <section v-if="!tenantId && !preview" class="sheet">
          <h2>Configurar organización</h2>
          <p class="muted">No existe una IPS habilitada para el contexto enviado por Smart. Contacta al administrador.</p>
        </section>
        <template v-else>
          <section v-if="view==='resumen'">
            <div class="hero"><div><span class="eyebrow">INTELIGENCIA DE CUENTAS MÉDICAS</span><h2>De la prevención a la respuesta.</h2><p>Clara analiza cuentas antes de radicar y apoya la contestación de glosas y devoluciones. Cada evaluación conserva sus reglas y evidencias.</p></div><div class="hero-icon"><span>AI</span></div></div>
            <div class="feature-grid">
              <button class="feature" @click="view='prevent'"><span class="feature-icon">01</span><strong>Prevenir glosas</strong><p>Revisión previa a la radicación desde Armado de Cuentas o archivos de otras IPS.</p><span class="feature-action">Abrir análisis <span>→</span></span></button>
              <button class="feature" @click="view='respond'"><span class="feature-icon">02</span><strong>Responder glosas</strong><p>Clasificación, evidencia, subsanación y borradores controlados frente a objeciones.</p><span class="feature-action">Abrir respuestas <span>→</span></span></button>
            </div>
            <div class="metrics"><div><small>Análisis registrados</small><strong>{{preview?"—":records.length}}</strong></div><div><small>Preventivos</small><strong>{{preview?'—':records.filter(r=>r.phase==='PREVENT').length}}</strong></div><div><small>De respuesta</small><strong>{{preview?'—':records.filter(r=>r.phase==='RESPOND').length}}</strong></div><div><small>Reglas activas</small><strong>{{preview?"—":rules.length}}</strong></div></div>
            <p class="muted footnote">{{preview?'Los indicadores se actualizarán cuando la institución comience a procesar cuentas.':'Los indicadores corresponden a los últimos 100 análisis de esta institución. No representan dinero recuperado ni probabilidad estadística.'}}</p>
          </section>
          <section v-else-if="view==='prevent'||view==='respond'">
            <div class="section-intro"><div><span class="eyebrow">{{view==='prevent'?'ANTES DE RADICAR':'DESPUÉS DE LA OBJECIÓN'}}</span><h2>{{view==='prevent'?'Análisis preventivo de cuentas':'Análisis de glosas y devoluciones'}}</h2><p>{{view==='prevent'?'Verifica riesgos con la información disponible. Si falta documentación, el resultado lo indica.':'Analiza causales y evidencia. Las contestaciones requieren revisión y aprobación institucional.'}}</p></div></div>
            <div class="two-panel">
              <div class="sheet">
                <div class="panel-heading"><h3>Nuevo análisis</h3><span class="subtle-label">Una cuenta</span></div>
                <div v-if="view==='respond'" class="form-grid">
                  <label>Referencia de glosa o devolución<input v-model="objectionRef" placeholder="Número de la objeción"/></label>
                  <label>Tipo<select v-model="objectionKind"><option value="GLOSA">Glosa</option><option value="DEVOLUCION">Devolución</option></select></label>
                  <label>Código de causal<input v-model="objectionCode" placeholder="Según comunicación recibida"/></label>
                  <label>Valor objetado <small>(opcional)</small><input v-model="objectionAmount" type="number" min="0" placeholder="0"/></label>
                  <label class="full">Descripción comunicada por la EPS<textarea v-model="objectionDescription" rows="3" placeholder="Transcribir la objeción recibida"/></label>
                </div>
                <div class="form-grid">
                  <label>Referencia de la cuenta<input v-if="view==='prevent'" v-model="preventAccount" placeholder="Identificador de la cuenta"/><input v-else v-model="respondAccount" placeholder="Identificador de la cuenta"/></label>
                  <label>EPS / Pagador<input v-if="view==='prevent'" v-model="preventPayer" placeholder="Nombre del pagador"/><input v-else v-model="respondPayer" placeholder="Nombre del pagador"/></label>
                  <label>Modalidad contractual <small>(opcional)</small><input v-if="view==='prevent'" v-model="preventModality" placeholder="Según el acuerdo"/><input v-else v-model="respondModality" placeholder="Según el acuerdo"/></label>
                  <label>Tipo de servicio <small>(opcional)</small><input v-if="view==='prevent'" v-model="preventService" placeholder="Servicio prestado"/><input v-else v-model="respondService" placeholder="Servicio prestado"/></label>
                </div>
                <details class="advanced"><summary>Información adicional y referencias de evidencia</summary>
                  <p class="muted">Datos disponibles de la cuenta en formato JSON. Los campos se interpretan según las reglas configuradas.</p>
                  <textarea v-if="view==='prevent'" v-model="preventFacts" class="mono" rows="4" spellcheck="false"/>
                  <textarea v-else v-model="respondFacts" class="mono" rows="4" spellcheck="false"/>
                  <p class="muted">Referencias de soportes existentes, una por línea: TIPO | REFERENCIA. Escribir una referencia no carga ni verifica el documento.</p>
                  <textarea v-if="view==='prevent'" v-model="preventEvidence" rows="3" placeholder="CONTRATO | Archivo contractual verificado"/>
                  <textarea v-else v-model="respondEvidence" rows="3" placeholder="FACTURA | Referencia del documento"/>
                </details>
                <div class="panel-footer"><button class="primary" :disabled="busy||preview" @click="runIndividual(view==='prevent'?'PREVENT':'RESPOND')">{{busy?'Analizando…':'Analizar cuenta'}}</button></div>
              </div>
              <div class="sheet">
                <div class="panel-heading"><h3>Analizar un lote</h3><span class="subtle-label">Hasta 500 registros</span></div>
                <p class="muted">{{preview?(view==='respond'?'Selecciona el CSV sintético para inspeccionar sus glosas, devoluciones y soportes. Se procesa solo en tu navegador.':'La prevención operativa estará disponible con el contexto seguro de tu IPS.'):'Carga CSV o JSON de tu IPS o EPS. Las columnas se relacionan sin imponer un formato único por pagador.'}}</p>
                <label class="upload-box" :class="{'upload-disabled':preview&&view==='prevent'}"><input type="file" :disabled="preview&&view==='prevent'" :accept="preview?'.csv':'.csv,.json'" @change="selectFile($event,view==='prevent'?'PREVENT':'RESPOND')"/><span>{{upload?.name|| (preview?'Seleccionar CSV sintético':'Seleccionar archivo CSV o JSON')}}</span></label>
                <button :disabled="busy||!upload||(preview&&view==='prevent')" class="secondary" @click="inspectFile">{{busy?'Leyendo archivo…':preview?'Volver a leer CSV':'Leer columnas'}}</button>
                <div v-if="preview&&syntheticImport&&view==='respond'" class="synthetic-results">
                  <div class="synthetic-head"><strong>Archivo reconocido</strong><small>{{syntheticImport.filename}}</small></div>
                  <div class="synthetic-metrics">
                    <div><strong>{{syntheticImport.items.length}}</strong><span>Objeciones</span></div>
                    <div><strong>{{syntheticImport.glosas}}</strong><span>Glosas</span></div>
                    <div><strong>{{syntheticImport.devoluciones}}</strong><span>Devoluciones</span></div>
                    <div><strong>{{syntheticImport.distinctAccounts}}</strong><span>Cuentas</span></div>
                  </div>
                  <div class="synthetic-amount">Valor objetado en el archivo <strong>{{formatCOP(syntheticImport.totalAmount)}}</strong></div>
                  <p v-if="syntheticImport.errors.length" class="alert">{{syntheticImport.errors.length}} filas necesitan revisión.</p>
                  <div class="synthetic-table-wrap"><table class="synthetic-table"><thead><tr><th>Referencia</th><th>Tipo</th><th>Causal</th><th>Valor</th></tr></thead><tbody>
                    <tr v-for="item in syntheticImport.items" :key="item.ref" :class="{selected:selectedSynthetic?.ref===item.ref}" @click="selectedSynthetic=item">
                      <td><button type="button" class="text-button" @click.stop="selectedSynthetic=item">{{item.ref}}</button></td><td>{{item.kind==='GLOSA'?'Glosa':'Devolución'}}</td><td>{{item.code}}</td><td>{{formatCOP(item.amount)}}</td>
                    </tr></tbody></table></div>
                  <div v-if="selectedSynthetic" class="synthetic-detail">
                    <div class="panel-heading"><h4>{{selectedSynthetic.ref}} · {{selectedSynthetic.family}}</h4><span class="subtle-label">{{selectedSynthetic.code}}</span></div>
                    <p>{{selectedSynthetic.description}}</p>
                    <div><strong>Cuenta:</strong> {{selectedSynthetic.account}}</div>
                    <div><strong>EPS:</strong> {{selectedSynthetic.payer||'No informada'}}</div>
                    <div><strong>Soporte:</strong> {{selectedSynthetic.support}}</div>
                    <div class="helper-note">Pendiente de evaluación normativa y documental. El reconocimiento del CSV no genera una contestación ni una recomendación de Gemini.</div>
                  </div>
                  <p class="muted synthetic-footer">Lectura local de datos sintéticos. No hay persistencia, auditoría médica ni transmisión a EPS. La respuesta automatizada operará al integrar la IPS.</p>
                </div>
                <div v-if="fileColumns.length&&!preview" class="mapping-panel"><div class="panel-heading"><h4>Relacionar campos</h4><small>{{importCount}} registros</small></div>
                  <div class="mapping-fields">
                    <label v-for="key in importTargetFields(importPhase)" :key="key">{{({account_ref:'Cuenta',payer:'EPS',modality:'Modalidad',service_type:'Servicio',issued_on:'Fecha de factura',objection_ref:'Referencia objeción',kind:'Glosa o devolución',description:'Descripción de la objeción',code:'Código de causal',amount:'Valor objetado'} as Record<string,string>)[key]||key}}
                      <select v-model="mapping[key]"><option value="">Sin mapear</option><option v-for="col in fileColumns" :key="col" :value="col">{{col}}</option></select>
                    </label>
                  </div>
                  <button class="primary" :disabled="busy||preview" @click="processImport">{{busy?'Procesando…':'Analizar registros normalizados'}}</button>
                </div>
                <p v-if="importErrors.length" class="alert">{{importErrors.length}} filas no pudieron procesarse. Revisa el archivo y sus campos.</p>
                <div class="helper-note"><b>Control:</b> se conserva la separación entre análisis y envío formal a EPS. Nada se transmite automáticamente.</div>
              </div>
            </div>
            <div v-if="recentResults.length" class="results">
              <div class="results-heading"><div><h3>Resultados del análisis</h3><p>{{recentResults.length}} {{recentResults.length===1?'cuenta evaluada':'registros evaluados'}}</p></div></div>
              <div v-for="item in recentResults.slice(0,30)" :key="item.id" class="result-card">
                <div class="result-top"><div><strong>{{item.account_ref}}</strong><span v-if="item.objection_ref"> · Objeción {{item.objection_ref}}</span></div><span :class="['status',item.summary.toLowerCase()]">{{statusText(item.summary)}}</span></div>
                <div class="result-stats"><span>{{item.counts.review}} alertas</span><span>{{item.counts.insufficient}} por completar</span><span>{{item.counts.passed}} validaciones superadas</span></div>
                <div v-for="(finding,i) in item.findings" :key="i" class="finding"><div><strong>{{finding.category}}</strong> · {{statusText(finding.status)}}<p>{{finding.message}}</p><small v-if="finding.recommendation">{{finding.recommendation}}</small><small v-if="finding.source_ref">Fuente: {{finding.source_ref}}</small></div></div>
                <div v-if="item.response_draft" class="draft"><strong>Propuesta basada en plantilla configurada</strong><p>{{item.response_draft}}</p><small>Requiere revisión de un auditor. No se transmite automáticamente.</small></div>
                <div v-else-if="item.phase==='RESPOND'" class="helper-note">No hay contestación sustentada generable con las reglas y evidencias actuales. Revisión humana requerida.</div>
                <div v-if="item.ai_review" class="draft" style="margin-top:14px">
                  <strong>Clara · análisis con Gemini</strong><small class="clara-model">{{item.ai_review.model}}</small>
                  <p>{{item.ai_review.summary}}</p>
                  <p><b>Tratamiento sugerido:</b> {{item.ai_review.suggested_action}}</p>
                  <p v-if="item.ai_review.draft"><b>Borrador sujeto a revision:</b> {{item.ai_review.draft}}</p>
                  <p v-if="item.ai_review.missing_information.length"><b>Informacion faltante:</b> {{item.ai_review.missing_information.join(' · ')}}</p>
                  <small>No se ha radicado, enviado ni aceptado ninguna objecion.</small>
                </div>
                <div class="result-bottom"><span>{{item.status==='APPROVED'?'Aprobado internamente':'Pendiente de revisión humana'}}</span><button v-if="geminiAvailable && item.status!=='APPROVED'" class="secondary small-button" :disabled="busy" @click="askGemini(item)">Consultar a Clara</button><button v-if="item.status!=='APPROVED'" class="secondary small-button" :disabled="busy" @click="approve(item.id)">Aprobar evaluación</button></div>
              </div>
              <p v-if="recentResults.length>30" class="muted">Se muestran los primeros 30 resultados. Consulta el histórico para acceder a todos.</p>
            </div>
          </section>
          <section v-else-if="view==='historial'">
            <div class="section-intro row-between"><div><span class="eyebrow">TRAZABILIDAD</span><h2>Seguimiento</h2><p>Histórico de análisis y estados de revisión de esta institución.</p></div><button class="secondary" :disabled="preview" @click="exportHistory">Exportar CSV</button></div>
            <div class="sheet table-sheet"><table><thead><tr><th>Cuenta</th><th>EPS</th><th>Proceso</th><th>Resultado</th><th>Estado</th><th></th></tr></thead><tbody><tr v-for="row in records" :key="row.id"><td>{{row.account_ref}}</td><td>{{row.payer||'—'}}</td><td>{{row.phase==='PREVENT'?'Preventivo':'Respuesta'}}</td><td>{{statusText(row.summary)}}</td><td>{{row.status==='APPROVED'?'Aprobado':'Por revisar'}}</td><td><button class="text-button" @click="openHistory(row.id)">Abrir</button></td></tr><tr v-if="!records.length"><td colspan="6">Aún no hay análisis registrados.</td></tr></tbody></table></div>
          </section>
          <section v-else-if="view==='reglas'">
            <div class="section-intro"><span class="eyebrow">MOTOR CONFIGURABLE</span><h2>Reglas de análisis</h2><p>Las condiciones se configuran por institución, pagador, modalidad y servicio. No se generan ni se publican reglas normativas automáticamente.</p></div>
            <div class="two-panel"><div class="sheet"><div class="panel-heading"><h3>Reglas vigentes</h3><span class="subtle-label">{{rules.length}} activas</span></div>
              <div v-for="rule in rules" :key="rule.id" class="listed-rule"><strong>{{rule.name}}</strong><div><span>{{rule.category}} · {{rule.phase}}</span><span>v{{rule.version}}</span></div><small>{{Object.entries(rule.scope).map(([k,v])=>k+': '+v).join(' · ')||'Sin restricción particular'}}</small></div>
              <p v-if="!rules.length" class="muted">No hay reglas configuradas. Ningún análisis se presentará como completo sin una base de evaluación aplicable.</p>
            </div><div class="sheet" v-if="canWriteRules"><div class="panel-heading"><h3>Agregar o actualizar regla</h3></div>
              <div class="form-grid">
                <label>Identificador<input v-model="newRule.rule_key" placeholder="familia.regla"/></label><label>Nombre<input v-model="newRule.name" placeholder="Descripción corta"/></label>
                <label>Fase<select v-model="newRule.phase"><option value="BOTH">Ambas</option><option value="PREVENT">Prevención</option><option value="RESPOND">Respuesta</option></select></label>
                <label>Categoría<input v-model="newRule.category" placeholder="Soportes, tarifas…"/></label>
                <label>EPS <small>(opcional)</small><input v-model="newRule.payer" placeholder="Para una EPS específica"/></label>
                <label>Modalidad <small>(opcional)</small><input v-model="newRule.modality" placeholder="Según contrato"/></label>
                <label>Tipo de servicio <small>(opcional)</small><input v-model="newRule.service_type" placeholder="Servicio"/></label>
                <label>Severidad<select v-model="newRule.severity"><option value="LOW">Baja</option><option value="MEDIUM">Media</option><option value="HIGH">Alta</option></select></label>
                <label>Campo a verificar<input v-model="newRule.field" placeholder="tariff.matches_contract"/></label>
                <label>Operador<select v-model="newRule.operator"><option value="exists">Existe</option><option value="eq">Igual</option><option value="neq">Diferente</option><option value="gte">Mayor o igual</option><option value="lte">Menor o igual</option><option value="gt">Mayor</option><option value="lt">Menor</option></select></label>
                <label v-if="newRule.operator!=='exists'">Valor esperado<input v-model="newRule.value" placeholder="true, 10, texto"/></label>
                <label>Soportes necesarios <small>(opcional)</small><input v-model="newRule.evidenceKinds" placeholder="CONTRATO, FACTURA"/></label>
                <label class="full">Hallazgo si no cumple<textarea v-model="newRule.finding" rows="2"/></label>
                <label class="full">Recomendación<textarea v-model="newRule.recommendation" rows="2"/></label>
                <label class="full">Fuente o referencia verificable<input v-model="newRule.sourceRef" placeholder="Norma, contrato, anexo y versión"/></label>
              </div>
              <details class="advanced"><summary>Plantilla opcional para contestación sustentada</summary><p class="muted">Solo se utilizará si hay regla aplicable, evidencia referenciada y fuente documentada.</p>
                <label>Tratamiento<select v-model="newRule.responseAction"><option value="">Sin acción automática</option><option value="CONTROVERTIR">Controvertir</option><option value="SUBSANAR">Subsanar</option><option value="ACEPTAR">Aceptar</option><option value="ESCALAR">Escalar</option></select></label>
                <label>Texto base<textarea v-model="newRule.responseTemplate" rows="4" placeholder="Puede utilizar {{account_ref}} y {{objection_ref}}"/></label>
              </details>
              <div class="panel-footer"><button class="primary" :disabled="busy" @click="createRule">Guardar regla versionada</button></div>
            </div></div>
          </section>
        </template>
      </div>
    </main>
  </div>
</template>
