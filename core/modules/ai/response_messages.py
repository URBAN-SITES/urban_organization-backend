from django.utils.translation import gettext_lazy as _

MSG_AI_BUSY = _("AI is busy, try again shortly.")
MSG_AI_INVALID_ARGUMENTS = _("Invalid or unsupported action arguments.")
MSG_AI_UNKNOWN_ACTION = _("This action is not available to the assistant.")
MSG_AI_ACTION_FAILED = _(
    "The action failed. Its outcome may be uncertain; check before retrying."
)
MSG_AI_ACTION_INTERRUPTED = _(
    "The assistant stopped. Review the action results before retrying; completed actions were not rolled back."
)
MSG_AI_INVALID_CONVERSATION = _(
    "Invalid or expired conversation. Start a new conversation."
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
