<script setup lang="ts">
import {computed, ref, watch} from 'vue'

type Screen = 'resumen'|'prevent'|'respond'|'historial'|'reglas'
type CaseInfo = {objection_ref:string;code:string|null;status:string}
type CountSummary = {total:number;counts:Record<string,number>}
type Message = {id:number;role:'user'|'assistant';text:string}

const props=defineProps<{
  screen:Screen
  api:string
  token:string
  tenantId:string
  institution:string|null
  geminiAvailable:boolean
  cases:CaseInfo[]
  summary:CountSummary|null
  initialCase:string
}>()
const emit=defineEmits<{navigate:[Screen];openCase:[string]}>()
const open=ref(false)
const question=ref('')
const chosenCase=ref('')
const messages=ref<Message[]>([])
const pending=ref(false)
const error=ref('')
let messageSequence=0

const screenTitle:Record<Screen,string>={
  resumen:'Inicio',prevent:'Prevención',respond:'Respuesta',
  historial:'Seguimiento',reglas:'Configuración'
}
const intro:Record<Screen,string>={
  resumen:'Puedo ayudarte a interpretar el avance de las glosas y a elegir el siguiente paso.',
  prevent:'Puedo orientarte sobre controles antes de radicar y soportes que debes verificar.',
  respond:'Selecciona una glosa para revisar su estado o consultar el criterio de Clara.',
  historial:'Puedo ayudarte a entender los estados y priorizar los casos pendientes.',
  reglas:'Puedo orientarte sobre hospitales, reglas de validación y gestión de cargas.'
}
const prompts:Record<Screen,string[]>={
  resumen:['¿Qué significa el avance de las glosas?','¿Qué debería revisar primero?'],
  prevent:['¿Qué debo verificar antes de radicar una cuenta?','¿Cómo identificar soportes faltantes?'],
  respond:['¿Qué necesito para sustentar una respuesta a glosa?','¿Cuándo corresponde subsanar una devolución?'],
  historial:['¿Cómo priorizar las glosas pendientes?','¿Qué diferencia hay entre propuesta y respondida?'],
  reglas:['¿Cómo organizar las reglas por IPS?','¿Qué validar antes de eliminar una carga?']
}
const contextualPrompts=computed(()=>prompts[props.screen])
const validCases=computed(()=>props.cases.slice(0,1000))
const hasInstitution=computed(()=>Boolean(props.tenantId&&props.token))
watch(()=>props.initialCase, ref=>{if(ref)chosenCase.value=ref},{immediate:true})
watch(()=>props.tenantId,()=>{
  chosenCase.value=''
  messages.value=[]
  question.value=''
  error.value=''
})
function switchView(screen:Screen){
  emit('navigate',screen)
  open.value=false
}
function goToCase(){
  if(!chosenCase.value)return
  emit('openCase',chosenCase.value)
  open.value=false
}
async function submit(value?:string){
  const text=(value??question.value).trim()
  if(!text||pending.value)return
  if(!hasInstitution.value){
    error.value='Selecciona una institución para consultar a Clara.'
    return
  }
  if(!props.geminiAvailable){
    error.value='Gemini no está disponible. Comprueba su configuración en la API.'
    return
  }
  question.value=''
  error.value=''
  messages.value.push({id:++messageSequence,role:'user',text})
  pending.value=true
  try{
    const response=await fetch(props.api+'/api/v1/clara/assist',{
      method:'POST',
      headers:{
        'Authorization':'Bearer '+props.token,
        'X-Tenant-Id':props.tenantId,
        'Content-Type':'application/json'
      },
      body:JSON.stringify({
        question:text,
        screen:props.screen,
        ...(chosenCase.value?{objection_ref:chosenCase.value}:{})
      })
    })
    let payload:{answer?:string;detail?:string}
    try{payload=await response.json()}catch{payload={}}
    if(!response.ok)throw new Error(payload.detail||'Clara no pudo completar esta consulta.')
    if(!payload.answer)throw new Error('Clara no devolvió una respuesta.')
    messages.value.push({id:++messageSequence,role:'assistant',text:payload.answer})
  }catch(e){
    error.value=e instanceof Error?e.message:'No fue posible consultar a Clara.'
  }finally{
    pending.value=false
  }
}
</script>

