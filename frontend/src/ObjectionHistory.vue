<script setup lang="ts">
import {computed, ref, watch} from 'vue'
type Status = 'POR_ANALIZAR'|'EN_REVISION'|'ANALIZADA'|'PROPUESTA'|'RESPONDIDA'
type Entry = {objection_ref:string;account_ref:string;kind:string;code:string|null;payer:string|null;description:string;amount:number|null;status:Status;findings:Array<{category:string;message:string;source_ref:string|null}>;ai_review?:{summary:string;suggested_action:string;draft:string|null;missing_information:string[]}|null;updated_at?:string|null}
type History = {total:number;progress:number;counts:Record<Status,number>;items:Entry[]}
const props=defineProps<{history:History|null;loading:boolean;triageBusy?:boolean}>()
const emit=defineEmits<{open:[string];triage:[]}>()
const filter=ref('TODAS')
const query=ref('')
const current=ref('')
const labels:Record<Status,string>={POR_ANALIZAR:'Por analizar',EN_REVISION:'En revisión documental',ANALIZADA:'Analizada',PROPUESTA:'Propuesta preparada',RESPONDIDA:'Respondida'}
const options=[{value:'TODAS',label:'Todas'},{value:'POR_ANALIZAR',label:'Por analizar'},{value:'EN_REVISION',label:'En revisión'},{value:'ANALIZADA',label:'Analizadas'},{value:'PROPUESTA',label:'Con propuesta'},{value:'RESPONDIDA',label:'Respondidas'}]
const visible=computed(()=>((props.history?.items)||[]).filter(row=>(filter.value==='TODAS'||row.status===filter.value)&&
  [row.objection_ref,row.account_ref,row.code,row.payer].some(v=>String(v||'').toLowerCase().includes(query.value.trim().toLowerCase()))))
const chosen=computed(()=>props.history?.items.find(x=>x.objection_ref===current.value)||null)
const money=(n:number|null)=>n===null?'—':new Intl.NumberFormat('es-CO',{style:'currency',currency:'COP',maximumFractionDigits:0}).format(n)
watch(()=>props.history?.total,(value)=>{if(!value)current.value=''})
function show(item:Entry){current.value=item.objection_ref}
function statusClass(value:Status){return 'track-status '+value.toLowerCase()}
</script>

