# Discord Briefing Bot

Bot do Discord que coleta preferências por conversa, busca notícias por tópico,
gera um briefing diário com IA via Agno e distribui automaticamente pelo Discord
e por e-mail.

## Pré-requisitos

- Python 3.11+
- Uma aplicação/bot no Discord com `MESSAGE CONTENT INTENT` habilitado
- Chave da OpenAI para uso pelo Agno
- Chave da NewsAPI, opcional mas recomendada
- Conta SMTP, por exemplo Gmail com app password
- `uv` ou Poetry para instalar dependências

## Instalação

```bash
git clone <seu-repositorio>
cd discord-briefing-bot
cp .env.example .env
```

Edite `.env` com os tokens reais:

```env
DISCORD_BOT_TOKEN=...
OPENAI_API_KEY=...
NEWS_API_KEY=...
SMTP_USER=...
SMTP_PASSWORD=...
EMAIL_FROM=...
```

Com `uv`:

```bash
uv sync --extra dev
```

Com Poetry:

```bash
poetry install --extras dev
```

## Como Executar

Com Poetry:

```bash
poetry run briefing-bot
```

Ou:

```bash
poetry run python -m briefing_bot
```

Com `uv`:

```bash
uv run python -m briefing_bot
```

Ou com o Python do ambiente virtual ativado:

```bash
python -m briefing_bot
```

## Como Usar o Bot

- `!start` inicia o onboarding e coleta tópicos, palavras-chave, limite, e-mail e canal.
- `!config` mostra as preferências salvas e reinicia a configuração.
- `!briefing` gera e envia um briefing imediato.
- `!status` mostra as preferências atuais.
- `!help` lista os comandos disponíveis.

## Estrutura de Diretórios

```text
discord-briefing-bot/
├── src/briefing_bot/
│   ├── main.py                  # Composição e entrypoint
│   ├── config/settings.py       # Leitura do .env
│   ├── agents/                  # Agentes Agno de onboarding e briefing
│   ├── bot/                     # Discord.py e máquina de estados
│   ├── services/                # NewsAPI, e-mail, scheduler e retry
│   ├── repositories/            # Persistência JSON das preferências
│   └── models/                  # Modelos Pydantic do domínio
├── tests/                       # Testes unitários
├── .env.example
├── README.md
└── pyproject.toml
```

## Arquitetura

A aplicação segue uma composição por injeção de dependências em `main.py`.
O bot do Discord apenas lida com comandos/eventos; a conversa fica em
`ConversationManager`; os agentes Agno extraem preferências e geram texto; os
serviços externos ficam atrás de protocolos pequenos; o agendador coordena o
pipeline buscar notícias → gerar briefing → enviar Discord → enviar e-mail.

`NewsAPIService` é a fonte primária quando `NEWS_API_KEY` existe. Se a NewsAPI
falhar ou não retornar artigos, `CompositeNewsService` usa o fallback
`AgnoWebSearchNewsService`, mantendo o sistema aberto para novas fontes sem
alterar o scheduler.

## Qualidade

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```