<template>
  <div class="clara-assistant">
    <button class="clara-launcher" type="button" :aria-expanded="open"
      aria-controls="clara-panel" aria-label="Abrir asistente Clara" @click="open=!open">
      <span class="clara-emblem">C</span>
      <span>Clara</span>
      <span class="clara-launcher-subtitle">Asistente IA</span>
    </button>
    <div v-if="open" class="clara-overlay" @click="open=false"></div>
    <section v-if="open" id="clara-panel" class="clara-panel"
      role="dialog" aria-modal="true" aria-label="Clara, asistente de glosas"
      @keydown.esc="open=false">
      <header class="clara-panel-header">
        <div class="clara-panel-identity">
          <div class="clara-panel-avatar">C</div>
          <div><strong>Clara</strong><small>Asistente de Smart Glosas AI</small></div>
        </div>
        <button class="clara-close" type="button" aria-label="Cerrar Clara" @click="open=false">×</button>
      </header>
      <div class="clara-panel-main">
        <div class="clara-context">
          <span>ESTÁS EN {{screenTitle[screen].toUpperCase()}}</span>
          <p>{{intro[screen]}}</p>
          <small v-if="institution">{{institution}}</small>
          <small v-else>Selecciona o crea una institución para trabajar con sus glosas.</small>
        </div>
        <div v-if="summary" class="clara-mini-metrics">
          <div><strong>{{summary.total}}</strong><span>Glosas</span></div>
          <div><strong>{{summary.counts.POR_ANALIZAR??0}}</strong><span>Por analizar</span></div>
          <div><strong>{{summary.counts.PROPUESTA??0}}</strong><span>Propuestas</span></div>
        </div>
        <div v-if="validCases.length" class="clara-case-row">
          <label for="clara-case-select">Consultar una glosa</label>
          <div class="clara-case-picker">
            <select id="clara-case-select" v-model="chosenCase">
              <option value="">Consulta general</option>
              <option v-for="item in validCases" :key="item.objection_ref" :value="item.objection_ref">
                {{item.objection_ref}} · {{item.code||'Sin causal'}}
              </option>
            </select>
            <button v-if="chosenCase" type="button" class="clara-open-case" @click="goToCase">Abrir</button>
          </div>
        </div>
        <div class="clara-actions">
          <button type="button" @click="switchView('prevent')">Prevenir glosas</button>
          <button type="button" @click="switchView('respond')">Responder glosas</button>
          <button type="button" @click="switchView('historial')">Seguimiento</button>
        </div>
        <div v-if="!messages.length" class="clara-questions">
          <p>Pregúntale a Clara</p>
          <button v-for="sample in contextualPrompts" :key="sample" type="button"
            :disabled="!geminiAvailable||!hasInstitution" @click="submit(sample)">{{sample}}</button>
        </div>
        <div v-else class="clara-conversation" aria-live="polite">
          <div v-for="item in messages" :key="item.id" :class="['clara-message',item.role]">
            <small>{{item.role==='assistant'?'Clara':'Tú'}}</small>
            <p>{{item.text}}</p>
          </div>
        </div>
        <div v-if="pending" class="clara-pending">Clara está preparando su respuesta…</div>
        <p v-if="error" class="clara-error" role="alert">{{error}}</p>
      </div>
      <footer class="clara-panel-footer">
        <form @submit.prevent="submit()">
          <textarea v-model="question" rows="2" maxlength="700"
            placeholder="Pregunta sobre glosas, prevención o seguimiento…"
            aria-label="Escribe una consulta para Clara"
            :disabled="pending||!hasInstitution||!geminiAvailable"
            @keydown.enter.exact.prevent="submit()"></textarea>
          <button type="submit" :disabled="!question.trim()||pending||!hasInstitution||!geminiAvailable">Enviar</button>
        </form>
        <p v-if="!geminiAvailable">Clara requiere conexión con Gemini para responder consultas.</p>
        <p v-else>Sin datos personales ni clínicos. Clara no modifica glosas ni envía respuestas a EPS.</p>
      </footer>
    </section>
  </div>
</template>
