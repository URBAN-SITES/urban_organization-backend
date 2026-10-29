# Transcrição e resumo das reuniões: comparação

Consulta feita em 29/10/2026. Os preços mudam: confira de novo antes de contratar.

## O que precisamos

- Transcrever as gravações da Fase 4 (MP4 no nosso bucket), em **português do Brasil**.
- Ter **timestamps** para o clique levar ao ponto certo do player.
- Ter **identificação de falantes**: "Falante 1", "Falante 2" etc.
- Gerar um resumo estruturado (JSON validado por schema) com:
  - tópicos, decisões, problemas, próximos passos e perguntas;
  - ações sugeridas com o trecho de origem.
- Rodar fora da requisição. O backend **já tem Celery com Redis** (`app/celery.py`) e um serviço `worker` no `docker-compose.yml`, então não precisa de fila nova.

## Base do cálculo

Reunião de **1 hora**, com uma gravação mista de todos os participantes.

Cerca de 9 mil palavras faladas viram uma transcrição com timestamps de uns **25 mil tokens**. O resumo gerado fica em uns **3 mil tokens**.

## Transcrição

| Critério | AssemblyAI | Deepgram Nova-3 | Gemini 3.5 Transcribe | OpenAI gpt-4o-transcribe-diarize |
|---|---|---|---|---|
| Português | Sim: Universal-2 cobre 99 idiomas. A página não confirma se o Universal-3.5 Pro, que tem 18 idiomas, inclui o português | Sim, no modelo multilíngue (`language=multi`) | Sim, `pt-BR` e `pt-PT` | Sim |
| Falantes | Sim (add-on) | Sim, incluso no pré-gravado | Sim, até 8. Com 3 ou mais é "experimental" | Sim |
| Timestamps | Por palavra | Por palavra | Por palavra (avisa que reduz a precisão) | A fonte consultada diz que não há timestamp granular nesse modelo |
| Limite por arquivo | Lê o arquivo por URL: mandamos a URL assinada do bucket | Lê por URL | **30 min** com falantes ou timestamps. Uma reunião de 1 h precisa ser cortada, e os falantes não se mantêm entre os pedaços | 25 MB: exige cortar e comprimir |
| **Custo por hora** | Universal-2 US$ 0,15 + falantes US$ 0,02 = **US$ 0,17** | Multilíngue US$ 0,0052/min = **US$ 0,31** | Cerca de **US$ 0,30** (fonte não oficial; a página de preços do Google não carregou daqui) | US$ 0,006/min = **US$ 0,36** |
| Gratuito para testar | Até 185 h de pré-gravado, sem cartão | Não confirmado | Free tier do Gemini, mas ele **usa os dados para treinar** | Não |
| Privacidade e retenção | O áudio é apagado em 24 a 48 h. A transcrição fica 30 dias, ou some antes se apagarmos pela API. **Pode treinar com os dados** se não fizermos opt-out da conta. Servidores na UE não treinam | Por padrão **guarda e treina**. Com `mip_opt_out=true` em cada pedido, guarda só durante o processamento | Plano pago: não usa para melhorar produtos. Free tier: usa | Os termos da API dizem que não treina por padrão |

## Resumo (LLM)

Todos têm saída em JSON com schema.

| Modelo | Custo por reunião de 1 h | Já está no projeto? | Treino e retenção |
|---|---|---|---|
| Gemini 3.6 Flash | 25k × 0,75 + 3k × 3,75 por milhão ≈ **US$ 0,03**. A partir de 1/1/2027, o dobro (≈ US$ 0,06) | **Sim**: `google-genai` e `GEMINI_API_KEY` | Pago: não usa. Free tier: usa |
| Gemini 3.5 Flash-Lite | ≈ **US$ 0,015** | Sim | Igual |
| Claude Haiku 5.5 | 25k × 0,10 + 3k × 0,50 por milhão ≈ **US$ 0,004** | Não: dependência `anthropic` e conta nova | Conteúdo não retido por padrão e não usado para treino sem permissão |
| Claude Sonnet 5.5 | ≈ **US$ 0,08** | Não | Igual |

## Custo estimado por reunião

| Combinação | 1 h | 20 h/mês (exemplo do REUNIOES.md) |
|---|---|---|
| **AssemblyAI + Gemini 3.6 Flash** (recomendada) | ≈ **US$ 0,20** | ≈ US$ 4 |
| AssemblyAI + Claude Haiku 5.5 | ≈ US$ 0,18 | ≈ US$ 3,60 |
| Deepgram + Gemini 3.6 Flash | ≈ US$ 0,34 | ≈ US$ 7 |
| Gemini 3.5 Transcribe + Gemini 3.6 Flash | ≈ US$ 0,33 | ≈ US$ 6,60 |

