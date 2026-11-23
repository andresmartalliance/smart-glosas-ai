<script setup lang="ts">
import {onMounted, ref, watch, nextTick} from 'vue'

interface GoogleIdentity {
  accounts: {id: {
    initialize: (options:{client_id:string;callback:(response:{credential:string})=>void})=>void
    renderButton: (element:HTMLElement, options:Record<string,string>)=>void
  }}
}
declare global {
  interface Window { google?: GoogleIdentity }
}
const props=defineProps<{clientId:string;loading?:boolean}>()
const emit=defineEmits<{credential:[token:string]}>()
const container=ref<HTMLElement|null>(null)
const state=ref<'loading'|'ready'|'missing'|'blocked'>('loading')
const explanation=ref('')
let active=true
let currentId=''

function showError(msg:string){
  if(!active)return
  state.value='blocked'
  explanation.value=msg
}
function render(){
  const id=props.clientId.trim()
  if(!active||!container.value)return
  if(!id){
    state.value='missing'
    return
  }
  if(!/^[0-9]+-[a-z0-9_-]+\.apps\.googleusercontent\.com$/.test(id)){
    showError('La configuración de Google OAuth no tiene un identificador válido.')
    return
  }
  if(!window.google?.accounts?.id)return
  if(currentId===id && container.value.childElementCount>0){state.value='ready';return}
  try{
    window.google.accounts.id.initialize({
      client_id:id,
      callback:reply=>{
        if(!reply?.credential){showError('Google no devolvió una credencial de acceso.');return}
        emit('credential',reply.credential)
      }
    })
    container.value.replaceChildren()
    window.google.accounts.id.renderButton(container.value,{
      theme:'outline',shape:'pill',size:'large',type:'standard',
      text:'signin_with',logo_alignment:'left',width:'260'
    })
    currentId=id
    state.value='ready'
    explanation.value=''
  }catch{
    showError('Google no pudo inicializarse. Comprueba que este dominio esté autorizado en OAuth.')
  }
}
function loadScript(){
  if(!active)return
  if(!props.clientId.trim()){state.value='missing';return}
  state.value='loading'
  if(window.google?.accounts?.id){render();return}
  const existing=document.querySelector<HTMLScriptElement>('script[data-google-identity]')
  const script=existing||document.createElement('script')
  if(!existing){
    script.src='https://accounts.google.com/gsi/client'
    script.async=true
    script.defer=true
    script.dataset.googleIdentity='1'
    document.head.appendChild(script)
  }
  script.addEventListener('load',()=>{if(active)render()},{once:true})
  script.addEventListener('error',()=>showError('El navegador bloqueó la carga de Google Identity Services.'),{once:true})
  // If an existing script has already loaded, render immediately.
  if(window.google?.accounts?.id)render()
}
async function start(){
  await nextTick()
  if(active)loadScript()
}
onMounted(start)
watch(()=>props.clientId,()=>{currentId='';void start()},{flush:'post'})
</script>

<template>
  <div class="google-access" aria-label="Acceso corporativo con Google">
    <div v-if="state==='loading'" class="google-access-status">Cargando acceso con Google…</div>
    <div v-else-if="state==='missing'" class="google-access-warning">
      El acceso corporativo con Google no está configurado. Revisa el identificador OAuth en la API.
    </div>
    <div v-else-if="state==='blocked'" class="google-access-warning">
      {{explanation}}
      <button type="button" class="google-access-retry" @click="start">Reintentar</button>
    </div>
    <div ref="container" class="google-access-button" :class="{inactive:state!=='ready'}"></div>
    <div v-if="loading" class="google-access-status">Validando cuenta corporativa…</div>
  </div>
</template>
