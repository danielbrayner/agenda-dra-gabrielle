const messagesEl = document.getElementById('messages')
const inputEl = document.getElementById('input')
const sendBtn = document.getElementById('send')

function appendMessage(text, cls){
  const div = document.createElement('div')
  div.className = `msg ${cls}`
  div.textContent = text
  messagesEl.appendChild(div)
  messagesEl.scrollTop = messagesEl.scrollHeight
}

async function sendMessage(){
  const text = inputEl.value.trim()
  if(!text) return
  appendMessage(text, 'user')
  inputEl.value = ''

  appendMessage('...', 'assistant')
  const lastPlaceholder = messagesEl.querySelector('.assistant:last-child')

  try{
    const resp = await fetch('/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: text})
    })
    const data = await resp.json()
    if(data.reply){
      lastPlaceholder.textContent = data.reply
    } else if(data.error){
      lastPlaceholder.textContent = 'Erro: ' + data.error
    } else {
      lastPlaceholder.textContent = 'Resposta inesperada.'
    }
  }catch(err){
    lastPlaceholder.textContent = 'Falha ao conectar: ' + err.message
  }
}

sendBtn.addEventListener('click', sendMessage)
inputEl.addEventListener('keydown', (e)=>{ if(e.key==='Enter' && !e.shiftKey){ e.preventDefault(); sendMessage() } })
