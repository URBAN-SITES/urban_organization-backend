from django.utils.translation import gettext_lazy as _

MSG_MEETINGS_NOT_CONFIGURED = _("Video meetings are not configured on the server.")
MSG_RECORDINGS_NOT_CONFIGURED = _("Recording storage is not configured on the server.")
MSG_LIVEKIT_UNAVAILABLE = _("The video server is unavailable, try again later.")
MSG_MEETING_ENDS_BEFORE_START = _("The meeting must end after it starts.")
MSG_MEETING_PARTICIPANT_INVALID = _(
    "Every participant must have access to the project."
)
MSG_MEETING_NOT_INVITED = _("Only invited participants can join this meeting.")
MSG_MEETING_ORGANIZER_REQUIRED = _(
    "Only the organizer or a project manager can do this."
)
MSG_MEETING_CONSENT_REQUIRED = _("Accept the recording notice to join.")
MSG_RECORDING_ALREADY_ACTIVE = _("This meeting is already being recorded.")
MSG_RECORDING_NOT_ACTIVE = _("This recording is not running.")
MSG_RECORDING_ROOM_EMPTY = _("Join the meeting before starting the recording.")
MSG_RECORDING_NOT_READY = _("The recording is not ready yet.")
MSG_LIVEKIT_SIGNATURE_INVALID = _("Invalid webhook signature.")
MSG_INSIGHTS_NOT_CONFIGURED = _(
    "Transcription and summaries are not configured on the server."
)
MSG_INSIGHT_ALREADY_RUNNING = _("This recording is already being processed.")
MSG_INSIGHT_ALREADY_DONE = _("This recording already has a transcript and summary.")
MSG_INSIGHT_NOT_DONE = _("The summary is not ready yet.")
MSG_INSIGHT_ACTION_INVALID = _("This suggested action does not exist.")
