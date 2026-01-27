const messagesEl = document.getElementById('messages')
const inputEl = document.getElementById('input')
const sendBtn = document.getElementById('send')


function getUserId(){
  let userId = localStorage.getItem("chat_user_id")
  if(!userId){
    userId = crypto.randomUUID()
    localStorage.setItem("chat_user_id", userId)
  }
  return userId
}


function appendMessage(text, cls){
  const div = document.createElement('div')
  div.className = `msg ${cls}`
  div.textContent = text
  messagesEl.appendChild(div)
  messagesEl.scrollTop = messagesEl.scrollHeight
}

// 🔘 FUNÇÃO PARA MOSTRAR BOTÕES DE OPÇÃO
function addOptions(options){
  const container = document.createElement('div')
  container.className = 'msg assistant options-container'

  // 👇 Faz os botões ficarem um embaixo do outro
  container.style.display = 'flex'
  container.style.flexDirection = 'column'
  container.style.gap = '8px'
  container.style.marginTop = '6px'

  options.forEach(opt => {
    const btn = document.createElement('button')
    btn.className = 'option-btn'
    btn.textContent = opt



    btn.onclick = () => {
      appendMessage(opt, 'user')   // mostra a escolha do usuário
      container.remove()           // remove os botões
      sendMessage(opt)             // envia pro backend
    }

    container.appendChild(btn)
  })

  messagesEl.appendChild(container)
  messagesEl.scrollTop = messagesEl.scrollHeight
}


// 🚀 ENVIO DE MENSAGEM (AGORA ACEITA TEXTO OPCIONAL)
async function sendMessage(textOverride = null){
  const text = textOverride || inputEl.value.trim()
  if(!text) return

  if(!textOverride){
    appendMessage(text, 'user')
    inputEl.value = ''
  }

  appendMessage('...', 'assistant')
  const lastPlaceholder = messagesEl.querySelector('.assistant:last-child')

  try{
    /*const resp = await fetch('/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: text})
    })*/

    const resp = await fetch('/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        message: text,
        user_id: getUserId()   // 👈 NOVO
      })
    })


    const data = await resp.json()

    if(data.reply){
      lastPlaceholder.textContent = data.reply
    } else if(data.error){
      lastPlaceholder.textContent = 'Erro: ' + data.error
    } else {
      lastPlaceholder.textContent = 'Resposta inesperada.'
    }

    // ⭐ SE O BACKEND ENVIAR OPÇÕES → MOSTRA BOTÕES
    if(data.options){
      addOptions(data.options)
    }

  }catch(err){
    lastPlaceholder.textContent = 'Falha ao conectar: ' + err.message
  }
}

sendBtn.addEventListener('click', () => sendMessage())
inputEl.addEventListener('keydown', (e)=>{
  if(e.key==='Enter' && !e.shiftKey){
    e.preventDefault()
    sendMessage()
  }
})