<template>
  <section class="workflow-board">
    <div class="workflow-board-head">
      <div>
        <span class="eyebrow">CLARA · INTELIGENCIA PARA GLOSAS</span>
        <h2>Gestión de objeciones</h2>
        <p>Seguimiento de glosas y devoluciones, desde la carga hasta la respuesta formal.</p>
      </div>
      <span class="workflow-tag">Estado de cartera</span>
    </div>
    <div class="workflow-summary">
      <div class="workflow-progress">
        <div class="workflow-ring" :style="{'--progress':(history?.progress||0)+'%'}" role="progressbar" :aria-valuenow="history?.progress||0" aria-valuemin="0" aria-valuemax="100" aria-label="Progreso general del proceso">
          <div class="workflow-ring-middle"><strong>{{history===null?'—':history.progress+'%'}}</strong><small>del proceso</small></div>
        </div>
        <div class="workflow-progress-description"><strong>Avance del ciclo</strong><p>Según el estado de cada objeción, sin suponer contestaciones enviadas.</p><small>En revisión: 20% · Analizada: 50% · Propuesta: 75% · Respondida: 100%</small></div>
      </div>
      <div class="workflow-stats">
        <div class="workflow-stat"><strong>{{history===null?'—':history.total}}</strong><span>Total</span></div>
        <div class="workflow-stat"><strong>{{history===null?'—':history.counts.POR_ANALIZAR}}</strong><span>Por analizar</span></div>
        <div class="workflow-stat"><strong>{{history===null?'—':history.counts.EN_REVISION}}</strong><span>En revisión</span></div>
        <div class="workflow-stat"><strong>{{history===null?'—':history.counts.ANALIZADA}}</strong><span>Analizadas</span></div>
        <div class="workflow-stat"><strong>{{history===null?'—':history.counts.PROPUESTA}}</strong><span>Con propuesta</span></div>
        <div class="workflow-stat"><strong>{{history===null?'—':history.counts.RESPONDIDA}}</strong><span>Respondidas</span></div>
      </div>
    </div>
    <div class="workflow-table-head">
      <div><h3>Histórico de glosas</h3><p>{{history?.total||0}} objeciones registradas</p></div>
      <div class="workflow-filters">
        <input v-model="query" aria-label="Buscar objeciones" placeholder="Buscar cuenta, causal o EPS"/>
        <select v-model="filter" aria-label="Filtrar por estado"><option v-for="f in options" :key="f.value" :value="f.value">{{f.label}}</option></select>
      </div>
    </div>
    <div v-if="history?.counts.POR_ANALIZAR" class="workflow-triage">
      <div><strong>{{history.counts.POR_ANALIZAR}} glosas pendientes de clasificar</strong>
        <p>Clasifica causales e identifica la información por verificar. Los expedientes no se consideran auditados ni respondidos.</p>
      </div>
      <button class="primary" :disabled="loading||triageBusy" @click="emit('triage')">{{triageBusy?'Clasificando…':'Iniciar revisión de pendientes'}}</button>
    </div>
    <div v-if="loading" class="workflow-empty">Consultando el histórico…</div>
    <div v-else-if="!history?.total" class="workflow-empty">
      <strong>{{history===null?'Sin institución vinculada':'No hay glosas registradas todavía.'}}</strong>
      <p>{{history===null?'El histórico se habilita al ingresar desde Smart con una institución autorizada.':'Carga glosas o registra una objeción para comenzar. Los expedientes estarán disponibles aquí.'}}</p>
    </div>
    <div v-else-if="!visible.length" class="workflow-empty">No hay glosas que coincidan con los filtros.</div>
    <div v-else class="workflow-table-scroll">
      <table class="workflow-history-table">
        <thead><tr><th>Objeción / cuenta</th><th>Pagador</th><th>Causal</th><th>Valor</th><th>Estado</th><th></th></tr></thead>
        <tbody>
          <tr v-for="item in visible" :key="item.objection_ref" :class="{selected:current===item.objection_ref}">
            <td><strong>{{item.objection_ref}}</strong><small>{{item.account_ref}} · {{item.kind==='DEVOLUCION'?'Devolución':'Glosa'}}</small></td>
            <td>{{item.payer}}</td><td>{{item.code||'—'}}</td><td>{{money(item.amount)}}</td>
            <td><span :class="statusClass(item.status)">{{labels[item.status]||item.status}}</span></td>
            <td><button class="text-button" @click="show(item)">Ver detalle</button></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="chosen" class="workflow-item-detail">
      <div class="panel-heading"><h3>{{chosen.objection_ref}} · {{chosen.code}}</h3><span :class="statusClass(chosen.status)">{{labels[chosen.status]}}</span></div>
      <p>{{chosen.description}}</p>
      <div v-if="chosen.findings?.length" class="workflow-evidence">
        <strong>Hallazgos documentales</strong>
        <div v-for="(f,i) in chosen.findings" :key="i"><b>{{f.category}}:</b> {{f.message}}<small>Fuente: {{f.source_ref}}</small></div>
      </div>
      <div v-if="chosen.ai_review" class="workflow-evidence">
        <strong>Clara · Gemini</strong>
        <p>{{chosen.ai_review.summary}}</p>
        <p><b>Actuación propuesta:</b> {{chosen.ai_review.suggested_action}}</p>
        <p v-if="chosen.ai_review.draft">{{chosen.ai_review.draft}}</p>
        <p v-else class="muted">No hay contestación sustentada para aprobar.</p>
      </div>
      <div class="workflow-item-actions">
        <span class="muted">{{chosen.status==='POR_ANALIZAR'?'Pendiente de clasificar':chosen.status==='EN_REVISION'?'Pendiente de soportes y reglas verificadas':chosen.status==='ANALIZADA'?'En revisión · puede solicitarse una propuesta':chosen.status==='PROPUESTA'?'Borrador pendiente de auditor':'Respuesta registrada'}}</span>
        <button class="secondary" @click="emit('open',chosen.objection_ref)">Abrir con Clara</button>
      </div>
    </div>
    <div class="workflow-footnote">Una propuesta de Clara requiere aprobación humana. Solo las respuestas efectivamente registradas se consideran respondidas.</div>
  </section>
</template>
