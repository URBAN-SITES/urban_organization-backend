# Calls and reactions in chat

Voice and video calls between people of a chat channel, plus emoji reactions on
messages. Adapted from the `calls` and chat-reaction modules of `template_backend`.

## Calls (WebRTC, peer to peer)

Calls are for quick conversations inside a channel: a direct message or a small
team/sector channel. The server only rings people and relays the WebRTC handshake
(signaling); audio and video go straight between the browsers, so a call costs no
server bandwidth. Big meetings, recordings and transcripts stay on LiveKit
(`docs/REUNIOES.md`).

Every participant connects to every other one (mesh), so calls are limited to
`CALL_MAX_PARTICIPANTS` people (default 6). A bigger channel gets a 400 and should use a
meeting.

### Flow

1. `POST /api/v1/calls/` `{"channel_id", "kind": "audio"|"video"}` creates the call.
   Everyone else in the channel gets `call.ringing` on `/ws/` and a notification
   (`event: call.incoming`, also sent as push).
2. Whoever answers calls `POST /calls/<id>/join/`. The response lists who is already
   in; the newcomer opens one `RTCPeerConnection` per person and sends each an offer.
3. Offers, answers and ICE candidates travel on the socket:
   `{"type": "call.signal", "call_id", "to_user_id", "data": {"sdp"|"candidate": ...}}`.
   The server relays it only to a participant that has joined (max 64 KB); errors come
   back as `call.error`. `POST /calls/<id>/signal/` is the HTTP fallback.
4. `POST /calls/<id>/media/` `{"muted", "video_off", "screen_sharing"}` tells the others
   what to show.
5. `POST /calls/<id>/leave/` or `/decline/`. A direct call ends when one side leaves; a
   group call when the last one leaves. A summary message (`message.call`) lands in the
   channel.

A call nobody answered within `CALL_RING_SECONDS` becomes **missed** (the people it
rang get a "Missed call" notification). Closing the last open tab of a user hangs up
their calls. The Celery beat job `expire-calls` (every minute) closes rings nobody
answered and calls left open longer than `CALL_MAX_HOURS`.

### Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/calls/` | My call history (latest 100) |
| `POST /api/v1/calls/` | Start a call in a channel I can read |
| `GET /api/v1/calls/ice-servers/` | `{"ice_servers": [...]}` for `RTCPeerConnection` |
| `GET /api/v1/calls/<id>/` | A call and its participants (only for people it rang) |
| `POST /api/v1/calls/<id>/join/` | Answer / join |
| `POST /api/v1/calls/<id>/decline/` | Decline while ringing |
| `POST /api/v1/calls/<id>/leave/` | Hang up |
| `POST /api/v1/calls/<id>/signal/` | Relay a WebRTC message (HTTP fallback) |
| `POST /api/v1/calls/<id>/media/` | My mic/camera/screen flags |

### WebSocket events (server -> client)

`call.ringing {call}`, `call.participant_joined {call_id, participant}`,
`call.participant_left {call_id, user_id}`, `call.declined {call_id, user_id}`,
`call.signal {call_id, from_user_id, data}`, `call.media {call_id, participant}`,
`call.ended {call_id, status}`, `call.error {call_id, detail}`.

### Environment variables

| Variable | Default | What it does |
|----------|---------|--------------|
| `CALL_RING_SECONDS` | `45` | How long a call rings before it is missed |
| `CALL_MAX_PARTICIPANTS` | `6` | Largest channel that can start a call (mesh limit) |
| `CALL_MAX_HOURS` | `6` | Calls still "ongoing" after this are closed by the beat job |
| `ICE_STUN_URLS` | `stun:stun.l.google.com:19302` | Comma-separated STUN servers |
| `TURN_URLS` | empty | Comma-separated TURN URLs of your own coturn (optional) |
| `TURN_SECRET` | empty | coturn `static-auth-secret`; credentials last 24 h |

Without TURN, people behind strict corporate networks or some mobile carriers may not
connect. Run [coturn](https://github.com/coturn/coturn) with `use-auth-secret` and
`static-auth-secret=<TURN_SECRET>` to fix that.

## Reactions

`POST /api/v1/chat/messages/<id>/reactions/` `{"emoji": "👍"}` toggles my reaction
(the same emoji again removes it). Only emoji are accepted (no ASCII), only on messages
of channels I can read and not on deleted messages. Every message now has
`reactions: [{"emoji", "user_ids"}]`, and the change is pushed as
`chat.message_updated`.

## Channel video meeting (LiveKit)

The "Start meeting" button of a chat channel no longer creates a Google Meet. It
opens the channel's own LiveKit room (`chat-<channel_id>`), the same video stack as
project meetings (`docs/REUNIOES.md`), but with no schedule and no recording.

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/chat/channels/<id>/meet/` | Posts `Join the video meeting: <FRONTEND_URL>/chat/sala/<id>` in the channel (members are notified). 503 when LiveKit is not configured, without posting |
| `POST /api/v1/chat/channels/<id>/room/` | `{url, token, room, identity, title, channel_id}` to join; anyone who can read the channel |

Needs `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` and `FRONTEND_URL`.

## Voice messages

Voice messages are ordinary message attachments (`audio/webm` from Chrome/Firefox,
`audio/mp4` from Safari) sent with `POST /chat/channels/<id>/messages/` as multipart.
They need `CLOUDINARY_URL` like every other upload; the 10 MB limit fits about
5 minutes of audio, which is also the recorder's limit in the frontend.