Isso soma ao custo da gravação da Fase 4 (LiveKit e storage).

## Recomendação: AssemblyAI para transcrever e Gemini Flash para resumir

1. **Português, falantes e timestamps por palavra num pedido só.** O AssemblyAI lê o MP4 direto pela URL assinada do nosso bucket. O servidor não baixa o arquivo, não usa ffmpeg e não corta o áudio. Assim, uma reunião de 1 h ou de 3 h sai do mesmo jeito.
2. **É a transcrição mais barata** (US$ 0,17/h) e tem 185 h grátis. Dá para fazer o teste do checkpoint sem cartão.
3. **O resumo usa o Gemini que o projeto já tem.** Não entra dependência nova. O schema de saída vai no `response_schema` e é validado de novo no Django antes de salvar.
4. **Não precisamos de SDK do AssemblyAI.** São três chamadas HTTP: enviar a URL, consultar o status e apagar a transcrição. Seguimos o padrão do LiveKit e do GitHub, com `requests`.

**Condições de privacidade (obrigatórias):**

- **Fazer o opt-out de treino** na conta do AssemblyAI, ou usar o servidor da UE (`api.eu.assemblyai.com`), que não treina. A UE é a opção mais simples.
- **Apagar a transcrição no AssemblyAI** assim que ela for salva no nosso banco (`DELETE /v2/transcript/{id}`).
- Usar uma **chave Gemini de projeto com faturamento ativo**. No free tier o Google usa os dados para treinar, e isso não serve para reunião de cliente. Não sei se a `GEMINI_API_KEY` atual é paga: confirme no Google AI Studio.

**Contra:**

- É um fornecedor a mais, com conta e chave novas, e só você pode criar.
- A identificação de falantes dá rótulos ("Falante A", "Falante B"), não nomes. Ligar o rótulo à pessoa exigiria gravar cada participante em separado, o que custa mais e complica o Egress. Proponho mostrar os rótulos e deixar quem gerencia renomeá-los na tela.

**Alternativa só com Google:** o Gemini 3.5 Transcribe evita um fornecedor novo. Em troca:

- precisa cortar o áudio em blocos de 30 min com ffmpeg;
- os falantes se perdem entre os blocos;
- com 3 ou mais pessoas, a identificação de falantes é "experimental";
- o preço por hora não está na página oficial que consegui ler.

**Se privacidade for o critério principal:** Claude Haiku 5.5 no resumo é o mais barato e não guarda o conteúdo por padrão. Mas exige a dependência `anthropic` e mais uma conta.

## O que vou precisar depois da aprovação

| Item | Detalhe |
|---|---|
| Conta AssemblyAI | Você cria, de preferência na região UE. `ASSEMBLYAI_API_KEY` e `ASSEMBLYAI_BASE_URL` no `.env` |
| Gemini pago | A mesma `GEMINI_API_KEY`, num projeto com faturamento. Modelo em `MEETING_SUMMARY_MODEL` |
| Worker Celery | Já existe no `docker-compose.yml`. Em produção, precisa estar rodando |
| Dependências novas | Nenhuma |
| Migração | Uma, com a transcrição, o resumo e o estado do processamento |
| Áudio de teste | Um áudio curto **gerado por nós e marcado como dado de teste**. Sem voz de pessoa real |

Criar contas e contratar serviço pago depende da sua autorização, conforme as regras do plano.

## Fontes

- AssemblyAI, preços: https://www.assemblyai.com/pricing
- AssemblyAI, retenção e treino: https://assemblyai.com/docs/faq/how-long-does-aai-retain-data
- Deepgram, preços: https://www.developersdigest.tech/models/speech/deepgram
- Deepgram, seus dados: https://developers.deepgram.com/trust-security/your-data
- Gemini API, preços e uso de dados por tier: https://ai.google.dev/gemini-api/docs/pricing
- Gemini, transcrição e limites: https://ai.google.dev/gemini-api/docs/transcribe e https://ai.google.dev/gemini-api/docs/models/gemini-3.5-transcribe
- Gemini 3.5 Transcribe, preço (não oficial): https://www.eesel.ai/blog/gemini-3-5-transcribe
- OpenAI, transcrição: https://costgoat.com/pricing/openai-transcription
- Anthropic, retenção na API: https://platform.claude.com/docs/en/manage-claude/api-and-data-retention
