export type SyntheticObjection = {
  ref: string
  account: string
  kind: 'GLOSA' | 'DEVOLUCION'
  code: string
  payer: string
  description: string
  amount: number
  support: string
  family: string
}
export type SyntheticImportResult = {
  filename: string
  items: SyntheticObjection[]
  errors: string[]
  distinctAccounts: number
  totalAmount: number
  glosas: number
  devoluciones: number
}
const MAX_BYTES = 4_000_000
const MAX_ROWS = 500
const familyNames: Record<string,string> = {
  FA:'Facturación', TA:'Tarifas', SO:'Soportes', AU:'Autorizaciones',
  CO:'Cobertura', CL:'Pertinencia clínica', SA:'Seguimiento contractual', DE:'Devoluciones'
}
function parseDelimited(text: string): string[][] {
  const data=text.replace(/^\uFEFF/,'')
  const first=data.split(/\r?\n/,1)[0] ?? ''
  const candidates=[',',';','\t']
  const delimiter=candidates.sort((a,b)=>first.split(b).length-first.split(a).length)[0]
  const output: string[][]=[]
  let field='',row: string[]=[],quoted=false
  for(let i=0;i<data.length;i++){
    const ch=data[i]
    if(ch==='"'){
      if(quoted && data[i+1]==='"'){field+='"';i++}
      else quoted=!quoted
    }else if(ch===delimiter && !quoted){
      row.push(field); field=''
    }else if((ch==='\r'||ch==='\n')&&!quoted){
      if(ch==='\r'&&data[i+1]==='\n')i++
      row.push(field); field=''
      if(row.some(v=>v.trim()!==''))output.push(row)
      row=[]
      if(output.length>MAX_ROWS+1)throw new Error('El archivo supera el máximo de 500 registros.')
    }else field+=ch
  }
  if(quoted)throw new Error('El CSV contiene comillas sin cerrar.')
  row.push(field)
  if(row.some(v=>v.trim()!==''))output.push(row)
  return output
}
function normalKind(value:string):'GLOSA'|'DEVOLUCION'|null{
  const s=value.trim().normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase()
  if(s==='GLOSA'||s==='G')return 'GLOSA'
  if(['DEVOLUCION','DEV','D'].includes(s))return 'DEVOLUCION'
  return null
}
export async function inspectSyntheticFile(file:File):Promise<SyntheticImportResult>{
  if(!/\.csv$/i.test(file.name))throw new Error('Para esta prueba usa el archivo CSV, no Excel ni JSON.')
  if(!file.size||file.size>MAX_BYTES)throw new Error('Selecciona un CSV de hasta 4 MB.')
  const text=await file.text()
  const parsed=parseDelimited(text)
  if(parsed.length<2)throw new Error('El archivo no contiene registros.')
  const headers=parsed[0].map(x=>x.trim().toLowerCase())
  const getIndex=(key:string)=>headers.indexOf(key.toLowerCase())
  for(const key of ['objection_ref','kind','code','description','account_ref','amount']){
    if(getIndex(key)<0)throw new Error('Falta la columna '+key+'. Usa el CSV sintético de Smart Glosas AI.')
  }
  const items:SyntheticObjection[]=[]
  const errors:string[]=[]
  for(let i=1;i<parsed.length;i++){
    const data=parsed[i]
    const pick=(key:string)=>{const ix=getIndex(key);return ix<0?'':(data[ix]??'').trim()}
    const ref=pick('objection_ref'),account=pick('account_ref')
    if(!/^OBJ-SYN-[A-Za-z0-9_-]+$/i.test(ref)||!/^CTA-SYN-[A-Za-z0-9_-]+$/i.test(account)){
      throw new Error('Esta función solo recibe casos sintéticos. No adjuntes datos de pacientes ni cuentas reales.')
    }
    const kind=normalKind(pick('kind'))
    const amountText=pick('amount')
    const amount=Number(amountText)
    const code=pick('code').toUpperCase()
    const description=pick('description')
    if(!kind||!description||!code||!Number.isFinite(amount)||amount<0){
      errors.push('Fila '+(i+1)+': tipo, código, descripción o valor inválido.')
      continue
    }
    items.push({
      ref,account,kind,code,description,amount,
      payer:pick('payer'),
      support:pick('Estado_Soporte')||'No indicado',
      family:familyNames[code.slice(0,2)]??'Otra causal'
    })
  }
  if(!items.length)throw new Error('No se reconocieron objeciones válidas.')
  return {
    filename:file.name,items,errors,distinctAccounts:new Set(items.map(x=>x.account)).size,
    totalAmount:items.reduce((n,x)=>n+x.amount,0),
    glosas:items.filter(x=>x.kind==='GLOSA').length,
    devoluciones:items.filter(x=>x.kind==='DEVOLUCION').length
  }
}
