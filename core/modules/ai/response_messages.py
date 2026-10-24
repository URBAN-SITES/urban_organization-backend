from django.utils.translation import gettext_lazy as _

MSG_AI_BUSY = _("AI is busy, try again shortly.")
MSG_AI_INVALID_ARGUMENTS = _("Invalid or unsupported action arguments.")
MSG_AI_UNKNOWN_ACTION = _("This action is not available to the assistant.")
MSG_AI_ACTION_FAILED = _(
    "The action failed. Its outcome may be uncertain; check before retrying."
)
MSG_AI_ACTION_INTERRUPTED = _(
    "O assistente parou antes de terminar. Confira os resultados das ações antes de tentar de novo; o que já foi feito não foi desfeito."
)
MSG_AI_STUCK = _(
    "Não consegui concluir porque as ações falharam várias vezes seguidas. "
    "Me diga com mais detalhe qual setor ou tarefa você quer e tento de novo."
)
MSG_AI_INVALID_CONVERSATION = _(
    "Invalid or expired conversation. Start a new conversation."
)
MSG_AI_CONFIRMATION_REQUIRED = _(
    "Not executed. The user must confirm this deletion first; ask for confirmation."
)  # read by the model, not shown to the user
MSG_AI_CONFIRMED_ALL = _("Exclusão confirmada e concluída (%(done)d de %(total)d).")
MSG_AI_CONFIRMED_PARTIAL = _(
    "Confirmado, mas só %(done)d de %(total)d ações foram concluídas; confira os resultados."
)
MSG_AI_INVALID_CONFIRMATION = _(
    "This confirmation expired or no longer applies. Request the deletion again."
)
MSG_AI_UNVERIFIED = _(
    "\n\n⚠️ Atenção: nenhuma alteração foi registrada no sistema, apesar do texto acima. "
    "Confira antes de considerar feito."
)
MSG_AI_PERSON_NOT_FOUND = _('Não encontrei "%(name)s" entre as pessoas deste setor.')
MSG_AI_PERSON_NO_ACCESS = _(
    '"%(name)s" é da organização, mas não tem acesso a este setor. Adicione a pessoa ao setor antes de atribuir.'
)
MSG_AI_PERSON_AMBIGUOUS = _(
    'Há mais de uma pessoa para "%(name)s": %(options)s. Pergunte ao usuário qual delas.'
)
MSG_AI_NOTE_TIME = _(
    "O quadro guarda só a data do prazo; o horário %(time)s foi registrado na descrição da tarefa."
)
MSG_AI_NOTE_TIME_NO_DATE = _(
    "O horário %(time)s foi registrado na descrição, mas a tarefa ficou sem data de prazo."
)
MSG_AI_NOTE_PEOPLE = _(
    "A tarefa tem um único responsável (%(first)s); %(others)s ficou registrado na descrição como envolvido. "
    "Ofereça criar uma tarefa separada para quem ficou de fora."
)
MSG_AI_CALENDAR_ACCESS = _(
    "Calendar access was denied. Check permissions or reconnect Google."
)
MSG_AI_UNAVAILABLE = _("AI service unavailable.")
MSG_AI_DECLINED = _("The AI declined this request.")
MSG_AI_INVALID_FILE = _("Upload a valid JPEG, PNG, WebP image or PDF document.")
MSG_AI_FILE_TOO_LARGE = _("A file exceeds the configured analysis size limit.")
MSG_AI_TOO_MANY_FILES = _("The number of files exceeds the configured analysis limit.")
MSG_AI_TOTAL_TOO_LARGE = _("The files exceed the configured total analysis size limit.")
MSG_AI_PDF_ENCRYPTED = _("Encrypted PDF documents cannot be analyzed.")
MSG_AI_PDF_PAGE_LIMIT = _("The PDF exceeds the configured analysis page limit.")
MSG_AI_IMAGE_LIMIT = _("The image exceeds the configured pixel limit or is animated.")
MSG_AI_INVALID_ANALYSIS = _("The AI returned an invalid or incomplete analysis.")
MSG_AI_ANALYSIS_FAILED = _("File analysis failed; no partial report was generated.")
MSG_AI_REPORT_FAILED = _("The analysis report could not be generated.")
MSG_AI_REPORT_TITLE = _("File analysis report")
MSG_AI_REPORT_GENERATED = _("Generated at")
MSG_AI_REPORT_COUNT = _("Files analyzed")
MSG_AI_REPORT_TYPE = _("Document type")
MSG_AI_REPORT_SUMMARY = _("Summary")
MSG_AI_REPORT_OBSERVATIONS = _("Observed information")
MSG_AI_REPORT_INFERENCES = _("Interpretations and inferences")
MSG_AI_REPORT_LIMITATIONS = _("Observations and limitations")
MSG_AI_REPORT_EMPTY = _("No information identified in this section.")
MSG_AI_REPORT_REVIEW = _(
    "AI-generated analysis. Review the results against the original files."
)
