# AlphaSignal — Sistema de Análise para Cassino Ao Vivo

Sistema privado para analisar resultados de jogos ao vivo e gerar sinais inteligentes baseados em estatística e reconhecimento de padrões.

## Jogos Suportados

- 🎲 **Bac Bo** — Player · Banker · Tie
- ⚽ **Football Studio** — Casa · Visitante · Empate
- 🐉 **Dragon Tiger** — em breve

## Funcionalidades

### Estratégias de Análise
- **Adaptativo 🧠** — Analisa os últimos 3 resultados e detecta o que costuma vir depois. Gera mais sinais, ideal para mesas ativas.
- **Pressure** — Aguarda sequência de 4+ resultados iguais e aposta na reversão. *(disponível apenas no Bac Bo)*
- **Consenso ⚡** — Combina Adaptativo + Pressure + Tendência. Sinaliza apenas quando 2 ou 3 concordam. Melhor equilíbrio sinal/assertividade.
- **Fluxo 🌊** — Ignora Empates, detecta sequência de 3+ iguais e aposta na cor principal após alternância. *(disponível apenas no Football Studio)*

### Análises Avançadas
- **Monte Carlo** — 5000 simulações para previsão de próximo resultado
- **Drift Detection** — Detecta mudanças de comportamento da mesa
- **Heatmap de Padrões** — Visualiza os padrões mais recorrentes no histórico
- **Auto-seleção inteligente** — Troca automaticamente para a estratégia com maior taxa de acerto

### Placar Automático com Gale
- Win/Loss detectado automaticamente ao receber novo resultado
- **1 Gale incluso** — se perder na entrada, repete (G1). Se perder no G1, conta como LOSS
- Empate conta como WIN automaticamente
- Funciona corretamente mesmo com histórico no limite de 150 resultados

### Gatilhos Personalizados
- Cadastre seus próprios padrões (ex: `B B B → Player`)
- O sistema calcula a taxa de acerto histórica de cada gatilho
- Gatilho ativo é destacado em tempo real

### Interface
- Dark Mode com estilo Neon/Cyber
- Seleção de jogo após login
- Badge do jogo ativo no header com botão de trocar jogo
- Histórico visual com círculos coloridos (até 150 resultados)
- Estatísticas em tempo real (atualização a cada 500ms)
- Alertas sonoros para sinais, vitórias e notificações
- Probabilidade mínima ajustável (40% a 90%)
- Slider de mínimo de sequência para estratégia Fluxo (2 a 5 rodadas)
- Logs de análise traduzidos por jogo (V/C/E no Football Studio)

## Configuração

### Backend — `backend/.env`

```env
APP_USER=admin
APP_PASSWORD=admin
```

### Frontend — `frontend/.env`

```env
REACT_APP_BACKEND_URL=http://localhost:8001
```

## Execução Local

```bash
# Backend
cd backend
pip install -r requirements.txt
python -m uvicorn server:app --reload --port 8001

# Frontend (em outro terminal)
cd frontend
npm install
npm start
```

O frontend abre automaticamente em `http://localhost:3000`.

## Extensão do Navegador

A extensão **AlphaSignal Capture** captura resultados do Bac Bo e Football Studio automaticamente e envia para o backend.

1. Abra `chrome://extensions`
2. Ative **Modo do desenvolvedor**
3. Clique em **Carregar sem compactação**
4. Selecione a pasta `Extensao AlphaSignal/extensao-dev`

> A extensão detecta automaticamente qual jogo está aberto e exibe status ativo/inativo por jogo no popup.

## API Endpoints

### Bac Bo

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/api/login` | Autenticação (zera histórico de ambos os jogos) |
| GET | `/api/state` | Estado completo |
| POST | `/api/historico` | Recebe histórico inicial |
| POST | `/api/resultado` | Recebe novo resultado |
| POST | `/api/strategy` | Altera estratégia |
| POST | `/api/probability` | Altera probabilidade mínima |
| POST | `/api/signal/feedback` | Registra vitória/derrota |
| POST | `/api/triggers` | Salva gatilhos personalizados |
| POST | `/api/auto_select` | Liga/desliga auto-seleção |
| POST | `/api/reset` | Reseta estatísticas |

### Football Studio

Mesmos endpoints com prefixo `/api/fs/` — ex: `/api/fs/state`, `/api/fs/resultado`, etc.

| Método | Endpoint Adicional | Descrição |
|--------|-------------------|-----------|
| POST | `/api/fs/seq_min` | Altera mínimo de sequência do Fluxo (2-5) |

## Desenvolvido por

**Fernando** — 2026

Suporte: [WhatsApp](https://wa.me/5563981228800)
