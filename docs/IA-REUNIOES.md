# Transcrição e resumo das reuniões: comparação (só opções gratuitas)

Consulta feita em 29/10/2026. **Regra: nada pago, nem cartão cadastrado.** Os limites dos planos grátis mudam: confira de novo antes de usar.

## O que precisamos

- Transcrever as gravações da Fase 4 em **português do Brasil**.
- Ter **timestamps** para o clique levar ao ponto do player.
- Ter, se possível, **identificação de falantes**.
- Gerar um resumo em JSON validado por schema.
- Rodar fora da requisição. O backend **já tem Celery com Redis** e um serviço `worker` no `docker-compose.yml`.

Para dimensionar: uma reunião de 1 h gera uma transcrição de uns 25 mil tokens, e o resumo gerado fica em uns 3 mil.

## Transcrição

| Critério | Whisper no nosso servidor (`faster-whisper`) | Groq, plano Free (`whisper-large-v3-turbo`) | Gemini, free tier |
|---|---|---|---|
| Custo | Zero. Usa a CPU do servidor | Zero (plano Free; confirmo no cadastro que não pede cartão) | Zero, sem cartão |
| Português | Sim (Whisper multilíngue) | O modelo cobre 99+ idiomas. A página não cita o português nominalmente | Sim, `pt-BR` |
| Timestamps | Por segmento e por palavra | Por segmento no formato compatível com a OpenAI (confirmo no teste) | Sim |
| Falantes | Não. Dá para somar diarização local (veja abaixo) | Não | Sim, até 8. Com 3 ou mais é "experimental" |
| Limites | Velocidade da CPU. Na CPU, o Whisper pode levar perto da duração da reunião ou mais. Não medi; meço no teste | 100 MB por arquivo, 2 h de áudio por hora, **8 h de áudio por dia**, 2.000 pedidos por dia | Cotas do free tier visíveis só no AI Studio. Áudio limitado a 30 min por pedido com falantes |
| Privacidade | **Nada sai do servidor** | Não retém por padrão. Pode guardar até 30 dias só para investigar erro ou abuso. Dá para ligar o Zero Data Retention no painel. A página não diz se treina | **O Google usa os dados do free tier para melhorar produtos** |
| O que muda no projeto | Dependência `faster-whisper` e modelo de uns 800 MB no worker, mais o ffmpeg na imagem Docker | ffmpeg na imagem Docker, para extrair o áudio do MP4. Sem dependência Python nova | Nenhuma: `google-genai` já existe |

## Resumo (LLM)

| Critério | Gemini Flash, free tier | Groq Free (`gpt-oss-120b`) | LLM local (Ollama) |
|---|---|---|---|
| Custo | Zero, sem cartão. **Já é usado no projeto** | Zero (plano Free) | Zero |
| Cabe uma reunião de 1 h? | Sim, num pedido só | **Não num pedido só**: o limite é de 8 mil tokens por minuto, e a transcrição tem uns 25 mil. Exigiria resumir por partes. Teto de 200 mil tokens por dia | Sim, mas leva minutos na CPU e precisa de uns 8 GB de RAM para um modelo de 7 a 8 bilhões de parâmetros |
| JSON com schema | Sim (`response_schema`) | Sim | Depende do modelo. Em português, a qualidade é menor |
| Privacidade | **O Google usa os dados do free tier** | Não retém por padrão; ZDR disponível | Nada sai do servidor |

## Diarização (quem falou) grátis

Nenhuma transcrição grátis que preserva a privacidade identifica os falantes. Há duas saídas:

- **Diarização local** com `sherpa-onnx` (Apache 2.0, roda na CPU, sem conta). É mais uma dependência, e o resultado é aproximado.
- **Sem falantes no início.** A transcrição mostra só o texto com horário. Os falantes entram depois, se fizerem falta.

## Recomendação: Groq Free para transcrever, Gemini free tier para resumir

1. **Custo zero.** As duas contas são gratuitas; se o cadastro do Groq pedir cartão, paro e troco pelo Whisper local.
2. **8 h de áudio por dia** é bem mais do que o volume previsto no REUNIOES.md (cerca de 1 h por dia útil).
3. **Rápido e leve para o servidor.** O worker só extrai o áudio com ffmpeg (um MP4 de 1 h vira uns 15 MB em Opus mono) e manda para o Groq. Rodar o Whisper na nossa CPU poderia levar uma hora por reunião e disputar a máquina com o backend.
4. **O resumo usa o Gemini que já está no projeto**, sem dependência nova.
5. **Fallback local:** se o Groq estiver fora ou a cota acabar, a tarefa fica "pendente" e tenta de novo no dia seguinte. Ela não falha à toa, não reprocessa o que já foi feito e nunca apaga a gravação.

**O custo é a privacidade.** No free tier, o Google pode usar a transcrição enviada para o resumo. Proponho:

- um aviso claro antes de gerar o resumo: "O resumo é feito pelo Google Gemini no plano gratuito, que pode usar o conteúdo para melhorar os produtos dele";
- o resumo **opcional por reunião**: quem gerencia decide se gera;
- ligar o **Zero Data Retention** no Groq.

**Se a privacidade pesar mais que a qualidade:**

- faster-whisper e Ollama, tudo no nosso servidor, também custam zero;
- em troca, a máquina precisa de mais CPU e RAM, e o resumo em português sai pior;
- dá para trocar depois: o pipeline fica igual, muda só quem transcreve e quem resume.

## Sobre a Fase 4 (vídeo e gravação)

A Fase 4 também foi pensada para não gerar cobrança:

- **LiveKit Cloud Build** é grátis, com teto rígido: passando da cota, a sala falha em vez de cobrar.
- O Build só tem **60 min de gravação por mês**.
- O **bucket das gravações** pode ser um **MinIO no próprio servidor** (software livre, compatível com S3, que foi o que usei no teste local). Ele substitui o AWS S3 ou o R2, que pedem cartão.
- O backend já aceita isso via `RECORDINGS_S3_ENDPOINT`. Não precisa mudar código.

## O que vou precisar depois da aprovação

| Item | Detalhe |
|---|---|
| Conta Groq (grátis) | Você cria, liga o ZDR e passa `GROQ_API_KEY` no `.env` |
| Gemini | A mesma `GEMINI_API_KEY` que o projeto já usa (free tier) |
| ffmpeg | Entra no `Dockerfile` do backend. É mudança de build, então precisa do seu ok |
| Dependências Python | Nenhuma nova |
| Migração | Uma, para a transcrição, o resumo e o estado do processamento |
| Áudio de teste | Curto, **marcado como dado de teste**, sem voz de pessoa real |

Criar contas, mesmo gratuitas, depende da sua autorização, conforme as regras do plano.

## Fontes

- Groq, limites do plano Free: https://console.groq.com/docs/rate-limits
- Groq, modelo Whisper: https://console.groq.com/docs/model/whisper-large-v3-turbo
- Groq, seus dados: https://console.groq.com/docs/your-data
- Gemini API, uso de dados por tier: https://ai.google.dev/gemini-api/docs/pricing
- Gemini, transcrição e limites: https://ai.google.dev/gemini-api/docs/transcribe
- faster-whisper: https://github.com/SYSTRAN/faster-whisper
- Diarização local (sherpa-onnx): https://huggingface.co/spaces/k2-fsa/speaker-diarization
